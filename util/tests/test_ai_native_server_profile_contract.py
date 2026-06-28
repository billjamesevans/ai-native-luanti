import pathlib
import re
import subprocess
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[2]
PROFILE_DIR = ROOT / "games" / "ai_runtime"
GAME_CONF = PROFILE_DIR / "game.conf"
README = PROFILE_DIR / "README.md"
BASE_MOD = PROFILE_DIR / "mods" / "ai_runtime_base" / "init.lua"
DOC = ROOT / "doc" / "ai-native-runtime" / "non-devtest-server-profile.md"
RUNTIME_README = ROOT / "doc" / "ai-native-runtime" / "README.md"
GITIGNORE = ROOT / ".gitignore"
CMAKE = ROOT / "CMakeLists.txt"

PRIVATE_PATTERNS = re.compile(
    r"minecraftpi|192\.168|spacebase|themepark|showcase100|disneyland100|"
    r"sk-[A-Za-z0-9_-]{20,}|OPENAI_API_KEY|private_prompt|asset_payload|/Users/",
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
        self.assertIn("/ai_runtime_smoke", readme)
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
        self.assertNotIn("first_mod", game_conf)
        self.assertNotIn("last_mod", game_conf)
        self.assertNotRegex(profile_text, r"\bdevtest\b|testnodes:", re.I)
        self.assertNotRegex(profile_text, PRIVATE_PATTERNS)

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


if __name__ == "__main__":
    unittest.main()
