import pathlib
import re
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[2]
PROFILE = ROOT / "games" / "ai_runtime"
PROFILE_README = PROFILE / "README.md"
PROFILE_INIT = PROFILE / "mods" / "ai_runtime_base" / "init.lua"
DOC = ROOT / "doc" / "ai-native-runtime" / "alpha-server-profile.md"
RUNTIME_INDEX = ROOT / "doc" / "ai-native-runtime" / "README.md"

PRIVATE_OR_SHOWCASE = re.compile(
    r"minecraftpi|192\.168|spacebase|themepark|showcase100|disneyland100|"
    r"(?<![A-Za-z0-9_-])sk-[A-Za-z0-9_-]{20,}|OPENAI_API_KEY|/Users/|bill@",
    re.I,
)


class AlphaProfileContractTests(unittest.TestCase):
    def read_profile_text(self):
        chunks = []
        for path in sorted(PROFILE.rglob("*")):
            if path.is_file() and path.suffix.lower() in {"", ".conf", ".lua", ".md", ".json"}:
                chunks.append(path.read_text(encoding="utf-8"))
        return "\n".join(chunks)

    def test_alpha_profile_boundary_is_documented(self):
        self.assertTrue(DOC.is_file())
        doc = DOC.read_text(encoding="utf-8")
        profile_readme = PROFILE_README.read_text(encoding="utf-8")
        index = RUNTIME_INDEX.read_text(encoding="utf-8")

        self.assertIn("player-ready alpha profile", doc)
        self.assertIn("games/ai_runtime", doc)
        self.assertIn("must not include", doc)
        self.assertIn("test fixtures", doc)
        self.assertIn("Required clean runtime surfaces", doc)
        self.assertIn("/ai_runtime_operator_status", doc)
        self.assertIn("/ai_runtime_operator_task_control", doc)
        self.assertIn("Alpha server profile", index)
        self.assertIn("player-ready alpha game profile", profile_readme)
        self.assertIn("operator status and receipt-gated task-control commands", profile_readme)
        self.assertIn("Runtime unit tests", profile_readme)
        self.assertNotRegex(doc, PRIVATE_OR_SHOWCASE)

    def test_clean_profile_excludes_privileged_default_grants(self):
        source = PROFILE_INIT.read_text(encoding="utf-8")

        self.assertIn('capability_profile = "clean"', source)
        for expected in (
            '["world.read"] = true',
            '["world.place"] = true',
            '["world.remove"] = true',
            '["entity.spawn"] = true',
            '["entity.control"] = true',
            '["task.cancel"] = true',
            '["http.llm"] = true',
        ):
            self.assertIn(expected, source)
        self.assertIn('core.register_entity(":" .. helper_entity_name', source)
        self.assertIn('local helper_entity_name = "ai_runtime_base:helper"', source)
        self.assertIn("agent_entity_name = helper_entity_name", source)
        self.assertNotIn("ai_demo_benchmark:helper", source)
        for forbidden in (
            "admin.override",
            "import.assets",
            "combat.defend",
            "player.teleport.other",
        ):
            self.assertNotIn(forbidden, source)
        self.assertIn("core.ai_rollback_storage.configure", source)
        self.assertIn("enabled = true", source)

    def test_profile_content_has_no_private_or_test_fixture_references(self):
        profile_text = self.read_profile_text()

        self.assertNotRegex(profile_text, PRIVATE_OR_SHOWCASE)
        for forbidden in (
            "devtest",
            "ai_runtime_test",
            "family_creatures",
            "mineclone2",
            "mcl_",
        ):
            self.assertNotIn(forbidden, profile_text.lower())


if __name__ == "__main__":
    unittest.main()
