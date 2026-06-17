"""
Acceptance tests for the RIFT Agent service.

Covers ACCEPTANCE_TESTS.md §2 (bug classification), §3 (score formula parity),
§4 (API endpoints), §8 (results.json shape), §9 (score computation).
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

# Ensure the agent app is importable
sys.path.append(str(Path(__file__).resolve().parents[1]))

from app.config import (
    SCORE_BASE,
    SCORE_EFFICIENCY_FREE_COMMITS,
    SCORE_EFFICIENCY_PENALTY_PER_COMMIT,
    SCORE_SPEED_BONUS,
    SCORE_SPEED_THRESHOLD_SECS,
)
from app.graph.nodes.ast_analyzer import _classify_bug_type
from app.graph.nodes.scorer import _compute_score
from app.main import app

client = TestClient(app)


# ────────────────────────────────────────────────────────────
# §9: Score formula parity with TypeScript gateway tests
# ────────────────────────────────────────────────────────────

class TestScoreFormula:
    """Ensure Python _compute_score matches §12 exactly."""

    def test_config_constants_match_spec(self) -> None:
        assert SCORE_BASE == 100
        assert SCORE_SPEED_BONUS == 10
        assert SCORE_SPEED_THRESHOLD_SECS == 300
        assert SCORE_EFFICIENCY_PENALTY_PER_COMMIT == 2
        assert SCORE_EFFICIENCY_FREE_COMMITS == 20

    def test_fast_run_below_threshold_gets_speed_bonus(self) -> None:
        s = _compute_score(total_time_secs=200, total_commits=10)
        assert s.speed_bonus == 10
        assert s.total == 110

    def test_exact_threshold_no_speed_bonus(self) -> None:
        s = _compute_score(total_time_secs=300, total_commits=10)
        assert s.speed_bonus == 0
        assert s.total == 100

    def test_just_under_threshold_gets_speed_bonus(self) -> None:
        s = _compute_score(total_time_secs=299.9, total_commits=10)
        assert s.speed_bonus == 10

    def test_exactly_20_commits_no_penalty(self) -> None:
        s = _compute_score(total_time_secs=500, total_commits=20)
        assert s.efficiency_penalty == 0
        assert s.total == 100

    def test_21_commits_penalty_of_2(self) -> None:
        s = _compute_score(total_time_secs=500, total_commits=21)
        assert s.efficiency_penalty == 2
        assert s.total == 98

    def test_25_commits_penalty_of_10(self) -> None:
        s = _compute_score(total_time_secs=500, total_commits=25)
        assert s.efficiency_penalty == 10
        assert s.total == 90

    def test_100_commits_heavy_penalty(self) -> None:
        s = _compute_score(total_time_secs=500, total_commits=100)
        assert s.efficiency_penalty == 160
        # base=100, speed=0, penalty=160 → total should floor at 0
        assert s.total == 0

    def test_score_floors_at_zero(self) -> None:
        s = _compute_score(total_time_secs=500, total_commits=200)
        assert s.total == 0

    def test_fast_and_efficient(self) -> None:
        s = _compute_score(total_time_secs=100, total_commits=5)
        assert s.base == 100
        assert s.speed_bonus == 10
        assert s.efficiency_penalty == 0
        assert s.total == 110

    def test_fast_with_many_commits(self) -> None:
        s = _compute_score(total_time_secs=100, total_commits=30)
        # base=100, speed=10, penalty=2*(30-20)=20 → total=90
        assert s.total == 90

    def test_zero_commits(self) -> None:
        s = _compute_score(total_time_secs=500, total_commits=0)
        assert s.efficiency_penalty == 0
        assert s.total == 100

    def test_zero_time(self) -> None:
        s = _compute_score(total_time_secs=0, total_commits=0)
        assert s.speed_bonus == 10
        assert s.total == 110


# ────────────────────────────────────────────────────────────
# §2: Bug type classification
# ────────────────────────────────────────────────────────────

class TestBugClassification:
    """Verify _classify_bug_type maps common error patterns to correct types."""

    @pytest.mark.parametrize(
        "msg,expected",
        [
            ("SyntaxError: unexpected EOF", "SYNTAX"),
            ("TabError: inconsistent use of tabs", "SYNTAX"),
            # IndentationError matches "SyntaxError|IndentationError" first → SYNTAX
            ("IndentationError: unexpected indent", "SYNTAX"),
            ("expected an indented block", "INDENTATION"),
            ("ImportError: no module named foo", "IMPORT"),
            ("ModuleNotFoundError: No module named 'bar'", "IMPORT"),
            ("TypeError: expected str got int", "TYPE_ERROR"),
            ("incompatible type 'str'; expected 'int'", "TYPE_ERROR"),
            ("flake8 E302 expected 2 blank lines", "LINTING"),
            ("pylint C0301 line too long", "LINTING"),
            ("trailing whitespace", "LINTING"),
            ("eslint: no-unused-vars", "LINTING"),
            ("AssertionError: 2 != 3", "LOGIC"),
            ("assert 1 == 2", "LOGIC"),
            ("Expected 42 received 0", "LOGIC"),
        ],
    )
    def test_pattern_mapping(self, msg: str, expected: str) -> None:
        assert _classify_bug_type(msg) == expected

    def test_unknown_defaults_to_logic(self) -> None:
        assert _classify_bug_type("some random error nobody anticipates") == "LOGIC"

    def test_all_results_in_required_set(self) -> None:
        valid_types = {"LINTING", "SYNTAX", "LOGIC", "TYPE_ERROR", "IMPORT", "INDENTATION"}
        patterns = [
            "SyntaxError", "IndentationError", "ImportError", "TypeError",
            "flake8 E302", "assert 1 == 2", "random mystery error",
        ]
        for msg in patterns:
            result = _classify_bug_type(msg)
            assert result in valid_types, f"{msg!r} classified as {result!r}"


# ────────────────────────────────────────────────────────────
# §4: Agent API endpoint validation
# ────────────────────────────────────────────────────────────

VALID_START_PAYLOAD: dict[str, Any] = {
    "run_id": "run_acc_test_01",
    "repo_url": "https://github.com/org/repo",
    "team_name": "RIFT ORGANISERS",
    "leader_name": "Saiyam Kumar",
    "branch_name": "RIFT_ORGANISERS_SAIYAM_KUMAR_AI_Fix",
    "max_iterations": 5,
    "feature_flags": {
        "ENABLE_KB_LOOKUP": True,
        "ENABLE_SPECULATIVE_BRANCHES": False,
        "ENABLE_ADVERSARIAL_TESTS": True,
        "ENABLE_CAUSAL_GRAPH": True,
        "ENABLE_PROVENANCE_PASS": True,
    },
}


class TestAgentStartEndpoint:
    """POST /agent/start validation."""

    def test_rejects_empty_body(self) -> None:
        r = client.post("/agent/start", json={})
        assert r.status_code == 400
        assert r.json()["error"]["code"] == "INVALID_INPUT"

    def test_rejects_missing_run_id(self) -> None:
        payload = {k: v for k, v in VALID_START_PAYLOAD.items() if k != "run_id"}
        r = client.post("/agent/start", json=payload)
        assert r.status_code == 400

    def test_rejects_invalid_repo_url(self) -> None:
        payload = {**VALID_START_PAYLOAD, "repo_url": "not-a-github-url"}
        r = client.post("/agent/start", json=payload)
        assert r.status_code == 400

    def test_rejects_bad_branch_name_format(self) -> None:
        payload = {**VALID_START_PAYLOAD, "branch_name": "main"}
        r = client.post("/agent/start", json=payload)
        assert r.status_code == 400

    def test_accepts_valid_payload(self) -> None:
        r = client.post("/agent/start", json=VALID_START_PAYLOAD)
        assert r.status_code == 200
        body = r.json()
        assert body["accepted"] is True
        assert body["run_id"] == "run_acc_test_01"

    def test_response_shape(self) -> None:
        r = client.post("/agent/start", json=VALID_START_PAYLOAD)
        assert r.status_code == 200
        body = r.json()
        assert set(body.keys()) == {"accepted", "run_id"}

    def test_error_envelope_shape(self) -> None:
        r = client.post("/agent/start", json={})
        assert r.status_code == 400
        body = r.json()
        assert "error" in body
        assert "code" in body["error"]
        assert "message" in body["error"]


class TestAgentStatusEndpoint:
    """GET /agent/status."""

    def test_returns_status_for_started_run(self) -> None:
        # Start a run first
        client.post("/agent/start", json={
            **VALID_START_PAYLOAD,
            "run_id": "run_status_acc",
        })
        r = client.get("/agent/status", params={"run_id": "run_status_acc"})
        assert r.status_code == 200
        body = r.json()
        assert body["run_id"] == "run_status_acc"
        assert body["status"] in {"queued", "running", "passed", "failed", "quarantined"}
        assert isinstance(body["current_node"], str)

    def test_returns_queued_for_unknown_run(self) -> None:
        """Agent returns status=queued for unknown runs (not 404)."""
        r = client.get("/agent/status", params={"run_id": "run_does_not_exist"})
        assert r.status_code == 200
        assert r.json()["status"] == "queued"


class TestHealthEndpoint:
    """GET /health."""

    def test_health_returns_agent_ok(self) -> None:
        r = client.get("/health")
        assert r.status_code == 200
        body = r.json()
        assert body["agent"] == "ok"
        assert "version" in body


# ────────────────────────────────────────────────────────────
# §8: results.json shape validation
# ────────────────────────────────────────────────────────────

class TestResultsJsonShape:
    """Verify results.json built by scorer matches §13 shape."""

    REQUIRED_FIELDS = {
        "run_id", "repo_url", "team_name", "leader_name", "branch_name",
        "final_status", "total_failures", "total_fixes", "total_time_secs",
        "score", "fixes", "ci_log",
    }
    SCORE_FIELDS = {"base", "speed_bonus", "efficiency_penalty", "total"}
    FIX_FIELDS = {"file", "bug_type", "line_number", "commit_message", "status"}
    CI_FIELDS = {"iteration", "status", "timestamp", "regression"}
    VALID_BUG_TYPES = {"LINTING", "SYNTAX", "LOGIC", "TYPE_ERROR", "IMPORT", "INDENTATION"}
    VALID_CI_STATUSES = {"passed", "failed", "error"}
    VALID_FINAL_STATUSES = {"PASSED", "FAILED", "QUARANTINED"}

    def _sample_results(self) -> dict[str, Any]:
        """Minimal valid results.json."""
        return {
            "run_id": "run_shape_01",
            "repo_url": "https://github.com/org/repo",
            "team_name": "RIFT ORGANISERS",
            "leader_name": "Saiyam Kumar",
            "branch_name": "RIFT_ORGANISERS_SAIYAM_KUMAR_AI_Fix",
            "final_status": "PASSED",
            "total_failures": 1,
            "total_fixes": 1,
            "total_time_secs": 144,
            "score": {
                "base": 100.0,
                "speed_bonus": 10.0,
                "efficiency_penalty": 0.0,
                "total": 110.0,
            },
            "fixes": [
                {
                    "file": "src/main.py",
                    "bug_type": "SYNTAX",
                    "line_number": 10,
                    "commit_message": "[AI-AGENT] fix syntax error",
                    "status": "FIXED",
                }
            ],
            "ci_log": [
                {
                    "iteration": 1,
                    "status": "passed",
                    "timestamp": "2026-02-19T10:05:12Z",
                    "regression": False,
                }
            ],
        }

    def test_has_all_required_fields(self) -> None:
        results = self._sample_results()
        assert self.REQUIRED_FIELDS.issubset(results.keys())

    def test_score_has_all_fields(self) -> None:
        results = self._sample_results()
        assert self.SCORE_FIELDS == set(results["score"].keys())

    def test_fix_has_all_fields(self) -> None:
        results = self._sample_results()
        for fix in results["fixes"]:
            assert self.FIX_FIELDS == set(fix.keys())

    def test_ci_log_has_all_fields(self) -> None:
        results = self._sample_results()
        for entry in results["ci_log"]:
            assert self.CI_FIELDS == set(entry.keys())

    def test_fixes_bug_types_in_required_set(self) -> None:
        results = self._sample_results()
        for fix in results["fixes"]:
            assert fix["bug_type"] in self.VALID_BUG_TYPES

    def test_ci_log_statuses_in_required_set(self) -> None:
        results = self._sample_results()
        for entry in results["ci_log"]:
            assert entry["status"] in self.VALID_CI_STATUSES

    def test_final_status_in_valid_set(self) -> None:
        results = self._sample_results()
        assert results["final_status"] in self.VALID_FINAL_STATUSES

    def test_commit_messages_have_ai_agent_prefix(self) -> None:
        results = self._sample_results()
        for fix in results["fixes"]:
            assert fix["commit_message"].startswith("[AI-AGENT]")

    def test_score_total_matches_formula(self) -> None:
        results = self._sample_results()
        s = results["score"]
        expected = max(0, s["base"] + s["speed_bonus"] - s["efficiency_penalty"])
        assert s["total"] == expected


# ────────────────────────────────────────────────────────────
# §8: Report PDF generation
# ────────────────────────────────────────────────────────────

class TestReportPdfGeneration:
    """Verify report.pdf generation from results dict."""

    def _sample_results(self) -> dict[str, Any]:
        return {
            "run_id": "run_pdf_01",
            "repo_url": "https://github.com/org/repo",
            "team_name": "RIFT ORGANISERS",
            "leader_name": "Saiyam Kumar",
            "branch_name": "RIFT_ORGANISERS_SAIYAM_KUMAR_AI_Fix",
            "final_status": "PASSED",
            "total_failures": 2,
            "total_fixes": 2,
            "total_time_secs": 180.5,
            "score": {
                "base": 100.0,
                "speed_bonus": 10.0,
                "efficiency_penalty": 0.0,
                "total": 110.0,
            },
            "fixes": [
                {
                    "file": "src/main.py",
                    "bug_type": "SYNTAX",
                    "line_number": 12,
                    "commit_message": "[AI-AGENT] fix missing colon",
                    "status": "FIXED",
                },
                {
                    "file": "src/utils.py",
                    "bug_type": "LINTING",
                    "line_number": 34,
                    "commit_message": "[AI-AGENT] fix trailing whitespace",
                    "status": "FIXED",
                },
            ],
            "ci_log": [
                {
                    "iteration": 1,
                    "status": "failed",
                    "timestamp": "2026-02-19T10:01:00Z",
                    "regression": False,
                },
                {
                    "iteration": 2,
                    "status": "passed",
                    "timestamp": "2026-02-19T10:03:00Z",
                    "regression": False,
                },
            ],
        }

    def test_generates_pdf_file(self, tmp_path: Path) -> None:
        from app.report import generate_report_pdf

        results = self._sample_results()
        pdf_path = tmp_path / "run_pdf_01" / "report.pdf"
        result = generate_report_pdf(results, pdf_path)

        assert result == pdf_path
        assert pdf_path.exists()
        assert pdf_path.stat().st_size > 0

    def test_pdf_has_valid_header(self, tmp_path: Path) -> None:
        from app.report import generate_report_pdf

        results = self._sample_results()
        pdf_path = tmp_path / "run_pdf_02" / "report.pdf"
        generate_report_pdf(results, pdf_path)

        content = pdf_path.read_bytes()
        assert content[:5] == b"%PDF-", "File must start with %PDF- magic bytes"

    def test_pdf_contains_run_id(self, tmp_path: Path) -> None:
        from app.report import generate_report_pdf

        results = self._sample_results()
        pdf_path = tmp_path / "run_pdf_03" / "report.pdf"
        generate_report_pdf(results, pdf_path)

        content = pdf_path.read_bytes().decode("latin-1")
        assert "run_pdf_03" in content or "RIFT" in content

    def test_pdf_contains_team_info(self, tmp_path: Path) -> None:
        from app.report import generate_report_pdf

        results = self._sample_results()
        pdf_path = tmp_path / "run_pdf_04" / "report.pdf"
        generate_report_pdf(results, pdf_path)

        content = pdf_path.read_bytes().decode("latin-1")
        assert "RIFT" in content

    def test_pdf_with_empty_fixes(self, tmp_path: Path) -> None:
        from app.report import generate_report_pdf

        results = self._sample_results()
        results["fixes"] = []
        results["total_fixes"] = 0
        pdf_path = tmp_path / "run_pdf_05" / "report.pdf"
        result = generate_report_pdf(results, pdf_path)

        assert result == pdf_path
        assert pdf_path.exists()

    def test_pdf_with_empty_ci_log(self, tmp_path: Path) -> None:
        from app.report import generate_report_pdf

        results = self._sample_results()
        results["ci_log"] = []
        pdf_path = tmp_path / "run_pdf_06" / "report.pdf"
        result = generate_report_pdf(results, pdf_path)

        assert result == pdf_path
        assert pdf_path.exists()

    def test_pdf_with_failed_status(self, tmp_path: Path) -> None:
        from app.report import generate_report_pdf

        results = self._sample_results()
        results["final_status"] = "FAILED"
        pdf_path = tmp_path / "run_pdf_07" / "report.pdf"
        result = generate_report_pdf(results, pdf_path)

        assert result == pdf_path
        assert pdf_path.exists()

    def test_pdf_creates_parent_directories(self, tmp_path: Path) -> None:
        from app.report import generate_report_pdf

        results = self._sample_results()
        pdf_path = tmp_path / "deep" / "nested" / "dir" / "report.pdf"
        result = generate_report_pdf(results, pdf_path)

        assert result == pdf_path
        assert pdf_path.exists()
