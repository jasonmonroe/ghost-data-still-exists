# code/agents/evidence_agent.py
# +---------------------------------------------------------------------------+
# |                               EVIDENCE AGENT                              |
# +---------------------------------------------------------------------------+

# Python Libraries
import json
import pathlib
import re
import sqlite3
from pathlib import Path

# Vendor Libraries
import pandas as pd
import pytesseract
from PIL import Image
from pypdf import PdfReader

# Local Libraries
from src.constants import DATASET_FILES


class EvidenceAgent:
    def __init__(
        self,
        evidence: dict,
        # evidence_files: pd.DataFrame,
        # system_activity: pd.DataFrame,
    ):
        self.evidence = evidence  # @TODO - might not need

        self.user = None
        self._evidence_files = None

        for dir_name, value in evidence.items():
            if hasattr(self, dir_name):
                setattr(self, dir_name, value)

    def search(self, user_dataset: dict) -> dict:

        # Search through filtered user data
        self.user = user_dataset
        self._evidence_files = user_dataset.get("evidence_files").to_dict(
            orient="records"
        )

        """
        1. read files 
        2. parse into records each table row / JSON record / log trace → one record
        3. normalize identifiers                        email lowercase, phone digits, prefix (email:, user:, ...)
        4. match against the user's identifier set      plus log lines grouped by trace_id
        5. collect the user's resource_ids              matched records + LINK rows + workflow-window events
        6. per resource: build a timeline + latest state
            - activity events (claims) for that resource, <= audit_at
            - evidence observations, newest captured_at wins
            - nothing observed? → newest full snapshot covering that system after the last action
            → absent there = ABSENT, with that file_id
        7. return a ledger of resources                 → DecisionRuleAgent
        """
        # Check evidence files for relevant data

        evidence_dataset = self._filter(self._get_evidence())

        # @TODO - what's next?

        # Now we have all the POSSIBLE data that relates to this user but we
        # need more investigation to determine the deletion status.

        # @TODO - What if there are still multiple system activity rows?
        # Which target_system value would I use??

        return {
            "system_id": "",  # system_activity.target_system
            "resource_id": "",  # system_activity.resource_id
            "category": "",  # deletion_rules.data_category
            "state": "",  # deletion_rules.required_action
            "evidence_id": "",  # evidence_files.file_id
            "exposed_fields": frozenset(),
            "attributes": {},
            "timeline": (),  # system_activity.activity_id -> activity ids oldest -> newest
        }

    def _filter(self, evidence_list: list) -> list:
        # Look through each file to determine if this is can Identify our user
        search_data = [
            self.user["user_identities"]
            .drop(columns=["updated_at"], errors="ignore")
            .to_dict(orient="records"),
            self.user["user_audit_log"]
            .drop(columns=[], errors="ignore")
            .to_dict(orient="records"),
            self.user["system_activity"]
            .drop(columns=[], errors="ignore")
            .to_dict(orient="records"),
        ]

        filtered_evidence = []
        for file_dict in evidence_list:
            content = file_dict["content"]
            file_ext = file_dict["file_path"].suffix.lower()

            # If no evidence list data matches content move on to other search
            for records in search_data:  # records is dict
                for record in records:
                    match = False
                    for _, value in record.values():  # key of csv rows
                        if self._search_content(value, content, file_ext):
                            filtered_evidence.append(file_dict)
                            match = True

                        if match:
                            continue

        filtered_evidence = list(set(filtered_evidence))
        return filtered_evidence

    def _search_content(self, term: str, content, file_ext: str) -> bool:
        """Based on file extension we can search the content"""
        if not term or content is None:
            return False

        # Ensure term is safe for regex
        escaped_term = re.escape(str(term))

        if file_ext in [".log", ".txt", ".pdf", ".sql", ".png"]:
            # Ensure content is a string before running regex
            text_content = str(content)
            if re.search(rf"\b{escaped_term}\b", text_content, re.IGNORECASE):
                return True

        elif file_ext == ".json":
            # Dump dict/list to string for searching
            json_str = (
                json.dumps(content)
                if isinstance(content, (dict, list))
                else str(content)
            )
            if (
                escaped_term in json_str
            ):  # Or use re.search if you want word boundaries here too
                return True

        return False

    def _get_evidence(self) -> list:
        """
        Only look for evidence files that are relevant to the user.
        Although the user didn't interact with all of these files their audit_at
        date was on or before these evidence files were touched.
        """

        evidence = []
        for evidence_file in self._evidence_files:
            filepath = Path(DATASET_FILES / evidence_file["file_path"])
            if not filepath.exists():
                print(f"🚨 Error: {filepath} does not exist.")
                continue

            file_dict = {
                "file_id": evidence_file["file_id"],
                "file_path": filepath,
                "origin": evidence_file["origin"],
                "captured_at": evidence_file["captured_at"],
                "content": self._read_evidence(filepath),
            }

            evidence.append(file_dict)

        return evidence

    def _read_evidence(self, path: pathlib.Path):
        ext = path.suffix.lower()

        if ext == ".pdf":
            content = self._read_pdf(path)
        elif ext in [".log", ".txt"]:
            content = self._read_log_or_text(path)
        elif ext == ".json":
            content = self._read_json(path)
        elif ext == ".png":
            content = self._read_image(path)
        elif ext == ".sql":
            content = self._read_sql(path)
        else:
            content = {
                "path": str(path),
                "type": "binary/unsupported",
                "size": path.stat().st_size,
                "ext": path.suffix,
            }

        return content

    def _read_pdf(self, filepath: pathlib.Path) -> str:
        reader = PdfReader(filepath)
        text = ""
        for page in reader.pages:
            content = page.extract_text()

            if content:
                text += content + "\n"

        return text.strip()

    def _read_log_or_text(self, filepath: pathlib.Path) -> str:
        with open(filepath, "r", encoding="utf-8", errors="ignore") as text_file:
            return text_file.read()

    def _read_json(self, filepath: pathlib.Path) -> json:
        with open(filepath, "r", encoding="utf-8") as json_file:
            return json.load(json_file)

    def _read_image(self, filepath: pathlib.Path) -> str:
        """
        Uses Tesseract OCR to extract text from a PNG or JPG evidence image.
        # Run OCR to convert image pixels into a string
        """
        try:
            with Image.open(filepath) as img:
                return pytesseract.image_to_string(img)
        except Exception as e:
            print(f"🚨 OCR failed for {filepath}: {e}")
            return ""

    def _read_sql(self, filepath: pathlib.Path) -> dict:
        """Reads a SQLite SQL snapshot export into a dictionary of DataFrames per table."""
        conn = sqlite3.connect(filepath)
        cursor = conn.cursor()

        # Get all table names from the database snapshot
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
        tables = [row[0] for row in cursor.fetchall()]

        # Load each table into a Pandas DataFrame
        db_data = {
            table: pd.read_sql_query(f"SELECT * FROM {table}", conn) for table in tables
        }
        conn.close()
        return db_data
