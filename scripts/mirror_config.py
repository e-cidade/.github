#!/usr/bin/env python3
"""Validate and query the declarative e-Cidade mirror catalog."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import sys
from typing import Any

REPOSITORY_RE = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")


class ConfigError(ValueError):
    pass


def load_config(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ConfigError(f"unable to load {path}: {exc}") from exc

    mirrors = data.get("mirrors")
    if not isinstance(mirrors, list):
        raise ConfigError("'mirrors' must be an array")

    seen_ids: set[str] = set()
    seen_destinations: set[str] = set()

    for index, mirror in enumerate(mirrors):
        if not isinstance(mirror, dict):
            raise ConfigError(f"mirror #{index + 1} must be an object")

        required = (
            "id",
            "display_name",
            "source",
            "destination",
            "destination_branch",
            "strip_upstream_workflows",
        )
        missing = [key for key in required if key not in mirror]
        if missing:
            raise ConfigError(
                f"mirror #{index + 1} missing required keys: {', '.join(missing)}"
            )

        mirror_id = mirror["id"]
        source = mirror["source"]
        destination = mirror["destination"]

        if not isinstance(mirror_id, str) or not ID_RE.fullmatch(mirror_id):
            raise ConfigError(f"invalid mirror id: {mirror_id!r}")
        if mirror_id in seen_ids:
            raise ConfigError(f"duplicate mirror id: {mirror_id}")

        for key, value in (("source", source), ("destination", destination)):
            if not isinstance(value, str) or not REPOSITORY_RE.fullmatch(value):
                raise ConfigError(f"invalid {key}: {value!r}")

        if source == destination:
            raise ConfigError(f"mirror {mirror_id}: source and destination must differ")
        if not destination.startswith("e-cidade/"):
            raise ConfigError(
                f"mirror {mirror_id}: destination must belong to e-cidade organization"
            )
        if destination in seen_destinations:
            raise ConfigError(f"duplicate mirror destination: {destination}")

        if not isinstance(mirror["destination_branch"], str) or not mirror[
            "destination_branch"
        ]:
            raise ConfigError(
                f"mirror {mirror_id}: destination_branch must be a non-empty string"
            )
        if not isinstance(mirror["strip_upstream_workflows"], bool):
            raise ConfigError(
                f"mirror {mirror_id}: strip_upstream_workflows must be boolean"
            )

        seen_ids.add(mirror_id)
        seen_destinations.add(destination)

    return data


def find_mirror(data: dict[str, Any], mirror_id: str) -> dict[str, Any]:
    for mirror in data["mirrors"]:
        if mirror["id"] == mirror_id:
            return mirror
    raise ConfigError(f"unknown mirror id: {mirror_id}")


def cmd_validate(args: argparse.Namespace) -> int:
    data = load_config(Path(args.config))
    print(f"validated {len(data['mirrors'])} mirror(s)")
    return 0


def cmd_get(args: argparse.Namespace) -> int:
    data = load_config(Path(args.config))
    mirror = find_mirror(data, args.mirror)
    if args.field:
        value = mirror.get(args.field)
        if value is None:
            raise ConfigError(f"unknown field: {args.field}")
        if isinstance(value, bool):
            print("true" if value else "false")
        elif isinstance(value, (dict, list)):
            print(json.dumps(value, separators=(",", ":")))
        else:
            print(value)
    else:
        print(json.dumps(mirror, separators=(",", ":"), sort_keys=True))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--config",
        default="mirrors/mirrors.json",
        help="path to mirror catalog",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    validate = sub.add_parser("validate")
    validate.set_defaults(func=cmd_validate)

    get = sub.add_parser("get")
    get.add_argument("mirror")
    get.add_argument("--field")
    get.set_defaults(func=cmd_get)
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    try:
        return args.func(args)
    except ConfigError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
