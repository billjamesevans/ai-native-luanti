import importlib.util
import json
import os
import pathlib
import tempfile
import unittest
from unittest import mock


ROOT = pathlib.Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "openrealm_advantage_kit" / "studio" / "server.py"


def load_module():
    spec = importlib.util.spec_from_file_location("openrealm_studio_server_test", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def gate_payload(**overrides):
    payload = {
        "schema_version": 1,
        "artifact_kind": "openrealm_live_review_gate_result",
        "status": "pass",
        "source_trace_id": "nova_trace:11",
        "selected_option_id": "fire",
        "case_hint": "fire_only_strict",
        "artifacts": {
            "review_packet": "local/review-packets/live-review/trace11-studio-review-packet.json",
            "candidate_queue": "local/review-packets/live-review/trace11-candidate-queue.json",
        },
        "checks": {
            "review_packet_public_safe": True,
            "operator_label_matched": True,
            "case_pack_has_cases": True,
        },
        "violations": [],
        "summary": {
            "operator_label_matched": True,
            "operator_labels_applied": 1,
            "candidate_queue_status": "ready",
            "case_pack_status": "ready",
            "cases_total": 1,
        },
        "safety": {
            "public_safe_output": True,
            "no_world_mutation": True,
            "no_raw_assets": True,
            "no_provider_prompts": True,
            "no_family_world_coordinates": True,
        },
    }
    payload.update(overrides)
    return payload


def adapter_record(*, ok=True, trace_id="nova_trace:1", selected_option_id="fire", direct_world_mutation=False):
    return {
        "created_at": "2026-07-02T12:00:00Z",
        "request": {
            "agent_id": "nova_agent:PromptEvalLive",
            "task_id": f"ai-agent-build-planner:{trace_id}",
        },
        "response": {
            "ok": ok,
            "elapsed_us": 12000,
            "response": {
                "agentic_execution": True,
                "tool_decision_source": "agents_sdk_function_tool",
                "selected_option_id": selected_option_id,
                "required_tool_calls_satisfied": True,
                "web_search_available": True,
                "world_mutation_authority": "luanti",
                "source_trace_id": trace_id,
                "build_action_plan": {
                    "selected_option_id": selected_option_id,
                    "planned_node_writes": 1,
                    "direct_world_mutation": direct_world_mutation,
                },
                "tools_enabled": ["select_build_option", "plan_build_actions"],
            },
        },
    }


class OpenRealmStudioStatusTests(unittest.TestCase):
    def env_for(self, root, gate_path):
        missing = str(root / "missing.json")
        return {
            "OPENREALM_LIVE_REVIEW_GATE": str(gate_path),
            "OPENREALM_QUALITY_GATE": missing,
            "OPENREALM_PROMPT_EVAL": missing,
            "OPENREALM_REQUEST_LOG_GATE": missing,
        }

    def test_live_review_gate_summary_is_public_safe(self):
        server = load_module()
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            gate_path = root / "gate-result.json"
            gate_path.write_text(json.dumps(gate_payload()) + "\n", encoding="utf-8")

            with mock.patch.dict(os.environ, self.env_for(root, gate_path)):
                summary = server.live_review_gate_status()
                quality = server.quality_gate_status(summary)

            self.assertTrue(summary["present"])
            self.assertEqual(summary["current_health"], "pass")
            self.assertEqual(summary["source_trace_id"], "nova_trace:11")
            self.assertEqual(summary["selected_option_id"], "fire")
            self.assertEqual(summary["checks_passed"], 3)
            self.assertEqual(summary["checks_total"], 3)
            self.assertEqual(summary["artifact_keys"], ["candidate_queue", "review_packet"])
            self.assertNotIn("trace11-studio-review-packet", json.dumps(summary))
            self.assertEqual(quality["status"], "pass")
            self.assertEqual(quality["live_review_gate_health"], "pass")

    def test_live_review_gate_rejects_unsafe_payload_without_leaking_details(self):
        server = load_module()
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            gate_path = root / "gate-result.json"
            unsafe = gate_payload(violations=[{"kind": "diagnostic", "details": "/Users/example/private"}])
            gate_path.write_text(json.dumps(unsafe) + "\n", encoding="utf-8")

            with mock.patch.dict(os.environ, self.env_for(root, gate_path)):
                summary = server.live_review_gate_status()
                quality = server.quality_gate_status(summary)

            encoded = json.dumps(summary)
            self.assertEqual(summary["current_health"], "fail")
            self.assertTrue(summary["unsafe_payload_rejected"])
            self.assertFalse(summary["public_safe_output"])
            self.assertNotIn("/Users/example/private", encoded)
            self.assertEqual(quality["status"], "fail")
            self.assertEqual(quality["live_review_gate_violations"], 1)

    def test_adapter_release_health_separates_latest_trace_from_history(self):
        server = load_module()
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            log_path = root / "agents-sdk-model-adapter.jsonl"
            log_path.write_text(
                "\n".join([
                    json.dumps(adapter_record(ok=False, trace_id="nova_trace:old")),
                    json.dumps(adapter_record(ok=True, trace_id="nova_trace:new", selected_option_id="generated_village")),
                ]) + "\n",
                encoding="utf-8",
            )

            with mock.patch.dict(os.environ, {"OPENREALM_ADAPTER_LOG": str(log_path)}):
                summary = server.adapter_log_status()

            self.assertTrue(summary["present"])
            self.assertEqual(summary["latest"]["source_trace_id"], "nova_trace:new")
            self.assertEqual(summary["latest"]["selected_option_id"], "generated_village")
            self.assertEqual(summary["latest_ok"], True)
            self.assertEqual(summary["release_health"], "pass")
            self.assertEqual(summary["recent_window_health"], "attention")
            self.assertEqual(summary["history_health"], "attention")
            self.assertEqual(summary["current_health"], "attention")
            self.assertEqual(summary["recent_failures"], 1)
            self.assertEqual(summary["failures"], 1)

    def test_studio_submission_builds_public_safe_model_adapter_request(self):
        server = load_module()
        payload = {
            "public_prompt": "build a wall of tnt",
            "plan": {
                "plan_id": "plan:studio",
                "summary": "bounded tnt wall preview",
                "features": ["tnt"],
                "materials": ["tnt:tnt"],
                "node_writes": 36,
                "safety": {
                    "status": "ready",
                    "risk": "medium",
                    "requires_approval": True,
                    "rollback_policy": "snapshot",
                },
            },
        }

        request = server.build_studio_model_adapter_request(payload, generated_at="2026-07-02T12:00:00Z")

        self.assertEqual(request["request_kind"], "ai_native_model_adapter_request")
        self.assertEqual(request["adapter_contract"], "provider_neutral_v1")
        self.assertEqual(request["agent_id"], "nova_agent:OpenRealmStudio")
        self.assertEqual(request["context"]["intent"], "build_planning")
        self.assertEqual(request["context"]["selected_candidate_id"], "tnt_wall")
        self.assertIn("tnt_wall:wall:tnt:36", request["context"]["candidate_summary"])
        self.assertTrue(request["safety"]["public_safe_request"])
        self.assertFalse(request["safety"]["private_input_retained"])
        self.assertNotIn("/Users/", json.dumps(request))
        self.assertNotIn("OPENAI_API_KEY", json.dumps(request))

    def test_studio_submission_rejects_private_payload(self):
        server = load_module()

        with self.assertRaises(server.ApiError) as raised:
            server.build_studio_model_adapter_request({
                "public_prompt": "load /Users/bill/private build",
                "plan": {"node_writes": 1},
            })

        self.assertEqual(raised.exception.status, server.HTTPStatus.BAD_REQUEST)

    def test_studio_submission_calls_loopback_adapter_and_logs_summary(self):
        server = load_module()
        adapter_response = {
            "ok": True,
            "message": "Live public-safe guidance.",
            "response": {
                "agentic_execution": True,
                "tool_decision_source": "agents_sdk_function_tool",
                "selected_option_id": "fire",
                "required_tool_calls_satisfied": True,
                "web_search_available": True,
                "world_mutation_authority": "luanti",
                "missing_required_tool_calls": [],
                "tool_trace": [
                    {"tool_name": "inspect_build_site_context"},
                    {"tool_name": "recall_build_prompt_memory"},
                    {"tool_name": "select_build_option"},
                    {"tool_name": "plan_build_actions"},
                ],
                "build_action_plan": {
                    "status": "ready",
                    "selected_option_id": "fire",
                    "build_kind": "fire",
                    "build_material_name": "fire",
                    "planned_node_writes": 1,
                    "plan_kind": "luanti_build_action_plan_v1",
                    "step_count": 4,
                    "direct_world_mutation": False,
                    "world_mutation_authority": "luanti",
                },
            },
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            log_path = pathlib.Path(tmpdir) / "studio-submissions.jsonl"

            with mock.patch.dict(os.environ, {
                    "OPENREALM_MODEL_ADAPTER_ENDPOINT": "http://127.0.0.1:8766/v1/model-adapter",
                    "OPENREALM_STUDIO_SUBMISSION_LOG": str(log_path),
            }), mock.patch.object(server, "http_post_json", return_value=(200, adapter_response)) as post:
                status, result = server.submit_studio_nova_plan({
                    "public_prompt": "build me a fire and only a fire",
                    "plan": {
                        "plan_id": "plan:fire",
                        "summary": "fire only",
                        "node_writes": 1,
                        "safety": {"status": "ready", "risk": "low", "requires_approval": True},
                    },
                })

            self.assertEqual(status, server.HTTPStatus.OK)
            self.assertTrue(result["ok"])
            self.assertTrue(result["logged"])
            self.assertEqual(result["adapter_http_status"], 200)
            self.assertEqual(result["runtime_handoff_status"], "ready_for_luanti_preview_approval_task")
            self.assertEqual(result["runtime_handoff"]["status"], "ready_for_luanti_preview_approval_task")
            self.assertEqual(result["world_mutation_authority"], "luanti")
            self.assertFalse(result["direct_world_mutation"])
            self.assertEqual(result["summary"]["selected_option_id"], "fire")
            self.assertEqual(result["summary"]["planned_node_writes"], 1)
            self.assertEqual(result["summary"]["tool_decision_source"], "agents_sdk_function_tool")
            self.assertTrue(result["summary"]["agentic_execution"])
            self.assertTrue(result["summary"]["required_tool_calls_satisfied"])
            self.assertFalse(result["summary"]["direct_world_mutation"])
            post.assert_called_once()
            submitted = post.call_args.args[1]
            self.assertEqual(submitted["context"]["selected_candidate_id"], "fire")
            self.assertTrue(log_path.exists())
            logged = json.loads(log_path.read_text(encoding="utf-8").strip())
            encoded = json.dumps(logged)
            self.assertEqual(logged["runtime_handoff"]["status"], "ready_for_luanti_preview_approval_task")
            self.assertEqual(logged["adapter"]["selected_option_id"], "fire")
            self.assertEqual(logged["adapter"]["tool_trace_names"], [
                "inspect_build_site_context",
                "recall_build_prompt_memory",
                "select_build_option",
                "plan_build_actions",
            ])
            self.assertNotIn("raw_provider", encoded)
            self.assertNotIn("OPENAI_API_KEY", encoded)


if __name__ == "__main__":
    unittest.main()
