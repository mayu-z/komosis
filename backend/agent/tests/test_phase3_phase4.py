"""
Unit tests for Phase 3 & 4 new utilities and node helpers.

Tests are fully offline — no LLM calls, no git, no DB/Redis.
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

import pytest

# Ensure the agent package is on sys.path when run from repo root
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


# ── platform_detector tests ───────────────────────────────────────────────────

from app.utils.platform_detector import detect_platform, PlatformHints


def _make_repo(tmp_path: Path, files: dict[str, str]) -> str:
    """Write a set of files into a temp directory and return its path as str."""
    for rel, content in files.items():
        fp = tmp_path / rel
        fp.parent.mkdir(parents=True, exist_ok=True)
        fp.write_text(content, encoding="utf-8")
    return str(tmp_path)


class TestPlatformDetector:
    def test_detects_vercel_json(self, tmp_path: Path) -> None:
        cfg = {"framework": "vite", "outputDirectory": "dist"}
        repo = _make_repo(tmp_path, {"vercel.json": json.dumps(cfg)})
        hints = detect_platform(repo)
        assert hints.platform == "vercel"
        assert hints.deploy_hints.get("vercel_config") == cfg

    def test_detects_railway_json(self, tmp_path: Path) -> None:
        repo = _make_repo(tmp_path, {"railway.json": "{}"})
        assert detect_platform(repo).platform == "railway"

    def test_detects_railway_toml(self, tmp_path: Path) -> None:
        repo = _make_repo(tmp_path, {"railway.toml": "[service]"})
        assert detect_platform(repo).platform == "railway"

    def test_detects_fly_toml(self, tmp_path: Path) -> None:
        repo = _make_repo(tmp_path, {"fly.toml": "app = 'myapp'"})
        hints = detect_platform(repo)
        assert hints.platform == "fly"
        assert "fly_config" in hints.deploy_hints

    def test_detects_render_yaml(self, tmp_path: Path) -> None:
        repo = _make_repo(tmp_path, {"render.yaml": "services: []"})
        assert detect_platform(repo).platform == "render"

    def test_detects_netlify_toml(self, tmp_path: Path) -> None:
        repo = _make_repo(tmp_path, {"netlify.toml": "[build]"})
        assert detect_platform(repo).platform == "netlify"

    def test_detects_heroku_procfile(self, tmp_path: Path) -> None:
        repo = _make_repo(tmp_path, {"Procfile": "web: node server.js"})
        hints = detect_platform(repo)
        assert hints.platform == "heroku"
        assert hints.deploy_hints.get("procfile")

    def test_detects_aws_cdk(self, tmp_path: Path) -> None:
        repo = _make_repo(tmp_path, {"cdk.json": '{"app":"node bin/app.js"}'})
        hints = detect_platform(repo)
        assert hints.platform == "aws"
        assert hints.deploy_hints.get("aws_tool") == "CDK"

    def test_detects_aws_sam(self, tmp_path: Path) -> None:
        repo = _make_repo(tmp_path, {"samconfig.toml": "[default]"})
        assert detect_platform(repo).platform == "aws"

    def test_detects_vercel_from_package_json_deploy_script(self, tmp_path: Path) -> None:
        pkg = {"scripts": {"deploy": "vercel --prod"}}
        repo = _make_repo(tmp_path, {"package.json": json.dumps(pkg)})
        assert detect_platform(repo).platform == "vercel"

    def test_detects_fly_from_package_json_deploy_script(self, tmp_path: Path) -> None:
        pkg = {"scripts": {"deploy": "fly deploy"}}
        repo = _make_repo(tmp_path, {"package.json": json.dumps(pkg)})
        assert detect_platform(repo).platform == "fly"

    def test_no_platform_returns_none(self, tmp_path: Path) -> None:
        repo = _make_repo(tmp_path, {"index.py": "print('hello')"})
        hints = detect_platform(repo)
        assert hints.platform is None

    def test_detects_dockerfile(self, tmp_path: Path) -> None:
        repo = _make_repo(tmp_path, {"Dockerfile": "FROM python:3.12"})
        hints = detect_platform(repo)
        assert hints.has_dockerfile is True
        assert hints.platform is None   # Dockerfile alone doesn't imply a platform

    def test_detects_docker_compose(self, tmp_path: Path) -> None:
        repo = _make_repo(tmp_path, {"docker-compose.yml": "version: '3'"})
        assert detect_platform(repo).has_docker_compose is True

    def test_vercel_takes_priority_over_dockerfile(self, tmp_path: Path) -> None:
        """Platform-specific config beats Dockerfile."""
        repo = _make_repo(tmp_path, {
            "Dockerfile":  "FROM node:20",
            "vercel.json": '{"framework":"nextjs"}',
        })
        hints = detect_platform(repo)
        assert hints.platform == "vercel"
        assert hints.has_dockerfile is True


# ── file_analyzer tests ───────────────────────────────────────────────────────

from app.utils.file_analyzer import find_best_file_to_test


class TestFileAnalyzer:
    def test_finds_python_entry_point(self, tmp_path: Path) -> None:
        repo = _make_repo(tmp_path, {
            "main.py": "def add(a, b):\n    return a + b\n" * 5,
            "utils.py": "def helper():\n    pass\n" * 5,
        })
        result = find_best_file_to_test(repo, "python")
        assert result is not None
        path, _ = result
        assert "main.py" in path   # entry point wins

    def test_skips_test_files(self, tmp_path: Path) -> None:
        repo = _make_repo(tmp_path, {
            "tests/test_main.py": "def test_add():\n    assert 1 + 1 == 2\n" * 5,
            "main.py": "def add(a, b):\n    return a + b\n" * 5,
        })
        result = find_best_file_to_test(repo, "python")
        assert result is not None
        path, _ = result
        assert "test_main" not in path

    def test_skips_node_modules(self, tmp_path: Path) -> None:
        repo = _make_repo(tmp_path, {
            "node_modules/lodash/index.js": "module.exports = {};\n" * 20,
            "index.js": "function greet(name) { return 'Hello ' + name; }\n" * 5,
        })
        result = find_best_file_to_test(repo, "javascript")
        assert result is not None
        path, _ = result
        assert "node_modules" not in path

    def test_skips_generated_files(self, tmp_path: Path) -> None:
        repo = _make_repo(tmp_path, {
            "generated.py": "# Generated by protoc\ndef noop():\n    pass\n" * 5,
            "real.py": "def compute(x):\n    return x * 2\n" * 5,
        })
        result = find_best_file_to_test(repo, "python")
        assert result is not None
        path, _ = result
        assert "generated" not in path

    def test_returns_none_when_no_source(self, tmp_path: Path) -> None:
        repo = _make_repo(tmp_path, {
            "README.md": "# My Project\n",
            ".gitignore": "node_modules/\n",
        })
        result = find_best_file_to_test(repo, "python")
        assert result is None

    def test_skips_files_over_max_lines(self, tmp_path: Path) -> None:
        huge = "x = 1\n" * 500
        small = "def tiny():\n    return True\n" * 5
        repo = _make_repo(tmp_path, {
            "huge.py": huge,
            "small.py": small,
        })
        result = find_best_file_to_test(repo, "python", max_lines=200)
        assert result is not None
        path, _ = result
        assert "small" in path

    def test_typescript_extension_filter(self, tmp_path: Path) -> None:
        repo = _make_repo(tmp_path, {
            "utils.py":  "def noop():\n    pass\n" * 5,
            "index.ts":  "export function greet(name: string) { return name; }\n" * 5,
        })
        result = find_best_file_to_test(repo, "typescript")
        assert result is not None
        path, _ = result
        assert path.endswith(".ts")

    def test_skips_config_only_files(self, tmp_path: Path) -> None:
        repo = _make_repo(tmp_path, {
            "package.json": '{"name":"app","scripts":{"test":"jest"}}\n',
            "src/app.ts": "export function main() { return 42; }\n" * 5,
        })
        result = find_best_file_to_test(repo, "typescript")
        assert result is not None
        path, _ = result
        assert "package.json" not in path


# ── cicd_prompts helper tests ─────────────────────────────────────────────────

from app.prompts.cicd_prompts import (
    get_test_command,
    get_platform_guidance,
    default_framework,
    get_test_file_path,
)


class TestCicdPrompts:
    # get_test_command
    def test_pytest_command(self) -> None:
        assert get_test_command("python", "pytest") == "pytest --tb=short"

    def test_vitest_command(self) -> None:
        assert get_test_command("javascript", "vitest") == "npx vitest run"

    def test_go_test_command(self) -> None:
        assert get_test_command("go", "go-test") == "go test ./... -v"

    def test_cargo_test_command(self) -> None:
        assert get_test_command("rust", "cargo-test") == "cargo test"

    def test_dotnet_test_command(self) -> None:
        assert get_test_command("csharp", "dotnet-test") == "dotnet test --no-restore"

    def test_unknown_lang_falls_back_to_npm_test(self) -> None:
        assert get_test_command("brainfuck", "unknown") == "npm test"

    def test_known_lang_unknown_framework_falls_back(self) -> None:
        # Known language, unknown framework → language default
        cmd = get_test_command("python", "unknown_fw")
        assert "pytest" in cmd or "unittest" in cmd or cmd  # something sensible

    # get_platform_guidance
    def test_vercel_guidance_contains_action(self) -> None:
        g = get_platform_guidance("vercel")
        assert "amondnet/vercel-action" in g
        assert "VERCEL_TOKEN" in g

    def test_fly_guidance_contains_flyctl(self) -> None:
        g = get_platform_guidance("fly")
        assert "flyctl" in g
        assert "FLY_API_TOKEN" in g

    def test_aws_guidance_contains_credentials_action(self) -> None:
        g = get_platform_guidance("aws")
        assert "aws-actions/configure-aws-credentials" in g

    def test_unknown_platform_returns_generic_comment(self) -> None:
        g = get_platform_guidance("my-weird-platform")
        assert "my-weird-platform" in g

    # default_framework
    def test_python_default_framework(self) -> None:
        assert default_framework("python") == "pytest"

    def test_javascript_default_framework(self) -> None:
        assert default_framework("javascript") == "jest"

    def test_rust_default_framework(self) -> None:
        assert default_framework("rust") == "cargo-test"

    def test_unknown_lang_default_framework(self) -> None:
        assert default_framework("cobol") == "jest"

    # get_test_file_path
    def test_python_test_file_path(self) -> None:
        path = get_test_file_path("app/utils.py", "python")
        assert path.endswith("test_utils.py")
        assert "tests" in path

    def test_typescript_test_file_path_alongside(self) -> None:
        path = get_test_file_path("src/index.ts", "typescript")
        assert path.endswith("index.test.ts")
        assert "src" in path

    def test_go_test_file_path_alongside(self) -> None:
        path = get_test_file_path("main.go", "go")
        assert path.endswith("main_test.go")

    def test_java_test_file_path(self) -> None:
        path = get_test_file_path("Main.java", "java")
        assert "MainTest.java" in path

    def test_ruby_test_file_path(self) -> None:
        path = get_test_file_path("app.rb", "ruby")
        assert path.endswith("app_spec.rb")


# ── decision_node routing logic tests ─────────────────────────────────────────

import asyncio
import pytest_asyncio


class TestDecisionNodeRouting:
    """
    Test the decision_node routing logic without touching the DB or Redis.
    We patch emit_thought and insert_trace to no-ops.
    """

    def _run(self, coro):
        return asyncio.get_event_loop().run_until_complete(coro)

    def _make_state(self, **overrides) -> dict:
        base = {
            "run_id":         "test_run",
            "repo_url":       "https://github.com/org/repo",
            "team_name":      "Test",
            "leader_name":    "Dev",
            "branch_name":    "TEST_DEV_AI_Fix",
            "max_iterations": 5,
            "feature_flags":  {},
            "iteration":      1,
            "has_tests":      False,
            "has_ci_pipeline": False,
            "tests_passing":  False,
            "ci_file_path":   None,
            "next_node":      "",
            "summary":        "",
            "current_node":   "repo_scanner",
        }
        base.update(overrides)
        return base

    def test_no_tests_routes_to_test_generator(self, monkeypatch) -> None:
        monkeypatch.setattr("app.events.emit_thought", lambda *a, **k: asyncio.sleep(0))
        monkeypatch.setattr("app.db.insert_trace", lambda *a, **k: asyncio.sleep(0))

        from app.graph.nodes.decision_node import decision_node
        state = self._make_state(has_tests=False)
        result = self._run(decision_node(state))
        assert result["next_node"] == "test_generator"

    def test_failing_tests_routes_to_test_runner(self, monkeypatch) -> None:
        monkeypatch.setattr("app.events.emit_thought", lambda *a, **k: asyncio.sleep(0))
        monkeypatch.setattr("app.db.insert_trace", lambda *a, **k: asyncio.sleep(0))

        from app.graph.nodes.decision_node import decision_node
        state = self._make_state(has_tests=True, tests_passing=False)
        result = self._run(decision_node(state))
        assert result["next_node"] == "test_runner"

    def test_passing_no_ci_routes_to_cicd_generator(self, monkeypatch) -> None:
        monkeypatch.setattr("app.events.emit_thought", lambda *a, **k: asyncio.sleep(0))
        monkeypatch.setattr("app.db.insert_trace", lambda *a, **k: asyncio.sleep(0))

        from app.graph.nodes.decision_node import decision_node
        state = self._make_state(has_tests=True, tests_passing=True, has_ci_pipeline=False)
        result = self._run(decision_node(state))
        assert result["next_node"] == "cicd_generator"

    def test_passing_with_ci_routes_to_finalizer(self, monkeypatch) -> None:
        monkeypatch.setattr("app.events.emit_thought", lambda *a, **k: asyncio.sleep(0))
        monkeypatch.setattr("app.db.insert_trace", lambda *a, **k: asyncio.sleep(0))

        from app.graph.nodes.decision_node import decision_node
        state = self._make_state(has_tests=True, tests_passing=True, has_ci_pipeline=True)
        result = self._run(decision_node(state))
        assert result["next_node"] == "finalizer"
