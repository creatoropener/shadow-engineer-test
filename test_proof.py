import tempfile
import unittest
from pathlib import Path

from proof import (
    PatchProofError,
    extract_json_object,
    render_report,
    validate_candidate,
)
from runtimes import detect_runtime


class JsonExtractionTests(unittest.TestCase):
    def test_extracts_fenced_json(self):
        value = extract_json_object('result:\n```json\n{"ok": true}\n```')
        self.assertEqual(value, {"ok": True})

    def test_extracts_json_after_reasoning(self):
        value = extract_json_object('thinking first\n{"value": 3}\nfinished')
        self.assertEqual(value["value"], 3)


class CandidateValidationTests(unittest.TestCase):
    def test_accepts_allowed_source_replacement(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "calculator.py").write_text("VALUE = 0\n", encoding="utf-8")
            adapter = detect_runtime(root)
            changes, summary = validate_candidate(
                {
                    "summary": "Fix edge case",
                    "edits": [
                        {
                            "path": "calculator.py",
                            "old": "VALUE = 0",
                            "new": "VALUE = 1",
                        }
                    ],
                },
                {"calculator.py"},
                root,
                adapter,
            )
            self.assertEqual(summary, "Fix edge case")
            self.assertEqual(changes[0]["path"], "calculator.py")
            self.assertEqual(changes[0]["content"], "VALUE = 1\n")

    def test_accepts_small_edit_in_large_html_file(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            html = "<html><script>function value() { return 0; }</script></html>"
            (root / "index.html").write_text(html, encoding="utf-8")
            adapter = detect_runtime(root)
            changes, _ = validate_candidate(
                {
                    "summary": "Correct web behavior",
                    "edits": [
                        {
                            "path": "index.html",
                            "old": "return 0;",
                            "new": "return 1;",
                        }
                    ],
                },
                {"index.html"},
                root,
                adapter,
            )
            self.assertIn("return 1;", changes[0]["content"])
            self.assertNotIn("return 0;", changes[0]["content"])

    def test_rejects_regression_test_edit(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "calculator.py").write_text("VALUE = 0\n", encoding="utf-8")
            adapter = detect_runtime(root)
            with self.assertRaises(PatchProofError):
                validate_candidate(
                    {
                        "summary": "Cheat",
                        "edits": [
                            {
                                "path": "test_patchproof_issue_1.py",
                                "old": "assert False",
                                "new": "assert True",
                            }
                        ],
                    },
                    {"calculator.py"},
                    root,
                    adapter,
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
        self.assertIn("PatchProof v0.5", report)
        self.assertIn("Candidate sandbox branches evaluated: 3", report)
        self.assertIn("Winner replayed from the clean base image", report)


if __name__ == "__main__":
    unittest.main()
