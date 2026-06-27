import pathlib
import re
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[2]
DOC = ROOT / "doc" / "ai-native-runtime" / "safe-entity-ops-api.md"
README = ROOT / "doc" / "ai-native-runtime" / "README.md"

PRIVATE_PATTERNS = re.compile(
    r"bill|wills|minecraftpi|192\.168|spacebase|themepark|showcase100|disneyland100|asset_payload|prompt",
    re.I,
)


class SafeEntityOpsContractTests(unittest.TestCase):
    def test_public_document_defines_safe_entity_ops_boundary(self):
        self.assertTrue(DOC.is_file(), f"missing {DOC}")
        body = DOC.read_text(encoding="utf-8")
        body_lower = body.lower()

        for phrase in (
            "core.ai_entity_ops",
            "spawn",
            "inspect",
            "move",
            "cleanup",
            "entity.spawn",
            "entity.control",
            "owner mismatch",
            "entity limit",
            "node mutation disabled",
            "action result",
            "runtime metrics",
            "audit",
            "generic demo helper",
        ):
            self.assertIn(phrase, body_lower)

        self.assertNotRegex(body, PRIVATE_PATTERNS)

    def test_readme_links_safe_entity_ops_contract(self):
        self.assertTrue(README.is_file(), f"missing {README}")
        self.assertIn(
            "[Safe entity operations API](safe-entity-ops-api.md)",
            README.read_text(encoding="utf-8"),
        )


if __name__ == "__main__":
    unittest.main()
