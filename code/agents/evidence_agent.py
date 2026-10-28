# code/agents/evidence_agent.py
# +---------------------------------------------------------------------------+
# |                               EVIDENCE AGENT                              |
# +---------------------------------------------------------------------------+

# Python Libraries
import hashlib
import json
import pathlib
import re
import sqlite3
from collections import defaultdict
from pathlib import Path

# Vendor Libraries
import pandas as pd
import pytesseract
from PIL import Image
from pypdf import PdfReader


class EvidenceAgent:
    def __init__(
        self,
        evidence: dict,
        # evidence_files: pd.DataFrame,
        # system_activity: pd.DataFrame,
    ):

        self.user = None
        # self.databases = None
        # self.documents = None
        ##self.images = None
        # self.logs = None
        # self.records = None

        self.evidence = evidence  # @TODO - might not need
        self._evidence_files = None
        # self._system_activity = None

        for dir_name, value in evidence.items():
            if hasattr(self, dir_name):
                setattr(self, dir_name, value)

    def search(self, user_dataset: dict) -> dict:

        # Search through filtered user data
        self.user = user_dataset
        self._evidence_files = user_dataset.get("evidence_files")
        # self._system_activity = user_dataset.get("system_activity")

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

        # Now we have all the POSSIBLE data that relates to this user but we
        # need more investigation to determine the deletion status.

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
            self.user["user_identities"].to_dict(orient="records"),
            self.user["user_audit_log"].to_dict(orient="records"),
            self.user["system_activity"].to_dict(orient="records"),
        ]

        filtered_evidence = defaultdict([])

        for file_dict in evidence_list:
            # Get needle & haystack
            content = file_dict["file_data"]
            file_ext = file_dict["file_path"].suffix().lower()

            # Get evidence list columns as search terms
            match = False
            evidence_values_list = [
                val
                for key, val in file_dict.items()
                if key not in ["file_path", "checksum"]
            ]
            for evidence_value in evidence_values_list:
                if self._search_content(evidence_value, content, file_ext):
                    filtered_evidence.append(file_dict)
                    match = True

                if match:
                    continue

            # If no evidence list data matches content move on to other search
            for records in search_data:  # records is dict
                for key, value in records.items():  # key of csv rows
                    # if value and str(value) in content:
                    if self._search_content(value, content, file_ext):
                        filtered_evidence.append(file_dict)

        return filtered_evidence

    def _search_content(self, term: str, content, file_ext: str) -> bool:
        """Based on file extension we can search the content"""
        if file_ext in [".log", ".txt", ".pdf", ".sql", ".png"]:
            if re.search(rf"\b{term}\b", content, re.IGNORECASE):
                return True
        # elif file_ext == ".png":
        # 💡 Note: For images content is actually a dict (data type)
        #    if re.search(rf"\b{term}\b", content["text"], re.IGNORECASE):
        #        return True

        elif file_ext == ".json":
            if term in json.dumps(content):
                return True

        return False

    def _get_evidence(self) -> list:
        # Only look for evidence files that are relevant to the user
        # Although the user didn't interact with all of these files
        # their audit_at date was on or before these evidence files
        # were touched.
        evidence = defaultdict([])

        for evidence_file in self._evidence_files.items():
            filepath = Path(evidence_file["file_path"])
            if not filepath.exists():
                print(f"🚨 Error: {filepath} does not exist.")
                continue

            content = self._read_evidence(filepath)

            # #TODO: Is this hashing the filepath string or the content?
            checksum = hashlib.file_digest(content, "sha256").hexdigest()

            file_dict = {
                "file_id": evidence_file["file_id"],
                "file_path": filepath,
                "origin": evidence_file["origin"],
                "captured_at": evidence_file["captured_at"],
                "content": content,
                "checksum": checksum,
            }

            evidence.append(file_dict)

        return evidence

    def _read_evidence(self, path: pathlib.Path):
        ext = path.suffix.lower()

        if ext == ".pdf":
            content = self.read_pdf(path)
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
                "ext": path.stem(),
            }

        return content

    def _read_pdf(self, filepath: pathlib.Path) -> dict:
        conn = sqlite3.connect(filepath)
        cursor = conn.cursor()

        query_table_name = "SELECT name FROM sqlite_master WHERE type='table';"
        cursor.execute(query_table_name)
        tables = [row[0] for row in cursor.fetchall()]
        db_data = {
            table: pd.read_sql_query(f"SELECT * FROM {table}", conn) for table in tables
        }
        conn.close()

        return db_data

    def _read_log_or_text(self, filepath: pathlib.Path):
        with open(filepath, "r", encoding="utf-8", errors="ignore") as text_file:
            return text_file.read()

    # records/
    def _read_json(self, filepath: pathlib.Path) -> json:
        with open(filepath, "r", encoding="utf-8") as json_file:
            return json.load(json_file)

    def _read_image(self, filepath: pathlib.Path) -> str:
        with Image.open(filepath) as img:
            # Run OCR to convert image pixels into a string
            return (pytesseract.image_to_string(img),)
            return {
                "path": str(filepath),
                "format": img.format,
                "size": int(img.size),
                "mode": img.mode,
                "text": pytesseract.image_to_string(img),
            }

    def _read_sql(self, filepath: pathlib.Path) -> str:
        reader = PdfReader(filepath)
        text = ""
        for page in reader.pages:
            content = page.extract_text()

            if content:
                text += content + "\n"

        return text.strip()

    def extract_text_from_image(filepath: str) -> str:
        """
        Uses Tesseract OCR to extract text from a PNG or JPG evidence image.
        """
        # path = pathlib.Path(filepath)
        # if not path.exists():
        # path = pathlib.Path("dataset") / filepath

        try:
            with Image.open(filepath) as img:
                # Run OCR to convert image pixels into a string
                extracted_text = pytesseract.image_to_string(img)
                return extracted_text
        except Exception as e:
            print(f"OCR failed for {filepath}: {e}")
            return ""
