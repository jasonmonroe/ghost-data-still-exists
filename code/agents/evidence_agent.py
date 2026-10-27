# code/agents/evidence_agent.py

# Python Libraries
import hashlib
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

        self.evidence = evidence  # @TODO - might not need
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
        evidence_dataset = self._get_evidence()

        # Parse and interpret Evidence results
        # @TODO - what should be done now?

        return evidence_dataset

    def _get_evidence(self) -> list:
        # Only look for evidence files that are relevant to the user
        evidence = []

        for evidence_file in self._evidence_files.items():
            filepath = Path(evidence_file["file_path"])
            if not filepath.exists():
                print(f"Error: {filepath} does not exist.")
                continue

            file_data = self._read_evidence(filepath)

            # Is this hashing the filepath string or the content?
            checksum = hashlib.file_digest(file_data, "sha256").hexdigest()

            file_dict = {
                "file_id": evidence_file["file_id"],
                "origin": evidence_file["origin"],
                "captured_at": evidence_file["captured_at"],
                "file_data": file_data,
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
        elif ext == ".png":
            content = self._read_image(path)
        elif ext == ".sql":
            content = self._read_sql(path)
        else:
            content = {
                "path": str(path),
                "type": "binary/unsupported",
                "size": path.stat().st_size,
            }

        return content

    def _read_pdf(self, filepath: pathlib.Path) -> dict:
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
