# code/tests/unit/agents/test_evidence_agent.py

import pytest
from agents.evidence_agent import EvidenceAgent


@pytest.fixture
def sample_agent():
    mock_evidence = {"_evidence_files": {}}
    return EvidenceAgent(mock_evidence)
