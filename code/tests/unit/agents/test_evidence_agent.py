# code/tests/unit/agents/test_evidence_agent.py
# EvidenceAgent turns raw evidence into ResourceFindings. These tests build
# tiny synthetic evidence files in tmp_path so every rule is exercised in
# isolation (Laravel parallel: Storage::fake() + factory data).

import hashlib
import json
from pathlib import Path

import agents.evidence_agent as ev_module
import pandas as pd
import pytest
from agents.deletion_rule_agent import DeletionRuleAgent
from agents.evidence_agent import EvidenceAgent, ResourceFinding
from src.enums import StepStates as St
from src.issues import get_issues

EMAIL = "amina@example.com"
OLD_EMAIL = "amina.old@example.com"
PHONE = "+971 50 482 7316"
USER = "user_01"

ACTIVITY_COLUMNS = [
    "activity_id",
    "event_time",
    "event_type",
    "source_system",
    "target_system",
    "resource_id",
    "reported_result",
    "details",
]


# --------------------------------------------------------------------------
# Builders
# --------------------------------------------------------------------------
def activity(rows):
    return pd.DataFrame(rows, columns=ACTIVITY_COLUMNS)


def user_dataset(
    system_activity=None, activity_pool=None, evidence_files=None, audit_log=None
):
    identities = pd.DataFrame(
        [
            {
                "user_id": USER,
                "name": "Amina",
                "email": EMAIL,
                "phone": PHONE,
                "email_hash": "ABC123HASH",
                "updated_at": "2026-01-01T00:00:00Z",
            }
        ]
    )
    if audit_log is None:
        audit_log = pd.DataFrame(
            [
                {
                    "audit_id": "audit_1",
                    "user_id": USER,
                    "event_time": "2025-01-01T00:00:00Z",
                    "field_name": "email",
                    "old_value": OLD_EMAIL,
                    "new_value": EMAIL,
                }
            ]
        )
    return {
        "user_identities": identities,
        "user_audit_log": audit_log,
        "system_activity": system_activity if system_activity is not None else activity([]),
        "activity_pool": activity_pool if activity_pool is not None else activity([]),
        "evidence_files": evidence_files,
    }


def ev(file_id, path, content, captured_at="2026-09-01T00:00:00Z"):
    """An already-read evidence entry, as _get_evidence() returns it."""
    return {
        "file_id": file_id,
        "file_path": Path(path),
        "origin": "test",
        "captured_at": captured_at,
        "content": content,
    }


@pytest.fixture
def agent():
    a = EvidenceAgent()
    a.user = user_dataset()
    a._terms = a._get_search_terms()
    return a


@pytest.fixture
def rules(rules_df):
    return DeletionRuleAgent(rules_df)


# --------------------------------------------------------------------------
# Identity matching
# --------------------------------------------------------------------------
class TestSearchTerms:
    def test_includes_user_id_current_and_historical_emails_and_hashes(self, agent):
        text_terms, phones = agent._terms
        assert {USER, EMAIL, OLD_EMAIL, "abc123hash"} <= text_terms
        assert hashlib.sha256(EMAIL.encode()).hexdigest() in text_terms
        assert hashlib.sha256(OLD_EMAIL.encode()).hexdigest() in text_terms
        assert phones == {"971504827316"}

    def test_historical_phone_from_audit_log(self):
        log = pd.DataFrame(
            [
                {
                    "audit_id": "a",
                    "user_id": USER,
                    "event_time": "x",
                    "field_name": "phone",
                    "old_value": "+33 6 24 34 80 16",
                    "new_value": PHONE,
                }
            ]
        )
        a = EvidenceAgent()
        a.user = user_dataset(audit_log=log)
        assert "33624348016" in a._get_search_terms()[1]


class TestMentionsUser:
    @pytest.mark.parametrize(
        "text",
        [
            f"owner={EMAIL}",
            f"lookup_key={EMAIL.upper()}",
            "user_id=user_01 deleted",
            "phone: +971-50-482-7316",
            '{"email_hash": "abc123hash"}',
        ],
    )
    def test_matches_any_identifier(self, agent, text):
        assert agent._mentions_user(text)

    @pytest.mark.parametrize(
        "text",
        [
            "user_010 is someone else",
            f"j{EMAIL}",  # different address that contains ours
            "nothing to see here",
            "Amina El-Masri",  # names are decoys, never matched
        ],
    )
    def test_whole_token_only(self, agent, text):
        assert not agent._mentions_user(text)

    def test_phones_in_extracts_digits(self):
        assert EvidenceAgent._phones_in("call +1 (555) 123-4567 now") == {"15551234567"}


# --------------------------------------------------------------------------
# Chunking (what counts as "the same record")
# --------------------------------------------------------------------------
class TestChunks:
    def test_log_lines_with_same_trace_id_are_one_chunk(self, agent):
        text = (
            "a trace_id=tr-1 resource_id=account_1\n"
            "b trace_id=tr-1 lookup_key=x\n"
            "c no trace here\n"
        )
        chunks = agent._get_content_chunks(text)
        assert chunks[0].count("\n") == 1 and "account_1" in chunks[0] and "lookup_key" in chunks[0]
        assert chunks[1] == "c no trace here"

    def test_sql_tables_become_one_json_chunk_per_row(self, agent):
        content = {"t": pd.DataFrame([{"resource_id": "account_1"}, {"resource_id": "account_2"}])}
        chunks = agent._get_content_chunks(content)
        assert [json.loads(c) for c in chunks] == [
            {"_table": "t", "resource_id": "account_1"},
            {"_table": "t", "resource_id": "account_2"},
        ]

    def test_nested_json_records_are_found_at_any_depth(self, agent):
        content = {"meta": {}, "records": [{"resource_id": "a_1", "x": {"resource_id": "b_2"}}]}
        ids = [json.loads(c)["resource_id"] for c in agent._get_content_chunks(content)]
        assert ids == ["a_1", "b_2"]

    def test_json_without_records_is_one_chunk(self, agent):
        assert agent._get_content_chunks({"k": "v"}) == ['{"k": "v"}']


# --------------------------------------------------------------------------
# File readers
# --------------------------------------------------------------------------
class TestReaders:
    def test_text_json_and_unknown_extensions(self, tmp_path, agent):
        (tmp_path / "a.log").write_text("hello")
        (tmp_path / "b.json").write_text('{"records": []}')
        (tmp_path / "c.bin").write_bytes(b"\x00")
        assert agent._extract_content(tmp_path / "a.log") == "hello"
        assert agent._extract_content(tmp_path / "b.json") == {"records": []}
        assert agent._extract_content(tmp_path / "c.bin") == ""

    def test_content_is_cached_per_path(self, tmp_path, agent):
        path = tmp_path / "a.txt"
        path.write_text("v1")
        assert agent._extract_content(path) == "v1"
        path.write_text("v2")
        assert agent._extract_content(path) == "v1"

    def test_sql_dump_is_loaded_into_tables(self, tmp_path, agent):
        path = tmp_path / "db.sql"
        path.write_text(
            "CREATE TABLE b (resource_id TEXT, restore_allowed INTEGER);\n"
            "INSERT INTO b VALUES ('backup_1', 1);\n"
            "CREATE TABLE a (resource_id TEXT);\n"
        )
        tables = agent._extract_content(path)
        assert sorted(tables) == ["a", "b"]
        assert tables["b"].to_dict("records") == [{"resource_id": "backup_1", "restore_allowed": "1"}]

    def test_pdf_text_is_extracted(self, tmp_path, agent):
        from pypdf import PdfWriter

        path = tmp_path / "blank.pdf"
        writer = PdfWriter()
        writer.add_blank_page(width=72, height=72)
        with path.open("wb") as fh:
            writer.write(fh)
        assert agent._extract_content(path) == ""

    def test_image_is_ocrd(self, tmp_path, agent, monkeypatch):
        from PIL import Image

        path = tmp_path / "shot.png"
        Image.new("RGB", (10, 10)).save(path)
        monkeypatch.setattr(ev_module.pytesseract, "image_to_string", lambda img: "OCR TEXT")
        assert agent._extract_content(path) == "OCR TEXT"

    def test_ocr_failure_is_a_warning_not_a_crash(self, tmp_path, agent):
        path = tmp_path / "broken.png"
        path.write_bytes(b"not an image")
        assert agent._extract_content(path) == ""
        assert get_issues()[0][0] == "WARNING"

    def test_get_evidence_reads_files_and_reports_missing_ones(self, tmp_path, monkeypatch):
        monkeypatch.setattr(ev_module, "DATASET_PATH", tmp_path)
        (tmp_path / "ok.log").write_text("line")
        files = pd.DataFrame(
            [
                {"file_id": "evidence_1", "file_path": "ok.log", "origin": "o", "captured_at": "t1"},
                {"file_id": "evidence_2", "file_path": "missing.log", "origin": "o", "captured_at": "t2"},
            ]
        )
        a = EvidenceAgent()
        a._evidence_files = files
        evidence = a._get_evidence()
        assert [e["file_id"] for e in evidence] == ["evidence_1"]
        assert evidence[0]["content"] == "line"
        assert "missing.log" in get_issues()[0][1]


# --------------------------------------------------------------------------
# Owner system per prefix
# --------------------------------------------------------------------------
def test_system_ownership_comes_from_json_evidence(tmp_path):
    path = tmp_path / "records.json"
    path.write_text(
        json.dumps(
            {
                "records": [
                    {"resource_id": "account_1", "system": "account_service"},
                    {"resource_id": "account_2", "system": "account_service"},
                    {"resource_id": "account_3", "data_store": "legacy_store"},
                    {"resource_id": "search_1", "data_store": "search_service"},
                ]
            }
        )
    )
    (tmp_path / "ignored.log").write_text("x")
    a = EvidenceAgent({"records": [path, tmp_path / "ignored.log"]})
    assert a._system_by_prefix["account"] == "account_service"  # majority wins
    assert a._system_by_prefix["search"] == "search_service"
    assert a._system_by_prefix["tombstone"] == "identity_service"  # TARGET_SYSTEMS fallback


# --------------------------------------------------------------------------
# State proof
# --------------------------------------------------------------------------
class TestGetState:
    def test_newest_mention_after_last_activity_is_present(self, agent):
        evidence = [
            ev("evidence_1", "a.log", "resource_id=account_1 rows=0", "2026-08-01T00:00:00Z"),
            ev("evidence_2", "b.log", "resource_id=account_1 ok", "2026-09-01T00:00:00Z"),
        ]
        assert agent._get_state("account_1", "2026-07-01T00:00:00Z", evidence) == (
            St.PRESENT,
            "evidence_2",
        )

    def test_lookup_returning_nothing_proves_absence(self, agent):
        evidence = [ev("evidence_9", "a.log", 'resource_id=account_1 rows="0" http_status=404')]
        assert agent._get_state("account_1", "", evidence) == (St.ABSENT, "evidence_9")

    def test_evidence_older_than_last_activity_is_ignored(self, agent):
        evidence = [ev("evidence_1", "a.log", "resource_id=account_1", "2026-01-01T00:00:00Z")]
        assert agent._get_state("account_1", "2026-06-01T00:00:00Z", evidence) == (St.UNKNOWN, None)

    def test_sql_snapshot_omitting_the_record_proves_absence(self, agent):
        snapshot = {"profiles": pd.DataFrame([{"resource_id": "account_2"}])}
        evidence = [ev("evidence_54", "db.sql", snapshot)]
        assert agent._get_state("account_1", "", evidence) == (St.ABSENT, "evidence_54")

    def test_json_listing_cannot_prove_absence_by_omission(self, agent):
        listing = {"records": [{"resource_id": "audit_record_2"}]}
        evidence = [ev("evidence_50", "ledger.json", listing)]
        assert agent._get_state("audit_record_1", "", evidence) == (St.UNKNOWN, None)

    def test_id_prefix_collision_is_not_a_mention(self, agent):
        evidence = [ev("evidence_1", "a.log", "resource_id=account_10")]
        assert agent._get_state("account_1", "", evidence) == (St.UNKNOWN, None)

    def test_backup_state_comes_from_its_flag(self, agent):
        evidence = [ev("evidence_3", "a.log", "resource_id=backup_7 restore_allowed=true")]
        assert agent._get_state("backup_7", "", evidence) == (St.ACTIVE, "evidence_3")


class TestProcessState:
    @pytest.mark.parametrize(
        ("resource_id", "chunk", "expected"),
        [
            ("backup_1", "| backup_service | backup_1 | BACKUP_ARCHIVE | ACTIVE | x |", St.ACTIVE),
            ("data_flow_1", "| data_flow_1 | DATA_FLOW | DISABLED | user_39 |", St.DISABLED),
            ("backup_1", "resource_id=backup_1 eligible=true deletion_block=false", St.ACTIVE),
            ("backup_1", "resource_id=backup_1 eligible=true deletion_block=true", St.BLOCKED),
            ("backup_1", '{"resource_id": "backup_1", "restore_allowed": false}', St.BLOCKED),
            ("data_flow_1", "resource_id=data_flow_1 enabled=true", St.ACTIVE),
            ("data_flow_1", '{"resource_id": "data_flow_1", "enabled": 0}', St.DISABLED),
            (
                "backup_1",
                "INSERT INTO backup_restore_entries VALUES ('backup_1', NULL, 'a@b.c', 'k', '1', 't');",
                St.ACTIVE,
            ),
            (
                "data_flow_1",
                "INSERT INTO connector_subscriptions VALUES ('data_flow_1', 'u', 'a@b.c', 'crm', 0, 'ok', 't');",
                St.DISABLED,
            ),
        ],
    )
    def test_reads_the_real_flag_in_every_format(self, resource_id, chunk, expected):
        assert EvidenceAgent._process_state(resource_id, [chunk]) == expected

    def test_ordinary_records_are_not_processes(self):
        assert EvidenceAgent._process_state("account_1", ["status=ACTIVE"]) is None

    def test_word_active_elsewhere_is_ignored(self):
        assert EvidenceAgent._process_state("backup_1", ["backup_1 note: ACTIVE customer"]) is None


def test_only_sql_dumps_are_snapshots():
    assert EvidenceAgent._is_snapshot({"file_path": Path("x.SQL")})
    assert not EvidenceAgent._is_snapshot({"file_path": Path("x.json")})


# --------------------------------------------------------------------------
# PII exposure and treated state
# --------------------------------------------------------------------------
class TestExposure:
    def test_exposed_fields_are_populated_pii_columns(self, agent):
        content = {"records": [{"resource_id": "support_1", "email": EMAIL, "name": "", "phone": None}]}
        evidence = [ev("evidence_7", "r.json", content)]
        assert agent._get_exposed(St.PRESENT, evidence, "support_1", "evidence_7") == {"email"}

    def test_not_inspectable_returns_none(self, agent):
        evidence = [ev("evidence_7", "r.log", "support_1 email=x")]
        assert agent._get_exposed(St.PRESENT, evidence, "support_1", "evidence_7") is None
        assert agent._get_exposed(St.ABSENT, evidence, "support_1", "evidence_7") is None
        assert agent._get_exposed(St.PRESENT, evidence, "support_1", None) is None

    def test_record_missing_from_its_proof_file_returns_none(self, agent):
        evidence = [ev("evidence_7", "r.json", {"records": [{"resource_id": "support_2"}]})]
        assert agent._get_exposed(St.PRESENT, evidence, "support_1", "evidence_7") is None

    def test_undecodable_chunk_is_reported(self):
        exposed = set()
        EvidenceAgent._inspect_chunk_for_personal_info("{not json", exposed)
        assert exposed == set()
        assert get_issues()[0][0] == "ERROR"

    @pytest.mark.parametrize(
        ("category", "inspected", "expected"),
        [
            ("SUPPORT_MESSAGE", set(), St.REDACTED),  # clean + REDACT rule
            ("ANALYTICS_PROFILE", set(), St.ANONYMIZED),  # clean + ANONYMIZE rule
            ("ANALYTICS_PROFILE", {"email"}, St.PRESENT),  # still exposed
            ("ANALYTICS_PROFILE", None, St.PRESENT),  # couldn't inspect
            ("USER_PROFILE", set(), St.PRESENT),  # DELETE rule: clean is not enough
        ],
    )
    def test_treated_state(self, rules, category, inspected, expected):
        assert EvidenceAgent._treated_state(St.PRESENT, category, inspected, rules) == expected

    def test_treated_state_leaves_non_present_alone(self, rules):
        assert EvidenceAgent._treated_state(St.ABSENT, "SUPPORT_MESSAGE", set(), rules) == St.ABSENT


# --------------------------------------------------------------------------
# Resource discovery and the full search
# --------------------------------------------------------------------------
def test_filter_keeps_only_files_that_mention_the_user(agent):
    files = [ev("e1", "a.log", f"x {EMAIL}"), ev("e2", "b.log", "nobody")]
    assert [f["file_id"] for f in agent._filter(files)] == ["e1"]


def test_get_resources_combines_window_cooccurrence_and_links(agent):
    agent.user = user_dataset(
        system_activity=activity(
            [["act_1", "t", "DELETE_RECORD", "deletion_worker", "s", "account_1", "OK", "d"]]
        ),
        activity_pool=activity(
            [
                [
                    "act_2",
                    "t",
                    "LINK_RESOURCE_IDENTITY",
                    "data_catalog",
                    "identity_service",
                    "tombstone_1",
                    "SUCCESS",
                    f"Data catalog linked tombstone_1 (user_01) to {EMAIL} and user_01.",
                ],
                [
                    "act_3",
                    "t",
                    "LINK_RESOURCE_IDENTITY",
                    "data_catalog",
                    "identity_service",
                    "tombstone_2",
                    "SUCCESS",
                    "Data catalog linked tombstone_2 (user_99) to other@x.com and user_99.",
                ],
            ]
        ),
    )
    matched = [ev("e1", "a.log", f"trace_id=tr-1 search_5 owner={EMAIL}\ntrace_id=tr-2 search_6")]
    assert agent._get_resources(matched) == {"account_1", "search_5", "tombstone_1"}


def test_mentioned_resource_ids_scans_every_file(agent):
    files = [ev("e1", "a.log", "account_1 and search_2"), ev("e2", "b.log", "backup_3")]
    assert agent._mentioned_resource_ids(files) == {"account_1", "search_2", "backup_3"}


def test_search_builds_findings_and_drops_unknown(tmp_path, monkeypatch, rules):
    monkeypatch.setattr(ev_module, "DATASET_PATH", tmp_path)
    (tmp_path / "snap.sql").write_text(
        "CREATE TABLE customer_profiles (resource_id TEXT, email TEXT);\n"
        f"INSERT INTO customer_profiles VALUES ('account_2', 'someone@else.com');\n"
        "CREATE TABLE search_index (resource_id TEXT, owner_email TEXT);\n"
        f"INSERT INTO search_index VALUES ('search_5', '{EMAIL}');\n"
    )
    files = pd.DataFrame(
        [{"file_id": "evidence_54", "file_path": "snap.sql", "origin": "o", "captured_at": "2026-09-01T00:00:00Z"}]
    )
    window = activity(
        [
            ["act_1", "2026-08-01T00:00:00Z", "DELETE_RECORD", "deletion_worker", "account_service", "account_1", "OK", "d"],
            ["act_2", "2026-08-01T00:00:00Z", "SEND_EMAIL", "notification_service", "x", "email_delivery_9", "OK", "d"],
        ]
    )
    agent = EvidenceAgent()
    findings = agent.search(
        user_dataset(system_activity=window, activity_pool=window, evidence_files=files), rules
    )
    by_id = {f.resource_id: f for f in findings}

    # account_1: deleted, and the SQL snapshot of profiles omits it -> ABSENT
    assert by_id["account_1"].state == St.ABSENT
    assert by_id["account_1"].evidence_id == "evidence_54"
    assert by_id["account_1"].timeline == ("act_1",)
    # search_5: still in the index next to the user's email -> PRESENT, PII exposed
    assert by_id["search_5"].state == St.PRESENT
    assert by_id["search_5"].exposed_fields == frozenset({"owner_email"})
    # email_delivery_9: nothing proves its state -> UNKNOWN -> dropped
    assert "email_delivery_9" not in by_id
    assert all(isinstance(f, ResourceFinding) for f in findings)
