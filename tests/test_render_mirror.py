import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "render_mirror.py"


class RenderMirrorTest(unittest.TestCase):
    def render(self, target):
        return subprocess.run(
            [sys.executable, str(SCRIPT), "dbseller", str(target)],
            cwd=ROOT,
            text=True,
            capture_output=True,
        )

    def test_renders_all_administrative_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp)
            (target / "README.md").write_text("# Upstream\n\nOriginal content.\n")

            result = self.render(target)
            self.assertEqual(result.returncode, 0, result.stderr)

            readme = (target / "README.md").read_text()
            self.assertEqual(readme.count("<!-- ecidade-mirror:begin -->"), 1)
            self.assertIn("DBSeller/e-cidade", readme)
            self.assertIn("# Upstream", readme)
            self.assertTrue((target / "CONTRIBUTING.md").exists())
            self.assertTrue((target / ".github/PULL_REQUEST_TEMPLATE.md").exists())
            self.assertTrue((target / ".github/ecidade-mirror.json").exists())

            marker = json.loads(
                (target / ".github/ecidade-mirror.json").read_text()
            )
            self.assertEqual(marker["source"], "DBSeller/e-cidade")
            self.assertEqual(marker["managed_by"], "e-cidade/.github")

    def test_second_render_is_idempotent(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp)
            (target / "README.md").write_text("# Upstream\n")

            first = self.render(target)
            self.assertEqual(first.returncode, 0, first.stderr)
            snapshot = {
                path.relative_to(target): path.read_bytes()
                for path in target.rglob("*")
                if path.is_file()
            }

            second = self.render(target)
            self.assertEqual(second.returncode, 0, second.stderr)
            self.assertIn("already up to date", second.stdout)
            after = {
                path.relative_to(target): path.read_bytes()
                for path in target.rglob("*")
                if path.is_file()
            }
            self.assertEqual(snapshot, after)

    def test_upstream_readme_changes_are_preserved(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp)
            readme = target / "README.md"
            readme.write_text("# Upstream\n\nVersion one.\n")
            self.assertEqual(self.render(target).returncode, 0)

            managed = readme.read_text()
            start = managed.index("<!-- ecidade-mirror:begin -->")
            end = managed.index("<!-- ecidade-mirror:end -->") + len(
                "<!-- ecidade-mirror:end -->"
            )
            banner = managed[start:end]
            readme.write_text(banner + "\n\n# Upstream\n\nVersion two.\n")

            result = self.render(target)
            self.assertEqual(result.returncode, 0, result.stderr)
            rendered = readme.read_text()
            self.assertIn("Version two.", rendered)
            self.assertNotIn("Version one.", rendered)
            self.assertEqual(rendered.count("<!-- ecidade-mirror:begin -->"), 1)

    def test_missing_readme_is_created(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp)
            result = self.render(target)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertTrue((target / "README.md").exists())

    def test_broken_marker_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp)
            (target / "README.md").write_text(
                "<!-- ecidade-mirror:begin -->\nBroken\n"
            )
            result = self.render(target)
            self.assertEqual(result.returncode, 2)
            self.assertIn("incomplete", result.stderr)


if __name__ == "__main__":
    unittest.main()
