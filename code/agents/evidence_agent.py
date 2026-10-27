# code/agents/evidence_agent.py

# Python Libraries
import json
import pathlib
import sqlite3
from pathlib import Path

# Vendor Libraries
import pandas as pd
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
        self.databases = None
        self.documents = None
        self.images = None
        self.logs = None
        self.records = None

        self._evidence_files = None
        self._system_activity = None

        for dir_name, value in evidence.items():
            if hasattr(self, dir_name):
                setattr(self, dir_name, value)

    def search(self, user_dataset: dict) -> dict:

        # Search through filtered user data
        self.user = user_dataset
        self._evidence_files = user_dataset.get("evidence_files")
        self._system_activity = user_dataset.get("system_activity")

        # Now that data is set, search through the evidence for related material
        # Get info user has ever used: user_ids, emails, phones, email hashes

        # Check evidence files for relevant data
        evidence_dataset = self._filter_evidence_files()

        # Parse and interpret Evidence results
        # @TODO - what should be done now?

        return evidence_dataset

    def _filter_system_activity(self):

        # user_audit_log.field_name == "email_hash", return  user_audit_log.new_value

        pass

    def _filter_evidence_files(self) -> dict:
        file_data = {}
        for evidence_file in self._evidence_files.items():
            file_id = evidence_file["file_id"]
            origin = evidence_file["origin"]
            captured_at = evidence_file["captured_at"]

            filepath = Path(evidence_file["file_path"])
            if not filepath.exists():
                print(f"Error: {filepath} does not exist.")
                continue

            file_ext = filepath.suffix.lower()

            if file_ext == ".pdf":
                file_data[file_id] = self.read_pdf(filepath)
            elif file_ext in [".log", ".txt"]:
                file_data[file_id] = self._read_log_or_text(filepath)
            elif file_ext == ".png":
                file_data[file_id] = self._read_image(filepath)
            elif file_ext == ".sql":
                file_data[file_id] = self._read_sql(filepath)
            else:
                file_data[file_id] = {
                    "path": str(filepath),
                    "type": "binary/unsupported",
                    "size": filepath.stat().st_size,
                }

            evidence_file["file_data"] = file_data

        # return file_data
        return evidence_file

    def _read_pdf(self, filepath: pathlib.Path):
        query_table_name = "SELECT name FROM sqlite_master WHERE type='table';"
        conn = sqlite3.connect(filepath)
        cursor = conn.cursor()
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

    def _read_json(self, filepath: pathlib.Path):
        with open(filepath, "r", encoding="utf-8") as json_file:
            return json.load(json_file)

    def _read_image(self, filepath: pathlib.Path):
        with Image.open(filepath) as img:
            return {
                "path": str(filepath),
                "format": img.format,
                "size": img.size,
                "mode": img.mode,
            }

    def _read_sql(self, filepath: pathlib.Path):
        reader = PdfReader(filepath)
        text = ""
        for page in reader.pages:
            content = page.extract_text()

            if content:
                text += content + "\n"

        return text
