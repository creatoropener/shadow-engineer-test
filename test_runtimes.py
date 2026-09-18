import json
import tempfile
import unittest
from pathlib import Path

from runtimes import RuntimeDetectionError, detect_runtime


class RuntimeDetectionTests(unittest.TestCase):
    def detect(self, files):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name)
        for name, content in files.items():
            path = root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")
        return detect_runtime(root)

    def test_detects_python_pytest(self):
        adapter = self.detect({"calculator.py": "VALUE = 1\n"})
        self.assertEqual(adapter.id, "python-pytest")
        self.assertEqual(adapter.test_suffix, ".py")

    def test_detects_node_package(self):
        adapter = self.detect(
            {
                "package.json": json.dumps(
                    {"scripts": {"test": "node --test tests/*.test.js"}}
                ),
                "src/app.js": "export const value = 1;\n",
            }
        )
        self.assertEqual(adapter.id, "node-package")
        self.assertIn("npm test", adapter.baseline_command)

    def test_detects_static_web(self):
        adapter = self.detect(
            {"index.html": "<html><script>const value = 1;</script></html>"}
        )
        self.assertEqual(adapter.id, "static-web")
        self.assertTrue(adapter.is_editable_source(Path("index.html")))
        self.assertIn("jsdom", adapter.verifier_guidance)

    def test_detects_src_html(self):
        adapter = self.detect({"src/index.html": "<html></html>"})
        self.assertIn("src/index.html", adapter.baseline_command)

    def test_detects_maven(self):
        adapter = self.detect({"pom.xml": "<project/>"})
        self.assertEqual(adapter.id, "java-maven")
        self.assertEqual(adapter.test_path(4), "src/test/java/PatchProofIssue4Test.java")
        self.assertIn("-Dtest=PatchProofIssue4Test", adapter.regression_command(adapter.test_path(4)))

    def test_maven_prefers_wrapper(self):
        adapter = self.detect({"pom.xml": "<project/>", "mvnw": "#!/bin/sh"})
        self.assertEqual(adapter.tool_command, "sh ./mvnw")

    def test_detects_gradle(self):
        adapter = self.detect({"build.gradle.kts": "plugins { java }", "gradlew": "",
                               "gradle/wrapper/gradle-wrapper.jar": "fixture",
                               "gradle/wrapper/gradle-wrapper.properties": "fixture"})
        self.assertEqual(adapter.id, "java-gradle")
        self.assertIn("--tests", adapter.regression_command(adapter.test_path(4)))
        self.assertIn("--rerun-tasks", adapter.baseline_command)

    def test_gradle_requires_wrapper(self):
        with self.assertRaises(RuntimeDetectionError):
            self.detect({"build.gradle": "plugins { id 'java' }"})

    def test_plain_java(self):
        adapter = self.detect({"src/main/java/App.java": "public class App {}"})
        self.assertEqual(adapter.id, "java-junit")

    def test_go(self):
        adapter = self.detect({"go.mod": "module example.org/app\n", "app.go": "package app\n"})
        self.assertEqual(adapter.id, "go")
        self.assertEqual(adapter.test_path(4), "patchproof_issue_4_test.go")
        self.assertIn("-count=1", adapter.regression_command(adapter.test_path(4)))

    def test_go_nested_package(self):
        adapter = self.detect({"go.mod": "module example.org/app\n", "internal/app.go": "package internal\n",
                               "patchproof.json": '{"runtime":"go", "test_directory":"internal"}'})
        self.assertEqual(adapter.test_path(4), "internal/patchproof_issue_4_test.go")
        self.assertIn("./internal", adapter.regression_command(adapter.test_path(4)))

    def test_go_without_root_package_needs_config(self):
        with self.assertRaises(RuntimeDetectionError):
            self.detect({"go.mod": "module app", "internal/app.go": "package app"})

    def test_rust(self):
        adapter = self.detect({"Cargo.toml": '[package]\nname="app"\nversion="0.1.0"'})
        self.assertEqual(adapter.id, "rust")
        self.assertEqual(adapter.test_path(4), "tests/patchproof_issue_4.rs")
        self.assertIn("--test patchproof_issue_4", adapter.regression_command(adapter.test_path(4)))

    def test_virtual_rust_workspace_rejected(self):
        with self.assertRaises(RuntimeDetectionError):
            self.detect({"Cargo.toml": '[workspace]\nmembers=[]'})

    def test_ambiguous_manifests_require_selection(self):
        with self.assertRaises(RuntimeDetectionError):
            self.detect({"pom.xml": "<project/>", "package.json": "{}"})
        adapter = self.detect({"pom.xml": "<project/>", "package.json": "{}", "patchproof.json": '{"runtime":"java-maven"}'})
        self.assertEqual(adapter.id, "java-maven")

    def test_rejects_test_directory_escape(self):
        with self.assertRaises(RuntimeDetectionError):
            self.detect({"patchproof.json": '{"runtime":"go", "test_directory":"../escape"}'})

    def test_node_assertion_not_import_failure(self):
        adapter = self.detect({"package.json": "{}"})
        self.assertTrue(adapter.is_regression_failure(1, "code: ERR_ASSERTION\n# fail 1"))
        self.assertFalse(adapter.is_regression_failure(1, "ERR_MODULE_NOT_FOUND"))
        self.assertFalse(adapter.is_regression_failure(1, "SyntaxError"))
        self.assertEqual(adapter.passed_count("# tests 3\n# pass 2\n# fail 1"), 2)

    def test_rust_assertion_not_compilation(self):
        adapter = self.detect({"Cargo.toml": '[package]\nname="app"\nversion="0.1.0"'})
        self.assertTrue(adapter.is_regression_failure(101, "assertion failed\ntest result: FAILED."))
        self.assertFalse(adapter.is_regression_failure(101, "could not compile app"))
        self.assertEqual(adapter.passed_count("test result: ok. 2 passed; 0 failed"), 2)

    def test_go_counts_tests_not_packages(self):
        adapter = self.detect({"go.mod": "module app", "app.go": "package app"})
        output = '\n'.join(json.dumps(e) for e in [
            {"Action":"pass", "Package":"app", "Test":"TestPatchProof"}, {"Action":"pass", "Package":"app"}])
        self.assertEqual(adapter.passed_count(output), 1)
        self.assertTrue(adapter.is_regression_failure(1, '{"Action":"fail","Test":"TestPatchProofWifi"}'))
        self.assertFalse(adapter.is_regression_failure(1, '{"Action":"fail","Package":"app"}'))

    def test_full_run_never_counts_baseline_as_regression(self):
        adapter = self.detect({"package.json": "{}"})
        self.assertIn("PATCHPROOF_REGRESSION_START", adapter.full_command(adapter.test_path(3)))
        self.assertEqual(adapter.passed_count("# pass 20\nPATCHPROOF_REGRESSION_START\n# pass 0"), 0)

    def test_detects_qrcrafts_style_playwright_hybrid(self):
        adapter = self.detect(
            {
                "index.html": "<html><script>const value = 1;</script></html>",
                "tests/requirements.txt": "pytest==9.1.1\nplaywright==1.55.0\n",
                "tests/test_browser.py": "from playwright.sync_api import sync_playwright\n",
            }
        )
        self.assertEqual(adapter.id, "web-playwright")
        self.assertIn("HTML", adapter.application_languages)
        self.assertEqual(adapter.test_runtime, "pytest-playwright")
        self.assertEqual(adapter.test_path(7), "tests/test_patchproof_issue_7.py")


if __name__ == "__main__":
    unittest.main()
