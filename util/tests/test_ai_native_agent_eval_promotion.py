import importlib.util
import json
import pathlib
import re
import subprocess
import sys
import tempfile
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[2]
QUEUE = ROOT / "util" / "ai_native_agent_eval_queue.py"
PROMOTE = ROOT / "util" / "ai_native_agent_eval_promote.py"
README = ROOT / "doc" / "ai-native-runtime" / "README.md"
OPERATING_LOOP = ROOT / "doc" / "ai-native-runtime" / "project-operating-loop.md"
ADAPTER_DOC = ROOT / "doc" / "ai-native-runtime" / "agents-sdk-model-adapter.md"
FIRST_PARTY_AGENT_DOC = ROOT / "doc" / "ai-native-runtime" / "first-party-agent-plugin.md"

PRIVATE_PATTERNS = re.compile(
    r"minecraftpi|192\.168|spacebase|themepark|showcase100|disneyland100|"
    r"(?<![A-Za-z0-9_-])sk-[A-Za-z0-9_-]{20,}|OPENAI_API_KEY|private_prompt|asset_payload|/Users/",
    re.I,
)
DOC_PRIVATE_PATTERNS = re.compile(
    r"minecraftpi|192\.168|spacebase|themepark|showcase100|disneyland100|"
    r"(?<![A-Za-z0-9_-])sk-[A-Za-z0-9_-]{20,}|/Users/",
    re.I,
)


def load_module(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def agents_sdk_log_entry(prompt="build me a fire and only a fire"):
    return {
        "schema_version": 1,
        "event_kind": "ai_native_agents_sdk_request_response",
        "created_at": "2026-06-30T12:00:00Z",
        "adapter_name": "openai-agents-sdk-model-adapter",
        "request": {
            "request_kind": "ai_native_model_adapter_request",
            "adapter_contract": "provider_neutral_v1",
            "agent_id": "nova_agent:Eval:guide",
            "owner": "Eval",
            "task_id": "ai-agent-eval:model",
            "public_prompt": prompt,
            "context": {"surface_id": "guide", "capabilities": "world.read,http.llm"},
            "safety": {"public_safe_request": True},
            "bounds": {"max_response_bytes": 4000},
        },
        "response": {
            "response_kind": "ai_native_model_adapter_response",
            "adapter_contract": "provider_neutral_v1",
            "ok": True,
            "message": "Use bounded planning.",
            "adapter_name": "openai-agents-sdk-model-adapter",
            "response": {
                "agentic_execution": True,
                "tools_enabled": ["select_build_option", "recommend_build_option"],
                "world_mutation_authority": "luanti",
            },
        },
    }


def agents_sdk_generated_option_entry():
    entry = agents_sdk_log_entry("AI-native Luanti model adapter request.")
    entry["request"]["context"].update({
        "intent": "build_planning",
        "player_request": "build a 6 wide 2 high lookout wall",
        "candidate_summary": "platform:platform:default:4|wall:wall:default:12",
    })
    generated = {
        "option_id": "generated_dimensioned_wall",
        "build_kind": "wall",
        "build_width": 6,
        "build_height": 2,
        "build_material_name": "stone",
        "planned_node_writes": 12,
    }
    select_result = {
        "selected_option_id": "generated_dimensioned_wall",
        "selection_status": "accepted",
        "candidate_count": 3,
        "decision_source": "agent_selected_generated_build_option",
        "generated_option_status": "ready",
        "generated_option": generated,
        "direct_world_mutation": False,
    }
    plan_result = {
        "status": "ready",
        "selected_option_id": "generated_dimensioned_wall",
        "step_count": 4,
        "direct_world_mutation": False,
        "world_mutation_authority": "luanti",
    }
    entry["response"]["response"].update({
        "agentic_execution": True,
        "tools_enabled": [
            "recall_build_prompt_memory",
            "propose_build_option",
            "select_build_option",
            "plan_build_actions",
        ],
        "selected_option_id": "generated_dimensioned_wall",
        "tool_decision_source": "agents_sdk_function_tool",
        "required_tool_calls": [
            "recall_build_prompt_memory",
            "select_build_option",
            "plan_build_actions",
            "propose_build_option",
        ],
        "missing_required_tool_calls": [],
        "required_tool_calls_satisfied": True,
        "world_mutation_authority": "luanti",
        "tool_trace": [
            {"tool_name": "recall_build_prompt_memory", "result": {}},
            {
                "tool_name": "propose_build_option",
                "result": {"status": "ready", "generated_option": generated},
            },
            {"tool_name": "select_build_option", "result": select_result},
            {"tool_name": "plan_build_actions", "result": plan_result},
        ],
        "build_action_plan": plan_result,
        "tool_decisions": {
            "build_option": select_result,
            "build_action_plan": plan_result,
        },
    })
    return entry


def agents_sdk_fire_tool_entry():
    entry = agents_sdk_log_entry("AI-native Luanti model adapter request.")
    entry["request"]["context"].update({
        "intent": "build_planning",
        "player_request": "build me a fire and only a fire",
        "candidate_summary": "fire:fire:fire:1|platform:platform:stone:4",
    })
    entry["response"]["response"].update({
        "agentic_execution": True,
        "tools_enabled": [
            "recall_build_prompt_memory",
            "select_build_option",
            "plan_build_actions",
        ],
        "selected_option_id": "fire",
        "tool_decision_source": "agents_sdk_function_tool",
        "required_tool_calls": [
            "recall_build_prompt_memory",
            "select_build_option",
            "plan_build_actions",
        ],
        "missing_required_tool_calls": [],
        "required_tool_calls_satisfied": True,
        "tool_trace": [
            {"tool_name": "recall_build_prompt_memory", "result": {}},
            {
                "tool_name": "select_build_option",
                "result": {
                    "selected_option_id": "fire",
                    "selection_status": "accepted",
                    "decision_source": "agent_selected_build_option",
                    "direct_world_mutation": False,
                },
            },
            {
                "tool_name": "plan_build_actions",
                "result": {
                    "status": "ready",
                    "selected_option_id": "fire",
                    "step_count": 3,
                    "direct_world_mutation": False,
                    "world_mutation_authority": "luanti",
                },
            },
        ],
        "tool_decisions": {
            "build_option": {
                "selected_option_id": "fire",
                "decision_source": "agent_selected_build_option",
            },
            "build_action_plan": {
                "status": "ready",
                "selected_option_id": "fire",
                "step_count": 3,
                "world_mutation_authority": "luanti",
            },
        },
        "world_mutation_authority": "luanti",
    })
    return entry


def nova_agent_fire_tool_entry():
    return {
        "ts": "2026-06-30T12:05:00Z",
        "player": "Eval",
        "prompt": "build me a fire and only a fire",
        "source": "agent_tool_contract_fast_path",
        "ok": True,
        "label": "single fire",
        "message": "Building one fire.",
        "tool_decision_source": "local_agent_tool_contract_fast_path",
        "required_tool_calls": [
            "recall_build_prompt_memory",
            "analyze_build_intent",
            "draft_build_options",
            "validate_plan_contract",
            "submit_nova_plan",
        ],
        "missing_required_tool_calls": [],
        "required_tool_calls_satisfied": True,
        "contract_satisfied": True,
        "prompt_contract": {
            "contract_kind": "single_fire",
            "contract_required": True,
        },
        "actions": [
            {
                "type": "place_node",
                "material": "fire",
                "count": 1,
            }
        ],
        "tool_trace": [
            {"tool_name": "recall_build_prompt_memory"},
            {"tool_name": "analyze_build_intent"},
            {"tool_name": "draft_build_options"},
            {"tool_name": "validate_plan_contract"},
            {"tool_name": "submit_nova_plan"},
        ],
    }


def nova_trace_line(prompt="build a wall of tnt"):
    payload = {
        "schema_version": 1,
        "event_kind": "nova_request_trace",
        "event": "completed",
        "trace": {
            "trace_id": "nova_trace:99",
            "owner": "Eval",
            "agent_id": "nova_agent:Eval:builder",
            "action": "build",
            "route": "deterministic_build_parser",
            "public_prompt": prompt,
            "completed_us": 123456,
            "response": {
                "ok": True,
                "status": "pending_approval",
                "action": "build",
                "build_kind": "wall",
                "build_material_name": "tnt",
                "planned_node_writes": 12,
            },
        },
    }
    return "[ai_agent_plugin] request_trace=" + json.dumps(payload, sort_keys=True)


def operator_labels_payload(prompt="build a bridge"):
    return {
        "schema_version": 1,
        "artifact_kind": "ai_native_agent_eval_operator_labels",
        "labels": [
            {
                "label_id": "reviewed_stone_bridge_platform",
                "prompt": prompt,
                "case_hint": "stone_bridge_platform",
                "expected": {
                    "action": "build",
                    "build_kind": "platform",
                    "build_material_name": "stone",
                    "planned_node_writes": 12,
                    "route": "agentic_build_planner",
                },
            }
        ],
    }


def candidate_queue_payload(operator_label_payloads=None):
    queue = load_module(QUEUE, "ai_native_agent_eval_queue_for_promotion")
    with tempfile.TemporaryDirectory() as tmpdir:
        root = pathlib.Path(tmpdir)
        sidecar_log = root / "agents-sdk-model-adapter.jsonl"
        action_log = root / "debug.log"
        sidecar_log.write_text(
            "\n".join([
                json.dumps(agents_sdk_log_entry("build me a fire and only a fire")),
                json.dumps(agents_sdk_log_entry("what can you plan with tools next?")),
            ]) + "\n",
            encoding="utf-8",
        )
        action_log.write_text(nova_trace_line() + "\n", encoding="utf-8")
        return queue.build_eval_candidate_queue(
            agents_sdk_logs=[sidecar_log],
            action_logs=[action_log],
            operator_label_payloads=operator_label_payloads or [],
            generated_at="2026-06-30T12:30:00Z",
        )


class AgentEvalPromotionTests(unittest.TestCase):
    def test_promotes_ready_candidates_to_runtime_case_pack(self):
        promote = load_module(PROMOTE, "ai_native_agent_eval_promote_test")
        queue_payload = candidate_queue_payload()

        pack = promote.build_case_pack(
            queue_payload,
            generated_at="2026-06-30T13:00:00Z",
            source_path="local/benchmarks/candidate-queue.json",
        )

        self.assertEqual(pack["artifact_kind"], "ai_native_agent_prompt_eval_case_pack")
        self.assertEqual(pack["status"], "ready")
        self.assertEqual(pack["summary"]["source_candidates_total"], 3)
        self.assertEqual(pack["summary"]["cases_total"], 2)
        self.assertEqual(pack["summary"]["ignored_not_ready"], 1)
        self.assertEqual(pack["runtime"]["runner"], "core.ai_agent_plugin.run_prompt_eval")
        self.assertEqual(pack["runtime"]["cases_option"], "custom")
        self.assertTrue(pack["safety"]["public_safe_output"])
        self.assertFalse(PRIVATE_PATTERNS.search(json.dumps(pack, sort_keys=True)))

        by_hint = {case["case_hint"]: case for case in pack["cases"]}
        fire = by_hint["fire_only_strict"]
        self.assertTrue(fire["case_id"].startswith("promoted_fire_only_strict_"))
        self.assertEqual(fire["prompt"], "build me a fire and only a fire")
        self.assertEqual(fire["expected"]["build_kind"], "fire")
        self.assertEqual(fire["expected"]["build_material_name"], "fire")
        self.assertEqual(fire["expected"]["planned_node_writes"], 1)
        self.assertEqual(fire["expected"]["route"], "deterministic_build_parser")

        tnt = by_hint["tnt_wall"]
        self.assertEqual(tnt["expected"]["build_kind"], "wall")
        self.assertEqual(tnt["expected"]["build_material_name"], "tnt")
        self.assertEqual(tnt["expected"]["planned_node_writes"], 12)
        self.assertFalse(tnt["expected"]["danger_refusal_allowed"])

    def test_promotes_generated_option_dimensions_to_runtime_case_pack(self):
        promote = load_module(PROMOTE, "ai_native_agent_eval_promote_generated")
        queue = load_module(QUEUE, "ai_native_agent_eval_queue_generated_fixture")
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            sidecar_log = root / "agents-sdk-model-adapter.jsonl"
            sidecar_log.write_text(
                json.dumps(agents_sdk_generated_option_entry()) + "\n",
                encoding="utf-8",
            )
            queue_payload = queue.build_eval_candidate_queue(
                agents_sdk_logs=[sidecar_log],
                generated_at="2026-06-30T12:30:00Z",
            )

        pack = promote.build_case_pack(
            queue_payload,
            generated_at="2026-06-30T13:00:00Z",
        )

        self.assertEqual(pack["status"], "ready")
        self.assertEqual(pack["summary"]["cases_total"], 1)
        case = pack["cases"][0]
        self.assertEqual(case["case_hint"], "generated_dimensioned_wall")
        self.assertEqual(case["prompt"], "build a 6 wide 2 high lookout wall")
        self.assertEqual(case["expected"]["route"], "agentic_build_planner")
        self.assertEqual(case["expected"]["selected_candidate_id"], "generated_dimensioned_wall")
        self.assertEqual(case["expected"]["build_kind"], "wall")
        self.assertEqual(case["expected"]["build_material_name"], "stone")
        self.assertEqual(case["expected"]["planned_node_writes"], 12)
        self.assertEqual(case["expected"]["build_width"], 6)
        self.assertEqual(case["expected"]["build_height"], 2)

    def test_selected_candidate_filter_promotes_only_requested_candidate(self):
        promote = load_module(PROMOTE, "ai_native_agent_eval_promote_selected")
        queue_payload = candidate_queue_payload()
        fire_candidate_id = next(
            candidate["candidate_id"]
            for candidate in queue_payload["candidates"]
            if candidate["case_hint"] == "fire_only_strict"
        )

        pack = promote.build_case_pack(
            queue_payload,
            generated_at="2026-06-30T13:00:00Z",
            selected_candidate_ids={fire_candidate_id},
        )

        self.assertEqual(pack["status"], "ready")
        self.assertEqual(pack["summary"]["cases_total"], 1)
        self.assertEqual(pack["cases"][0]["source_candidate_id"], fire_candidate_id)
        self.assertEqual(pack["cases"][0]["case_hint"], "fire_only_strict")

    def test_promotes_operator_labeled_candidate_with_overlay_provenance(self):
        promote = load_module(PROMOTE, "ai_native_agent_eval_promote_operator_label")
        queue = load_module(QUEUE, "ai_native_agent_eval_queue_operator_label_fixture")
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            sidecar_log = root / "agents-sdk-model-adapter.jsonl"
            sidecar_log.write_text(
                json.dumps(agents_sdk_log_entry("build a bridge")) + "\n",
                encoding="utf-8",
            )
            queue_payload = queue.build_eval_candidate_queue(
                agents_sdk_logs=[sidecar_log],
                operator_label_payloads=[operator_labels_payload()],
                generated_at="2026-06-30T12:30:00Z",
            )

        pack = promote.build_case_pack(
            queue_payload,
            generated_at="2026-06-30T13:00:00Z",
        )

        self.assertEqual(pack["status"], "ready")
        self.assertEqual(pack["summary"]["cases_total"], 1)
        case = pack["cases"][0]
        self.assertEqual(case["case_hint"], "stone_bridge_platform")
        self.assertEqual(case["prompt"], "build a bridge")
        self.assertEqual(case["expected"]["build_kind"], "platform")
        self.assertEqual(case["expected"]["build_material_name"], "stone")
        self.assertEqual(case["expected"]["planned_node_writes"], 12)
        self.assertEqual(case["promotion"]["mode"], "operator_label_overlay")
        self.assertEqual(case["promotion"]["review_status"], "operator_labeled_candidate_ready")
        self.assertFalse(case["promotion"]["default_gate_eligible"])
        self.assertTrue(case["promotion"]["requires_maintainer_review_before_default_gate"])
        self.assertFalse(PRIVATE_PATTERNS.search(json.dumps(pack, sort_keys=True)))

    def test_repeated_verified_agent_tool_case_can_enter_default_gate(self):
        promote = load_module(PROMOTE, "ai_native_agent_eval_promote_default_gate")
        queue = load_module(QUEUE, "ai_native_agent_eval_queue_default_gate_fixture")
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            sidecar_log = root / "agents-sdk-model-adapter.jsonl"
            nova_agent_log = root / "nova-agent-requests.jsonl"
            sidecar_log.write_text(
                json.dumps(agents_sdk_fire_tool_entry()) + "\n",
                encoding="utf-8",
            )
            nova_agent_log.write_text(
                json.dumps(nova_agent_fire_tool_entry()) + "\n",
                encoding="utf-8",
            )
            queue_payload = queue.build_eval_candidate_queue(
                agents_sdk_logs=[sidecar_log],
                nova_agent_logs=[nova_agent_log],
                generated_at="2026-06-30T12:30:00Z",
            )

        pack = promote.build_case_pack(
            queue_payload,
            generated_at="2026-06-30T13:00:00Z",
        )

        self.assertEqual(pack["status"], "ready")
        self.assertEqual(pack["summary"]["cases_total"], 1)
        self.assertEqual(pack["summary"]["default_gate_eligible_cases"], 1)
        self.assertEqual(pack["summary"]["review_required_cases"], 0)
        self.assertFalse(pack["summary"]["requires_maintainer_review_before_default_gate"])
        self.assertTrue(pack["safety"]["auto_default_gate_requires_verified_repeat"])
        self.assertTrue(pack["safety"]["auto_default_gate_requires_agent_tool_contract"])
        case = pack["cases"][0]
        self.assertEqual(case["case_hint"], "fire_only_strict")
        self.assertFalse(case["promotion"]["requires_maintainer_review_before_default_gate"])
        self.assertTrue(case["promotion"]["default_gate_eligible"])
        evidence = case["promotion"]["default_gate_evidence"]
        self.assertEqual(evidence["reason"], "verified_repeat_agent_tool_contract")
        self.assertEqual(evidence["independent_source_count"], 2)
        self.assertEqual(evidence["required_independent_source_count"], 2)
        self.assertEqual(
            evidence["source_kinds"],
            ["agents_sdk_request_response", "nova_agent_sidecar_request_response"],
        )
        self.assertFalse(PRIVATE_PATTERNS.search(json.dumps(pack, sort_keys=True)))

    def test_private_candidate_queue_fails_public_safety(self):
        promote = load_module(PROMOTE, "ai_native_agent_eval_promote_private")
        queue_payload = candidate_queue_payload()
        queue_payload["candidates"][0]["prompt"] = "leak private_prompt"

        pack = promote.build_case_pack(
            queue_payload,
            generated_at="2026-06-30T13:00:00Z",
        )

        self.assertEqual(pack["status"], "fail")
        self.assertFalse(pack["safety"]["public_safe_output"])
        self.assertTrue(pack["violations"])

    def test_cli_writes_case_pack(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            candidate_queue = root / "candidate-queue.json"
            output = root / "case-pack.json"
            candidate_queue.write_text(json.dumps(candidate_queue_payload()), encoding="utf-8")

            completed = subprocess.run(
                [
                    sys.executable,
                    str(PROMOTE),
                    "--root",
                    str(root),
                    "--candidate-queue",
                    str(candidate_queue),
                    "--output",
                    str(output),
                    "--generated-at",
                    "2026-06-30T13:00:00Z",
                ],
                cwd=ROOT,
                check=False,
                text=True,
                capture_output=True,
            )

            self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
            pack = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(pack["artifact_kind"], "ai_native_agent_prompt_eval_case_pack")
            self.assertEqual(pack["summary"]["cases_total"], 2)

    def test_docs_include_case_pack_promotion_path(self):
        bodies = [
            path.read_text(encoding="utf-8")
            for path in (README, OPERATING_LOOP, ADAPTER_DOC, FIRST_PARTY_AGENT_DOC)
        ]
        combined = "\n".join(bodies)
        self.assertIn("ai_native_agent_eval_promote.py", combined)
        self.assertIn("ai_native_agent_prompt_eval_case_pack", combined)
        self.assertIn("custom_cases", combined)
        self.assertIn("--operator-labels", combined)
        self.assertIn("--from-operator-feedback", combined)
        self.assertIn("/ai_agent_feedback", combined)
        self.assertIn("ai_native_agent_eval_operator_labels", combined)
        loop_sections = []
        for body in bodies:
            if "Agent Improvement Loop" not in body:
                continue
            section = body.split("Agent Improvement Loop", 1)[1]
            section = section.split("\n## ", 1)[0]
            loop_sections.append(section)
        self.assertGreaterEqual(len(loop_sections), 2)
        self.assertNotRegex("\n".join(loop_sections), DOC_PRIVATE_PATTERNS)


if __name__ == "__main__":
    unittest.main()
