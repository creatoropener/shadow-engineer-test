"""Offline contract tests: fake Sandbox transport, real orchestration/adapters.

These do not claim to run native toolchains or the Nebius API.
"""
import itertools
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import proof
from patchproof_runtime.junit_check import classify_reports
from runtimes import detect_runtime


FIXTURES = {
    "python-pytest": {"app.py": "VALUE = 0\n"},
    "node-package": {"package.json": "{}", "app.js": "const value = 0;"},
    "static-web": {"index.html": "<script>const value = 0;</script>"},
    "web-playwright": {"index.html": "<script>const value = 0;</script>", "tests/requirements.txt": "playwright"},
    "java-junit": {"src/main/java/App.java": "class App {}"},
    "java-maven": {"pom.xml": "<project/>", "src/main/java/App.java": "class App {}"},
    "java-gradle": {"build.gradle": "plugins { id 'java' }", "gradlew": "",
                    "gradle/wrapper/gradle-wrapper.jar": "fixture", "gradle/wrapper/gradle-wrapper.properties": "fixture",
                    "src/main/java/App.java": "class App {}"},
    "go": {"go.mod": "module example.org/app", "app.go": "package app"},
    "rust": {"Cargo.toml": '[package]\nname="app"\nversion="0.1.0"', "src/lib.rs": "pub fn value() -> i32 { 0 }"},
}


class OrchestrationTests(unittest.TestCase):
    def test_all_adapters_reach_clean_replay(self):
        for (runtime, files), mode in itertools.product(FIXTURES.items(), ("pass", "zero_tests", "compile_error", "tampered_test")):
            with self.subTest(runtime=runtime, mode=mode), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                for name, content in files.items():
                    path = root / name
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_text(content)
                adapter = detect_runtime(root)
                context, allowed = proof.collect_repository_context(root, adapter, include_tests=False)
                self.assertTrue(context)
                self.assertTrue(allowed)
                source = sorted(allowed)[0]
                test_content = "# verifier\n" if adapter.test_suffix == ".py" else "verifier-test\n"
                test_hash = proof.sha256_text(test_content)
                commands, starts, applied = [], [], []
                parent = self

                class State:
                    uuid = "fake-image"
                    exit_code = 0
                    stdout = ""
                    stderr = ""

                    def run(self, *, shell, **kwargs):
                        commands.append(shell)
                        return self

                    def wait(self):
                        return self

                    def apply_files(self, *, files):
                        applied.append(files)
                        return State()

                base = State()
                def workspace(image, archive, selected, repo):
                    starts.append(image)
                    parent.assertIs(image, base)
                    parent.assertEqual(selected.id, runtime)
                    parent.assertTrue(archive.is_file())
                    return State()

                def run_tests(state, test_path, command):
                    commands.append(command)
                    parent.assertEqual(test_path, adapter.test_path(9))
                    if command == adapter.regression_command(test_path):
                        code = 101 if runtime == "rust" else 1
                        output = {"go": '{"Action":"fail","Test":"TestPatchProofValue"}',
                                  "rust": "assertion failed\ntest result: FAILED."}.get(runtime)
                        if output is None:
                            output = ("PATCHPROOF_JUNIT_ASSERTION_FAILURE=1" if adapter.test_runtime == "junit" else
                                      "ERR_ASSERTION\n# fail 1" if adapter.test_runtime == "node-test" else "AssertionError\n1 failed")
                    else:
                        parent.assertEqual(command, adapter.full_command(test_path))
                        code = 0
                        output = {"go": '{"Action":"pass","Test":"TestPatchProofValue"}',
                                  "rust": "test result: ok. 1 passed; 0 failed"}.get(runtime)
                        if output is None:
                            output = ("PATCHPROOF_JUNIT_PASS=1" if adapter.test_runtime == "junit" else
                                      "# pass 1" if adapter.test_runtime == "node-test" else "1 passed")
                    output += f"\nPATCHPROOF_TEST_HASH_BEFORE={test_hash}\nPATCHPROOF_TEST_HASH_AFTER={test_hash}\n"
                    if mode == "compile_error" and command == adapter.regression_command(test_path):
                        code, output = 2, "Compilation failed"
                    if mode == "zero_tests" and command == adapter.full_command(test_path):
                        output = output.replace("PASS=1", "PASS=0").replace("# pass 1", "# pass 0").replace("1 passed", "0 passed").replace('"Action":"pass"', '"Action":"skip"')
                    if mode == "tampered_test":
                        output = output.replace(f"PATCHPROOF_TEST_HASH_AFTER={test_hash}", "PATCHPROOF_TEST_HASH_AFTER=" + "0" * 64)
                    return SimpleNamespace(exit_code=code, stdout=output, stderr="", uuid="result")

                selected_secret = f"CONTREE_IMAGE_{runtime.replace('-', '_').upper()}"
                sdk = SimpleNamespace(images=SimpleNamespace(use=lambda uuid, strict: base))
                env = {"NEBIUS_API_KEY": "test", "NEBIUS_PROJECT_ID": "test", "NEBIUS_MODEL": "test", selected_secret: "selected-image"}
                evidence = {"candidates": []}
                with patch.dict("os.environ", env, clear=True), \
                     patch.object(proof, "create_sandbox_client", return_value=sdk), \
                     patch.object(proof, "sandbox_workspace", side_effect=workspace), \
                     patch.object(proof, "generate_regression_test", return_value=(test_content, "test rationale")), \
                     patch.object(proof, "generate_candidate", return_value=([{"path": source, "content": files[source] + "\n"}], "repair")) as generate, \
                     patch.object(proof, "run_protected_tests", side_effect=run_tests):
                    if mode == "pass":
                        result = proof.execute(root, proof.Issue(9, "Bug", "Expected value"), evidence)
                    else:
                        with self.assertRaises(proof.PatchProofError):
                            proof.execute(root, proof.Issue(9, "Bug", "Expected value"), evidence)
                        self.assertFalse((root / adapter.test_path(9)).exists())
                        self.assertEqual((root / source).read_text(), files[source])
                        self.assertEqual(generate.call_count, 3 if mode == "zero_tests" else 0)
                        continue
                self.assertEqual(result["verdict"], "verified")
                self.assertEqual(result["runtime"]["image_env"], selected_secret)
                self.assertEqual(generate.call_count, 3)
                self.assertEqual(len(starts), 2, "Replay must start from original image again")
                self.assertIn(adapter.baseline_command, commands)
                self.assertEqual(commands.count(adapter.full_command(adapter.test_path(9))), 4)
                self.assertEqual((root / adapter.test_path(9)).read_text(), test_content)

    def test_protected_paths_all_ecosystems(self):
        for name in ("thing_test.go", "src/test/java/Thing.java", "ThingTest.java", "TestThing.java",
                     "app.test.ts", "app.spec.js", "tests/check.rs", "build.rs", "patchproof.json"):
            with self.subTest(name=name):
                self.assertTrue(proof.is_protected_path(Path(name)))

    def test_context_excludes_build_and_dependencies(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name in ("app.py", "node_modules/bad.py", "target/bad.py", "vendor/bad.py"):
                path = root / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("VALUE = 0")
            context, allowed = proof.collect_repository_context(root, detect_runtime(root), include_tests=False)
            self.assertEqual(allowed, {"app.py"})
            self.assertNotIn("bad.py", context)


class JunitEvidenceTests(unittest.TestCase):
    def check(self, xml, returncode):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "TEST.xml"
            path.write_text(xml)
            return classify_reports([path], "PatchProofIssue9Test", returncode)

    def test_passed_test(self):
        self.assertEqual(self.check('<testsuite><testcase classname="PatchProofIssue9Test"/></testsuite>', 0), (0, 1))

    def test_assertion_failure(self):
        self.assertEqual(self.check('<testsuite><testcase classname="PatchProofIssue9Test"><failure type="org.opentest4j.AssertionFailedError"/></testcase></testsuite>', 1), (1, 0))

    def test_runtime_error_is_not_reproduction(self):
        self.assertEqual(self.check('<testsuite><testcase classname="PatchProofIssue9Test"><failure type="java.lang.NullPointerException"/></testcase></testsuite>', 1), (2, 0))

    def test_skipped_empty_wrong_class_and_malformed_fail_closed(self):
        for xml in ('<testsuite/>', '<testsuite><testcase classname="OtherTest"/></testsuite>',
                    '<testsuite><testcase classname="PatchProofIssue9Test"><skipped/></testcase></testsuite>', 'not xml'):
            with self.subTest(xml=xml):
                self.assertEqual(self.check(xml, 0), (2, 0))

    def test_compile_failure_cannot_reuse_passing_report(self):
        self.assertEqual(self.check('<testsuite><testcase classname="PatchProofIssue9Test"/></testsuite>', 1), (2, 0))


if __name__ == "__main__":
    unittest.main()
