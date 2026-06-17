"""
ast_analyzer node — parse test output and classify failures into the
six canonical bug types required by the hackathon scoring rubric.

Strategy (per SOURCE_OF_TRUTH §7):
  1. Rule-based parser/classifier first.
  2. LLM fallback only when rule path cannot resolve.
"""
from __future__ import annotations

import logging
import re
from pathlib import Path

from ...config import OPENAI_API_KEY, OPENAI_MODEL
from ...db import insert_trace
from ...events import emit_thought
from ...llm import get_llm, has_llm_keys
from ..state import AgentState, BugType, TestFailure

logger = logging.getLogger("rift.node.ast_analyzer")

# ── Canonical bug types (must match DB CHECK constraint) ────
_VALID_BUG_TYPES = {"LINTING", "SYNTAX", "LOGIC", "TYPE_ERROR", "IMPORT", "INDENTATION"}

# Map common LLM-invented types back to the 6 canonical ones
_BUG_TYPE_ALIASES: dict[str, BugType] = {
    "CONFIG": "SYNTAX",
    "CONFIGURATION": "SYNTAX",
    "RUNTIME": "LOGIC",
    "RUNTIME_ERROR": "LOGIC",
    "BUILD": "SYNTAX",
    "BUILD_ERROR": "SYNTAX",
    "COMPILE": "SYNTAX",
    "COMPILE_ERROR": "SYNTAX",
    "DEPENDENCY": "IMPORT",
    "MISSING_DEPENDENCY": "IMPORT",
    "MISSING_MODULE": "IMPORT",
    "MISSING_IMPORT": "IMPORT",
    "STYLE": "LINTING",
    "FORMAT": "LINTING",
    "FORMATTING": "LINTING",
    "ASSERTION": "LOGIC",
    "TEST_FAILURE": "LOGIC",
    "NULL_REFERENCE": "TYPE_ERROR",
    "WHITESPACE": "INDENTATION",
}


def _sanitize_bug_type(raw: str | None) -> BugType:
    """Ensure bug_type is one of the 6 canonical values."""
    if not raw:
        return "LOGIC"
    upper = raw.strip().upper().replace(" ", "_")
    if upper in _VALID_BUG_TYPES:
        return upper  # type: ignore[return-value]
    if upper in _BUG_TYPE_ALIASES:
        return _BUG_TYPE_ALIASES[upper]
    return "LOGIC"  # safe default


# ── Rule-based classifiers ──────────────────────────────────

_PYTEST_FAILURE_RE = re.compile(
    r"^(?:FAILED|ERROR)\s+([\w/\\.]+)::(\w+)"
    r"(?:\s*-\s*(.+))?$",
    re.MULTILINE,
)

_FILE_LINE_RE = re.compile(
    r'File "([^"]+)", line (\d+)',
)

_JEST_FAILURE_RE = re.compile(
    r"●\s+([\w\s]+)\s+›\s+([\w\s]+)\n\n\s+(.+)",
    re.MULTILINE,
)

# Error message patterns → bug type (universal across all languages)
_BUG_PATTERNS: list[tuple[re.Pattern[str], BugType]] = [
    # ── Syntax ──
    (re.compile(
        r"SyntaxError|IndentationError|TabError"
        r"|error CS\d+|error TS\d+"                    # C# / TypeScript compiler
        r"|ParseError|parse error"                      # PHP
        r"|expected.*\btoken\b|unexpected token"        # generic
        r"|syntax error|SyntaxException"                # generic
        r"|error\[E\d+\].*expected"                     # Rust
        r"|\.go:\d+:\d+:.*expected"                     # Go
        r"|error:.*expected.*;|missing semicolon"        # C/C++/Java
    , re.I), "SYNTAX"),

    # ── Indentation (subset of syntax, checked first) ──
    (re.compile(
        r"IndentationError|unexpected indent|expected an indented block"
        r"|inconsistent use of tabs and spaces"
    , re.I), "INDENTATION"),

    # ── Import / Module resolution ──
    (re.compile(
        r"ImportError|ModuleNotFoundError|No module named"
        r"|cannot find module|Cannot find module"        # Node.js / TS
        r"|unresolved import|cannot find type"           # Rust / generic
        r"|missing.*reference|CS0246"                    # C#
        r"|package .* is not in GOROOT"                  # Go
        r"|error\[E0432\]|error\[E0433\]"               # Rust unresolved
        r"|no required module provides"                  # Go
        r"|LoadError|require.*cannot load such file"     # Ruby
        r"|Class .* not found|Fatal error.*not found"    # PHP
        r"|UndefinedFunctionError|module .* is not available"  # Elixir
        r"|Could not resolve"                            # Dart/Flutter
        r"|error: package .* does not exist"             # Java
        r"|import .* could not be resolved"              # generic
    , re.I), "IMPORT"),

    # ── Type errors ──
    (re.compile(
        r"TypeError|type.?error|expected.*got|incompatible type"
        r"|CS0029|CS1503|cannot.?convert"                # C#
        r"|error TS\d+:.*Type .* is not assignable"      # TypeScript
        r"|type mismatch|expected type"                  # Rust / Go / generic
        r"|error\[E0308\]"                               # Rust type mismatch
        r"|cannot use .* as type"                        # Go
        r"|incompatible types|found.*required"           # Java
        r"|Argument .* must be of type"                  # PHP
    , re.I), "TYPE_ERROR"),

    # ── Linting / style / warnings ──
    (re.compile(
        r"flake8|pylint|eslint|E\d{3}|W\d{3}"
        r"|trailing whitespace|line too long"
        r"|CS8600|nullable"                              # C# nullable
        r"|clippy|warning\[.*\]"                         # Rust clippy
        r"|golint|staticcheck|go vet"                    # Go lint
        r"|rubocop|standardrb"                           # Ruby
        r"|phpcs|psalm|phpstan"                          # PHP
        r"|credo|dialyzer"                               # Elixir
        r"|hlint"                                        # Haskell
        r"|dart analyze|analysis_options"                 # Dart
        r"|checkstyle|spotbugs|PMD"                      # Java
        r"|ktlint|detekt"                                # Kotlin
    , re.I), "LINTING"),

    # ── Logic / assertion failures (broadest — last) ──
    (re.compile(
        r"AssertionError|assert\s|Expected.*received|to equal|toBe|not equal"
        r"|Assert\.Equal|Assert\.True|Xunit|NUnit|MSTest"   # .NET
        r"|FAIL.*Test|test.*failed"                          # generic
        r"|panicked at|assertion failed"                     # Rust
        r"|FAIL:.*Test|--- FAIL:"                            # Go
        r"|Failure/Error:|expected.*to\b|RSpec"              # Ruby
        r"|PHPUnit.*Failed|Failed asserting"                 # PHP
        r"|Assertion.*failed|ExUnit"                         # Elixir
        r"|assertEqual|assertRaises"                         # Python unittest
    , re.I), "LOGIC"),
]


def _classify_bug_type(error_msg: str) -> BugType:
    """Match error message against known patterns."""
    for pattern, bug_type in _BUG_PATTERNS:
        if pattern.search(error_msg):
            return bug_type
    return "LOGIC"  # default fallback


def _parse_pytest_output(output: str, repo_dir: str) -> list[TestFailure]:
    """Extract failures from pytest output."""
    failures: list[TestFailure] = []

    # Split output into sections per failure
    sections = re.split(r"_{10,}\s+", output)

    for section in sections:
        # Try to find FAILED lines
        m = _PYTEST_FAILURE_RE.search(section)
        if not m:
            continue

        file_path = m.group(1)
        test_name = m.group(2)
        error_msg = m.group(3) or section[:500]

        # Try to extract line number
        line_match = _FILE_LINE_RE.search(section)
        line_number = int(line_match.group(2)) if line_match else 1

        bug_type = _classify_bug_type(error_msg)

        failures.append(
            TestFailure(
                file_path=file_path,
                test_name=test_name,
                line_number=line_number,
                error_message=error_msg.strip()[:500],
                bug_type=bug_type,
                raw_output=section[:1000],
            )
        )

    # If regex didn't catch structured failures, try line-by-line FAILED pattern
    if not failures:
        for line in output.splitlines():
            stripped = line.strip()
            if stripped.startswith("FAILED ") or stripped.startswith("ERROR "):
                parts = stripped.split(" ", 1)
                if len(parts) > 1:
                    loc = parts[1].split("::")
                    file_path = loc[0] if loc else "unknown"
                    test_name = loc[1] if len(loc) > 1 else "unknown"
                    error_msg = " ".join(loc[2:]) if len(loc) > 2 else stripped
                    failures.append(
                        TestFailure(
                            file_path=file_path,
                            test_name=test_name,
                            line_number=1,
                            error_message=error_msg[:500],
                            bug_type=_classify_bug_type(error_msg),
                            raw_output=stripped,
                        )
                    )

    return failures


def _parse_jest_output(output: str, repo_dir: str) -> list[TestFailure]:
    """Extract failures from Jest/Vitest output."""
    failures: list[TestFailure] = []

    # Look for "● suite › test" pattern
    blocks = re.split(r"●\s+", output)
    for block in blocks[1:]:  # skip first empty part
        lines = block.strip().splitlines()
        if not lines:
            continue

        header = lines[0]
        error_msg = "\n".join(lines[1:])[:500]

        # Try to find file reference
        file_match = re.search(r"at.*?[( ]([\w./\\]+):(\d+):\d+", block)
        file_path = file_match.group(1) if file_match else "unknown"
        line_number = int(file_match.group(2)) if file_match else 1

        parts = header.split(" › ")
        test_name = parts[-1].strip() if parts else header

        failures.append(
            TestFailure(
                file_path=file_path,
                test_name=test_name,
                line_number=line_number,
                error_message=error_msg.strip()[:500],
                bug_type=_classify_bug_type(error_msg),
                raw_output=block[:1000],
            )
        )

    return failures


def _parse_dotnet_output(output: str, repo_dir: str) -> list[TestFailure]:
    """Extract failures from `dotnet test` output.

    Typical lines:
      Failed MethodName [12 ms]
        Error Message:
           Assert.Equal() Failure ...
        Stack Trace:
           at Namespace.Class.Method() in /path/File.cs:line 42
    """
    failures: list[TestFailure] = []

    # Split on "Failed " lines to get blocks per failure
    # Pattern: "  Failed TestName [123 ms]"
    failed_re = re.compile(r"^\s*Failed\s+(\S+)\s*(?:\[.*\])?\s*$", re.MULTILINE)

    positions = [(m.start(), m.group(1)) for m in failed_re.finditer(output)]
    for i, (start, test_name) in enumerate(positions):
        end = positions[i + 1][0] if i + 1 < len(positions) else len(output)
        block = output[start:end]

        # Extract error message (after "Error Message:" line)
        error_msg = ""
        msg_match = re.search(r"Error Message:\s*\n\s*(.+?)(?:\n\s*Stack Trace:|\Z)", block, re.DOTALL)
        if msg_match:
            error_msg = msg_match.group(1).strip()[:500]

        # Extract file path and line number from stack trace
        file_path = "unknown"
        line_number = 1
        stack_match = re.search(r"in\s+(.+?):line\s+(\d+)", block)
        if stack_match:
            file_path = stack_match.group(1).strip()
            line_number = int(stack_match.group(2))
        else:
            # Try C# compiler error format: File.cs(42,10)
            cs_match = re.search(r"([\w/.\\]+\.cs)\((\d+),\d+\)", block)
            if cs_match:
                file_path = cs_match.group(1)
                line_number = int(cs_match.group(2))

        if not error_msg:
            error_msg = block.strip()[:500]

        failures.append(
            TestFailure(
                file_path=file_path,
                test_name=test_name,
                line_number=line_number,
                error_message=error_msg,
                bug_type=_classify_bug_type(error_msg),
                raw_output=block[:1000],
            )
        )

    # Also catch MSBuild/compiler errors: "error CS1002: ; expected"
    if not failures:
        cs_error_re = re.compile(
            r"([\w/.\\]+\.cs)\((\d+),\d+\):\s*error\s+(CS\d+):\s*(.+)",
        )
        for m in cs_error_re.finditer(output):
            failures.append(
                TestFailure(
                    file_path=m.group(1),
                    test_name=f"Build error {m.group(3)}",
                    line_number=int(m.group(2)),
                    error_message=m.group(4).strip()[:500],
                    bug_type="SYNTAX",
                    raw_output=m.group(0),
                )
            )

    return failures


def _parse_go_output(output: str, repo_dir: str) -> list[TestFailure]:
    """Extract failures from `go test -v` output.

    Typical pattern:
        --- FAIL: TestName (0.00s)
            file_test.go:42: expected X, got Y
    """
    failures: list[TestFailure] = []
    fail_re = re.compile(r"---\s*FAIL:\s+(\S+)\s*\(", re.MULTILINE)

    positions = [(m.start(), m.group(1)) for m in fail_re.finditer(output)]
    for i, (start, test_name) in enumerate(positions):
        end = positions[i + 1][0] if i + 1 < len(positions) else min(start + 2000, len(output))
        block = output[start:end]

        # Extract file:line from indented lines
        loc_match = re.search(r"(\S+\.go):(\d+):\s*(.+)", block)
        file_path = loc_match.group(1) if loc_match else "unknown"
        line_number = int(loc_match.group(2)) if loc_match else 1
        error_msg = loc_match.group(3).strip() if loc_match else block.strip()[:500]

        failures.append(
            TestFailure(
                file_path=file_path,
                test_name=test_name,
                line_number=line_number,
                error_message=error_msg[:500],
                bug_type=_classify_bug_type(error_msg),
                raw_output=block[:1000],
            )
        )
    return failures


def _parse_rust_output(output: str, repo_dir: str) -> list[TestFailure]:
    """Extract failures from `cargo test` output.

    Typical pattern:
        ---- tests::test_name stdout ----
        thread 'tests::test_name' panicked at 'assertion failed...', src/lib.rs:42:5
        test tests::test_name ... FAILED
    """
    failures: list[TestFailure] = []
    fail_re = re.compile(r"test\s+([\w:]+)\s+\.\.\.\s+FAILED", re.MULTILINE)

    for m in fail_re.finditer(output):
        test_name = m.group(1)
        # Look backwards for the panic message
        block_start = max(0, m.start() - 2000)
        block = output[block_start:m.end()]

        panic_match = re.search(
            r"panicked at '([^']+)',\s*([\w/.]+):(\d+):\d+", block
        )
        if panic_match:
            error_msg = panic_match.group(1)
            file_path = panic_match.group(2)
            line_number = int(panic_match.group(3))
        else:
            error_msg = f"Test {test_name} failed"
            file_path = "unknown"
            line_number = 1

        failures.append(
            TestFailure(
                file_path=file_path,
                test_name=test_name,
                line_number=line_number,
                error_message=error_msg[:500],
                bug_type=_classify_bug_type(error_msg),
                raw_output=block[-1000:],
            )
        )
    return failures


def _parse_generic_output(output: str, repo_dir: str) -> list[TestFailure]:
    """Best-effort parser for Java/Ruby/PHP/Elixir/any framework.

    Looks for common failure indicators and file:line patterns.
    """
    failures: list[TestFailure] = []
    seen: set[str] = set()

    # Generic patterns: "FAIL", "FAILED", "Error", "Failure" lines
    fail_line_re = re.compile(
        r"(?:FAIL(?:ED)?|Error|Failure|FAILURE)[:\s]+(.+)", re.MULTILINE
    )
    # file:line patterns across languages
    loc_re = re.compile(
        r"([\w/.\\-]+\.(?:java|kt|scala|rb|php|ex|exs|hs|lua|R|pl|jl|groovy|swift|dart|c|cpp|cc|rs|go|py|js|ts))"
        r"[:\(](\d+)"
    )

    for fm in fail_line_re.finditer(output):
        msg = fm.group(1).strip()[:500]
        key = msg[:80]
        if key in seen:
            continue
        seen.add(key)

        # Try to find a file:line near this failure
        context = output[max(0, fm.start() - 500):fm.end() + 500]
        loc_match = loc_re.search(context)
        file_path = loc_match.group(1) if loc_match else "unknown"
        line_number = int(loc_match.group(2)) if loc_match else 1

        failures.append(
            TestFailure(
                file_path=file_path,
                test_name=msg[:80],
                line_number=line_number,
                error_message=msg,
                bug_type=_classify_bug_type(msg),
                raw_output=context[:1000],
            )
        )

    return failures


async def _llm_classify_failures(output: str) -> list[TestFailure]:
    """Use LLM as fallback to extract and classify failures."""
    if not has_llm_keys():
        logger.warning("No LLM keys configured — cannot use LLM fallback")
        return []

    from langchain_core.messages import HumanMessage, SystemMessage

    llm = get_llm(temperature=0.0)

    prompt = f"""Analyze this test output and extract each failure as JSON.
For each failure return:
- file_path: string
- test_name: string
- line_number: int
- error_message: string (brief)
- bug_type: one of LINTING, SYNTAX, LOGIC, TYPE_ERROR, IMPORT, INDENTATION

Return ONLY a JSON array. No markdown, no explanation.

Test output:
```
{output[:4000]}
```"""

    import json
    try:
        resp = await llm.ainvoke([
            SystemMessage(content="You are a test output parser. Return valid JSON only."),
            HumanMessage(content=prompt),
        ])
        raw = str(resp.content).strip()
        # Strip markdown fences if present
        if raw.startswith("```"):
            lines_out = raw.splitlines()
            if lines_out[0].startswith("```"):
                lines_out = lines_out[1:]
            if lines_out and lines_out[-1].strip() == "```":
                lines_out = lines_out[:-1]
            raw = "\n".join(lines_out)
        items = json.loads(raw)
        if not isinstance(items, list):
            items = [items]
        return [
            TestFailure(
                file_path=str(item.get("file_path") or "unknown"),
                test_name=str(item.get("test_name") or "unknown"),
                line_number=int(item.get("line_number") or 1),
                error_message=str(item.get("error_message") or "unknown error"),
                bug_type=_sanitize_bug_type(item.get("bug_type")),
                raw_output="",
            )
            for item in items
        ]
    except Exception as exc:
        logger.warning("LLM failure-classification fallback failed: %s", exc)
        return []


def _guess_config_file(repo_dir: str, framework: str) -> str:
    """Guess the most likely config file to fix based on the framework."""
    p = Path(repo_dir)
    _CANDIDATES = [
        "package.json",
        "pyproject.toml",
        "setup.py",
        "pom.xml",
        "build.gradle",
        "Cargo.toml",
        "go.mod",
        "Gemfile",
        "composer.json",
        "mix.exs",
        "pubspec.yaml",
    ]
    for c in _CANDIDATES:
        if (p / c).exists():
            return c
    return "package.json"  # fallback


async def _llm_analyze_repo_failures(
    test_output: str, repo_dir: str, framework: str,
) -> list[TestFailure]:
    """Use LLM to analyze the repo itself when tests couldn't even run.

    Instead of parsing test output (which is just a config error), this
    scans the repo and asks the LLM to identify what files need fixing.
    """
    if not has_llm_keys():
        return []

    import json as _json
    from langchain_core.messages import HumanMessage, SystemMessage

    llm = get_llm(temperature=0.0)

    # Gather repo context
    p = Path(repo_dir)
    file_list: list[str] = []
    for f in sorted(p.rglob("*")):
        rel = str(f.relative_to(p))
        if f.is_file() and not any(skip in rel for skip in [
            "node_modules", ".git", "__pycache__", ".tox", "venv",
            "dist/", "build/", ".next",
        ]):
            file_list.append(rel)

    # Read key config files
    config_contents: dict[str, str] = {}
    for fname in ["package.json", "pyproject.toml", "pom.xml",
                   "build.gradle", "Cargo.toml", "go.mod", "Gemfile",
                   "composer.json", "tsconfig.json"]:
        cfg = p / fname
        if cfg.exists():
            try:
                config_contents[fname] = cfg.read_text("utf-8")[:2000]
            except Exception:
                pass

    # Also read a few source files to understand the project
    source_snippets: dict[str, str] = {}
    for f in file_list[:15]:
        fp = p / f
        if fp.suffix in (".js", ".ts", ".py", ".java", ".cs", ".go", ".rb", ".php", ".rs"):
            try:
                source_snippets[f] = fp.read_text("utf-8")[:1500]
            except Exception:
                pass

    prompt = f"""The test runner for this {framework} project failed with a config error:

**Test output**: {test_output.strip()}

**File listing**: {chr(10).join(file_list[:60])}

**Config files**:
{chr(10).join(f'--- {k} ---{chr(10)}{v}' for k, v in config_contents.items())}

**Source files**:
{chr(10).join(f'--- {k} ---{chr(10)}{v}' for k, v in list(source_snippets.items())[:5])}

Analyze the project and identify REAL bugs or misconfigurations in actual source/config files.
For each issue return:
- file_path: the actual file that needs to be fixed (must be a real file from the listing)
- test_name: a descriptive name for the issue
- line_number: approximate line number
- error_message: what's wrong and how to fix it
- bug_type: one of LINTING, SYNTAX, LOGIC, TYPE_ERROR, IMPORT, INDENTATION

Return ONLY a JSON array. No markdown, no explanation.
If the project has real bugs in source files, identify those.
If the issue is purely a missing test script, return a single item pointing at the config file (e.g. package.json)."""

    try:
        resp = await llm.ainvoke([
            SystemMessage(content="You are a senior code reviewer. Identify real bugs in real files. Return valid JSON only."),
            HumanMessage(content=prompt),
        ])

        raw = str(resp.content).strip()
        # Strip markdown fences
        if raw.startswith("```"):
            lines = raw.splitlines()
            if lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            raw = "\n".join(lines)

        items = _json.loads(raw)
        return [
            TestFailure(
                file_path=str(item.get("file_path") or _guess_config_file(repo_dir, framework)),
                test_name=str(item.get("test_name") or "config_issue"),
                line_number=int(item.get("line_number") or 1),
                error_message=str(item.get("error_message") or "Configuration error"),
                bug_type=_sanitize_bug_type(item.get("bug_type")),
                raw_output=test_output[:500],
            )
            for item in items
            if isinstance(item, dict)
        ]
    except Exception:
        logger.exception("LLM repo analysis failed")
        return []


async def ast_analyzer(state: AgentState) -> AgentState:
    """
    Parse test output and classify each failure.
    Rule-based first, LLM fallback if empty.
    """
    run_id = state["run_id"]
    test_output = state.get("test_output", "")
    test_exit_code = state.get("test_exit_code", 0)
    framework = state.get("framework", "pytest")
    repo_dir = state.get("repo_dir", "")
    iteration = state.get("iteration", 1)
    step = iteration * 10 + 4

    await emit_thought(run_id, "ast_analyzer", "Analyzing test failures…", step)

    # If tests passed, no failures to analyze
    if test_exit_code == 0:
        await emit_thought(run_id, "ast_analyzer", "All tests passed ✓", step + 1)
        return {
            "failures": [],
            "current_node": "ast_analyzer",
        }

    # ── Early detection of config / env-level errors (not real test failures) ──
    # These are cases where the test runner itself couldn't run, not
    # where tests ran and found bugs.  Send them straight to LLM with
    # repo context so it can identify the *actual* source file to fix.
    _CONFIG_ERROR_MARKERS = [
        "no test specified",
        "Error: no test specified",
        "missing script: test",
        'missing script: "test"',
        "missing script 'test'",
        "command not found",
        "ERROR: Test command not found",
        "Test execution timed out",
        "npm ERR! missing script",
        "npm error missing script",
        "Cannot find module",
        "Could not locate a valid entry",
    ]
    output_lower = test_output.lower()
    missing_test_script = bool(
        re.search(r"missing script:\s*[\"']?test[\"']?", test_output, re.I)
        or "no test specified" in output_lower
    )
    is_config_error = (
        any(marker.lower() in output_lower for marker in _CONFIG_ERROR_MARKERS)
        or missing_test_script
    )

    if is_config_error:
        await emit_thought(
            run_id, "ast_analyzer",
            "Detected config/environment error (not a test failure) — analyzing config…",
            step + 1,
        )
        # Deterministic handling for common npm config failure.
        pkg_path = Path(repo_dir) / "package.json"
        if missing_test_script and pkg_path.exists():
            failures = [
                TestFailure(
                    file_path="package.json",
                    test_name="missing_test_script",
                    line_number=1,
                    error_message=test_output.strip()[:500],
                    bug_type="SYNTAX",
                    raw_output=test_output[:1000],
                )
            ]
        else:
            failures = await _llm_analyze_repo_failures(test_output, repo_dir, framework)
            if not failures:
                # Produce a single meaningful failure pointing at likely config file
                config_file = _guess_config_file(repo_dir, framework)
                failures = [
                    TestFailure(
                        file_path=config_file,
                        test_name="test_configuration",
                        line_number=1,
                        error_message=test_output.strip()[:500],
                        bug_type="SYNTAX",
                        raw_output=test_output[:1000],
                    )
                ]
    else:
        # ── Normal flow: rule-based parsing by framework ──
        _JEST_LIKE = {"jest", "vitest", "ava", "jasmine", "hardhat", "truffle"}
        _DOTNET_LIKE = {"dotnet-test"}
        _GO_LIKE = {"go-test"}
        _RUST_LIKE = {"cargo-test"}
        _PYTEST_LIKE = {"pytest"}

        if framework in _JEST_LIKE:
            failures = _parse_jest_output(test_output, repo_dir)
        elif framework in _DOTNET_LIKE:
            failures = _parse_dotnet_output(test_output, repo_dir)
        elif framework in _GO_LIKE:
            failures = _parse_go_output(test_output, repo_dir)
        elif framework in _RUST_LIKE:
            failures = _parse_rust_output(test_output, repo_dir)
        elif framework in _PYTEST_LIKE:
            failures = _parse_pytest_output(test_output, repo_dir)
        else:
            failures = _parse_generic_output(test_output, repo_dir)

        # LLM fallback if rule-based found nothing
        if not failures and test_exit_code != 0:
            await emit_thought(
                run_id, "ast_analyzer",
                "Rule-based parsing found no structured failures — trying LLM fallback…",
                step + 1,
            )
            failures = await _llm_classify_failures(test_output)

    # Ensure we cover all 6 required bug types for demo if we have failures
    seen_types = {f.bug_type for f in failures}
    logger.info(
        "ast_analyzer run=%s found %d failures, types=%s",
        run_id, len(failures), seen_types,
    )

    await emit_thought(
        run_id,
        "ast_analyzer",
        f"Found {len(failures)} failure(s): {', '.join(seen_types) if seen_types else 'none'}",
        step + 2,
    )

    await insert_trace(
        run_id,
        step_index=step,
        agent_node="ast_analyzer",
        action_type="analysis",
        action_label=f"Classified {len(failures)} failures",
        payload={
            "failure_count": len(failures),
            "bug_types": list(seen_types),
        },
    )

    return {
        "failures": failures,
        "current_node": "ast_analyzer",
    }
