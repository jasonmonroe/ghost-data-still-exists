# code/agents/evidence_agent.py

"""
+-----------------------------------------------------------------------------+
|                                EVIDENCE AGENT                               |
+-----------------------------------------------------------------------------+

                ** Bread & Butter of the application **

Digital detective—its sole job is to answer: "Does this resource exist in the
evidence, what is its state (PRESENT/ABSENT), and what is its timeline?" It
shouldn't need to know about compliance policies or required remediation actions.

Turns raw evidence into a per-resource ledger for one case.

    all_evidence (files captured <= audit_at)
       ├─ A. _get_resources()  which records belong to this user
       ├─ B. _timeline()        what was done to each record (claims)
       ├─ C. _state()           what is true at audit_at (proof + file_id)
       └─ D. ResourceFinding    one per record → DecisionRuleAgent
"""

# Python Libraries
import hashlib
import json
import re
import sqlite3
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path

# Vendor Libraries
import pandas as pd
import pytesseract
from PIL import Image
from pypdf import PdfReader

# Local Libraries
from src.constants import (
    ABSENT_HINT_RE,
    DATASET_PATH,
    DEFAULT_FIELD_NAME,
    LINK_RE,
    PHONE_LEN,
    PHONE_RE,
    PII_FIELDS,
    RESOURCE_ID_RE,
    TARGET_SYSTEMS,
    TRACE_ID_RE,
)
from src.enums import StepStates
from src.utils import clean_str, prefix_of


@dataclass(frozen=True)
class ResourceFinding:
    system_id: str
    resource_id: str
    category: str | None
    state: str  # PRESENT | ABSENT | UNKNOWN (REDACTED/ACTIVE/... come later)
    evidence_id: str | None
    exposed_fields: frozenset = field(default_factory=frozenset)
    attributes: dict = field(default_factory=dict)
    timeline: tuple = ()  # activity_ids, oldest -> newest


class EvidenceAgent:
    def __init__(self, evidence: dict | None = None):
        self.evidence = evidence or {}  # {"records": [Path, ...], ...} from DataHandler
        self.user: dict | None = None
        self._evidence_files: list[dict] = []
        self._content_cache: dict[Path, object] = {}  # parse each file once
        self._terms: tuple[set[str], set[str]] = (set(), set())
        self._system_by_prefix: dict[str, str] = self._build_system_by_prefix()

    def search(self, user_dataset: dict, rules_agent) -> list[ResourceFinding]:
        """
        When you call agent.search(user_dataset), it executes four major phases:

        _get_evidence(): Loads and parses every evidence file whose capture time
        is on or before the case's audit_at timestamp.

        _filter(): Narrows down the massive pool of evidence files to only those
        that actually mention the user.

        _get_resources(): Extracts every resource ID tied to the user (via
        system activity events, co-occurrence in evidence chunks, or
        resource-identity link tables).

        _build_finding(): For each discovered resource, it reconstructs its
        lifecycle timeline and inspects newer evidence to prove its final state
        at audit_at.
        """

        self._evidence_files = user_dataset.get("evidence_files", None)
        self.user = user_dataset
        self._terms = self._get_search_terms()  # needed by _filter/_get_exposed

        # every file <= audit_at (needed for absence proof)
        all_evidence = self._get_evidence()

        # files that mention the user
        filtered_evidence = self._filter(all_evidence)
        resource_ids = self._get_resources(filtered_evidence)

        return [
            self._build_finding(rid, all_evidence, rules_agent)
            for rid in sorted(resource_ids)
        ]

    def _get_resources(self, matched: list[dict]) -> set[str]:
        """
        Pass filtered evidence in and get the resource data from system activities.
        Parse all evidence data into chunks and check if any chunk matches any
        of the search terms.
        """
        resources: set[str] = set()

        # The case's own workflow events (reported_at +/- window)
        resources |= {
            clean_str(r)
            for r in self.user["system_activity"]["resource_id"]
            if clean_str(r)
        }

        # Resources in the SAME line / row / record / trace as a user identifier
        for f in matched:
            for chunk in self._chunks(f["content"]):
                if self._mentions_user(chunk):
                    resources |= set(RESOURCE_ID_RE.findall(chunk))

        # Data-catalog LINK_RESOURCE_IDENTITY rows naming this user
        pool = self._activity_pool()
        links = pool[pool["event_type"] == "LINK_RESOURCE_IDENTITY"]

        for details in links["details"]:
            m = LINK_RE.search(clean_str(details))
            if m and self._mentions_user(f"{m.group(2)} {m.group(3)}"):
                resources.add(m.group(1))

        return resources

    def _timeline(self, resource_id: str) -> pd.DataFrame:
        pool = self._activity_pool()
        return pool[pool["resource_id"] == resource_id].sort_values(
            ["event_time", "activity_id"]
        )

    def _activity_pool(self) -> pd.DataFrame:
        """All activity <= audit_at (falls back to the workflow window if not supplied)."""
        pool = self.user.get("activity_pool")
        return pool if pool is not None else self.user["system_activity"]

    def _state(
        self, resource_id: str, after: str, evidence: list[dict]
    ) -> tuple[str, str | None]:
        """
        Newest evidence captured after the last action decides the state.

        To determine if a resource is PRESENT or ABSENT, the agent looks at
        evidence captured after the user's last deletion action:
        If it finds the resource ID in a fresh snapshot or log, it's marked
        PRESENT.
        If it finds explicit absence indicators (like 404 HTTP statuses, rows=0,
        or NOT_FOUND hints), or if a full system snapshot lists other items of
        that type but omits this specific resource ID, it definitively proves
        ABSENT.
        """

        candidates = sorted(
            (f for f in evidence if f["captured_at"] >= after),
            key=lambda f: (f["captured_at"], f["file_id"]),
            reverse=True,
        )
        rid_re = re.compile(rf"\b{re.escape(resource_id)}\b")
        same_type_re = re.compile(rf"\b{re.escape(prefix_of(resource_id))}_\d+\b")

        for f in candidates:
            chunks = self._chunks(f["content"])
            hits = [c for c in chunks if rid_re.search(c)]
            if hits:
                # A lookup that returned 0 rows / 404 / NOT_FOUND proves absence, not presence
                if all(ABSENT_HINT_RE.search(c) for c in hits):
                    return StepStates.ABSENT, f["file_id"]
                return StepStates.PRESENT, f["file_id"]
            # Snapshot lists other records of this type but not this one -> absent
            if self._is_snapshot(f) and any(same_type_re.search(c) for c in chunks):
                return StepStates.ABSENT, f["file_id"]
        return StepStates.UNKNOWN, None

    @staticmethod
    def _is_snapshot(f: dict) -> bool:
        """Only full listings (SQL tables, JSON record sets) can prove absence by omission."""
        return f["file_path"].suffix.lower() in {".sql", ".json"}

    def _build_finding(
        self, resource_id: str, evidence: list[dict], rules_agent
    ) -> ResourceFinding:
        timeline = self._timeline(resource_id)
        after = timeline["event_time"].max() if not timeline.empty else ""
        state, evidence_id = self._state(resource_id, after, evidence)

        # @TODO identifier fields still filled -> REPORT_EXPOSED_PII (StepOperations.__)
        exposed = frozenset(
            self._get_exposed(state, evidence, resource_id, evidence_id)
        )

        return ResourceFinding(
            system_id=self._system_by_prefix.get(
                prefix_of(resource_id), str(StepStates.UNKNOWN.value).lower()
            ),
            resource_id=resource_id,
            category=rules_agent.get_category(resource_id),
            state=str(state.value),
            evidence_id=evidence_id,
            exposed_fields=exposed,
            attributes={},
            timeline=tuple(timeline["activity_id"]),
        )

    def _get_exposed(
        self, state: str, evidence: list[dict], resource_id: str, evidence_id: str
    ) -> set[str]:
        exposed: set[str] = set()
        if state != StepStates.PRESENT or not evidence_id:
            return exposed

        target = next((e for e in evidence if e.get("file_id") == evidence_id), None)
        if not target:
            return exposed

        # Only inspect structured JSON/SQL chunks for PII fields
        if target["file_path"].suffix.lower() not in {".json", ".sql"}:
            return exposed

        for chunk in self._chunks(target["content"]):
            if resource_id in chunk:
                try:
                    record = json.loads(chunk) if isinstance(chunk, str) else chunk
                    if isinstance(record, dict):
                        for field in PII_FIELDS:
                            value = record.get(field)
                            if value not in (None, "", "null"):
                                exposed.add(field)
                        break
                except Exception:
                    continue

        return exposed

    # @depracted
    def _get_exposed_2(
        self, state: str, evidence: list[dict], resource_id: str, evidence_id: str
    ) -> set[str]:
        """
        Inspects the structured proof record to find exact PII field names
        that are still populated (not null or empty).

        Which kinds of identifier ("identifier", "phone") the proof chunk still
        shows.

        Blacklist certain information (PII) based on indentified field names from
        the user. Some recoreds aren't deleted.  Policy says keep the record,
        but black out the personal details.
        """
        exposed: set[str] = set()

        if state != StepStates.PRESENT or not evidence_id:
            return exposed

        # Directly pluck the matching evidence file
        target = next((e for e in evidence if e.get("file_id") == evidence_id), None)
        if not target:
            return exposed

        # Inspect chunks (or parse JSON/SQL record dictionaries directly)
        for chunk in self._chunks(target["content"]):
            if resource_id in chunk:
                try:
                    # If chunk is a JSON string of a record, load it as a dict
                    record = json.loads(chunk) if isinstance(chunk, str) else chunk
                    if isinstance(record, dict):
                        # Check which PII fields are still present and not empty/null
                        for field in PII_FIELDS:
                            value = record.get(field)
                            if value not in (None, "", "null"):
                                exposed.add(field)
                        break
                except Exception:
                    # Fallback if chunk isn't valid JSON
                    print("⚠️ Warning: chunk is not valid JSON.")
                    continue

        return exposed

    # @depracated
    def _get_exposed_old(
        self, state: str, evidence: list[dict], resource_id: str, evidence_id: str
    ) -> set[str]:

        exposed: set[str] = set()
        if state != StepStates.PRESENT or not evidence_id:
            return exposed

        # 1. Directly pluck the matching evidence file
        target = next((e for e in evidence if e.get("file_id") == evidence_id), None)
        if not target:
            return exposed

        text_terms, phone_terms = self._terms

        # 2. First chunk of that file naming the resource decides what is exposed
        for chunk in self._chunks(target["content"]):
            if resource_id in chunk:
                chunk_lower = chunk.lower()

                # Check for specific text terms (emails, hashes, user identifiers)
                for term in text_terms:
                    if term and self._term_in_text(term, chunk_lower):
                        # Optional: refinement: if it's an email format
                        exposed_field = "email" if "@" in term else DEFAULT_FIELD_NAME
                        exposed.add(exposed_field)

                if phone_terms & self._phones_in(chunk):
                    exposed.add("phone")
                break

        return exposed

    def _get_search_terms(self) -> tuple[set[str], set[str]]:
        """(text terms, phone digit strings) for this user: current + historical."""
        user_identity = self.user["user_identities"].iloc[0]
        user_audit_log = self.user["user_audit_log"]

        # field_name -> how a raw value is normalized before matching
        normalizers = {
            "email": str.lower,
            "email_hash": str.lower,
            "phone": lambda v: re.sub(r"\D", "", v),
        }

        def values_for(field_name: str) -> set[str]:
            """Current value + every old/new value from the audit log, normalized."""
            rows = user_audit_log[user_audit_log["field_name"] == field_name]
            raw = {clean_str(user_identity[field_name])} | {
                clean_str(v) for v in pd.concat([rows["old_value"], rows["new_value"]])
            }
            return {normalizers[field_name](v) for v in raw if v}

        emails = values_for("email")
        hashes = values_for("email_hash")
        hashes |= {hashlib.sha256(e.encode()).hexdigest() for e in emails}
        phones = values_for("phone")

        # Emails and email hashes join the user_id as text needles.
        text_terms = {clean_str(user_identity["user_id"]).lower()} | emails | hashes

        return text_terms - {""}, {p for p in phones if len(p) >= PHONE_LEN}

    @staticmethod
    def _term_in_text(term: str, low: str) -> bool:
        """Whole-token match on lowercased text: 'user_01' must not hit 'user_010',
        'amina@x.com' must not hit 'jamina@x.com'."""
        return bool(re.search(rf"(?<![\w.+-]){re.escape(term)}(?![\w-]|\.\w)", low))

    @staticmethod
    def _phones_in(text: str) -> set[str]:
        """Digit-only phone numbers found in text."""
        return {re.sub(r"\D", "", p) for p in PHONE_RE.findall(text)}

    def _mentions_user(self, text: str) -> bool:
        r"""
        Instead of loose substring searches (which cause false positives), the
        agent:
        Resolves current and historical identities (emails, email hashes, phone
        numbers, and user IDs) from user_identities.csv and user_audit_log.csv.
        Uses negative lookaheads and lookbehinds in regular expressions
        ((?<![\w.+-])) to ensure exact token boundaries. For example, searching
        for user_01 will successfully match, but will not falsely trigger on
        user_010.
        """

        text_terms, phone_terms = self._terms
        text_lower = text.lower()

        if any(self._term_in_text(t, text_lower) for t in text_terms):
            return True

        return bool(phone_terms & self._phones_in(text))

    def _filter(self, evidence_list: list[dict]) -> list[dict]:
        """Files with at least one chunk that mentions the user (each file once)."""
        return [
            f
            for f in evidence_list
            if any(self._mentions_user(c) for c in self._chunks(f["content"]))
        ]

    def _chunks(self, content) -> list[str]:
        """
        Split content into units where co-occurrence means 'same record'.
        Different files store data differently (SQL tables vs. JSON trees vs.
        raw log lines). The agent breaks files into logical "chunks" so that
        finding a user identifier right next to a resource ID in the same chunk
        proves they belong together:

        SQL (.sql): Converts every table row into a self-contained JSON string
        chunk.
        JSON (.json): Recursively drills down into nested dictionaries to extract
        individual records.
        Logs/Text (.log, .txt): Groups log lines sharing the same trace_id
        together so that a distributed transaction trace is evaluated as a
        single unit.

        """
        if (
            isinstance(content, dict)
            and content
            and all(isinstance(v, pd.DataFrame) for v in content.values())
        ):
            return [  # SQL: one chunk per row, every row (no display truncation)
                json.dumps({"_table": table, **row}, default=str)
                for table, df in content.items()
                for row in df.to_dict(orient="records")
            ]
        if isinstance(content, (dict, list)):
            records = list(self._json_records(content))
            return [json.dumps(r, default=str) for r in records] or [
                json.dumps(content, default=str)
            ]

        return self._text_chunks(str(content))

    def _json_records(self, node):
        """Yield every dict that carries a resource_id (records nested at any depth)."""
        if isinstance(node, dict):
            if "resource_id" in node:
                yield node
            for value in node.values():
                yield from self._json_records(value)
        elif isinstance(node, list):
            for item in node:
                yield from self._json_records(item)

    @staticmethod
    def _text_chunks(text: str) -> list[str]:
        """Lines; log lines sharing a trace_id are merged into one chunk."""
        traces: dict[str, list[str]] = defaultdict(list)
        singles: list[str] = []
        for line in text.splitlines():
            m = TRACE_ID_RE.search(line)
            (traces[m.group(1)] if m else singles).append(line)
        return ["\n".join(lines) for lines in traces.values()] + singles

    # ------------------------------------------------------- system ownership
    def _build_system_by_prefix(self) -> dict[str, str]:
        """Owner system per resource prefix, from the evidence's own system/data_store fields."""
        counts: dict[str, Counter] = defaultdict(Counter)
        for path in self.evidence.get("records", []):
            if Path(path).suffix.lower() != ".json":
                continue
            for rec in self._json_records(self._extract_content(Path(path))):
                system = rec.get("system") or rec.get("data_store")

                if rec.get("resource_id") and system:
                    counts[prefix_of(str(rec["resource_id"]))][system] += 1

        mapping = {p: c.most_common(1)[0][0] for p, c in counts.items()}

        # Prefixes not present in JSON evidence (single owner in system_activity)
        for p, system in TARGET_SYSTEMS.items():
            mapping.setdefault(p, system)

        return mapping

    # ---------------------------------------------------------------- reading
    def _get_evidence(self) -> list[dict]:
        """Read every candidate file (already filtered to captured_at <= audit_at)."""
        evidence = []
        for evidence_file in self._evidence_files.to_dict(orient="records"):
            filepath = DATASET_PATH / evidence_file["file_path"]

            if not filepath.exists():
                print(f"🚨 Error: {filepath} does not exist.")
                continue

            evidence.append(
                {
                    "file_id": evidence_file["file_id"],
                    "file_path": filepath,
                    "origin": evidence_file["origin"],
                    "captured_at": evidence_file["captured_at"],
                    "content": self._extract_content(filepath),
                }
            )
        return evidence

    def _extract_content(self, path: Path):
        """
        It includes all the robust readers we discussed earlier:
        _read_pdf: Extracts text page-by-page using PdfReader.
        _read_log_or_text: Reads raw text with UTF-8 fallback error handling.
        _read_json: Loads structured JSON payloads.
        _read_image: Runs Tesseract OCR (pytesseract) to pull text out of
        screenshots or image artifacts.
        _read_sql: Safely spins up an in-memory SQLite database (:memory:),
        executes the SQL script via executescript(), and pulls every table
        into a clean Pandas DataFrame.
        """

        if path in self._content_cache:
            return self._content_cache[path]

        ext = path.suffix.lower()
        if ext == ".pdf":
            content = self._read_pdf(path)
        elif ext in (".log", ".txt"):
            content = self._read_log_or_text(path)
        elif ext == ".json":
            content = self._read_json(path)
        elif ext in (".png", ".jpg", ".jpeg"):
            content = self._read_image(path)
        elif ext == ".sql":
            content = self._read_sql(path)
        else:
            content = ""

        self._content_cache[path] = content
        return content

    @staticmethod
    def _read_pdf(filepath: Path) -> str:
        return "\n".join(
            p.extract_text() or "" for p in PdfReader(filepath).pages
        ).strip()

    @staticmethod
    def _read_log_or_text(filepath: Path) -> str:
        return filepath.read_text(encoding="utf-8", errors="ignore")

    @staticmethod
    def _read_json(filepath: Path):
        return json.loads(filepath.read_text(encoding="utf-8"))

    @staticmethod
    def _read_image(filepath: Path) -> str:
        """Tesseract OCR: image pixels -> text."""
        try:
            with Image.open(filepath) as img:
                return pytesseract.image_to_string(img)
        except Exception as e:  # OCR is best-effort
            print(f"🚨 OCR failed for {filepath}: {e}")
            return ""

    @staticmethod
    def _read_sql(filepath: Path) -> dict[str, pd.DataFrame]:
        """Import a SQL text dump into in-memory SQLite and return every table."""
        conn = sqlite3.connect(":memory:")
        try:
            conn.executescript(filepath.read_text(encoding="utf-8"))
            tables = [
                r[0]
                for r in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
                )
            ]
            return {
                t: pd.read_sql_query(f'SELECT * FROM "{t}"', conn, dtype=str)
                for t in tables
            }
        finally:
            conn.close()

    def request(self):
        # Ask the model what the resource findings should be based on data collected.
        """
        Example: case_001: COMPLETE
        [
            {"step_no": 1, "phase": "VERIFICATION", "system_id": "account_service", "resource_id": "account_001",
            "operation": "VERIFY_RECORD_ABSENT", "state": "ABSENT", "evidence_id": "evidence_54"}
        ]

        Example: case_002: INCOMPLETE
        [
          {"step_no": 1, "phase": "FINDING",      "system_id": "account_service", "resource_id": "account_005",
           "operation": "REPORT_REMAINING_RECORD", "state": "PRESENT", "evidence_id": "evidence_54"},
          {"step_no": 2, "phase": "REMEDIATION",  "system_id": "account_service", "resource_id": "account_005",
           "operation": "DELETE_RECORD",           "state": "ABSENT",  "evidence_id": ""},
          {"step_no": 3, "phase": "VERIFICATION", "system_id": "account_service", "resource_id": "account_005",
           "operation": "VERIFY_RECORD_ABSENT",    "state": "ABSENT",  "evidence_id": ""}
        ]

        """
