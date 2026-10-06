import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]


class GovernanceConfigTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = json.loads(
            (ROOT / "governance.config.json").read_text()
        )

    def test_mirror_policy_replaces_default_ruleset(self):
        policies = self.data["policies"]
        self.assertEqual(
            policies["mirror-default"]["name"],
            policies["protected-default"]["name"],
        )

    def test_dbseller_uses_mirror_policy(self):
        repo = self.data["repositories"]["e-cidade/e-cidade-DBSeller"]
        self.assertIn("mirror-default", repo["policies"])

    def test_contass_is_not_managed_as_mirror(self):
        repo = self.data["repositories"].get("e-cidade/e-cidade-Contass", {})
        self.assertNotIn("mirror-default", repo.get("policies", []))

    def test_initial_managed_repository_scope_is_explicit(self):
        self.assertEqual(
            set(self.data["repositories"]),
            {
                "e-cidade/.github",
                "e-cidade/e-cidade",
                "e-cidade/e-cidade-DBSeller",
            },
        )

    def test_contass_is_outside_managed_scope(self):
        self.assertNotIn(
            "e-cidade/e-cidade-Contass",
            self.data["repositories"],
        )

    def test_control_plane_requires_its_ci(self):
        repo = self.data["repositories"]["e-cidade/.github"]
        self.assertIn("organization-config-ci", repo["policies"])

        checks = (
            self.data["policies"]["organization-config-ci"]
            ["rules"][0]["parameters"]["required_status_checks"]
        )
        contexts = {item["context"] for item in checks}
        self.assertEqual(
            contexts,
            {"Configuration", "actionlint", "zizmor"},
        )


if __name__ == "__main__":
    unittest.main()
