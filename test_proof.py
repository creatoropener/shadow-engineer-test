import unittest

from proof import (
    PatchProofError,
    extract_json_object,
    render_report,
    validate_candidate,
)


class JsonExtractionTests(unittest.TestCase):
    def test_extracts_fenced_json(self):
        value = extract_json_object('result:\n```json\n{"ok": true}\n```')
        self.assertEqual(value, {"ok": True})

    def test_extracts_json_after_reasoning(self):
        value = extract_json_object('thinking first\n{"value": 3}\nfinished')
        self.assertEqual(value["value"], 3)


class CandidateValidationTests(unittest.TestCase):
    def test_accepts_allowed_source_replacement(self):
        changes, summary = validate_candidate(
            {
                "summary": "Fix edge case",
                "changes": [{"path": "calculator.py", "content": "VALUE = 1\n"}],
            },
            {"calculator.py"},
        )
        self.assertEqual(summary, "Fix edge case")
        self.assertEqual(changes[0]["path"], "calculator.py")

    def test_rejects_regression_test_edit(self):
        with self.assertRaises(PatchProofError):
            validate_candidate(
                {
                    "summary": "Cheat",
                    "changes": [
                        {
                            "path": "test_patchproof_issue_1.py",
                            "content": "def test_fake(): assert True\n",
                        }
                    ],
                },
                {"calculator.py"},
            )


class ReportTests(unittest.TestCase):
    def test_verified_report_contains_evidence(self):
        report = render_report(
            {
                "verdict": "verified",
                "issue": {"number": 1, "title": "Bug"},
                "model": "nvidia/example",
                "sandbox": {"base_image": "image-1"},
                "regression_test": {
                    "path": "test_patchproof_issue_1.py",
                    "failed_before_fix": True,
                    "protected": True,
                },
                "candidates": [
                    {
                        "candidate": index,
                        "passed": index == 2,
                        "test_protected": True,
                        "changed_files": ["calculator.py"],
                        "duration_seconds": 1.0,
                        "image": f"candidate-image-{index}",
                    }
                    for index in range(1, 4)
                ],
                "winner": {"candidate": 2, "summary": "Fix"},
                "clean_replay": {"passed": True, "tests_passed": 6},
            }
        )
        self.assertIn("VERIFIED", report)
        self.assertIn("Candidate sandbox branches evaluated: 3", report)
        self.assertIn("Winner replayed from the clean base image", report)


if __name__ == "__main__":
    unittest.main()
