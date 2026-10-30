# code/tests/unit/src/test_data_handler.py

import json

import pandas as pd
import src.data_handler as data_handler
from src.constants import DATASET_FILES, OUTPUT_COLUMNS
from src.data_handler import DataHandler


def test_loads_every_dataset_file_as_a_dataframe(dataset):
    for name in DATASET_FILES:
        assert isinstance(dataset[name], pd.DataFrame), name


def test_sample_mode_swaps_in_the_32_sample_cases(dataset):
    assert len(dataset["deletion_requests"]) == 32
    assert dataset["deletion_requests"] is dataset["sample_deletion_requests"]
    assert dataset["output"] is dataset["sample_output"]


def test_full_mode_keeps_all_518_requests(monkeypatch):
    monkeypatch.setattr(data_handler, "USE_SAMPLE", False)
    handler = DataHandler()
    assert len(handler.deletion_requests) == 518


def test_evidence_index_lists_existing_record_files(dataset):
    records = dataset["evidence"]["records"]
    assert records, "expected at least one evidence/records file"
    for path in records:
        assert "evidence/records/" in path.as_posix()
        assert path.exists(), path


def test_save_writes_graded_format_sorted_by_case_id(outputs):
    rows = [
        ["case_02", "COMPLETE", [{"step_no": 1, "phase": "VERIFICATION"}]],
        ["case_01", "NOT_APPLICABLE", []],
    ]
    handler = DataHandler.__new__(DataHandler)  # no CSV loading needed
    handler.save(rows)

    saved = pd.read_csv(outputs.output)
    assert list(saved.columns) == OUTPUT_COLUMNS
    assert list(saved["case_id"]) == ["case_01", "case_02"]
    assert json.loads(saved.loc[0, "steps_json"]) == []
    assert json.loads(saved.loc[1, "steps_json"])[0]["step_no"] == 1
