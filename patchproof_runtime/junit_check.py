"""Run a filtered JVM regression and classify fresh JUnit XML evidence.

Exit 0: executed and passed; 1: assertion failure; 2: infrastructure/unknown.
Build commands must clean their test output first (Maven clean / Gradle cleanTest).
"""
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path


def classify_reports(paths, class_name, returncode):
    cases = []
    for path in paths:
        try:
            document = ET.parse(path)
        except (OSError, ET.ParseError):
            return 2, 0
        cases.extend(case for case in document.iter("testcase")
                     if case.get("classname", "").rsplit(".", 1)[-1] == class_name)
    if not cases or any(case.find("error") is not None or case.find("skipped") is not None for case in cases):
        return 2, 0
    failures = [failure for case in cases for failure in case.findall("failure")]
    if failures:
        assertion_only = all(any(marker in failure.get("type", "")
                                 for marker in ("Assertion", "ComparisonFailure")) for failure in failures)
        return (1 if returncode != 0 and assertion_only else 2), 0
    return (0, len(cases)) if returncode == 0 else (2, 0)


def main():
    runtime, class_name, command = sys.argv[1:]
    patterns = {"java-maven": "target/surefire-reports/TEST-*.xml",
                "java-gradle": "build/test-results/test/TEST-*.xml",
                "java-junit": "/tmp/patchproof-java/reports/TEST-*.xml"}
    pattern = patterns[runtime]
    # Never trust reports left by an earlier run, including cached Gradle output.
    directory, glob = pattern.rsplit("/", 1)
    for path in Path(directory).glob(glob):
        path.unlink()
    result = subprocess.run(["sh", "-c", command], check=False)
    code, passed = classify_reports(Path(directory).glob(glob), class_name, result.returncode)
    print(f"PATCHPROOF_JUNIT_PASS={passed}")
    if code == 1:
        print("PATCHPROOF_JUNIT_ASSERTION_FAILURE=1")
    if code == 2:
        print("PatchProof: no trustworthy executed JUnit regression (build error, skipped test, missing XML, or runtime exception).", file=sys.stderr)
    return code


if __name__ == "__main__":
    sys.exit(main())
