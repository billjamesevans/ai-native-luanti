import json
import pathlib
import re
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[2]
SCHEMA = ROOT / "doc" / "ai-native-runtime" / "schemas" / "ai-runtime-rollback-record.schema.json"
EXAMPLE = ROOT / "doc" / "ai-native-runtime" / "examples" / "rollback-record.example.json"
CHUNKED_EXAMPLE = ROOT / "doc" / "ai-native-runtime" / "examples" / "rollback-record-chunked.example.json"
DOC = ROOT / "doc" / "ai-native-runtime" / "rollback-metadata.md"


class RollbackMetadataContractTests(unittest.TestCase):
    def load_json(self, path):
        with self.subTest(path=path.name):
            self.assertTrue(path.is_file(), f"missing {path}")
        return json.loads(path.read_text(encoding="utf-8"))

    def test_schema_declares_required_rollback_metadata_fields(self):
        schema = self.load_json(SCHEMA)

        self.assertEqual(schema["$schema"], "https://json-schema.org/draft/2020-12/schema")
        required = set(schema["required"])
        for field in (
            "schema_version",
            "record_id",
            "policy",
            "world_id",
            "task_id",
            "agent_id",
            "owner_ref",
            "operation_label",
            "mutation_class",
            "bounds",
            "changed_positions",
            "previous_nodes",
            "chunk",
            "created_at",
        ):
            self.assertIn(field, required)

        previous_node_required = set(schema["$defs"]["previous_node"]["required"])
        for field in ("pos", "node"):
            self.assertIn(field, previous_node_required)
        self.assertFalse(schema.get("additionalProperties", True))

    def test_examples_match_required_contract_without_private_payloads(self):
        schema = self.load_json(SCHEMA)
        required = set(schema["required"])
        for path in (EXAMPLE, CHUNKED_EXAMPLE):
            with self.subTest(example=path.name):
                payload = self.load_json(path)
                self.assertTrue(required.issubset(payload))
                self.assertEqual(payload["schema_version"], 1)
                self.assertRegex(payload["record_id"], r"^rollback:")
                self.assertIn(payload["policy"], {"manifest", "snapshot", "chunked"})
                self.assertIn(payload["mutation_class"], {"repair", "build", "compat_import"})
                self.assertGreaterEqual(len(payload["changed_positions"]), 1)
                self.assertGreaterEqual(len(payload["previous_nodes"]), 1)
                self.assertNotIn("prompt", json.dumps(payload).lower())
                self.assertNotIn("asset_payload", json.dumps(payload).lower())
                self.assertNotRegex(json.dumps(payload), re.compile(r"bill|wills|minecraftpi|192\.168", re.I))

    def test_public_document_describes_failure_behavior_and_non_goals(self):
        self.assertTrue(DOC.is_file(), f"missing {DOC}")
        body = DOC.read_text(encoding="utf-8")

        for phrase in (
            "abort before mutation",
            "rollback_metadata_unavailable",
            "core.ai_rollback_storage.configure",
            "default storage adapter",
            "world path",
            "inspect",
            "prune",
            "private prompts",
            "asset payload bytes",
            "chunk_index",
            "chunk_count",
        ):
            self.assertIn(phrase, body)


if __name__ == "__main__":
    unittest.main()
