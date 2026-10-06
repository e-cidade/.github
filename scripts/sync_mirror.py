#!/usr/bin/env python3
"""Synchronize one configured e-Cidade mirror.

The synchronizer keeps upstream Git history intact, publishes source branches
under upstream/*, renders the local administrative overlay, and opens the public
default branch through a normal Git history rather than a synthetic export.

Network mutations are opt-in through explicit commands. Configuration parsing
and state inspection are separated so they can be tested without GitHub.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from typing import Iterable

from mirror_config import ConfigError, find_mirror, load_config
from render_mirror import RenderError, render_layer


class SyncError(RuntimeError):
    pass


@dataclass(frozen=True)
class RemoteState:
    default_branch: str
    heads: dict[str, str]
    tags: dict[str, str]

    @property
    def fingerprint(self) -> str:
        payload = {
            "default_branch": self.default_branch,
            "heads": dict(sorted(self.heads.items())),
            "tags": dict(sorted(self.tags.items())),
        }
        encoded = json.dumps(payload, separators=(",", ":"), sort_keys=True)
        return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def run(
    args: list[str],
    *,
    cwd: Path | None = None,
    capture: bool = True,
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        args,
        cwd=cwd,
        text=True,
        capture_output=capture,
        env=env,
    )
    if result.returncode != 0:
        stderr = result.stderr.strip() if result.stderr else ""
        raise SyncError(f"command failed ({' '.join(args)}): {stderr}")
    return result


def authenticated_repo_url(repository: str, token: str | None) -> str:
    if not token:
        return f"https://github.com/{repository}.git"
    return f"https://x-access-token:{token}@github.com/{repository}.git"


def parse_ls_remote(text: str) -> tuple[dict[str, str], dict[str, str]]:
    heads: dict[str, str] = {}
    tags: dict[str, str] = {}

    for raw in text.splitlines():
        raw = raw.strip()
        if not raw:
            continue
        sha, ref = raw.split("\t", 1)
        if ref.startswith("refs/heads/"):
            heads[ref.removeprefix("refs/heads/")] = sha
        elif ref.startswith("refs/tags/") and not ref.endswith("^{}"):
            tags[ref.removeprefix("refs/tags/")] = sha

    return heads, tags


def discover_remote_state(source: str, default_branch: str | None = None) -> RemoteState:
    url = authenticated_repo_url(source, None)

    symref = run(
        ["git", "ls-remote", "--symref", url, "HEAD"],
    ).stdout
    discovered = None
    for line in symref.splitlines():
        if line.startswith("ref: refs/heads/") and line.endswith("\tHEAD"):
            discovered = line.split("\t", 1)[0].removeprefix("ref: refs/heads/")
            break

    branch = default_branch or discovered
    if not branch:
        raise SyncError(f"unable to discover default branch for {source}")

    refs = run(
        ["git", "ls-remote", "--heads", "--tags", url],
    ).stdout
    heads, tags = parse_ls_remote(refs)

    if branch not in heads:
        raise SyncError(f"default branch {branch!r} not present in {source}")

    return RemoteState(default_branch=branch, heads=heads, tags=tags)


def strip_upstream_workflows(repo: Path) -> list[str]:
    workflow_dir = repo / ".github" / "workflows"
    if not workflow_dir.exists():
        return []

    removed: list[str] = []
    for path in sorted(workflow_dir.rglob("*"), reverse=True):
        if path.is_file() or path.is_symlink():
            removed.append(str(path.relative_to(repo)))
            path.unlink()
        elif path.is_dir():
            try:
                path.rmdir()
            except OSError:
                pass

    try:
        workflow_dir.rmdir()
    except OSError:
        pass

    github_dir = repo / ".github"
    try:
        github_dir.rmdir()
    except OSError:
        pass

    return removed


def configure_identity(repo: Path) -> None:
    run(["git", "config", "user.name", "e-Cidade Mirror Bot"], cwd=repo)
    run(
        [
            "git",
            "config",
            "user.email",
            "e-cidade-mirror[bot]@users.noreply.github.com",
        ],
        cwd=repo,
    )


def has_changes(repo: Path) -> bool:
    status = run(["git", "status", "--porcelain"], cwd=repo).stdout
    return bool(status.strip())


def commit_if_needed(repo: Path, message: str) -> bool:
    if not has_changes(repo):
        return False
    run(["git", "add", "-A"], cwd=repo)
    run(["git", "commit", "-s", "-m", message], cwd=repo)
    return True


def read_marker(target: Path) -> dict[str, object] | None:
    marker = target / ".github" / "ecidade-mirror.json"
    if not marker.exists():
        return None
    try:
        return json.loads(marker.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise SyncError(f"invalid mirror marker: {exc}") from exc


def write_sync_state(target: Path, state: RemoteState) -> None:
    marker = target / ".github" / "ecidade-mirror.json"
    data = read_marker(target) or {}
    data.update(
        {
            "upstream_default_branch": state.default_branch,
            "upstream_default_sha": state.heads[state.default_branch],
            "upstream_fingerprint": state.fingerprint,
        }
    )
    marker.parent.mkdir(parents=True, exist_ok=True)
    marker.write_text(
        json.dumps(data, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def marker_matches_state(target: Path, state: RemoteState) -> bool:
    marker = read_marker(target)
    if not marker:
        return False
    return marker.get("upstream_fingerprint") == state.fingerprint


def publish_upstream_refs(
    repo: Path,
    destination: str,
    state: RemoteState,
    token: str | None,
) -> None:
    destination_url = authenticated_repo_url(destination, token)

    for branch in sorted(state.heads):
        run(
            [
                "git",
                "push",
                destination_url,
                f"+refs/remotes/upstream/{branch}:refs/heads/upstream/{branch}",
            ],
            cwd=repo,
        )

    for tag in sorted(state.tags):
        run(
            [
                "git",
                "push",
                destination_url,
                f"+refs/tags/{tag}:refs/tags/upstream/{tag}",
            ],
            cwd=repo,
        )


def clone_source(source: str, workdir: Path, state: RemoteState) -> Path:
    repo = workdir / "source"
    run(
        [
            "git",
            "clone",
            "--no-checkout",
            authenticated_repo_url(source, None),
            str(repo),
        ]
    )
    run(
        ["git", "remote", "rename", "origin", "upstream"],
        cwd=repo,
    )
    run(
        ["git", "fetch", "upstream", "+refs/heads/*:refs/remotes/upstream/*", "--tags"],
        cwd=repo,
    )
    run(
        ["git", "switch", "-C", "mirror-base", f"upstream/{state.default_branch}"],
        cwd=repo,
    )
    configure_identity(repo)
    return repo


def bootstrap(
    mirror: dict[str, object],
    state: RemoteState,
    *,
    config: Path,
    templates: Path,
    token: str | None,
    workdir: Path,
    dry_run: bool,
) -> None:
    source = str(mirror["source"])
    destination = str(mirror["destination"])
    destination_branch = str(mirror["destination_branch"])

    repo = clone_source(source, workdir, state)

    if bool(mirror["strip_upstream_workflows"]):
        strip_upstream_workflows(repo)

    render_layer(config, str(mirror["id"]), repo, templates)
    write_sync_state(repo, state)
    commit_if_needed(repo, "chore: apply e-Cidade mirror administrative layer")

    if dry_run:
        print(
            json.dumps(
                {
                    "operation": "bootstrap",
                    "source": source,
                    "destination": destination,
                    "default_branch": state.default_branch,
                    "destination_branch": destination_branch,
                    "upstream_sha": state.heads[state.default_branch],
                    "fingerprint": state.fingerprint,
                },
                indent=2,
                sort_keys=True,
            )
        )
        return

    publish_upstream_refs(repo, destination, state, token)
    destination_url = authenticated_repo_url(destination, token)
    run(
        [
            "git",
            "push",
            destination_url,
            f"HEAD:refs/heads/{destination_branch}",
        ],
        cwd=repo,
    )


def update(
    mirror: dict[str, object],
    state: RemoteState,
    *,
    config: Path,
    templates: Path,
    token: str | None,
    workdir: Path,
    dry_run: bool,
) -> str | None:
    destination = str(mirror["destination"])
    destination_branch = str(mirror["destination_branch"])
    destination_url = authenticated_repo_url(destination, token)

    target = workdir / "target"
    run(["git", "clone", destination_url, str(target)])
    configure_identity(target)

    if marker_matches_state(target, state):
        print("mirror is already synchronized")
        return None

    source_url = authenticated_repo_url(str(mirror["source"]), None)
    run(["git", "remote", "add", "upstream", source_url], cwd=target)
    run(
        ["git", "fetch", "upstream", "+refs/heads/*:refs/remotes/upstream/*", "--tags"],
        cwd=target,
    )

    short_sha = state.heads[state.default_branch][:12]
    sync_branch = f"sync/upstream-{state.default_branch}-{short_sha}"
    run(["git", "switch", "-C", sync_branch, destination_branch], cwd=target)

    merge = subprocess.run(
        [
            "git",
            "merge",
            "--no-ff",
            "--no-edit",
            f"upstream/{state.default_branch}",
        ],
        cwd=target,
        text=True,
        capture_output=True,
    )
    if merge.returncode != 0:
        conflicts = run(
            ["git", "diff", "--name-only", "--diff-filter=U"],
            cwd=target,
        ).stdout.splitlines()

        managed = {
            "README.md",
            "CONTRIBUTING.md",
            ".github/PULL_REQUEST_TEMPLATE.md",
            ".github/ecidade-mirror.json",
        }
        unexpected = sorted(path for path in conflicts if path not in managed)
        if unexpected:
            raise SyncError(
                "merge conflicts require human intervention: "
                + ", ".join(unexpected)
            )

        for path in conflicts:
            run(
                ["git", "checkout", "--theirs", "--", path],
                cwd=target,
            )
            run(["git", "add", "--", path], cwd=target)

        run(["git", "commit", "--no-edit"], cwd=target)

    if bool(mirror["strip_upstream_workflows"]):
        strip_upstream_workflows(target)

    render_layer(config, str(mirror["id"]), target, templates)
    write_sync_state(target, state)
    commit_if_needed(target, "chore: refresh e-Cidade mirror administrative layer")

    if dry_run:
        print(
            json.dumps(
                {
                    "operation": "update",
                    "branch": sync_branch,
                    "source": mirror["source"],
                    "destination": destination,
                    "upstream_sha": state.heads[state.default_branch],
                    "fingerprint": state.fingerprint,
                },
                indent=2,
                sort_keys=True,
            )
        )
        return sync_branch

    publish_upstream_refs(target, destination, state, token)
    run(
        ["git", "push", "-u", destination_url, f"HEAD:refs/heads/{sync_branch}"],
        cwd=target,
    )

    existing = run(
        [
            "gh",
            "pr",
            "list",
            "--repo",
            destination,
            "--state",
            "open",
            "--head",
            sync_branch,
            "--json",
            "url",
            "--jq",
            ".[0].url // empty",
        ],
        cwd=target,
    ).stdout.strip()

    if not existing:
        run(
            [
                "gh",
                "pr",
                "create",
                "--repo",
                destination,
                "--base",
                destination_branch,
                "--head",
                sync_branch,
                "--title",
                f"sync: upstream {state.default_branch} {short_sha}",
                "--body",
                (
                    "Sincronização automática do upstream "
                    f"`{mirror['source']}` até `{state.heads[state.default_branch]}`.\n\n"
                    "Este PR preserva o histórico Git do upstream e reaplica "
                    "somente a camada administrativa do mirror."
                ),
            ],
            cwd=target,
        )

    return sync_branch


def destination_has_branch(destination: str, branch: str, token: str | None) -> bool:
    url = authenticated_repo_url(destination, token)
    result = subprocess.run(
        ["git", "ls-remote", "--exit-code", "--heads", url, f"refs/heads/{branch}"],
        text=True,
        capture_output=True,
    )
    if result.returncode == 0:
        return True
    if result.returncode == 2:
        return False
    raise SyncError(result.stderr.strip() or "unable to inspect destination")


def command_plan(args: argparse.Namespace) -> int:
    data = load_config(Path(args.config))
    mirror = find_mirror(data, args.mirror)
    state = discover_remote_state(str(mirror["source"]))
    print(
        json.dumps(
            {
                "mirror": mirror["id"],
                "source": mirror["source"],
                "destination": mirror["destination"],
                "upstream_default_branch": state.default_branch,
                "upstream_default_sha": state.heads[state.default_branch],
                "heads": len(state.heads),
                "tags": len(state.tags),
                "fingerprint": state.fingerprint,
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


def command_sync(args: argparse.Namespace) -> int:
    config = Path(args.config).resolve()
    templates = Path(args.templates).resolve()
    data = load_config(config)
    mirror = find_mirror(data, args.mirror)
    state = discover_remote_state(str(mirror["source"]))
    token = os.environ.get("GH_TOKEN")

    if not args.dry_run and not token:
        raise SyncError("GH_TOKEN is required for write operations")

    destination_branch = str(mirror["destination_branch"])
    has_destination = destination_has_branch(
        str(mirror["destination"]),
        destination_branch,
        token if not args.dry_run else None,
    )

    with tempfile.TemporaryDirectory(prefix="ecidade-mirror-") as tmp:
        workdir = Path(tmp)
        if not has_destination:
            bootstrap(
                mirror,
                state,
                config=config,
                templates=templates,
                token=token,
                workdir=workdir,
                dry_run=args.dry_run,
            )
            return 0

        branch = update(
            mirror,
            state,
            config=config,
            templates=templates,
            token=token,
            workdir=workdir,
            dry_run=args.dry_run,
        )
        if branch:
            print(f"sync_branch={branch}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--config",
        default="mirrors/mirrors.json",
    )
    parser.add_argument(
        "--templates",
        default="mirrors/templates",
    )

    sub = parser.add_subparsers(dest="command", required=True)

    plan = sub.add_parser("plan")
    plan.add_argument("mirror")
    plan.set_defaults(func=command_plan)

    sync = sub.add_parser("sync")
    sync.add_argument("mirror")
    sync.add_argument("--dry-run", action="store_true")
    sync.set_defaults(func=command_sync)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        return args.func(args)
    except (ConfigError, RenderError, SyncError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
