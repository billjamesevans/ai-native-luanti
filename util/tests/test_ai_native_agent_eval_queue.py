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
README = ROOT / "doc" / "ai-native-runtime" / "README.md"
OPERATING_LOOP = ROOT / "doc" / "ai-native-runtime" / "project-operating-loop.md"
ADAPTER_DOC = ROOT / "doc" / "ai-native-runtime" / "agents-sdk-model-adapter.md"

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


def load_queue_module():
    assert QUEUE.is_file(), f"missing {QUEUE}"
    spec = importlib.util.spec_from_file_location("ai_native_agent_eval_queue", QUEUE)
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
            "context": {
                "surface_id": "guide",
                "capabilities": "world.read,http.llm",
            },
            "safety": {"public_safe_request": True},
            "bounds": {"max_response_bytes": 4000},
        },
        "response": {
            "response_kind": "ai_native_model_adapter_response",
            "adapter_contract": "provider_neutral_v1",
            "ok": True,
            "message": "Use the fire primitive only after Luanti preview approval.",
            "adapter_name": "openai-agents-sdk-model-adapter",
            "elapsed_us": 42,
            "response": {
                "agentic_execution": True,
                "tools_enabled": ["select_build_option", "recommend_build_option", "classify_world_action"],
                "world_mutation_authority": "luanti",
            },
        },
    }


def agents_sdk_missing_required_tool_entry():
    entry = agents_sdk_log_entry("AI-native Luanti model adapter request.")
    entry["request"]["context"].update({
        "intent": "build_planning",
        "player_request": "build me a tower",
        "candidate_summary": "platform:platform:default:4|wall:wall:default:12",
    })
    entry["response"]["message"] = "Fell back to bounded tower planning after missing SDK tool evidence."
    entry["response"]["response"].update({
        "agentic_execution": True,
        "selected_option_id": "generated_tower_wall",
        "tool_decision_source": "adapter_fallback_after_agent_missing_required_tool",
        "required_tool_calls": [
            "recall_build_prompt_memory",
            "select_build_option",
            "propose_build_option",
        ],
        "missing_required_tool_calls": ["propose_build_option"],
        "required_tool_calls_satisfied": False,
        "tool_trace": [
            {"tool_name": "recall_build_prompt_memory"},
            {"tool_name": "select_build_option"},
        ],
        "tool_decisions": {
            "build_option": {
                "selected_option_id": "generated_tower_wall",
                "decision_source": "agent_selected_generated_build_option",
                "generated_option_status": "ready",
                "direct_world_mutation": False,
            },
        },
    })
    return entry


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
        "reason": "player_requested_specific_dimensions",
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
    entry["response"]["message"] = "Use the generated 6 wide 2 high wall option."
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
                "result": {
                    "status": "ready",
                    "generated_option": generated,
                    "direct_world_mutation": False,
                },
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
                "approval_id": "approval:tnt",
                "selected_candidate_id": "tnt_wall",
                "adapter_selected_candidate_id": "tnt_wall",
                "model_selected_candidate_id": "tnt_wall",
                "selection_source": "model_tool_decision",
                "adapter_tool_decision_source": "agents_sdk_function_tool",
                "adapter_required_tool_calls": [
                    "recall_build_prompt_memory",
                    "select_build_option",
                ],
                "adapter_missing_required_tool_calls": [],
                "adapter_required_tool_calls_satisfied": True,
                "build_option_decision_source": "agent_selected_build_option",
                "adapter_memory_available": True,
                "adapter_memory_matched_case_id": "promoted_tnt_wall_123",
                "adapter_memory_case_hint": "tnt_wall",
                "adapter_tool_trace_names": [
                    "recall_build_prompt_memory",
                    "select_build_option",
                    "plan_build_actions",
                ],
                "adapter_build_action_plan_status": "ready",
                "adapter_build_action_plan_step_count": 4,
                "adapter_build_action_plan_selected_candidate_id": "tnt_wall",
            },
        },
    }
    return "[ai_agent_plugin] request_trace=" + json.dumps(payload, sort_keys=True)


def nova_agent_log_entry(prompt="build a wall of tnt"):
    return {
        "ts": "2026-06-30T12:10:00Z",
        "player": "Eval",
        "prompt": prompt,
        "model": "gpt-5-nano",
        "source": "agents_sdk",
        "ok": True,
        "label": "tnt wall",
        "message": "Building a tnt wall.",
        "correction_source": "prompt_contract",
        "contract_satisfied": True,
        "prompt_contract": {
            "intent": "build",
            "material": "tnt",
            "contract_kind": "tnt_wall",
            "contract_required": True,
        },
        "actions": [
            {
                "type": "fill_box",
                "material": "tnt",
                "offset": {"x": 0, "y": 1, "z": 0},
                "size": {"x": 15, "y": 5, "z": 1},
            }
        ],
        "tool_trace": [
            {"tool_name": "analyze_build_intent", "result": {"contract_kind": "tnt_wall"}},
            {"tool_name": "validate_plan_contract", "result": {"contract_satisfied": False}},
        ],
    }


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


class AgentEvalQueueTests(unittest.TestCase):
    def test_builds_public_safe_eval_candidates_from_sidecar_and_nova_logs(self):
        module = load_queue_module()
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            sidecar_log = root / "agents-sdk-model-adapter.jsonl"
            nova_agent_log = root / "nova-agent-requests.jsonl"
            action_log = root / "debug.log"
            sidecar_log.write_text(json.dumps(agents_sdk_log_entry()) + "\n", encoding="utf-8")
            nova_agent_log.write_text(json.dumps(nova_agent_log_entry()) + "\n", encoding="utf-8")
            action_log.write_text(nova_trace_line() + "\n", encoding="utf-8")

            payload = module.build_eval_candidate_queue(
                agents_sdk_logs=[sidecar_log],
                nova_agent_logs=[nova_agent_log],
                action_logs=[action_log],
                generated_at="2026-06-30T12:30:00Z",
            )

        self.assertEqual(payload["artifact_kind"], "ai_native_agent_eval_candidate_queue")
        self.assertEqual(payload["status"], "ready")
        self.assertEqual(payload["source_summary"]["agents_sdk_log_entries_read"], 1)
        self.assertEqual(payload["source_summary"]["nova_agent_log_entries_read"], 1)
        self.assertEqual(payload["source_summary"]["nova_request_traces_read"], 1)
        self.assertEqual(payload["source_summary"]["candidates_total"], 3)
        self.assertEqual(payload["source_summary"]["ready_for_prompt_eval"], 3)
        self.assertTrue(payload["safety"]["public_safe_output"])
        self.assertFalse(PRIVATE_PATTERNS.search(json.dumps(payload, sort_keys=True)))

        fire = next(candidate for candidate in payload["candidates"] if candidate["case_hint"] == "fire_only_strict")
        self.assertTrue(fire["ready_for_prompt_eval"])
        self.assertEqual(fire["expected"]["build_kind"], "fire")
        self.assertEqual(fire["expected"]["build_material_name"], "fire")
        self.assertEqual(fire["expected"]["planned_node_writes"], 1)
        self.assertTrue(fire["expected"]["forbidden_extra_structure"])

        tnt_sources = {
            candidate["source_kind"]: candidate
            for candidate in payload["candidates"]
            if candidate["case_hint"] == "tnt_wall"
        }
        self.assertIn("nova_request_trace", tnt_sources)
        self.assertIn("nova_agent_sidecar_request_response", tnt_sources)
        trace_tnt = tnt_sources["nova_request_trace"]
        self.assertEqual(trace_tnt["expected"]["build_kind"], "wall")
        self.assertEqual(trace_tnt["expected"]["build_material_name"], "tnt")
        self.assertEqual(trace_tnt["expected"]["planned_node_writes"], 12)
        self.assertFalse(trace_tnt["expected"]["danger_refusal_allowed"])
        self.assertEqual(
            trace_tnt["observed"]["adapter_tool_decision_source"],
            "agents_sdk_function_tool",
        )
        self.assertEqual(
            trace_tnt["observed"]["adapter_required_tool_calls"],
            ["recall_build_prompt_memory", "select_build_option"],
        )
        self.assertEqual(trace_tnt["observed"]["adapter_missing_required_tool_calls"], [])
        self.assertTrue(trace_tnt["observed"]["adapter_required_tool_calls_satisfied"])
        self.assertEqual(
            trace_tnt["observed"]["build_option_decision_source"],
            "agent_selected_build_option",
        )
        self.assertTrue(trace_tnt["observed"]["adapter_memory_available"])
        self.assertEqual(
            trace_tnt["observed"]["adapter_memory_matched_case_id"],
            "promoted_tnt_wall_123",
        )
        self.assertEqual(
            trace_tnt["observed"]["adapter_tool_trace_names"],
            ["recall_build_prompt_memory", "select_build_option", "plan_build_actions"],
        )
        self.assertEqual(trace_tnt["observed"]["adapter_build_action_plan_status"], "ready")
        self.assertEqual(trace_tnt["observed"]["adapter_build_action_plan_step_count"], 4)
        self.assertEqual(
            trace_tnt["observed"]["adapter_build_action_plan_selected_candidate_id"],
            "tnt_wall",
        )
        self.assertEqual(trace_tnt["observed"]["selected_candidate_id"], "tnt_wall")
        self.assertEqual(trace_tnt["observed"]["model_selected_candidate_id"], "tnt_wall")
        self.assertEqual(trace_tnt["observed"]["selection_source"], "model_tool_decision")
        sidecar_tnt = tnt_sources["nova_agent_sidecar_request_response"]
        self.assertEqual(sidecar_tnt["observed"]["contract_kind"], "tnt_wall")
        self.assertTrue(sidecar_tnt["observed"]["contract_satisfied"])
        self.assertEqual(sidecar_tnt["observed"]["correction_source"], "prompt_contract")
        self.assertEqual(sidecar_tnt["observed"]["build_kind"], "wall")
        self.assertEqual(sidecar_tnt["observed"]["build_material_name"], "tnt")
        self.assertEqual(sidecar_tnt["observed"]["planned_node_writes"], 75)
        self.assertEqual(
            sidecar_tnt["observed"]["tool_trace_names"],
            ["analyze_build_intent", "validate_plan_contract"],
        )

    def test_private_entries_are_skipped_and_not_retained(self):
        module = load_queue_module()
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            sidecar_log = root / "agents-sdk-model-adapter.jsonl"
            private_entry = agents_sdk_log_entry("explain this private path")
            private_entry["request"]["context"]["private_prompt"] = "must not be retained"
            sidecar_log.write_text(json.dumps(private_entry) + "\n", encoding="utf-8")

            payload = module.build_eval_candidate_queue(
                agents_sdk_logs=[sidecar_log],
                generated_at="2026-06-30T12:30:00Z",
            )

        raw = json.dumps(payload, sort_keys=True)
        self.assertEqual(payload["status"], "empty")
        self.assertEqual(payload["source_summary"]["entries_skipped_private"], 1)
        self.assertEqual(payload["source_summary"]["candidates_total"], 0)
        self.assertNotIn("must not be retained", raw)
        self.assertNotIn("private_prompt", raw)
        self.assertTrue(payload["violations"])
        self.assertTrue(payload["safety"]["public_safe_output"])

    def test_agents_sdk_candidate_uses_player_request_and_tool_trace(self):
        module = load_queue_module()
        entry = agents_sdk_log_entry(
            "AI-native Luanti model adapter request.\nplayer_request: build me a fire and only a fire"
        )
        entry["request"]["context"].update({
            "intent": "build_planning",
            "player_request": "build me a fire and only a fire",
            "candidate_summary": "fire:fire:fire:1|platform:platform:stone:9",
        })
        entry["response"]["response"].update({
            "selected_option_id": "fire",
            "tool_decision_source": "agents_sdk_function_tool",
            "tool_trace": [
                {"tool_name": "recall_build_prompt_memory"},
                {"tool_name": "select_build_option"},
                {"tool_name": "plan_build_actions"},
            ],
            "build_action_plan": {
                "status": "ready",
                "selected_option_id": "fire",
                "plan_kind": "luanti_build_action_plan_v1",
                "step_count": 4,
                "direct_world_mutation": False,
                "world_mutation_authority": "luanti",
            },
            "tool_decisions": {
                "build_option": {
                    "selected_option_id": "fire",
                    "decision_source": "agent_selected_build_option",
                    "memory_match": {
                        "memory_available": True,
                        "matched_case_id": "promoted_fire_only_strict_123",
                    },
                },
                "build_action_plan": {
                    "status": "ready",
                    "selected_option_id": "fire",
                    "plan_kind": "luanti_build_action_plan_v1",
                    "step_count": 4,
                    "direct_world_mutation": False,
                    "world_mutation_authority": "luanti",
                },
            },
        })

        candidate = module.candidate_from_agents_sdk_entry(entry)

        self.assertIsNotNone(candidate)
        self.assertEqual(candidate["prompt"], "build me a fire and only a fire")
        self.assertEqual(candidate["prompt_source"], "context.player_request")
        self.assertEqual(candidate["case_hint"], "fire_only_strict")
        self.assertEqual(candidate["observed"]["selected_option_id"], "fire")
        self.assertEqual(candidate["observed"]["tool_decision_source"], "agents_sdk_function_tool")
        self.assertEqual(candidate["observed"]["build_option_decision_source"], "agent_selected_build_option")
        self.assertEqual(candidate["observed"]["build_option_selected_option_id"], "fire")
        self.assertTrue(candidate["observed"]["memory_available"])
        self.assertEqual(
            candidate["observed"]["tool_trace_names"],
            ["recall_build_prompt_memory", "select_build_option", "plan_build_actions"],
        )
        self.assertEqual(candidate["observed"]["build_action_plan_status"], "ready")
        self.assertEqual(candidate["observed"]["build_action_plan_step_count"], 4)
        self.assertEqual(
            candidate["observed"]["build_action_plan_selected_option_id"],
            "fire",
        )
        self.assertEqual(
            candidate["observed"]["build_action_plan_world_mutation_authority"],
            "luanti",
        )
        self.assertFalse(candidate["ready_for_adapter_contract_eval"])

    def test_agents_sdk_candidate_retains_rejected_model_choice(self):
        module = load_queue_module()
        entry = agents_sdk_log_entry(
            "AI-native Luanti model adapter request.\nplayer_request: build me a fire and only a fire"
        )
        entry["request"]["context"].update({
            "intent": "build_planning",
            "player_request": "build me a fire and only a fire",
            "candidate_summary": "platform:platform:default:4|fire:fire:fire:1",
        })
        entry["response"]["response"].update({
            "selected_option_id": "fire",
            "model_selected_option_id": "platform",
            "rejected_model_selected_option_id": "platform",
            "intent_constraint_option_id": "fire",
            "intent_constraint_reason": "player_request_requires_fire_only",
            "tool_decision_source":
                "adapter_fallback_after_agent_violated_player_request_constraints",
            "tool_trace": [
                {"tool_name": "recall_build_prompt_memory"},
                {
                    "tool_name": "select_build_option",
                    "args": {"selected_option_id": "platform"},
                    "result": {"selected_option_id": None, "selection_status": "rejected"},
                },
            ],
            "tool_decisions": {
                "build_option": {
                    "selected_option_id": "fire",
                    "decision_source": "offline_adapter_fallback",
                    "memory_match": {"memory_available": True},
                },
            },
        })

        candidate = module.candidate_from_agents_sdk_entry(entry)

        self.assertIsNotNone(candidate)
        observed = candidate["observed"]
        self.assertEqual(observed["selected_option_id"], "fire")
        self.assertEqual(observed["model_selected_option_id"], "platform")
        self.assertEqual(observed["rejected_model_selected_option_id"], "platform")
        self.assertEqual(observed["intent_constraint_option_id"], "fire")
        self.assertEqual(
            observed["intent_constraint_reason"],
            "player_request_requires_fire_only",
        )
        self.assertEqual(
            observed["tool_decision_source"],
            "adapter_fallback_after_agent_violated_player_request_constraints",
        )

    def test_nova_trace_candidate_retains_rejected_model_choice(self):
        module = load_queue_module()
        payload = json.loads(
            nova_trace_line("build me a fire and only a fire").split("request_trace=", 1)[1]
        )
        response = payload["trace"]["response"]
        response.update({
            "build_kind": "fire",
            "build_material_name": "fire",
            "planned_node_writes": 1,
            "selected_candidate_id": "fire",
            "adapter_selected_candidate_id": "fire",
            "model_selected_candidate_id": "platform",
            "selection_source": "model_tool_decision_rejected_intent_constraint",
            "intent_constraint_option_id": "fire",
            "intent_constraint_reason": "player_request_requires_fire_only",
            "adapter_tool_decision_source":
                "adapter_fallback_after_agent_violated_player_request_constraints",
            "adapter_model_selected_candidate_id": "platform",
            "adapter_rejected_model_selected_candidate_id": "platform",
        })

        candidate = module.candidate_from_nova_trace(payload)

        self.assertIsNotNone(candidate)
        observed = candidate["observed"]
        self.assertEqual(observed["selected_candidate_id"], "fire")
        self.assertEqual(observed["adapter_selected_candidate_id"], "fire")
        self.assertEqual(observed["model_selected_candidate_id"], "platform")
        self.assertEqual(
            observed["selection_source"],
            "model_tool_decision_rejected_intent_constraint",
        )
        self.assertEqual(observed["intent_constraint_option_id"], "fire")
        self.assertEqual(
            observed["adapter_rejected_model_selected_candidate_id"],
            "platform",
        )

    def test_agents_sdk_missing_required_tool_becomes_contract_eval_candidate(self):
        module = load_queue_module()
        entry = agents_sdk_missing_required_tool_entry()

        candidate = module.candidate_from_agents_sdk_entry(entry)

        self.assertIsNotNone(candidate)
        self.assertEqual(candidate["prompt"], "build me a tower")
        self.assertEqual(candidate["case_hint"], "model_adapter_review")
        self.assertEqual(candidate["priority"], "high")
        self.assertFalse(candidate["ready_for_prompt_eval"])
        self.assertTrue(candidate["ready_for_adapter_contract_eval"])
        self.assertEqual(candidate["adapter_contract_review_status"], "adapter_contract_candidate_ready")
        contract = candidate["adapter_tool_contract"]
        self.assertEqual(contract["status"], "fail")
        self.assertEqual(
            contract["required_tool_calls"],
            ["recall_build_prompt_memory", "select_build_option", "propose_build_option"],
        )
        self.assertEqual(contract["missing_required_tool_calls"], ["propose_build_option"])
        self.assertFalse(contract["required_tool_calls_satisfied"])
        self.assertEqual(
            contract["expected"]["missing_required_tool_calls"],
            [],
        )
        self.assertEqual(
            contract["expected"]["tool_decision_source"],
            "agents_sdk_function_tool",
        )
        replay_request = candidate["adapter_replay_request"]
        self.assertEqual(replay_request["request_kind"], "ai_native_model_adapter_request")
        self.assertEqual(replay_request["adapter_contract"], "provider_neutral_v1")
        self.assertEqual(replay_request["context"]["intent"], "build_planning")
        self.assertEqual(replay_request["context"]["player_request"], "build me a tower")
        self.assertIn("candidate_summary", replay_request["context"])
        self.assertTrue(replay_request["safety"]["public_safe_request"])
        self.assertFalse(PRIVATE_PATTERNS.search(json.dumps(replay_request, sort_keys=True)))

    def test_queue_counts_adapter_contract_failures(self):
        module = load_queue_module()
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            sidecar_log = root / "agents-sdk-model-adapter.jsonl"
            sidecar_log.write_text(
                json.dumps(agents_sdk_missing_required_tool_entry()) + "\n",
                encoding="utf-8",
            )

            payload = module.build_eval_candidate_queue(
                agents_sdk_logs=[sidecar_log],
                generated_at="2026-06-30T12:30:00Z",
            )

        self.assertEqual(payload["status"], "ready")
        self.assertEqual(payload["source_summary"]["candidates_total"], 1)
        self.assertEqual(payload["source_summary"]["ready_for_prompt_eval"], 0)
        self.assertEqual(payload["source_summary"]["manual_review_required"], 1)
        self.assertEqual(payload["source_summary"]["ready_for_adapter_contract_eval"], 1)
        self.assertEqual(payload["source_summary"]["adapter_contract_failures"], 1)
        self.assertTrue(payload["candidates"][0]["ready_for_adapter_contract_eval"])

    def test_verified_generated_option_becomes_prompt_eval_candidate(self):
        module = load_queue_module()

        candidate = module.candidate_from_agents_sdk_entry(agents_sdk_generated_option_entry())

        self.assertIsNotNone(candidate)
        self.assertEqual(candidate["prompt"], "build a 6 wide 2 high lookout wall")
        self.assertEqual(candidate["case_hint"], "generated_dimensioned_wall")
        self.assertTrue(candidate["ready_for_prompt_eval"])
        self.assertFalse(candidate["ready_for_adapter_contract_eval"])
        self.assertEqual(candidate["review_status"], "candidate_ready")
        self.assertEqual(candidate["expected"]["route"], "agentic_build_planner")
        self.assertEqual(candidate["expected"]["selected_candidate_id"], "generated_dimensioned_wall")
        self.assertEqual(candidate["expected"]["build_kind"], "wall")
        self.assertEqual(candidate["expected"]["build_material_name"], "stone")
        self.assertEqual(candidate["expected"]["planned_node_writes"], 12)
        self.assertEqual(candidate["expected"]["build_width"], 6)
        self.assertEqual(candidate["expected"]["build_height"], 2)
        self.assertTrue(candidate["expected"]["forbidden_extra_structure"])
        observed = candidate["observed"]
        self.assertEqual(observed["generated_option_id"], "generated_dimensioned_wall")
        self.assertEqual(observed["generated_option_status"], "ready")
        self.assertEqual(observed["generated_option_build_width"], 6)
        self.assertEqual(observed["generated_option_build_height"], 2)
        self.assertEqual(
            observed["tool_trace_names"],
            [
                "recall_build_prompt_memory",
                "propose_build_option",
                "select_build_option",
                "plan_build_actions",
            ],
        )

    def test_generated_option_survives_small_candidate_queue(self):
        module = load_queue_module()
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            sidecar_log = root / "agents-sdk-model-adapter.jsonl"
            entries = []
            for index in range(8):
                entry = agents_sdk_log_entry("build me a fire and only a fire")
                entry["created_at"] = f"2026-06-30T12:00:{index:02d}Z"
                entries.append(json.dumps(entry))
            generated = agents_sdk_generated_option_entry()
            generated["created_at"] = "2026-06-30T12:01:00Z"
            entries.append(json.dumps(generated))
            sidecar_log.write_text("\n".join(entries) + "\n", encoding="utf-8")

            payload = module.build_eval_candidate_queue(
                agents_sdk_logs=[sidecar_log],
                generated_at="2026-06-30T12:30:00Z",
                max_candidates=3,
                max_bytes=100000,
            )

        self.assertEqual(payload["source_summary"]["candidates_total"], 3)
        self.assertIn(
            "generated_dimensioned_wall",
            {candidate["case_hint"] for candidate in payload["candidates"]},
        )

    def test_agents_sdk_candidate_extracts_embedded_player_request_from_wrapper_prompt(self):
        module = load_queue_module()
        entry = agents_sdk_log_entry(
            "\n".join(
                [
                    "Plan a Luanti build request using only the listed executable options.",
                    "Luanti will enforce capabilities, approval, rollback, and world mutation.",
                    "Player request: build a small shelter",
                    "Options:",
                    "- fire: Single fire kind=fire material=fire planned_writes=1",
                ]
            )
        )

        candidate = module.candidate_from_agents_sdk_entry(entry)

        self.assertIsNotNone(candidate)
        self.assertEqual(candidate["prompt"], "build a small shelter")
        self.assertEqual(candidate["prompt_source"], "request.public_prompt.player_request")
        self.assertNotEqual(candidate["case_hint"], "fire_only_strict")
        self.assertFalse(candidate["ready_for_prompt_eval"])

    def test_nova_trace_accepts_null_tool_trace_names_from_live_log(self):
        module = load_queue_module()
        payload = json.loads(nova_trace_line().split("request_trace=", 1)[1])
        payload["trace"]["response"]["adapter_tool_trace_names"] = None

        candidate = module.candidate_from_nova_trace(payload)

        self.assertIsNotNone(candidate)
        self.assertEqual(candidate["source_kind"], "nova_request_trace")
        self.assertEqual(candidate["observed"]["adapter_tool_trace_names"], [])

    def test_action_log_queue_handles_null_and_non_object_response_without_crashing(self):
        module = load_queue_module()
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            action_log = root / "debug.log"
            null_tool_payload = json.loads(nova_trace_line().split("request_trace=", 1)[1])
            null_tool_payload["trace"]["response"]["adapter_tool_trace_names"] = None
            invalid_payload = json.loads(nova_trace_line().split("request_trace=", 1)[1])
            invalid_payload["trace"]["response"] = "not a response object"
            action_log.write_text(
                "[ai_agent_plugin] request_trace="
                + json.dumps(null_tool_payload, sort_keys=True)
                + "\n"
                + "[ai_agent_plugin] request_trace="
                + json.dumps(invalid_payload, sort_keys=True)
                + "\n",
                encoding="utf-8",
            )

            payload = module.build_eval_candidate_queue(
                action_logs=[action_log],
                generated_at="2026-06-30T13:45:00Z",
            )

        self.assertEqual(payload["source_summary"]["nova_request_traces_read"], 2)
        self.assertEqual(payload["source_summary"]["candidates_total"], 2)
        self.assertEqual(payload["candidates"][0]["observed"]["adapter_tool_trace_names"], [])

    def test_operator_labels_promote_unknown_prompt_to_reviewed_candidate(self):
        module = load_queue_module()
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            sidecar_log = root / "agents-sdk-model-adapter.jsonl"
            sidecar_log.write_text(
                json.dumps(agents_sdk_log_entry("build a bridge")) + "\n",
                encoding="utf-8",
            )

            unlabelled = module.build_eval_candidate_queue(
                agents_sdk_logs=[sidecar_log],
                generated_at="2026-06-30T12:30:00Z",
            )
            labelled = module.build_eval_candidate_queue(
                agents_sdk_logs=[sidecar_log],
                operator_label_payloads=[operator_labels_payload()],
                generated_at="2026-06-30T12:30:00Z",
            )

        self.assertEqual(unlabelled["source_summary"]["ready_for_prompt_eval"], 0)
        self.assertEqual(unlabelled["candidates"][0]["review_status"], "needs_operator_label")
        self.assertEqual(labelled["source_summary"]["operator_labels_read"], 1)
        self.assertEqual(labelled["source_summary"]["operator_labels_applied"], 1)
        self.assertEqual(labelled["source_summary"]["ready_for_prompt_eval"], 1)
        candidate = labelled["candidates"][0]
        self.assertEqual(candidate["case_hint"], "stone_bridge_platform")
        self.assertEqual(candidate["review_status"], "operator_labeled_candidate_ready")
        self.assertEqual(candidate["operator_label"]["mode"], "operator_label_overlay")
        self.assertEqual(candidate["expected"]["build_kind"], "platform")
        self.assertEqual(candidate["expected"]["build_material_name"], "stone")
        self.assertEqual(candidate["expected"]["planned_node_writes"], 12)
        self.assertFalse(PRIVATE_PATTERNS.search(json.dumps(labelled, sort_keys=True)))

    def test_private_operator_labels_are_rejected_without_promoting_candidate(self):
        module = load_queue_module()
        private_labels = operator_labels_payload()
        private_labels["labels"][0]["expected"]["private_prompt"] = "must not be retained"

        payload = module.build_eval_candidate_queue(
            operator_label_payloads=[private_labels],
            generated_at="2026-06-30T12:30:00Z",
        )

        self.assertEqual(payload["status"], "empty")
        self.assertEqual(payload["source_summary"]["operator_labels_read"], 0)
        self.assertEqual(payload["source_summary"]["operator_labels_applied"], 0)
        self.assertTrue(any(item["kind"] == "operator_labels_not_public_safe" for item in payload["violations"]))
        self.assertNotIn("must not be retained", json.dumps(payload, sort_keys=True))

    def test_nova_agent_log_candidate_records_contract_and_correction(self):
        module = load_queue_module()

        candidate = module.candidate_from_nova_agent_log_entry(nova_agent_log_entry())

        self.assertIsNotNone(candidate)
        self.assertEqual(candidate["source_kind"], "nova_agent_sidecar_request_response")
        self.assertEqual(candidate["case_hint"], "tnt_wall")
        self.assertEqual(candidate["priority"], "high")
        self.assertEqual(candidate["route"], "agents_sdk")
        self.assertEqual(candidate["action"], "build")
        self.assertEqual(candidate["observed_status"], "corrected")
        self.assertEqual(candidate["observed_reason"], "prompt_contract")
        self.assertEqual(candidate["observed"]["contract_kind"], "tnt_wall")
        self.assertTrue(candidate["observed"]["contract_satisfied"])
        self.assertEqual(candidate["observed"]["planned_node_writes"], 75)
        self.assertEqual(candidate["expected"]["planned_node_writes"], 12)

    def test_cli_writes_candidate_queue(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            sidecar_log = root / "agents-sdk-model-adapter.jsonl"
            nova_agent_log = root / "nova-agent-requests.jsonl"
            operator_labels = root / "operator-labels.json"
            output = root / "candidate-queue.json"
            sidecar_log.write_text(json.dumps(agents_sdk_log_entry("build a fire")) + "\n", encoding="utf-8")
            nova_agent_log.write_text(json.dumps(nova_agent_log_entry()) + "\n", encoding="utf-8")
            operator_labels.write_text(json.dumps(operator_labels_payload()), encoding="utf-8")

            completed = subprocess.run(
                [
                    sys.executable,
                    str(QUEUE),
                    "--root",
                    str(root),
                    "--agents-sdk-log",
                    str(sidecar_log),
                    "--nova-agent-log",
                    str(nova_agent_log),
                    "--operator-labels",
                    str(operator_labels),
                    "--output",
                    str(output),
                    "--generated-at",
                    "2026-06-30T12:30:00Z",
                ],
                cwd=ROOT,
                check=False,
                text=True,
                capture_output=True,
            )

            self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
            payload = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(payload["status"], "ready")
            self.assertEqual(payload["source_summary"]["nova_agent_log_entries_read"], 1)
            self.assertEqual(payload["source_summary"]["operator_labels_read"], 1)
            self.assertEqual(payload["source_summary"]["operator_labels_applied"], 0)
            self.assertEqual(
                {candidate["case_hint"] for candidate in payload["candidates"]},
                {"build_fire", "tnt_wall"},
            )

    def test_docs_include_agent_improvement_loop(self):
        bodies = [path.read_text(encoding="utf-8") for path in (README, OPERATING_LOOP, ADAPTER_DOC)]
        combined = "\n".join(bodies)
        self.assertIn("ai_native_agent_eval_queue.py", combined)
        self.assertIn("ai_native_agent_feedback_packet.py", combined)
        self.assertIn("Agent Improvement Loop", combined)
        self.assertIn("agents-sdk-model-adapter.jsonl", combined)
        self.assertIn("--operator-labels", combined)
        self.assertIn("--from-operator-feedback", combined)
        self.assertIn("/ai_agent_feedback", combined)
        self.assertIn("ai_native_agent_eval_operator_labels", combined)
        loop_sections = []
        for body in bodies:
            if "## Agent Improvement Loop" not in body:
                continue
            section = body.split("## Agent Improvement Loop", 1)[1]
            section = section.split("\n## ", 1)[0]
            loop_sections.append(section)
        self.assertGreaterEqual(len(loop_sections), 2)
        self.assertNotRegex("\n".join(loop_sections), DOC_PRIVATE_PATTERNS)


if __name__ == "__main__":
    unittest.main()
