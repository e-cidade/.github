#!/usr/bin/env python3
"""Render the organization-owned administrative layer for an e-Cidade mirror."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import sys
from typing import Any

from mirror_config import ConfigError, find_mirror, load_config

BEGIN = "<!-- ecidade-mirror:begin -->"
END = "<!-- ecidade-mirror:end -->"


class RenderError(ValueError):
    pass


def render_template(text: str, mirror: dict[str, Any]) -> str:
    values = {
        "id": mirror["id"],
        "display_name": mirror["display_name"],
        "source": mirror["source"],
        "destination": mirror["destination"],
        "destination_branch": mirror["destination_branch"],
    }
    rendered = text
    for key, value in values.items():
        rendered = rendered.replace("{{" + key + "}}", str(value))

    unknown = sorted(set(re.findall(r"\{\{([a-zA-Z0-9_-]+)\}\}", rendered)))
    if unknown:
        raise RenderError("unknown template variables: " + ", ".join(unknown))
    return rendered


def replace_banner(readme: str, banner: str) -> str:
    """Place one managed banner before the current upstream README.

    Existing managed banners are replaced in place. Content outside the managed
    marker remains untouched.
    """
    if BEGIN not in banner or END not in banner:
        raise RenderError("README banner template must contain managed markers")

    begin_count = readme.count(BEGIN)
    end_count = readme.count(END)
    if begin_count != end_count:
        raise RenderError("README contains incomplete e-Cidade mirror marker")
    if begin_count > 1:
        raise RenderError("README contains multiple e-Cidade mirror banners")

    clean_banner = banner.strip()
    if begin_count == 1:
        start = readme.index(BEGIN)
        stop = readme.index(END, start) + len(END)
        prefix = readme[:start].rstrip()
        suffix = readme[stop:].lstrip()
        parts = [part for part in (prefix, clean_banner, suffix) if part]
        return "\n\n".join(parts).rstrip() + "\n"

    if not readme.strip():
        return clean_banner + "\n"
    return clean_banner + "\n\n" + readme.lstrip()


def write_if_changed(path: Path, content: str) -> bool:
    content = content.rstrip() + "\n"
    if path.exists() and path.read_text(encoding="utf-8") == content:
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return True


def render_layer(
    config_path: Path,
    mirror_id: str,
    target: Path,
    templates: Path,
) -> list[str]:
    data = load_config(config_path)
    mirror = find_mirror(data, mirror_id)
    changed: list[str] = []

    banner_template = (templates / "README_BANNER.md.tpl").read_text(encoding="utf-8")
    contributing_template = (templates / "CONTRIBUTING.md.tpl").read_text(
        encoding="utf-8"
    )
    pr_template = (templates / "PULL_REQUEST_TEMPLATE.md.tpl").read_text(
        encoding="utf-8"
    )

    readme_path = target / "README.md"
    upstream_readme = (
        readme_path.read_text(encoding="utf-8") if readme_path.exists() else ""
    )
    banner = render_template(banner_template, mirror)
    if write_if_changed(readme_path, replace_banner(upstream_readme, banner)):
        changed.append("README.md")

    if write_if_changed(
        target / "CONTRIBUTING.md",
        render_template(contributing_template, mirror),
    ):
        changed.append("CONTRIBUTING.md")

    if write_if_changed(
        target / ".github" / "PULL_REQUEST_TEMPLATE.md",
        render_template(pr_template, mirror),
    ):
        changed.append(".github/PULL_REQUEST_TEMPLATE.md")

    marker = {
        "schema": 1,
        "mirror": mirror["id"],
        "source": mirror["source"],
        "destination": mirror["destination"],
        "managed_by": "e-cidade/.github",
    }
    marker_content = json.dumps(marker, indent=2, sort_keys=True) + "\n"
    marker_path = target / ".github" / "ecidade-mirror.json"
    if not marker_path.exists() or marker_path.read_text(encoding="utf-8") != marker_content:
        marker_path.parent.mkdir(parents=True, exist_ok=True)
        marker_path.write_text(marker_content, encoding="utf-8")
        changed.append(".github/ecidade-mirror.json")

    return changed


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("mirror", help="mirror id from mirrors/mirrors.json")
    parser.add_argument("target", help="checked-out mirror repository")
    parser.add_argument(
        "--config",
        default="mirrors/mirrors.json",
        help="mirror catalog path",
    )
    parser.add_argument(
        "--templates",
        default="mirrors/templates",
        help="administrative layer templates",
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        changed = render_layer(
            Path(args.config),
            args.mirror,
            Path(args.target),
            Path(args.templates),
        )
    except (ConfigError, RenderError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    if changed:
        print("updated:")
        for path in changed:
            print(f"- {path}")
    else:
        print("administrative layer already up to date")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
