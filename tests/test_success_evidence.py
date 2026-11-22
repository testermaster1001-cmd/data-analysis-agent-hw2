"""Offline consistency checks for the synthetic-data example included in the repository."""
import json
from pathlib import Path

from scripts.audit_trace import audit_trace


def test_checked_in_success_trace_has_valid_result_references():
    root = Path(__file__).resolve().parents[1]
    trace = json.loads((root / 'documents/evidence/success_case/openai_podman_trace.json').read_text(encoding='utf-8'))
    assert trace['provider'] == 'openai'
    assert trace['status'] == 'completed'
    report = audit_trace(trace)
    assert report['passed'], report['issues']
    assert trace['tool_executions'] == len(report['observations'])
