# code/src/prompt_builder.py

# +---------------------------------------------------------------------------+
# |                              PROMPT BUILDER                               |
# +---------------------------------------------------------------------------+
# @depracted

# Python Libraries
import pandas as pd
import xmltodict

# Local Libraries
from src.constants import OUTCOME_PROMPT


class PromptBuilder:
    def __init__(self, dataset: dict, case: pd.Series):
        self.prompt = ""

        self._build(dataset, case)

    def _build(self, dataset: dict, case: pd.Series) -> str:
        """
        Build the XML data from activity dataset that will be inserted into
        the prompt.

        Evidence Data consists of: evidence_files, system_activity, user_audit_log
        user_identity, deletion_status, evidence_dataset (dynamic data)

        Here's an example:
        <case id="">
            <user id="">
                <identity>
                    <name></name>
                    <email></email>
                    <phone></phone>
                </identity>
                <audit_log id="">
                    <event_time></event_time>
                    <field_name></field_name>
                    <old_value></old_value>
                    <new_value></new_value>
                </audit_log>
                <system_activity id="">
                    <event_time></event_time>
                    <event_type></event_type>
                    <source_system></source_system>
                    <target_system></target_system>
                    <resource_id></resource_id>
                </system_activity>
            </user>
            <!-- Dynamic evidence data -->
            <evidence id="">
                <path></path>
                <origin></origin>
                <captured_at></captured_at>
                <data></data>
                <checksum></checksum>
            </evidence>
        </case>
        """

        """
        Example:
        sample_dict = {
            "case": {
                "@id": "case_001",
                "user": {
                    "@id": "user_005",
                    "identity": {
                        "name": "Jane Doe",
                        "email": "jane.doe@example.com",
                        "phone": "+1-555-0199"
                    },
                    "audit_log": {
                        "@id": "audit_01",
                        "event_time": "2026-02-10T10:00:00Z",
                        "field_name": "email",
                        "old_value": "old_jane@example.com",
                        "new_value": "jane.doe@example.com"
                    },
                    "system_activity": {
                        "@id": "activity_01",
                        "event_time": "2026-02-11T12:00:00Z",
                        "event_type": "INDEX_RECORD",
                        "source_system": "account_service",
                        "target_system": "search_service",
                        "resource_id": "account_3372"
                    }
                },
                "evidence": {
                    "@id": "evidence_01",
                    "path": "evidence/records/customer_snapshot.json",
                    "origin": "records_assurance_snapshot_bundle",
                    "captured_at": "2026-09-17T12:00:00Z",
                    "content": "{'user_id': 'user_005', 'status': 'active'}",
                }
            }
        }
        """

        # Initialize case tag
        data_dict = {}

        # Get case ID
        data_dict["case"] = self._requests(case)

        # Get user dict
        user = self._user(dataset)
        if bool(user):
            data_dict["case"].update(user)

        # Get evidence dict
        evidence = self._evidence(dataset)
        if bool(evidence):
            data_dict["case"].update(evidence)

        # Convert dataset to XML data
        case_xml = self._convert_to_xml(data_dict)
        self.prompt = self._format(case_xml)

    def _convert_to_xml(self, case_dict):
        return xmltodict.unparse(case_dict, pretty=True, indent="    ")

    def _format(self, case_xml) -> str:
        return OUTCOME_PROMPT.format(case_data=case_xml)

    def _requests(self, case_s: pd.Series) -> dict:
        case_s = case_s.to_dict()
        case_dict = {
            "@id": case_s["case_id"],
        }

        for key, value in case_s.items():
            if key not in ["email", "request_text"]:
                case_dict[key] = value

        return case_dict

    def _user(self, dataset: dict) -> dict:
        """Create dict for users. Convert Pandas to dict"""

        # @TODO - is the datatype a pd.series?
        user_identity = dataset.get("user_identies", "")
        user_audit_log = dataset.get("user_audit_log", "")
        system_activity = dataset.get("system_activity", "")

        if not bool(user_identity):
            print("⚠️ Warning: User Identity not found in prompt builder.")
            return {}

        user = {"@id": user_identity["user_id"], "identity": user_identity}

        # Audit Log
        audit_log = user_audit_log.to_dict(orient="records")
        if bool(audit_log):
            user.update(audit_log)

        # System Activity
        system_activity = system_activity.to_dict(orient="records")
        if bool(system_activity):
            user.update(system_activity)

        return {"user": user}

    def _evidence(self, dataset: dict) -> dict:
        evidence = dataset.get("evidence", [])
        if not evidence:
            return {}

        # evidence_list = []

        # for item in evidence.items():
        return {"evidence": evidence}
