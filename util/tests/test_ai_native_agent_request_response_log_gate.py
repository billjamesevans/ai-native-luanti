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


def nova_agent_log_entry(
    *,
    prompt: str,
    label: str,
    contract_kind: str,
    actions: list[dict],
    build_kind: str,
    build_material_name: str,
    planned_node_writes: int,
    message: str = "Submitted through Nova tools.",
    agent_model_called: bool = True,
    source: str = "agents_sdk_tool_plan",
    tool_decision_source: str = "agents_sdk_submit_nova_plan_tool",
    required_tool_calls_satisfied: bool = True,
    missing_required_tool_calls=None,
) -> dict:
    missing = list(missing_required_tool_calls or [])
    trace_names = [
        name
        for name in ("resolve_build_plan", "submit_nova_plan")
        if name not in set(missing)
    ]
    return {
        "ts": "2026-07-01T11:55:12Z",
        "player": "Eval",
        "prompt": prompt,
        "model": "gpt-4o-mini",
        "agent_runtime": "openai-agents-sdk",
        "agent_model_called": agent_model_called,
        "agent_model_status": "success_early_submit" if agent_model_called else "skipped",
        "fallback_reason": None,
        "source": source,
        "tool_decision_source": tool_decision_source,
        "required_tool_calls": ["resolve_build_plan", "submit_nova_plan"],
        "missing_required_tool_calls": missing,
        "required_tool_calls_satisfied": required_tool_calls_satisfied,
        "ok": True,
        "label": label,
        "message": message,
        "selected_option_id": "reviewed_prompt_memory",
        "build_kind": build_kind,
        "build_material_name": build_material_name,
        "planned_node_writes": planned_node_writes,
        "decision_reason": "Selected reviewed prompt memory because it satisfies the prompt contract.",
        "correction_source": "",
        "contract_satisfied": True,
        "prompt_contract": {
            "intent": "build",
            "material": build_material_name,
            "contract_kind": contract_kind,
            "contract_required": True,
            "policy": "game_materials_are_allowed_when_executor_bounds_apply",
        },
        "reviewed_prompt_memory": {
            "memory_available": True,
            "case_count": 11,
            "matched_case_id": f"promoted_{contract_kind}_abc123",
            "match_quality": "exact",
            "direct_world_mutation": False,
        },
        "build_options": [
            {
                "option_id": "reviewed_prompt_memory",
                "source": "reviewed_prompt_memory",
                "label": label,
                "build_kind": build_kind,
                "build_material_name": build_material_name,
                "planned_node_writes": planned_node_writes,
                "contract_satisfied": True,
                "action_count": len(actions),
            }
        ],
        "actions": actions,
        "tool_trace": [{"tool_name": name} for name in trace_names],
    }


def passing_nova_agent_entries() -> list[dict]:
    return [
        nova_agent_log_entry(
            prompt="build me a fire and only a fire",
            label="single fire",
            contract_kind="single_fire",
            build_kind="place_node",
            build_material_name="fire",
            planned_node_writes=1,
            actions=[
                {
                    "type": "place_node",
                    "material": "fire",
                    "offset": {"x": 0, "y": 1, "z": 0},
                    "count": 1,
                }
            ],
        ),
        nova_agent_log_entry(
            prompt="build a wall of tnt",
            label="tnt wall",
            contract_kind="tnt_wall",
            build_kind="wall",
            build_material_name="tnt",
            planned_node_writes=75,
            actions=[
                {
                    "type": "fill_box",
                    "material": "tnt",
                    "offset": {"x": 0, "y": 1, "z": 0},
                    "size": {"x": 15, "y": 5, "z": 1},
                }
            ],
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
        self.assertEqual(report["source_summary"]["nova_agent_log_entries_read"], 0)
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

    def test_accepts_nova_agent_log_as_live_proving_ground_contracts(self):
        module = load_gate_module()
        with tempfile.TemporaryDirectory() as tmpdir:
            log_path = pathlib.Path(tmpdir) / "nova-agent-requests.jsonl"
            write_jsonl(log_path, passing_nova_agent_entries())

            report = module.build_report(
                nova_agent_log_paths=[log_path],
                generated_at="2026-07-01T12:00:00Z",
            )

        self.assertEqual(report["status"], "pass", report)
        self.assertEqual(report["source_summary"]["case_count"], 2)
        self.assertEqual(report["source_summary"]["cases_passed"], 2)
        self.assertEqual(report["source_summary"]["entries_read"], 0)
        self.assertEqual(report["source_summary"]["nova_agent_log_entries_read"], 2)
        by_id = {case["case_id"]: case for case in report["cases"]}
        fire = by_id["nova_agent_fire_only_strict"]["observed"]["response"]
        self.assertTrue(fire["agent_model_called"])
        self.assertEqual(fire["tool_trace_names"], ["resolve_build_plan", "submit_nova_plan"])
        self.assertEqual(fire["actions"][0]["type"], "place_node")
        self.assertEqual(fire["actions"][0]["material"], "fire")
        tnt = by_id["nova_agent_tnt_wall"]["observed"]["response"]
        self.assertEqual(tnt["actions"][0]["type"], "fill_box")
        self.assertEqual(tnt["actions"][0]["material"], "tnt")
        self.assertEqual(tnt["computed_node_writes"], 75)

    def test_fails_nova_agent_fire_when_model_not_called_or_extra_structure_added(self):
        module = load_gate_module()
        entries = passing_nova_agent_entries()
        entries[0] = nova_agent_log_entry(
            prompt="build me a fire and only a fire",
            label="generic fire structure",
            contract_kind="single_fire",
            build_kind="house",
            build_material_name="fire",
            planned_node_writes=26,
            agent_model_called=False,
            actions=[
                {"type": "place_node", "material": "fire", "count": 1},
                {"type": "hollow_box", "material": "stone", "size": {"x": 5, "y": 4, "z": 5}},
            ],
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            log_path = pathlib.Path(tmpdir) / "nova-agent-requests.jsonl"
            write_jsonl(log_path, entries)

            report = module.build_report(nova_agent_log_paths=[log_path])

        self.assertEqual(report["status"], "fail")
        fire = next(case for case in report["cases"] if case["case_id"] == "nova_agent_fire_only_strict")
        self.assertIn("agent_model_not_called", fire["failures"])
        self.assertIn("action_count_mismatch", fire["failures"])
        self.assertIn("extra_structure_detected", fire["failures"])

    def test_fails_nova_agent_tnt_wall_when_refused_as_real_world_danger(self):
        module = load_gate_module()
        entries = passing_nova_agent_entries()
        entries[1]["message"] = "I cannot build that because TNT is dangerous in the real world."
        with tempfile.TemporaryDirectory() as tmpdir:
            log_path = pathlib.Path(tmpdir) / "nova-agent-requests.jsonl"
            write_jsonl(log_path, entries)

            report = module.build_report(nova_agent_log_paths=[log_path])

        self.assertEqual(report["status"], "fail")
        tnt = next(case for case in report["cases"] if case["case_id"] == "nova_agent_tnt_wall")
        self.assertIn("danger_refusal_detected", tnt["failures"])

    def test_accepts_generated_tool_completion_source(self):
        module = load_gate_module()
        entries = passing_entries()
        entries[3]["response"]["response"][
            "tool_decision_source"
        ] = "agents_sdk_generated_tool_completion"
        entries[4]["response"]["response"][
            "tool_decision_source"
        ] = "agents_sdk_generated_tool_completion"
        with tempfile.TemporaryDirectory() as tmpdir:
            log_path = pathlib.Path(tmpdir) / "agents-sdk-model-adapter.jsonl"
            write_jsonl(log_path, entries)

            report = module.build_report(
                log_paths=[log_path],
                generated_at="2026-06-30T20:00:00Z",
            )

        self.assertEqual(report["status"], "pass", report)
        by_id = {case["case_id"]: case for case in report["cases"]}
        self.assertEqual(
            by_id["generated_build_option"]["observed"]["response"]["tool_decision_source"],
            "agents_sdk_generated_tool_completion",
        )
        self.assertEqual(
            by_id["generated_dimensioned_wall"]["observed"]["response"]["tool_decision_source"],
            "agents_sdk_generated_tool_completion",
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

    def test_cli_accepts_nova_agent_log_only(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            log_path = root / "nova-agent-requests.jsonl"
            output = root / "nova-log-gate.json"
            write_jsonl(log_path, passing_nova_agent_entries())

            completed = subprocess.run(
                [
                    sys.executable,
                    str(GATE),
                    "--root",
                    str(root),
                    "--nova-agent-log",
                    str(log_path),
                    "--output",
                    str(output),
                    "--generated-at",
                    "2026-07-01T12:00:00Z",
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
        self.assertEqual(summary["cases_passed"], 2)
        self.assertEqual(summary["nova_agent_log_entries_read"], 2)


if __name__ == "__main__":
    unittest.main()
