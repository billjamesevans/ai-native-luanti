import importlib.util
import json
import pathlib
import subprocess
import sys
import tempfile
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[2]
GATE = ROOT / "util" / "ai_native_agent_request_response_log_gate.py"


def load_gate_module():
    spec = importlib.util.spec_from_file_location("ai_native_agent_request_response_log_gate", GATE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def log_entry(
    *,
    prompt: str,
    selected_option_id: str,
    tool_decision_source: str = "agents_sdk_function_tool",
    required_tool_calls_satisfied: bool = True,
    missing_required_tool_calls=None,
    message: str = "Selected a bounded Luanti build option.",
) -> dict:
    required = [
        "inspect_build_site_context",
        "recall_build_prompt_memory",
        "select_build_option",
        "plan_build_actions",
    ]
    option = {
        "selected_option_id": selected_option_id,
        "candidate_count": 4,
        "direct_world_mutation": False,
    }
    if selected_option_id.startswith("generated_"):
        required.append("propose_build_option")
        option.update({
            "generated_option_status": "ready",
            "generated_option": {
                "option_id": selected_option_id,
                "build_kind": "platform",
                "build_material_name": "stone",
                "planned_node_writes": 12,
            },
        })
    missing = list(missing_required_tool_calls or [])
    trace_names = [
        "inspect_build_site_context",
        "recall_build_prompt_memory",
    ]
    if selected_option_id.startswith("generated_"):
        trace_names.append("propose_build_option")
    trace_names.extend([
        "select_build_option",
        "plan_build_actions",
    ])
    trace_names = [name for name in trace_names if name not in set(missing)]
    plan = {
        "status": "ready",
        "selected_option_id": selected_option_id,
        "step_count": 4,
        "direct_world_mutation": False,
        "world_mutation_authority": "luanti",
    }
    return {
        "schema_version": 1,
        "event_kind": "ai_native_agents_sdk_request_response",
        "created_at": "2026-06-30T20:00:00Z",
        "adapter_name": "openai-agents-sdk-model-adapter",
        "request": {
            "request_kind": "ai_native_model_adapter_request",
            "adapter_contract": "provider_neutral_v1",
            "agent_id": "nova_agent:Gate:builder",
            "owner": "Gate",
            "task_id": f"gate:{selected_option_id}",
            "public_prompt": f"Plan a Luanti build request. Player request: {prompt}",
            "context": {
                "intent": "build_planning",
                "player_request": prompt,
                "candidate_summary": "platform:platform:stone:4|fire:fire:fire:1|tnt_wall:wall:tnt:12",
                "surface_id": "builder",
            },
            "safety": {"public_safe_request": True},
            "bounds": {"max_response_bytes": 4000},
        },
        "response": {
            "response_kind": "ai_native_model_adapter_response",
            "adapter_contract": "provider_neutral_v1",
            "ok": True,
            "message": message,
            "adapter_name": "openai-agents-sdk-model-adapter",
            "response": {
                "agentic_execution": True,
                "selected_option_id": selected_option_id,
                "tool_decision_source": tool_decision_source,
                "required_tool_calls": required,
                "missing_required_tool_calls": missing,
                "required_tool_calls_satisfied": required_tool_calls_satisfied,
                "tool_trace": [{"tool_name": name} for name in trace_names],
                "build_action_plan": plan,
                "tool_decisions": {
                    "build_option": option,
                    "build_action_plan": plan,
                },
                "world_mutation_authority": "luanti",
            },
        },
    }


def passing_entries() -> list[dict]:
    return [
        log_entry(prompt="build a fire", selected_option_id="fire"),
        log_entry(prompt="build me a fire and only a fire", selected_option_id="fire"),
        log_entry(prompt="build a wall of tnt", selected_option_id="tnt_wall"),
        log_entry(prompt="build a small shelter", selected_option_id="generated_shelter_floor"),
        log_entry(
            prompt="build a 6 wide 2 high lookout wall",
            selected_option_id="generated_dimensioned_wall",
        ),
    ]


def write_jsonl(path: pathlib.Path, entries: list[dict]) -> None:
    path.write_text(
        "".join(json.dumps(entry, sort_keys=True) + "\n" for entry in entries),
        encoding="utf-8",
    )


class AgentRequestResponseLogGateTests(unittest.TestCase):
    def test_passes_when_critical_prompts_have_agent_tool_evidence(self):
        module = load_gate_module()
        with tempfile.TemporaryDirectory() as tmpdir:
            log_path = pathlib.Path(tmpdir) / "agents-sdk-model-adapter.jsonl"
            write_jsonl(log_path, passing_entries())

            report = module.build_report(
                log_paths=[log_path],
                generated_at="2026-06-30T20:00:00Z",
            )

        self.assertEqual(report["status"], "pass", report)
        self.assertEqual(report["source_summary"]["cases_passed"], 5)
        self.assertEqual(report["source_summary"]["entries_read"], 5)
        by_id = {case["case_id"]: case for case in report["cases"]}
        self.assertEqual(
            by_id["fire_only_strict"]["observed"]["response"]["selected_option_id"],
            "fire",
        )
        self.assertEqual(
            by_id["tnt_wall"]["observed"]["response"]["selected_option_id"],
            "tnt_wall",
        )
        self.assertEqual(
            by_id["generated_build_option"]["observed"]["response"]["selected_option_id"],
            "generated_shelter_floor",
        )
        self.assertEqual(
            by_id["generated_dimensioned_wall"]["observed"]["response"]["selected_option_id"],
            "generated_dimensioned_wall",
        )

    def test_fails_when_fire_only_selects_generic_structure(self):
        module = load_gate_module()
        entries = passing_entries()
        entries[1] = log_entry(
            prompt="build me a fire and only a fire",
            selected_option_id="platform",
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            log_path = pathlib.Path(tmpdir) / "agents-sdk-model-adapter.jsonl"
            write_jsonl(log_path, entries)

            report = module.build_report(log_paths=[log_path])

        self.assertEqual(report["status"], "fail")
        fire_only = next(case for case in report["cases"] if case["case_id"] == "fire_only_strict")
        self.assertIn("selected_option_id_mismatch", fire_only["failures"])

    def test_fails_when_tnt_wall_is_refused_as_dangerous(self):
        module = load_gate_module()
        entries = passing_entries()
        entries[2] = log_entry(
            prompt="build a wall of tnt",
            selected_option_id="tnt_wall",
            message="I cannot build that because TNT is dangerous.",
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            log_path = pathlib.Path(tmpdir) / "agents-sdk-model-adapter.jsonl"
            write_jsonl(log_path, entries)

            report = module.build_report(log_paths=[log_path])

        self.assertEqual(report["status"], "fail")
        tnt = next(case for case in report["cases"] if case["case_id"] == "tnt_wall")
        self.assertIn("danger_refusal_detected", tnt["failures"])

    def test_fails_when_generated_option_missing_propose_tool_trace(self):
        module = load_gate_module()
        entries = passing_entries()
        entries[3] = log_entry(
            prompt="build a small shelter",
            selected_option_id="generated_shelter_floor",
            required_tool_calls_satisfied=False,
            missing_required_tool_calls=["propose_build_option"],
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            log_path = pathlib.Path(tmpdir) / "agents-sdk-model-adapter.jsonl"
            write_jsonl(log_path, entries)

            report = module.build_report(log_paths=[log_path])

        self.assertEqual(report["status"], "fail")
        generated = next(case for case in report["cases"] if case["case_id"] == "generated_build_option")
        self.assertIn("required_tool_calls_not_satisfied", generated["failures"])
        self.assertIn("missing_required_tool_calls_present", generated["failures"])
        self.assertIn("tool_trace_incomplete", generated["failures"])

    def test_fails_when_generated_option_selected_before_propose_tool(self):
        module = load_gate_module()
        entries = passing_entries()
        body = entries[3]["response"]["response"]
        body["tool_trace"] = [
            {"tool_name": "inspect_build_site_context"},
            {"tool_name": "recall_build_prompt_memory"},
            {
                "tool_name": "select_build_option",
                "args": {"selected_option_id": "generated_shelter_floor"},
                "result": {
                    "selected_option_id": None,
                    "selection_status": "rejected",
                    "generated_option_status": "tool_call_required",
                },
            },
            {"tool_name": "propose_build_option", "result": {"status": "ready"}},
            {
                "tool_name": "select_build_option",
                "args": {"selected_option_id": "generated_shelter_floor"},
                "result": {
                    "selected_option_id": "generated_shelter_floor",
                    "selection_status": "accepted",
                },
            },
            {"tool_name": "plan_build_actions"},
        ]
        with tempfile.TemporaryDirectory() as tmpdir:
            log_path = pathlib.Path(tmpdir) / "agents-sdk-model-adapter.jsonl"
            write_jsonl(log_path, entries)

            report = module.build_report(log_paths=[log_path])

        self.assertEqual(report["status"], "fail")
        generated = next(case for case in report["cases"] if case["case_id"] == "generated_build_option")
        self.assertIn("generated_select_before_propose", generated["failures"])
        self.assertTrue(
            generated["observed"]["response"]["generated_select_before_propose"]
        )

    def test_cli_writes_report(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            log_path = root / "agents-sdk-model-adapter.jsonl"
            output = root / "log-gate.json"
            write_jsonl(log_path, passing_entries())

            completed = subprocess.run(
                [
                    sys.executable,
                    str(GATE),
                    "--root",
                    str(root),
                    "--agents-sdk-log",
                    str(log_path),
                    "--output",
                    str(output),
                    "--generated-at",
                    "2026-06-30T20:00:00Z",
                ],
                cwd=ROOT,
                text=True,
                capture_output=True,
                check=False,
            )

            self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
            report = json.loads(output.read_text(encoding="utf-8"))
            summary = json.loads(completed.stdout)

        self.assertEqual(report["artifact_kind"], "ai_native_agent_request_response_log_gate")
        self.assertEqual(summary["cases_passed"], 5)


if __name__ == "__main__":
    unittest.main()
