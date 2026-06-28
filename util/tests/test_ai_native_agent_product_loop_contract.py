import pathlib
import re
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[2]
PLUGIN = ROOT / "builtin" / "game" / "ai_agent_plugin.lua"
DOC = ROOT / "doc" / "ai-native-runtime" / "first-party-agent-plugin.md"
AI_RUNTIME_BASE = ROOT / "games" / "ai_runtime" / "mods" / "ai_runtime_base" / "init.lua"

PRIVATE_PATTERNS = re.compile(
    r"minecraftpi|192\.168|spacebase|themepark|showcase100|disneyland100|"
    r"sk-[A-Za-z0-9_-]{20,}|OPENAI_API_KEY|private_prompt|asset_payload|/Users/",
    re.I,
)


class AgentProductLoopContractTests(unittest.TestCase):
    def test_first_party_agent_plugin_documents_product_loop_commands(self):
        body = DOC.read_text(encoding="utf-8")

        for phrase in (
            "`core.build_agent.define_task`",
            "`core.build_agent.plan`",
            "`core.repair_agent.queue_apply_task`",
            "`core.ai_player_ops.defend`",
            "`core.ai_entity_ops.move`",
            "`guide`",
            "`audit`",
            "`rollback`",
            "`defend`",
            "`follow N`",
            "`build plan`",
            "`repair plan`",
            "continuous follow",
            "total-distance budgets",
            "`ai_agent.follow_step`",
            "rollback-backed",
            "combat.defend",
        ):
            self.assertIn(phrase, body)
        self.assertNotRegex(body, PRIVATE_PATTERNS)

    def test_first_party_agent_plugin_uses_runtime_surfaces_not_raw_world_writes(self):
        source = PLUGIN.read_text(encoding="utf-8")

        for phrase in (
            "core.build_agent.define_task",
            "core.build_agent.plan",
            "core.repair_agent.queue_apply_task",
            "core.ai_player_ops.defend",
            "core.ai_entity_ops.move",
            "ai_agent.follow_step",
            "follow_distance_limit_exceeded",
            "core.get_ai_runtime_audit",
        ):
            self.assertIn(phrase, source)
        for forbidden in (
            "core.set_node",
            "core.remove_node",
            "core.bulk_set_node",
            ":set_pos(",
            ".set_pos(",
        ):
            self.assertNotIn(forbidden, source)

    def test_clean_ai_runtime_profile_enables_default_rollback_storage(self):
        source = AI_RUNTIME_BASE.read_text(encoding="utf-8")

        self.assertIn("core.ai_rollback_storage.configure", source)
        self.assertIn("enabled = true", source)


if __name__ == "__main__":
    unittest.main()
