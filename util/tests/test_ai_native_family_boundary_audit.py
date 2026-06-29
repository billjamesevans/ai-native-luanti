import pathlib
import re
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[2]
AUDIT_DOC = ROOT / "doc" / "ai-native-runtime" / "family-creatures-boundary-audit.md"
BOUNDARY_DOC = ROOT / "doc" / "ai-native-runtime" / "family-prototype-plugin-boundaries.md"
README = ROOT / "doc" / "ai-native-runtime" / "README.md"


class FamilyBoundaryAuditTests(unittest.TestCase):
    def test_audit_doc_classifies_family_prototype_boundaries(self):
        text = AUDIT_DOC.read_text(encoding="utf-8")

        for phrase in (
            "Player-owned AI companion",
            "Provider-specific model calls",
            "Queued builder tasks",
            "Large fixed landmark builders",
            "Conservative terrain repair bot",
            "Rideable vehicles",
            "Admin convenience commands",
            "Private content that must stay out",
            "First-party `build_agent` plugin behavior",
            "First-party `repair_agent` plugin behavior",
            "Optional demo vehicle plugin",
            "No new engine API should be added for this audit alone",
            "tests before engine APIs change",
            "spacebase",
            "themepark",
            "showcase100",
            "disneyland100",
            "must not copy `family_creatures/init.lua` or assets wholesale",
        ):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, text)

    def test_docs_link_audit_from_runtime_index_and_boundary_map(self):
        readme = README.read_text(encoding="utf-8")
        boundary = BOUNDARY_DOC.read_text(encoding="utf-8")

        self.assertIn("family-creatures-boundary-audit.md", readme)
        self.assertIn("family-creatures-boundary-audit.md", boundary)

    def test_audit_doc_does_not_retain_private_operational_details(self):
        text = AUDIT_DOC.read_text(encoding="utf-8")
        private_patterns = [
            r"/Users/",
            r"/opt/",
            r"minecraftpi",
            r"192\.168",
            r"OPENAI_API_KEY",
            r"sk-[A-Za-z0-9_-]{20,}",
            r"private_prompt",
            r"asset_payload",
            r"\b-?\d+,\s*-?\d+,\s*-?\d+\b",
        ]

        for pattern in private_patterns:
            with self.subTest(pattern=pattern):
                self.assertIsNone(re.search(pattern, text, re.I))


if __name__ == "__main__":
    unittest.main()
