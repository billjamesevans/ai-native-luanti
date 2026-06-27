import pathlib
import re
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[2]
DOC = ROOT / "doc" / "ai-native-runtime" / "demo-entity-vehicle-provenance.md"
README = ROOT / "doc" / "ai-native-runtime" / "README.md"


class DemoEntityVehicleProvenanceContractTests(unittest.TestCase):
    def test_public_document_covers_asset_and_behavior_clearance(self):
        self.assertTrue(DOC.is_file(), f"missing {DOC}")
        body = DOC.read_text(encoding="utf-8")
        body_lower = body.lower()

        for phrase in (
            "art",
            "models",
            "sounds",
            "names",
            "licenses",
            "behavior defaults",
            "generic examples",
            "no private family-server content",
            "no destructive behavior by default",
        ):
            self.assertIn(phrase, body_lower)

    def test_public_document_covers_entity_and_vehicle_benchmarks(self):
        self.assertTrue(DOC.is_file(), f"missing {DOC}")
        body = DOC.read_text(encoding="utf-8")
        body_lower = body.lower()

        for phrase in (
            "entity count",
            "movement",
            "collision",
            "control cost",
            "server-step impact",
            "p95",
            "max lag",
        ):
            self.assertIn(phrase, body_lower)

    def test_public_document_blocks_assets_and_private_payloads(self):
        self.assertTrue(DOC.is_file(), f"missing {DOC}")
        body = DOC.read_text(encoding="utf-8")

        for phrase in (
            "Do not commit assets",
            "Do not commit models",
            "Do not commit sounds",
            "Do not commit private commands",
            "Do not commit private world data",
        ):
            self.assertIn(phrase, body)
        self.assertNotRegex(body, re.compile(r"bill|wills|minecraftpi|192\.168", re.I))

    def test_readme_links_contract(self):
        self.assertTrue(README.is_file(), f"missing {README}")
        self.assertIn(
            "[Demo entity and vehicle provenance](demo-entity-vehicle-provenance.md)",
            README.read_text(encoding="utf-8"),
        )


if __name__ == "__main__":
    unittest.main()
