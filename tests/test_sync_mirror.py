import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "sync_mirror.py"

spec = importlib.util.spec_from_file_location("sync_mirror", SCRIPT)
sync_mirror = importlib.util.module_from_spec(spec)
assert spec.loader
sys.path.insert(0, str(ROOT / "scripts"))
sys.modules[spec.name] = sync_mirror
spec.loader.exec_module(sync_mirror)


def git(*args, cwd=None):
    result = subprocess.run(
        ["git", *args],
        cwd=cwd,
        text=True,
        capture_output=True,
    )
    if result.returncode:
        raise AssertionError(result.stderr)
    return result.stdout.strip()


class SyncMirrorUnitTest(unittest.TestCase):
    def test_parse_ls_remote(self):
        heads, tags = sync_mirror.parse_ls_remote(
            "a\trefs/heads/master\n"
            "b\trefs/heads/stable\n"
            "c\trefs/tags/v1\n"
            "d\trefs/tags/v1^{}\n"
        )
        self.assertEqual(heads, {"master": "a", "stable": "b"})
        self.assertEqual(tags, {"v1": "c"})

    def test_fingerprint_is_stable_for_ordering(self):
        one = sync_mirror.RemoteState(
            default_branch="master",
            heads={"b": "2", "a": "1"},
            tags={"v2": "4", "v1": "3"},
        )
        two = sync_mirror.RemoteState(
            default_branch="master",
            heads={"a": "1", "b": "2"},
            tags={"v1": "3", "v2": "4"},
        )
        self.assertEqual(one.fingerprint, two.fingerprint)

    def test_strip_workflows_preserves_other_github_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            workflows = repo / ".github" / "workflows"
            workflows.mkdir(parents=True)
            (workflows / "ci.yml").write_text("name: CI\n")
            (repo / ".github" / "CODEOWNERS").write_text("* @example\n")

            removed = sync_mirror.strip_upstream_workflows(repo)

            self.assertEqual(removed, [".github/workflows/ci.yml"])
            self.assertFalse(workflows.exists())
            self.assertTrue((repo / ".github/CODEOWNERS").exists())

    def test_marker_state_round_trip(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp)
            marker = target / ".github" / "ecidade-mirror.json"
            marker.parent.mkdir(parents=True)
            marker.write_text(
                json.dumps(
                    {
                        "schema": 1,
                        "mirror": "dbseller",
                        "source": "DBSeller/e-cidade",
                    }
                )
            )
            state = sync_mirror.RemoteState(
                default_branch="master",
                heads={"master": "abc"},
                tags={},
            )
            sync_mirror.write_sync_state(target, state)
            self.assertTrue(sync_mirror.marker_matches_state(target, state))

    def test_local_git_history_can_receive_overlay_commit(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp) / "repo"
            repo.mkdir()
            git("init", cwd=repo)
            git("config", "user.name", "Test", cwd=repo)
            git("config", "user.email", "test@example.com", cwd=repo)
            (repo / "README.md").write_text("# Upstream\n")
            git("add", "README.md", cwd=repo)
            git("commit", "-m", "upstream", cwd=repo)
            upstream_sha = git("rev-parse", "HEAD", cwd=repo)

            (repo / "CONTRIBUTING.md").write_text("local\n")
            committed = sync_mirror.commit_if_needed(
                repo,
                "chore: apply overlay",
            )
            self.assertTrue(committed)
            parent = git("rev-parse", "HEAD^", cwd=repo)
            self.assertEqual(parent, upstream_sha)


if __name__ == "__main__":
    unittest.main()

class SyncMirrorSecurityTest(unittest.TestCase):
    def test_authenticated_url_never_contains_token(self):
        url = sync_mirror.authenticated_repo_url(
            "e-cidade/e-cidade-DBSeller",
            "super-secret-token",
        )
        self.assertEqual(
            url,
            "https://github.com/e-cidade/e-cidade-DBSeller.git",
        )
        self.assertNotIn("super-secret-token", url)
