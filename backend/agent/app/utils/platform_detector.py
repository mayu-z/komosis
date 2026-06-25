"""
Platform detection utility for CI/CD generation.

Scans a cloned repository for deployment platform signals before the LLM
generates any YAML, so the CD section is accurate rather than generic.

Platforms detected: vercel, railway, fly, render, aws, netlify, heroku.
Falls back to None when no platform can be inferred.
"""
from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger("komosis.utils.platform_detector")


@dataclass
class PlatformHints:
    """Results of a platform detection scan."""
    platform: str | None                        # canonical platform name or None
    has_dockerfile: bool = False
    has_docker_compose: bool = False
    deploy_hints: dict = field(default_factory=dict)  # extra context for LLM prompt


def _read_json_safe(path: Path) -> dict:
    """Read and parse a JSON file; return empty dict on any error."""
    try:
        return json.loads(path.read_text(encoding="utf-8", errors="replace"))
    except Exception:
        return {}


def _read_text_safe(path: Path, max_chars: int = 500) -> str:
    """Read a text file; return empty string on any error."""
    try:
        return path.read_text(encoding="utf-8", errors="replace")[:max_chars]
    except Exception:
        return ""


def detect_platform(workspace_dir: str) -> PlatformHints:
    """
    Scan a repository for deployment platform signals.

    Detection is intentionally ordered from most-specific to least-specific.
    Stops at the first confident match so we don't mix signals from multiple
    platforms in a monorepo.

    Returns a PlatformHints instance ready to pass to prompt templates.
    """
    root = Path(workspace_dir)
    hints = PlatformHints(platform=None)

    # ── Docker ───────────────────────────────────────────────────────────────
    hints.has_dockerfile = (root / "Dockerfile").exists()
    hints.has_docker_compose = (
        (root / "docker-compose.yml").exists()
        or (root / "docker-compose.yaml").exists()
    )

    # ── Vercel ───────────────────────────────────────────────────────────────
    if (root / "vercel.json").exists():
        hints.platform = "vercel"
        cfg = _read_json_safe(root / "vercel.json")
        if cfg:
            hints.deploy_hints["vercel_config"] = cfg
        logger.info("Platform detected: vercel (vercel.json)")
        return hints

    # ── Railway ──────────────────────────────────────────────────────────────
    if (root / "railway.json").exists() or (root / "railway.toml").exists():
        hints.platform = "railway"
        logger.info("Platform detected: railway")
        return hints

    # ── Fly.io ───────────────────────────────────────────────────────────────
    if (root / "fly.toml").exists():
        hints.platform = "fly"
        hints.deploy_hints["fly_config"] = _read_text_safe(root / "fly.toml")
        logger.info("Platform detected: fly")
        return hints

    # ── Render ───────────────────────────────────────────────────────────────
    if (root / "render.yaml").exists() or (root / "render.yml").exists():
        hints.platform = "render"
        logger.info("Platform detected: render")
        return hints

    # ── Netlify ──────────────────────────────────────────────────────────────
    if (root / "netlify.toml").exists() or (root / "_redirects").exists():
        hints.platform = "netlify"
        hints.deploy_hints["netlify_config"] = _read_text_safe(root / "netlify.toml")
        logger.info("Platform detected: netlify")
        return hints

    # ── Heroku ───────────────────────────────────────────────────────────────
    if (root / "Procfile").exists():
        hints.platform = "heroku"
        hints.deploy_hints["procfile"] = _read_text_safe(root / "Procfile")
        logger.info("Platform detected: heroku (Procfile)")
        return hints

    # ── AWS (CDK / SAM / Elastic Beanstalk / CodeDeploy) ─────────────────────
    _AWS_SIGNALS: list[tuple[str, str]] = [
        ("cdk.json",                       "CDK"),
        ("samconfig.toml",                 "SAM"),
        ("template.yaml",                  "SAM/CloudFormation"),
        (".elasticbeanstalk/config.yml",   "Elastic Beanstalk"),
        ("appspec.yml",                    "CodeDeploy"),
    ]
    for rel_path, aws_kind in _AWS_SIGNALS:
        if (root / rel_path).exists():
            hints.platform = "aws"
            hints.deploy_hints["aws_tool"] = aws_kind
            hints.deploy_hints["aws_config_file"] = rel_path
            logger.info("Platform detected: aws (%s)", aws_kind)
            return hints

    # ── Infer from package.json deploy scripts ───────────────────────────────
    pkg_path = root / "package.json"
    if pkg_path.exists():
        pkg = _read_json_safe(pkg_path)
        scripts: dict = pkg.get("scripts", {})
        deploy_script = str(scripts.get("deploy", "")).lower()

        _SCRIPT_SIGNALS: list[tuple[str, str]] = [
            ("vercel",   "vercel"),
            ("railway",  "railway"),
            ("fly",      "fly"),
            ("netlify",  "netlify"),
            ("heroku",   "heroku"),
        ]
        for keyword, platform in _SCRIPT_SIGNALS:
            if keyword in deploy_script:
                hints.platform = platform
                hints.deploy_hints["deploy_script"] = deploy_script
                logger.info("Platform inferred from package.json deploy script: %s", platform)
                return hints

    logger.info(
        "No deployment platform detected (dockerfile=%s, compose=%s)",
        hints.has_dockerfile,
        hints.has_docker_compose,
    )
    return hints
