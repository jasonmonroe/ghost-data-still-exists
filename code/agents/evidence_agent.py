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
       ├─ C. _get_state()           what is true at audit_at (proof + file_id)
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
    LINK_RE,
    PERSONAL_INFO_FIELDS,
    PHONE_LEN,
    PHONE_RE,
    PROCESS_FLAGS,
    PROCESS_TABLE_STATE_RE,
    RESOURCE_ID_RE,
    SQL_VALUE_RE,
    TARGET_SYSTEMS,
    TRACE_ID_RE,
)
from src.enums import StepOperations, StepStates
from src.issues import ERROR, WARNING, report_issue
from src.utils import clean_str, prefix_of


@dataclass(frozen=True)
class ResourceFinding:
    system_id: str
    resource_id: str
    category: str | None
    state: str  # PRESENT | ABSENT | UNKNOWN (REDACTED/ACTIVE/... come later)
    evidence_id: str | None
    exposed_fields: frozenset = field(default_factory=frozenset)
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
        filtered_evidence = self._filter(all_evidence)
        resource_ids = self._get_resources(filtered_evidence)

        findings = []
        for resource_id in sorted(resource_ids):
            finding = self._build_finding(resource_id, all_evidence, rules_agent)

            # Only keep findings that are successfully resolved
            if finding and finding.state != StepStates.UNKNOWN:
                findings.append(finding)

        return findings

    def _get_resources(self, matched: list[dict], all_evidence: list[dict]) -> set[str]:
        """
        Pass filtered evidence in and get the resource data from system activities.
        Parse all evidence data into chunks and check if any chunk matches any
        of the search terms.
        """
        resources: set[str] = set()

        # The case's own workflow events (reported_at +/- window)
        # Note: This is causing an issue and needs to be done over...
        resources |= {
            clean_str(r)
            for r in self.user["system_activity"]["resource_id"]
            if clean_str(r)
        }

        # The hybrid: delete the block, keep one narrow exception
        # Keep a window record only when both of these are true:

        # It was logged by the deletion worker (source_system), and
        # No evidence file up to audit_at mentions that resource ID anywhere

        # Window exception: the deletion worker touched it at request time AND it
        # has vanished from every evidence file <= audit_at (a deleted record
        # can't co-occur with the user's identifiers, so nothing else finds it).
        # window = self.user["system_activity"]
        # workflow = window[window["source_system"] == WORKFLOW_SOURCE_SYSTEM]
        # mentioned = self._mentioned_resource_ids(all_evidence)
        # for raw_id in workflow["resource_id"]:
        #    resource_id = clean_str(raw_id)
        #    if resource_id and resource_id not in mentioned:
        #        resources.add(resource_id)

        # Resources in the SAME line / row / record / trace as a user identifier
        for f in matched:
            for chunk in self._get_content_chunks(f["content"]):
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

    def _mentioned_resource_ids(self, evidence: list[dict]) -> set[str]:
        """Every resource ID that appears anywhere in these evidence files."""
        ids: set[str] = set()
        for f in evidence:
            for chunk in self._get_content_chunks(f["content"]):
                ids |= set(RESOURCE_ID_RE.findall(chunk))

        return ids

    def _timeline(self, resource_id: str) -> pd.DataFrame:
        pool = self._activity_pool()
        return pool[pool["resource_id"] == resource_id].sort_values(
            ["event_time", "activity_id"]
        )

    def _activity_pool(self) -> pd.DataFrame:
        """All activity <= audit_at (falls back to the workflow window if not supplied)."""
        pool = self.user.get("activity_pool")
        return pool if pool is not None else self.user["system_activity"]

    def _get_state(
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

        Adding category or keyword awareness in state checking.  Checks if the
        resource prefix or content indicates a running process or unblocked
        backup path before returning PRESENT.
        """

        sorted_evidence_files = sorted(
            (
                sorted_ev_file
                for sorted_ev_file in evidence
                if sorted_ev_file["captured_at"] >= after
            ),
            key=lambda sorted_ev_file: (
                sorted_ev_file["captured_at"],
                sorted_ev_file["file_id"],
            ),
            reverse=True,
        )
        rid_re = re.compile(rf"\b{re.escape(resource_id)}\b")
        same_type_re = re.compile(rf"\b{re.escape(prefix_of(resource_id))}_\d+\b")

        for sorted_ev_file in sorted_evidence_files:
            chunks = self._get_content_chunks(sorted_ev_file["content"])
            hits = [chunk for chunk in chunks if rid_re.search(chunk)]

            if hits:
                # If lookup returned 0 rows / 404 / NOT_FOUND -> ABSENT
                if all(ABSENT_HINT_RE.search(c) for c in hits):
                    return StepStates.ABSENT, sorted_ev_file["file_id"]

                # Backups / data flows: state comes from their own flag field
                process_state = self._process_state(resource_id, hits)
                if process_state is not None:
                    return process_state, sorted_ev_file["file_id"]

                return StepStates.PRESENT, sorted_ev_file["file_id"]

            # Snapshot lists other records of this type but not this one -> absent
            if self._is_snapshot(sorted_ev_file) and any(
                same_type_re.search(c) for c in chunks
            ):
                return StepStates.ABSENT, sorted_ev_file["file_id"]

        return StepStates.UNKNOWN, None

    @staticmethod
    def _process_state(resource_id: str, hits: list[str]) -> StepStates | None:
        """ACTIVE / BLOCKED / DISABLED for process resources; None for ordinary records."""
        flag = PROCESS_FLAGS.get(prefix_of(resource_id))
        if flag is None:
            return None

        field_name, sql_col, if_true, if_false = flag
        kv_re = re.compile(
            rf'{field_name}"?\s*[:=]\s*"?(true|false|1|0)\b', re.IGNORECASE
        )
        for chunk in hits:
            # Handover tables state it outright
            m = PROCESS_TABLE_STATE_RE.search(chunk)
            if m:
                return StepStates(m.group(1).upper())

            # Restore-candidate logs: eligible=true deletion_block=false -> restorable
            if prefix_of(resource_id) == "backup" and "deletion_block=" in chunk:
                return if_false if "deletion_block=true" in chunk.lower() else if_true

            # JSON ("enabled": true) and logs (enabled=true)
            m = kv_re.search(chunk)
            if m:
                return if_true if m.group(1).lower() in ("true", "1") else if_false

            # SQL rows: positional column in INSERT ... VALUES (...)
            for line in chunk.splitlines():
                if "INSERT INTO" in line and resource_id in line:
                    values = [
                        a or b or c
                        for a, b, c in SQL_VALUE_RE.findall(line.split("VALUES", 1)[1])
                    ]
                    if len(values) > sql_col:
                        return if_true if values[sql_col] == "1" else if_false
        return None

    @staticmethod
    def _is_snapshot(f: dict) -> bool:
        """Only full SQL table dumps can prove absence by omission."""
        return f["file_path"].suffix.lower() == ".sql"

    def _build_finding(
        self, resource_id: str, evidence: list[dict], rules_agent
    ) -> ResourceFinding:
        timeline = self._timeline(resource_id)
        after = timeline["event_time"].max() if not timeline.empty else ""
        state, evidence_id = self._get_state(resource_id, after, evidence)

        category = rules_agent.get_category(resource_id)
        inspected = self._get_exposed(state, evidence, resource_id, evidence_id)
        state = self._treated_state(state, category, inspected, rules_agent)
        exposed = frozenset(inspected or ())
        system_id = self._system_by_prefix.get(
            prefix_of(resource_id), str(StepStates.UNKNOWN.value).lower()
        )

        return ResourceFinding(
            system_id=system_id,
            resource_id=resource_id,
            category=category,
            state=str(state.value),
            evidence_id=evidence_id,
            exposed_fields=exposed,
            timeline=tuple(timeline["activity_id"]),
        )

    def _get_exposed(
        self, state: str, evidence: list[dict], resource_id: str, evidence_id: str
    ) -> set[str] | None:
        """
        Inspects the structured proof record dictionary to find exact PII field names
        that are still populated, ignoring reference fields.

        Returns the exposed fields (empty set = record inspected and clean), or
        None when the record could not be inspected (not PRESENT, or proof is
        not structured JSON/SQL).
        """
        if state != StepStates.PRESENT or not evidence_id:
            return None

        target = next((e for e in evidence if e.get("file_id") == evidence_id), None)
        if not target or target["file_path"].suffix.lower() not in {".json", ".sql"}:
            return None

        for chunk in self._get_content_chunks(target["content"]):
            if resource_id in chunk:
                exposed: set[str] = set()
                self._inspect_chunk_for_personal_info(chunk, exposed)
                return exposed

        return None

    @staticmethod
    def _treated_state(state, category, inspected, rules_agent):
        """A record that still exists but exposes no personal fields has the
        treatment its rule demands: REDACT -> REDACTED, ANONYMIZE -> ANONYMIZED.
        Only applies when the record was actually inspected and found clean."""
        if state != StepStates.PRESENT or inspected != set():
            return state

        action = rules_agent.get_rule_by_category(category).get("required_action")
        return {
            StepOperations.REDACT_RECORD: StepStates.REDACTED,
            StepOperations.ANONYMIZE_RECORD: StepStates.ANONYMIZED,
        }.get(action, state)

    @staticmethod
    def _inspect_chunk_for_personal_info(chunk, exposed: set[str]) -> None:
        try:
            record = json.loads(chunk) if isinstance(chunk, str) else chunk
            if isinstance(record, dict):
                for field in PERSONAL_INFO_FIELDS:
                    value = record.get(field)
                    if value not in (None, "", "null"):
                        exposed.add(field)
        except (json.JSONDecodeError, TypeError):
            report_issue(ERROR, "Evidence record JSON could not be decoded.")

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
            if any(
                self._mentions_user(c) for c in self._get_content_chunks(f["content"])
            )
        ]

    def _get_content_chunks(self, content) -> list[str]:
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

        return self._get_text_chunks(str(content))

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
    def _get_text_chunks(text: str) -> list[str]:
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
                report_issue(ERROR, f"Evidence file {filepath} does not exist.")
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
            report_issue(WARNING, f"OCR failed for {filepath}: {e}")
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
