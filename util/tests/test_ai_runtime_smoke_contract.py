import pathlib
import re
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[2]
DOC = ROOT / "doc" / "ai-native-runtime" / "synthetic-runtime-smoke.md"
README = ROOT / "doc" / "ai-native-runtime" / "README.md"

PRIVATE_PATTERNS = re.compile(
    r"minecraftpi|192\.168|spacebase|themepark|showcase100|disneyland100|"
    r"sk-[A-Za-z0-9_-]{20,}|OPENAI_API_KEY|private_prompt|asset_payload|/Users/",
    re.I,
)


class AIRuntimeSmokeContractTests(unittest.TestCase):
    def test_smoke_doc_covers_task_loop_summary_and_privacy_boundary(self):
        self.assertTrue(DOC.is_file(), f"missing {DOC}")
        body = DOC.read_text(encoding="utf-8")
        readme = README.read_text(encoding="utf-8")

        for phrase in (
            "core.ai_runtime_smoke.run_scenario",
            "synthetic-task-loop-smoke",
            "bounded build-agent task",
            "repair-agent apply task",
            "rollback metadata",
            "blocked_or_unsafe_outcomes",
            "audit_event_count",
            "bin/luantiserver --run-unittests --test-module TestAIRuntime",
            "util/ai_native_benchmark_gate.py",
            "no live server",
            "backup-first",
        ):
            self.assertIn(phrase, body)
        self.assertIn("synthetic-runtime-smoke.md", readme)
        self.assertNotRegex(body, PRIVATE_PATTERNS)


if __name__ == "__main__":
    unittest.main()
