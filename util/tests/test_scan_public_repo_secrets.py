import unittest
from types import SimpleNamespace
from unittest.mock import patch

from util import scan_public_repo_secrets
from util.scan_public_repo_secrets import scan_text


class TestPublicRepoSecretScan(unittest.TestCase):
    def test_task_control_words_do_not_match_openai_keys(self):
        findings = scan_text(
            "ai-runtime-operator-task-control-command-result.json",
            source="test",
            path="fixture.txt",
        )

        self.assertEqual(findings, [])

    def test_high_entropy_openai_key_is_reported_without_value(self):
        secret = "sk-" + "AbCDefGhIJklMNopQRstUVwxYZ1234567890"
        findings = scan_text(
            f"OPENAI_API_KEY={secret}",
            source="test",
            path="fixture.env",
        )

        self.assertEqual(len(findings), 2)
        self.assertEqual({finding.pattern for finding in findings}, {"openai_api_key", "secret_env_assignment"})
        self.assertTrue(all(secret not in repr(finding) for finding in findings))

    def test_commit_blob_decode_ignores_non_utf8_bytes(self):
        with patch.object(scan_public_repo_secrets.subprocess, "run") as run:
            run.return_value = SimpleNamespace(returncode=0, stdout=b"safe\x9btext\n")

            text = scan_public_repo_secrets.show_commit_file("abc123", "fixture.txt")

        self.assertEqual(text, "safetext\n")

    def test_history_blob_paths_skip_duplicates_and_binary_extensions(self):
        output = "\n".join(
            [
                "abc123",
                "blob1 safe.env",
                "blob1 duplicate.env",
                "blob2 image.png",
                "blob3 nested/config.txt",
            ]
        )
        with patch.object(scan_public_repo_secrets, "run_git", return_value=output):
            blobs = scan_public_repo_secrets.all_history_blob_paths()

        self.assertEqual(blobs, {"blob1": "safe.env", "blob3": "nested/config.txt"})

    def test_history_blob_decode_ignores_non_utf8_bytes(self):
        with patch.object(scan_public_repo_secrets.subprocess, "run") as run:
            run.return_value = SimpleNamespace(returncode=0, stdout=b"safe\x9btext\n")

            text = scan_public_repo_secrets.show_blob("blob1")

        self.assertEqual(text, "safetext\n")


if __name__ == "__main__":
    unittest.main()
