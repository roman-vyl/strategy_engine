"""Parity gate: the current evaluator must reproduce the golden baseline
bit-for-bit (intermediates, projection, NDJSON bytes, failure semantics).

Each case replays the request payload stored *in the golden file* (not the
corpus builders), so the comparison never depends on re-deriving inputs.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

import pytest
from fastapi.testclient import TestClient

from parity.compare import compare_case, format_report
from parity.corpus import all_cases
from parity.harness import (
    GOLDEN_DIR,
    PARITY_DIR,
    Recorder,
    market_fixture_bytes,
    record_payload,
    recording_services,
)
from parity.snapshot import ArrayStore, read_json_gz
from strategy_engine.adapters.http.app import create_app

MANIFEST = json.loads((GOLDEN_DIR / "manifest.json").read_text())
CASE_NAMES = [entry["case"] for entry in MANIFEST["cases"]]


def load_golden_case(name: str) -> dict[str, Any]:
    return read_json_gz(GOLDEN_DIR / "cases" / f"{name}.json.gz")


@pytest.fixture(scope="session")
def golden_store() -> ArrayStore:
    return ArrayStore.load(GOLDEN_DIR / "arrays.npz", verify=True)


@pytest.mark.parametrize("case_name", CASE_NAMES)
def test_current_evaluator_matches_golden(case_name: str, golden_store: ArrayStore) -> None:
    golden = load_golden_case(case_name)
    actual, actual_store = record_payload(case_name, golden["request_payload"])
    mismatches = compare_case(golden, actual, golden_store, actual_store)
    assert not mismatches, format_report(mismatches)


def test_golden_files_and_fixture_match_manifest() -> None:
    fixture = MANIFEST["market_fixture"]
    assert hashlib.sha256(market_fixture_bytes()).hexdigest() == fixture["sha256"]
    arrays = GOLDEN_DIR / MANIFEST["arrays"]["file"]
    assert hashlib.sha256(arrays.read_bytes()).hexdigest() == MANIFEST["arrays"]["sha256"]
    for entry in MANIFEST["cases"]:
        path = GOLDEN_DIR / entry["file"]
        assert hashlib.sha256(path.read_bytes()).hexdigest() == entry["sha256"], entry["case"]
    assert (PARITY_DIR / fixture["file"]).is_file()


def test_corpus_builders_still_produce_the_golden_requests() -> None:
    """Guards against the corpus definition drifting away from the recorded
    baseline (the gate itself replays the stored payloads)."""

    cases = {case.name: case for case in all_cases()}
    assert sorted(cases) == sorted(CASE_NAMES)
    for name, case in cases.items():
        golden = load_golden_case(name)
        assert json.loads(json.dumps(case.payload())) == golden["request_payload"], name


def test_ndjson_bytes_over_http_equal_route_body() -> None:
    """The harness drains the real route's streaming body in-process; the
    same request over the ASGI HTTP stack yields the identical byte stream."""

    golden = load_golden_case("synthetic_failures_mixed")
    with (
        recording_services(Recorder()) as services,
        TestClient(create_app(services=services)) as client,
    ):
        response = client.post(
            "/v1/strategy-evaluations/range-batch", json=golden["request_payload"]
        )
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/x-ndjson"
    assert response.content == "".join(golden["ndjson"]["lines"]).encode("utf-8")
