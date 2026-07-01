import unittest

from util.scan_public_repo_secrets import scan_text


class TestPublicRepoSecretScan(unittest.TestCase):
    def test_task_control_words_do_not_match_openai_keys(self):
        findings = scan_text(
            "ai-runtime-operator-taREDACTED_KEY_FIXTURE.json",
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


if __name__ == "__main__":
    unittest.main()
