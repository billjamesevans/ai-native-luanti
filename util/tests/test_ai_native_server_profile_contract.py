import pathlib
import re
import subprocess
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[2]
PROFILE_DIR = ROOT / "games" / "ai_runtime"
GAME_CONF = PROFILE_DIR / "game.conf"
README = PROFILE_DIR / "README.md"
BASE_MOD = PROFILE_DIR / "mods" / "ai_runtime_base" / "init.lua"
AGENTS_SDK_BRIDGE_MOD = PROFILE_DIR / "mods" / "ai_runtime_agents_sdk_bridge" / "init.lua"
SMOKE_LUA = ROOT / "builtin" / "game" / "ai_runtime_smoke.lua"
DEMO_BENCHMARK_LUA = ROOT / "builtin" / "game" / "demo_entity_benchmark.lua"
MODEL_ADAPTER_PLUGIN_LUA = ROOT / "builtin" / "game" / "ai_model_adapter_plugin.lua"
AGENTS_SDK_ADAPTER_PLUGIN_LUA = ROOT / "builtin" / "game" / "ai_agents_sdk_adapter_plugin.lua"
AI_RUNTIME_UNITTEST = ROOT / "src" / "unittest" / "test_ai_runtime.cpp"
DOC = ROOT / "doc" / "ai-native-runtime" / "non-devtest-server-profile.md"
CAPABILITY_PROFILES_DOC = ROOT / "doc" / "ai-native-runtime" / "agent-capability-profiles.md"
RUNTIME_README = ROOT / "doc" / "ai-native-runtime" / "README.md"
GITIGNORE = ROOT / ".gitignore"
CMAKE = ROOT / "CMakeLists.txt"

PRIVATE_PATTERNS = re.compile(
    r"minecraftpi|192\.168|spacebase|themepark|showcase100|disneyland100|"
    r"(?<![A-Za-z0-9_-])sk-[A-Za-z0-9_-]{20,}|OPENAI_API_KEY|private_prompt|asset_payload|/Users/",
    re.I,
)


class AIRuntimeServerProfileContractTests(unittest.TestCase):
    def test_profile_files_define_public_safe_non_devtest_game(self):
        self.assertTrue(GAME_CONF.is_file(), f"missing {GAME_CONF}")
        self.assertTrue(README.is_file(), f"missing {README}")
        self.assertTrue(BASE_MOD.is_file(), f"missing {BASE_MOD}")

        game_conf = GAME_CONF.read_text(encoding="utf-8")
        readme = README.read_text(encoding="utf-8")
        base_mod = BASE_MOD.read_text(encoding="utf-8")
        profile_text = game_conf + "\n" + readme + "\n" + base_mod

        self.assertIn("title = AI Runtime", game_conf)
        self.assertIn("description =", game_conf)
        self.assertIn("production-like", readme)
        self.assertIn("explicit dev/test settings", readme)
        self.assertIn("disabled by default", readme)
        for alias in (
            'core.register_alias("mapgen_stone"',
            'core.register_alias("mapgen_water_source"',
            'core.register_alias("mapgen_river_water_source"',
            'core.register_alias("mapgen_lava_source"',
            'core.register_alias("mapgen_dirt"',
            'core.register_alias("mapgen_dirt_with_grass"',
            'core.register_alias("mapgen_sand"',
            'core.register_alias("mapgen_cobble"',
        ):
            self.assertIn(alias, base_mod)
        self.assertIn('local helper_entity_name = "ai_runtime_base:helper"', base_mod)
        self.assertIn('core.register_entity(":" .. helper_entity_name', base_mod)
        self.assertIn("agent_entity_name = helper_entity_name", base_mod)
        self.assertNotIn("ai_demo_benchmark:helper", base_mod)
        self.assertNotIn("first_mod", game_conf)
        self.assertNotIn("last_mod", game_conf)
        self.assertNotRegex(profile_text, r"\bdevtest\b|testnodes:", re.I)
        self.assertNotRegex(profile_text, PRIVATE_PATTERNS)

    def test_fixture_and_benchmark_commands_require_explicit_dev_settings(self):
        self.assertTrue(SMOKE_LUA.is_file(), f"missing {SMOKE_LUA}")
        self.assertTrue(DEMO_BENCHMARK_LUA.is_file(), f"missing {DEMO_BENCHMARK_LUA}")
        self.assertTrue(MODEL_ADAPTER_PLUGIN_LUA.is_file(), f"missing {MODEL_ADAPTER_PLUGIN_LUA}")
        self.assertTrue(AI_RUNTIME_UNITTEST.is_file(), f"missing {AI_RUNTIME_UNITTEST}")

        smoke_lua = SMOKE_LUA.read_text(encoding="utf-8")
        demo_lua = DEMO_BENCHMARK_LUA.read_text(encoding="utf-8")
        adapter_lua = MODEL_ADAPTER_PLUGIN_LUA.read_text(encoding="utf-8")
        unittest_cpp = AI_RUNTIME_UNITTEST.read_text(encoding="utf-8")

        self.assertIn('core.settings:get_bool("ai_runtime.enable_smoke_command", false)', smoke_lua)
        self.assertIn('core.settings:get_bool("ai_runtime.enable_demo_benchmark_command", false)', demo_lua)
        self.assertIn(
            'core.settings:get_bool("ai_runtime.enable_model_adapter_probe_command", false)',
            adapter_lua,
        )
        agents_sdk_adapter_lua = AGENTS_SDK_ADAPTER_PLUGIN_LUA.read_text(encoding="utf-8")
        self.assertIn(
            'core.settings:get_bool("ai_runtime.enable_agents_sdk_adapter", false)',
            agents_sdk_adapter_lua,
        )
        self.assertLess(
            smoke_lua.find('core.settings:get_bool("ai_runtime.enable_smoke_command", false)'),
            smoke_lua.find('core.register_chatcommand("ai_runtime_smoke"'),
        )
        self.assertLess(
            demo_lua.find('core.settings:get_bool("ai_runtime.enable_demo_benchmark_command", false)'),
            demo_lua.find('core.register_chatcommand("ai_demo_entity_benchmark"'),
        )
        self.assertLess(
            adapter_lua.find(
                'core.settings:get_bool("ai_runtime.enable_model_adapter_probe_command", false)'
            ),
            adapter_lua.find('core.register_chatcommand("ai_model_adapter_probe"'),
        )
        self.assertLess(
            agents_sdk_adapter_lua.find(
                'core.settings:get_bool("ai_runtime.enable_agents_sdk_adapter", false)'
            ),
            agents_sdk_adapter_lua.find('core.register_chatcommand("ai_agents_sdk_adapter_probe"'),
        )
        self.assertIn(
            'core.register_chatcommand("ai_agents_sdk_adapter_probe_async"',
            agents_sdk_adapter_lua,
        )
        self.assertIn('g_settings->setBool("ai_runtime.enable_smoke_command", true)', unittest_cpp)
        self.assertIn('g_settings->setBool("ai_runtime.enable_demo_benchmark_command", true)', unittest_cpp)
        self.assertIn(
            'g_settings->setBool("ai_runtime.enable_model_adapter_probe_command", true)',
            unittest_cpp,
        )
        self.assertIn(
            'g_settings->setBool("ai_runtime.enable_agents_sdk_adapter", true)',
            unittest_cpp,
        )

    def test_profile_declares_first_party_agent_capability_policy(self):
        base_mod = BASE_MOD.read_text(encoding="utf-8")

        self.assertIn("core.ai_agent_plugin.configure", base_mod)
        self.assertIn('capability_profile = "clean"', base_mod)
        self.assertIn("agent_entity_name = helper_entity_name", base_mod)
        self.assertIn("capabilities = {", base_mod)
        for capability in (
            "world.read",
            "world.place",
            "world.remove",
            "entity.spawn",
            "entity.control",
            "task.cancel",
            "http.llm",
        ):
            self.assertIn(f'["{capability}"] = true', base_mod)
        for forbidden in (
            "admin.override",
            "import.assets",
            "player.teleport.other",
            "combat.defend",
        ):
            self.assertNotIn(forbidden, base_mod)

    def test_agents_sdk_profile_bridge_only_provides_http_handle(self):
        self.assertTrue(AGENTS_SDK_BRIDGE_MOD.is_file(), f"missing {AGENTS_SDK_BRIDGE_MOD}")
        body = AGENTS_SDK_BRIDGE_MOD.read_text(encoding="utf-8")

        self.assertIn("core.ai_agents_sdk_adapter_plugin", body)
        self.assertIn("core.request_http_api", body)
        self.assertIn("bridge.configure", body)
        self.assertIn("http_api = core.request_http_api()", body)
        self.assertNotRegex(body, PRIVATE_PATTERNS)
        for forbidden in (
            "OPENAI",
            "http://",
            "https://",
            "world.place",
            "world.remove",
            "set_node",
            "remove_node",
            "register_chatcommand",
        ):
            self.assertNotIn(forbidden, body)

    def test_profile_is_tracked_despite_generated_games_ignore_rule(self):
        ignored = subprocess.run(
            ["git", "check-ignore", "-q", "games/ai_runtime/game.conf"],
            cwd=ROOT,
            check=False,
        )
        self.assertNotEqual(ignored.returncode, 0, "games/ai_runtime must not be ignored")

        gitignore = GITIGNORE.read_text(encoding="utf-8")
        self.assertIn("!/games/ai_runtime/", gitignore)
        self.assertIn("!/games/ai_runtime/**", gitignore)

    def test_profile_has_install_wiring(self):
        cmake = CMAKE.read_text(encoding="utf-8")
        self.assertIn("INSTALL_AI_RUNTIME_PROFILE", cmake)
        self.assertIn("games/ai_runtime", cmake)

    def test_docs_explain_local_profile_and_boundaries(self):
        self.assertTrue(DOC.is_file(), f"missing {DOC}")
        body = DOC.read_text(encoding="utf-8")
        readme = RUNTIME_README.read_text(encoding="utf-8")

        for phrase in (
            "--gameid ai_runtime",
            "local/worlds/ai-runtime-profile",
            "/ai_runtime_smoke",
            "no live server",
            "no private world",
            "no model-network",
            "issue #72",
            "after `util/ai_native_runtime_verify.py`",
        ):
            self.assertIn(phrase, body)
        self.assertIn("non-devtest-server-profile.md", readme)
        self.assertNotRegex(body, r"\bdevtest\b|testnodes:", re.I)
        self.assertNotRegex(body, PRIVATE_PATTERNS)

    def test_capability_profiles_are_documented_and_public_safe(self):
        self.assertTrue(CAPABILITY_PROFILES_DOC.is_file(), f"missing {CAPABILITY_PROFILES_DOC}")
        body = CAPABILITY_PROFILES_DOC.read_text(encoding="utf-8")
        readme = RUNTIME_README.read_text(encoding="utf-8")

        for phrase in (
            "Clean Profile",
            "Operator Profile",
            "Family-Plugin Profile",
            "capability_profile = \"clean\"",
            "capability_profile = \"operator\"",
            "admin.override",
            "audit",
            "explicit opt-in",
            "outside the core engine fork",
        ):
            self.assertIn(phrase, body)
        self.assertIn("agent-capability-profiles.md", readme)
        self.assertNotRegex(body, PRIVATE_PATTERNS)


if __name__ == "__main__":
    unittest.main()
