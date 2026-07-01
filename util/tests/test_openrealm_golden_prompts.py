import importlib.util
import pathlib
import unittest

from util.tests.test_ai_native_agent_quality_gate import (
    adapter_eval_payload,
    candidate_queue_payload,
    case_pack_payload,
    live_prompt_eval_payload,
    review_queue_payload,
)


ROOT = pathlib.Path(__file__).resolve().parents[2]
QUALITY_GATE = ROOT / "util" / "ai_native_agent_quality_gate.py"
PROMPT_EVAL = ROOT / "util" / "ai_native_agent_prompt_eval_live_probe.py"


def load_module(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class OpenRealmGoldenPromptTests(unittest.TestCase):
    def test_live_prompt_eval_exposes_named_openrealm_golden_suite(self):
        prompt_eval = load_module(PROMPT_EVAL, "openrealm_prompt_eval_test")
        evidence = prompt_eval.validate_live_result(live_prompt_eval_payload())

        self.assertEqual(evidence["agent_prompt_eval_golden_prompt_suite"], "openrealm_creator_loop")
        self.assertEqual(evidence["agent_prompt_eval_golden_prompt_backlog_total"], 11)
        self.assertEqual(evidence["agent_prompt_eval_golden_prompts_total"], 4)
        self.assertEqual(evidence["agent_prompt_eval_golden_prompts_passed"], 4)
        self.assertEqual(evidence["agent_prompt_eval_golden_prompts_failed"], 0)

    def test_quality_gate_blocks_openrealm_golden_prompt_regression(self):
        quality_gate = load_module(QUALITY_GATE, "openrealm_quality_gate_test")
        live_eval = live_prompt_eval_payload()
        live_eval["summary"]["golden_prompt_case_ids"]["fire_only_strict"] = False
        live_eval["summary"]["golden_prompts_passed"] = 3
        live_eval["summary"]["golden_prompts_failed"] = 1

        report = quality_gate.build_quality_gate(
            candidate_queue=candidate_queue_payload(),
            case_pack=case_pack_payload(),
            review=review_queue_payload(),
            adapter_eval=adapter_eval_payload(),
            live_prompt_eval=live_eval,
            generated_at="2026-07-01T00:00:00Z",
        )

        self.assertEqual(report["status"], "fail")
        self.assertEqual(report["summary"]["live_prompt_eval_golden_prompts_failed"], 1)
        self.assertTrue(any(item["kind"] == "golden_prompt_regression" for item in report["violations"]))


if __name__ == "__main__":
    unittest.main()
