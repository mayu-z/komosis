"""
Prompt templates and helper functions for CI/CD and test generation.

All prompts are structured to:
  1. Request ONLY raw YAML/code with no markdown fences or explanation.
  2. Use pinned action versions, never @latest.
  3. Reference GitHub Secrets by name so no credentials appear in YAML.

Separate system and user message content is passed to the LLM to make
the role split explicit — system = behavioural constraint, user = context.
"""
from __future__ import annotations

# ── CI/CD system role ─────────────────────────────────────────────────────────

CICD_SYSTEM = (
    "You are a senior DevOps engineer writing production-grade GitHub Actions "
    "pipelines. Respond with ONLY the raw YAML file content — no markdown "
    "fences, no code blocks, no explanations, no preamble or postamble. "
    "The first character of your response must be 'n' (start of 'name:')."
)

# ── CI-only template (no CD section) ─────────────────────────────────────────

CI_ONLY_PROMPT = """\
Generate a production-grade GitHub Actions CI pipeline for this repository.

Repository details:
  Language       : {language}
  Test framework : {framework}
  Test command   : {test_command}
  Has Dockerfile : {has_dockerfile}

Requirements:
1. name: "CI"
2. Trigger on push AND pull_request targeting branches: [main, master].
3. Single job "test" running on ubuntu-latest.
4. Steps — in order:
     a. actions/checkout@v4
     b. Language-specific setup action (pinned version, not @latest).
     c. Dependency caching (use actions/cache@v4 with the correct key).
     d. Install dependencies.
     e. Lint (if a linter is conventional for this language/framework).
     f. Run tests: {test_command}
     g. Build artifact (if applicable for this language/framework).
     h. If Has Dockerfile is true: docker build (no push) as a sanity check.
5. Pin every action version (e.g. actions/checkout@v4, NOT @latest).
6. Use the correct package manager for the detected language.

Output ONLY the YAML. First line must be "name: CI".
"""

# ── CI + CD template (platform detected) ─────────────────────────────────────

CI_WITH_CD_PROMPT = """\
Generate a production-grade GitHub Actions CI/CD pipeline for this repository.

Repository details:
  Language           : {language}
  Test framework     : {framework}
  Test command       : {test_command}
  Has Dockerfile     : {has_dockerfile}
  Deployment platform: {platform}
  Platform config    : {platform_hints}

Requirements:
1. name: "CI/CD"
2. Trigger on push AND pull_request targeting branches: [main, master].
3. Two jobs:
     a. "ci" — runs on every event (test + build)
     b. "deploy" — needs: [ci], runs ONLY on push to main or master
4. "ci" job steps:
     a. actions/checkout@v4
     b. Language-specific setup action (pinned version).
     c. Dependency caching (actions/cache@v4).
     d. Install dependencies.
     e. Lint if applicable.
     f. Run tests: {test_command}
     g. Build if applicable.
5. "deploy" job — use the EXACT action versions listed below for {platform}:
{platform_guidance}
6. ALL credentials in the "deploy" job MUST come from GitHub Secrets
   (e.g. ${{{{ secrets.VERCEL_TOKEN }}}}).  Never hardcode any value.
7. Pin every action version.

Output ONLY the YAML. First line must be "name: CI/CD".
"""

# Platform-specific deploy job guidance inserted into CI_WITH_CD_PROMPT
_PLATFORM_GUIDANCE: dict[str, str] = {
    "vercel": """\
     Use: amondnet/vercel-action@v25
     Required secrets: VERCEL_TOKEN, VERCEL_ORG_ID, VERCEL_PROJECT_ID
     Set vercel-args: '--prod' for production deployments.""",

    "railway": """\
     Use: bervProject/railway-github-action@v1.1
     Required secrets: RAILWAY_TOKEN
     Set service: set to your Railway service name.""",

    "fly": """\
     Use: superfly/flyctl-actions/setup-flyctl@master then run: flyctl deploy --remote-only
     Required secrets: FLY_API_TOKEN""",

    "render": """\
     Use: johnbeynon/render-deploy-action@v0.0.8
     Required secrets: RENDER_SERVICE_ID, RENDER_API_KEY""",

    "netlify": """\
     Use: nwtgck/actions-netlify@v3.0 with publish-dir and production-branch: main
     Required secrets: NETLIFY_AUTH_TOKEN, NETLIFY_SITE_ID""",

    "heroku": """\
     Use: akhileshns/heroku-deploy@v3.13.15
     Required secrets: HEROKU_API_KEY, HEROKU_APP_NAME, HEROKU_EMAIL""",

    "aws": """\
     Use: aws-actions/configure-aws-credentials@v4 then the appropriate AWS deploy action.
     Required secrets: AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY, AWS_REGION
     Choose the correct deploy step: ECS (aws-actions/amazon-ecs-deploy-task-definition@v2),
     Elastic Beanstalk (einaregilsson/beanstalk-deploy@v21), or Lambda (aws-actions/aws-codedeploy-for-github-actions)
     depending on the platform config hints provided.""",
}

# ── CI + placeholder CD block (no platform detected) ─────────────────────────

CI_PLACEHOLDER_PROMPT = """\
Generate a GitHub Actions CI pipeline for this repository. No deployment
platform was detected, so include a clearly commented CD placeholder block.

Repository details:
  Language       : {language}
  Test framework : {framework}
  Test command   : {test_command}
  Has Dockerfile : {has_dockerfile}

Requirements:
1. name: "CI/CD"
2. Trigger on push AND pull_request targeting branches: [main, master].
3. Complete, working "ci" job — install, lint if applicable, test, build.
4. A "deploy" job skeleton after "ci" that looks like this EXACTLY:

  deploy:
    name: Deploy
    needs: [ci]
    runs-on: ubuntu-latest
    if: github.event_name == 'push' && (github.ref == 'refs/heads/main' || github.ref == 'refs/heads/master')
    steps:
      - uses: actions/checkout@v4
      # ─────────────────────────────────────────────────────────────────────
      # CD PLACEHOLDER — choose and uncomment your deployment platform
      # ─────────────────────────────────────────────────────────────────────
      #
      # VERCEL
      # - uses: amondnet/vercel-action@v25
      #   with:
      #     vercel-token: ${{{{ secrets.VERCEL_TOKEN }}}}
      #     vercel-org-id: ${{{{ secrets.VERCEL_ORG_ID }}}}
      #     vercel-project-id: ${{{{ secrets.VERCEL_PROJECT_ID }}}}
      #     vercel-args: '--prod'
      #
      # RAILWAY
      # - uses: bervProject/railway-github-action@v1.1
      #   with:
      #     railway-token: ${{{{ secrets.RAILWAY_TOKEN }}}}
      #
      # FLY.IO
      # - uses: superfly/flyctl-actions/setup-flyctl@master
      # - run: flyctl deploy --remote-only
      #   env:
      #     FLY_API_TOKEN: ${{{{ secrets.FLY_API_TOKEN }}}}
      #
      # RENDER
      # - uses: johnbeynon/render-deploy-action@v0.0.8
      #   with:
      #     service-id: ${{{{ secrets.RENDER_SERVICE_ID }}}}
      #     api-key: ${{{{ secrets.RENDER_API_KEY }}}}
      # ─────────────────────────────────────────────────────────────────────
      - run: echo "No deployment platform configured — add one above"

5. Pin every action version in the CI job.
6. Use the correct package manager and cache strategy for {language}.

Output ONLY the YAML. First line must be "name: CI/CD".
"""

# ── Test generation ───────────────────────────────────────────────────────────

TEST_GENERATION_SYSTEM = (
    "You are a senior software engineer writing clean, runnable unit tests. "
    "Respond with ONLY the raw test file content — no markdown fences, "
    "no code blocks, no explanations. The output is written directly to disk "
    "and must be valid, importable source code."
)

TEST_GENERATION_PROMPT = """\
Generate a test file for the following source code.

Language      : {language}
Test framework: {framework}
Source file   : {file_path}

Source code:
{source_code}

Requirements:
1. Write tests for EVERY public function or exported symbol in the file.
2. Cover at least: happy path + one edge case (empty input, None, boundary value).
3. Import the module correctly relative to the test file location shown above.
4. Do NOT test private/internal functions (prefixed with _ in Python, # private in Ruby etc.).
5. Every assertion must be meaningful — no `assert True` or bare `pass`.
6. Keep each test small and focused (one behaviour per test function/method).
7. Use {framework} idioms (e.g. pytest fixtures, jest describe/it blocks, etc.)
8. No mocking unless the function under test makes an I/O call that cannot
   be avoided (network, filesystem, database). Prefer pure function testing.
9. If the source has no testable public surface, generate one test that
   imports the module without error (smoke test).

Output ONLY the test file content. No markdown fences.
"""


# ── Framework/language helpers ────────────────────────────────────────────────

# Maps (language, framework) pairs to their test command.
# Framework names match what repo_scanner.py detects.
_TEST_COMMANDS: dict[tuple[str, str], str] = {
    ("python",     "pytest"):       "pytest --tb=short",
    ("python",     "unittest"):     "python -m unittest discover -s tests",
    ("javascript", "jest"):         "npm test",
    ("javascript", "vitest"):       "npx vitest run",
    ("javascript", "mocha"):        "npm test",
    ("javascript", "ava"):          "npm test",
    ("javascript", "jasmine"):      "npm test",
    ("typescript", "jest"):         "npm test",
    ("typescript", "vitest"):       "npx vitest run",
    ("typescript", "mocha"):        "npm test",
    ("go",         "go-test"):      "go test ./... -v",
    ("java",       "maven"):        "mvn test -B",
    ("java",       "gradle"):       "gradle test --info",
    ("ruby",       "rspec"):        "bundle exec rspec",
    ("ruby",       "minitest"):     "bundle exec rake test",
    ("rust",       "cargo-test"):   "cargo test",
    ("csharp",     "dotnet-test"):  "dotnet test --no-restore",
    ("php",        "phpunit"):      "vendor/bin/phpunit",
    ("elixir",     "mix-test"):     "mix test",
    ("swift",      "swift-test"):   "swift test",
    ("dart",       "dart-test"):    "dart test",
}

_DEFAULT_COMMANDS: dict[str, str] = {
    "python":     "pytest --tb=short",
    "javascript": "npm test",
    "typescript": "npm test",
    "go":         "go test ./...",
    "java":       "mvn test -B",
    "ruby":       "bundle exec rspec",
    "rust":       "cargo test",
    "csharp":     "dotnet test",
    "php":        "vendor/bin/phpunit",
    "elixir":     "mix test",
    "kotlin":     "gradle test",
}


def get_test_command(language: str, framework: str) -> str:
    """
    Return the correct test runner command for the detected language/framework.

    Falls back gracefully when the specific combination isn't in the map.
    """
    key = (language.lower(), framework.lower())
    if key in _TEST_COMMANDS:
        return _TEST_COMMANDS[key]
    lang = language.lower()
    return _DEFAULT_COMMANDS.get(lang, "npm test")


def get_platform_guidance(platform: str) -> str:
    """Return the platform-specific deploy job snippet for CI_WITH_CD_PROMPT."""
    return _PLATFORM_GUIDANCE.get(platform, f"     # Deploy to {platform} — consult your platform's documentation.")


# Maps language → default test framework when framework is not detected
_DEFAULT_FRAMEWORKS: dict[str, str] = {
    "python":     "pytest",
    "javascript": "jest",
    "typescript": "jest",
    "go":         "go-test",
    "java":       "maven",
    "ruby":       "rspec",
    "rust":       "cargo-test",
    "csharp":     "dotnet-test",
    "php":        "phpunit",
    "elixir":     "mix-test",
}


def default_framework(language: str) -> str:
    """Return the conventional test framework for a language."""
    return _DEFAULT_FRAMEWORKS.get(language.lower(), "jest")


# Maps (language, framework) → canonical test file extension/suffix
_TEST_FILE_PATTERNS: dict[str, dict] = {
    "python":     {"dir": "tests", "prefix": "test_",   "ext": ".py"},
    "javascript": {"dir": "",      "prefix": "",        "ext": ".test.js",   "alongside": True},
    "typescript": {"dir": "",      "prefix": "",        "ext": ".test.ts",   "alongside": True},
    "go":         {"dir": "",      "prefix": "",        "ext": "_test.go",   "alongside": True},
    "java":       {"dir": "src/test/java", "prefix": "", "suffix": "Test", "ext": ".java"},
    "ruby":       {"dir": "spec",  "prefix": "",        "ext": "_spec.rb"},
    "rust":       {"dir": "tests", "prefix": "",        "ext": ".rs"},
    "csharp":     {"dir": "Tests", "prefix": "",        "suffix": "Tests",   "ext": ".cs"},
    "php":        {"dir": "tests", "prefix": "",        "suffix": "Test",    "ext": ".php"},
    "elixir":     {"dir": "test",  "prefix": "",        "ext": "_test.exs"},
}


def get_test_file_path(source_path: str, language: str) -> str:
    """
    Derive the canonical test file path for a given source file.

    e.g.  app/utils.py  (python)  →  tests/test_utils.py
          src/index.ts  (ts)      →  src/index.test.ts
          main.go       (go)      →  main_test.go
    """
    import os
    base_no_ext = os.path.splitext(os.path.basename(source_path))[0]
    source_dir  = os.path.dirname(source_path)
    pattern     = _TEST_FILE_PATTERNS.get(language.lower(), {"dir": "tests", "prefix": "test_", "ext": ".py"})

    alongside = pattern.get("alongside", False)
    prefix    = pattern.get("prefix", "")
    suffix    = pattern.get("suffix", "")
    ext       = pattern.get("ext", ".py")
    test_dir  = pattern.get("dir", "tests")

    test_filename = f"{prefix}{base_no_ext}{suffix}{ext}"

    if alongside:
        # place test next to the source file
        return os.path.join(source_dir, test_filename) if source_dir else test_filename

    # place test in the designated test directory
    return os.path.join(test_dir, test_filename) if test_dir else test_filename
