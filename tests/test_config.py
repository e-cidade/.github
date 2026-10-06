import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]

class ConfigTest(unittest.TestCase):
    def test_mirrors_are_unique_and_inside_org(self):
        data = json.loads((ROOT / "mirrors" / "mirrors.json").read_text())
        ids = set()
        destinations = set()
        for mirror in data["mirrors"]:
            self.assertNotIn(mirror["id"], ids)
            self.assertNotIn(mirror["destination"], destinations)
            self.assertTrue(mirror["destination"].startswith("e-cidade/"))
            self.assertNotEqual(mirror["source"], mirror["destination"])
            ids.add(mirror["id"])
            destinations.add(mirror["destination"])

    def test_governance_references_known_mirror(self):
        mirrors = json.loads((ROOT / "mirrors" / "mirrors.json").read_text())
        governance = json.loads((ROOT / "governance.config.json").read_text())
        for mirror in mirrors["mirrors"]:
            repo = governance["repositories"][mirror["destination"]]
            self.assertIn("mirror-default", repo["policies"])

if __name__ == "__main__":
    unittest.main()
