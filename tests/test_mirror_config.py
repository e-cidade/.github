import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "mirror_config.py"


class MirrorConfigTest(unittest.TestCase):
    def run_config(self, payload, *args):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "mirrors.json"
            path.write_text(json.dumps(payload))
            return subprocess.run(
                [sys.executable, str(SCRIPT), "--config", str(path), *args],
                text=True,
                capture_output=True,
            )

    def valid_mirror(self, **changes):
        mirror = {
            "id": "dbseller",
            "display_name": "DBSeller",
            "source": "DBSeller/e-cidade",
            "destination": "e-cidade/e-cidade-DBSeller",
            "destination_branch": "main",
            "strip_upstream_workflows": True,
        }
        mirror.update(changes)
        return mirror

    def test_repository_catalog_is_valid(self):
        result = subprocess.run(
            [sys.executable, str(SCRIPT), "validate"],
            cwd=ROOT,
            text=True,
            capture_output=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_get_returns_requested_field(self):
        result = subprocess.run(
            [
                sys.executable,
                str(SCRIPT),
                "get",
                "dbseller",
                "--field",
                "source",
            ],
            cwd=ROOT,
            text=True,
            capture_output=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), "DBSeller/e-cidade")

    def test_list_returns_configured_mirror_ids(self):
        result = self.run_config(
            {
                "mirrors": [
                    self.valid_mirror(),
                    self.valid_mirror(
                        id="other",
                        source="example/e-cidade",
                        destination="e-cidade/e-cidade-Other",
                    ),
                ]
            },
            "list",
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(
            json.loads(result.stdout),
            ["dbseller", "other"],
        )

    def test_duplicate_id_is_rejected(self):
        mirror = self.valid_mirror()
        result = self.run_config({"mirrors": [mirror, mirror]}, "validate")
        self.assertEqual(result.returncode, 2)
        self.assertIn("duplicate mirror id", result.stderr)

    def test_duplicate_destination_is_rejected(self):
        first = self.valid_mirror()
        second = self.valid_mirror(
            id="other",
            source="example/e-cidade",
        )
        result = self.run_config({"mirrors": [first, second]}, "validate")
        self.assertEqual(result.returncode, 2)
        self.assertIn("duplicate mirror destination", result.stderr)

    def test_source_equal_destination_is_rejected(self):
        result = self.run_config(
            {
                "mirrors": [
                    self.valid_mirror(
                        source="e-cidade/e-cidade-DBSeller",
                    )
                ]
            },
            "validate",
        )
        self.assertEqual(result.returncode, 2)
        self.assertIn("source and destination must differ", result.stderr)

    def test_destination_outside_org_is_rejected(self):
        result = self.run_config(
            {
                "mirrors": [
                    self.valid_mirror(destination="other/e-cidade-DBSeller")
                ]
            },
            "validate",
        )
        self.assertEqual(result.returncode, 2)
        self.assertIn("must belong to e-cidade", result.stderr)

    def test_invalid_boolean_is_rejected(self):
        result = self.run_config(
            {
                "mirrors": [
                    self.valid_mirror(strip_upstream_workflows="yes")
                ]
            },
            "validate",
        )
        self.assertEqual(result.returncode, 2)
        self.assertIn("must be boolean", result.stderr)


if __name__ == "__main__":
    unittest.main()
