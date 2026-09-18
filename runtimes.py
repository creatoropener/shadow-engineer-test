"""Runtime adapters for PatchProof's language-neutral orchestration layer."""

from __future__ import annotations

import json
import shlex
import re
from dataclasses import dataclass
from pathlib import Path


class RuntimeDetectionError(ValueError):
    """Raised when a repository cannot be mapped to a supported runtime."""


@dataclass(frozen=True)
class RuntimeAdapter:
    id: str
    display_name: str
    application_languages: tuple[str, ...]
    test_runtime: str
    source_extensions: frozenset[str]
    context_extensions: frozenset[str]
    context_names: frozenset[str]
    test_suffix: str
    baseline_command: str
    bootstrap_command: str
    preflight_command: str
    verifier_guidance: str
    solver_guidance: str
    test_directory: str = ""
    tool_command: str = ""

    def test_path(self, issue_number: int) -> str:
        identifier = str(issue_number) if issue_number else "manual"
        if self.test_runtime == "junit":
            return f"src/test/java/PatchProofIssue{identifier}Test.java"
        if self.id == "go":
            return f"{self.test_directory}/patchproof_issue_{identifier}_test.go".lstrip("/")
        if self.id == "rust":
            return f"tests/patchproof_issue_{identifier}.rs"
        prefix = "tests/" if self.id == "web-playwright" else ""
        if self.test_suffix == ".py":
            return f"{prefix}test_patchproof_issue_{identifier}.py"
        return f"{prefix}test_patchproof_issue_{identifier}{self.test_suffix}"

    def regression_command(self, test_path: str) -> str:
        target = shlex.quote(test_path)
        name = Path(test_path).stem
        if self.id == "go":
            directory = shlex.quote("./" + str(Path(test_path).parent))
            identifier = name.removeprefix("patchproof_issue_").removesuffix("_test")
            pattern = shlex.quote(f"^TestPatchProofIssue{identifier}($|_)")
            return f"go test -json -count=1 {directory} -run {pattern}"
        if self.id == "rust":
            return f"cargo test --locked --offline --test {shlex.quote(name)} -- --nocapture"
        if self.test_runtime == "junit":
            if self.id == "java-maven":
                command = f"{self.tool_command} -B clean test -Dtest={name} -DfailIfNoTests=true"
            elif self.id == "java-gradle":
                command = f"{self.tool_command} --no-daemon --console=plain cleanTest test --rerun-tasks --tests '*{name}'"
            else:
                command = f"python /patchproof/java_check.py {shlex.quote(name)}"
            return f"python /patchproof/junit_check.py {self.id} {shlex.quote(name)} {shlex.quote(command)}"
        if self.test_runtime in {"pytest", "pytest-playwright"}:
            prefix = (
                "PLAYWRIGHT_BROWSERS_PATH=0 "
                if self.test_runtime == "pytest-playwright"
                else ""
            )
            return f"{prefix}python -m pytest -q {target}"
        return f"node --test {target}"

    def full_command(self, test_path: str) -> str:
        # The isolated regression always runs explicitly, even if a project's
        # normal suite silently excludes new test files.
        return f"{self.baseline_command} && echo PATCHPROOF_REGRESSION_START && {self.regression_command(test_path)}"

    def is_context_file(self, path: Path) -> bool:
        return (
            path.name in self.context_names
            or path.suffix.lower() in self.context_extensions
        )

    def is_editable_source(self, path: Path) -> bool:
        return path.suffix.lower() in self.source_extensions

    def validate_generated_test(self, content: str, filename: str) -> None:
        if not content.strip():
            raise ValueError("Generated regression test is empty.")
        if self.test_suffix == ".py":
            compile(content, filename, "exec")

    def validate_candidate_file(self, path: str, content: str) -> None:
        if Path(path).suffix.lower() == ".py":
            compile(content, path, "exec")

    def passed_count(self, output: str) -> int | None:
        output = output.rsplit("PATCHPROOF_REGRESSION_START", 1)[-1]
        if self.id == "go":
            events = _go_events(output)
            counts = [e for e in events if e.get("Action") == "pass" and e.get("Test")]
            return len(counts) if events else None
        if self.test_runtime == "junit":
            patterns = [r"PATCHPROOF_JUNIT_PASS=(\d+)"]
        elif self.id == "rust":
            patterns = [r"test result: ok\. (\d+) passed"]
        elif self.test_runtime == "node-test":
            patterns = [r"# pass\s+(\d+)"]
        else:
            patterns = [r"(\d+) passed"]
        for pattern in patterns:
            matches = re.findall(pattern, output)
            if matches:
                return int(matches[-1])
        return None

    def is_regression_failure(self, exit_code: int, output: str) -> bool:
        if self.id == "rust":
            return (exit_code == 101 and "test result: FAILED." in output
                    and "assertion" in output and "could not compile" not in output)
        if exit_code != 1:
            return False
        if self.test_runtime == "junit":
            return "PATCHPROOF_JUNIT_ASSERTION_FAILURE=1" in output
        if self.id == "go":
            return any(e.get("Action") == "fail" and e.get("Test", "").startswith("TestPatchProof")
                       for e in _go_events(output)) and "[build failed]" not in output
        if self.test_runtime == "node-test":
            return "ERR_ASSERTION" in output and "ERR_MODULE_NOT_FOUND" not in output and "SyntaxError" not in output
        return ("AssertionError" in output and bool(re.search(r"\d+ failed", output))
                and not re.search(r"\d+ errors?", output))


def _go_events(output: str) -> list[dict]:
    events = []
    for line in output.splitlines():
        try:
            item = json.loads(line)
            if isinstance(item, dict) and "Action" in item:
                events.append(item)
        except ValueError:
            pass
    return events


def _contains_playwright(root: Path) -> bool:
    candidates = [
        root / "tests" / "requirements.txt",
        root / "requirements.txt",
        root / "pyproject.toml",
    ]
    for path in candidates:
        if path.is_file():
            try:
                if "playwright" in path.read_text(encoding="utf-8").lower():
                    return True
            except (OSError, UnicodeDecodeError):
                pass
    for path in (root / "tests").glob("*.py") if (root / "tests").is_dir() else ():
        try:
            if "playwright" in path.read_text(encoding="utf-8").lower():
                return True
        except (OSError, UnicodeDecodeError):
            pass
    return False


def _python_bootstrap(root: Path) -> str:
    if (root / "requirements.txt").is_file():
        return "python -m pip install --disable-pip-version-check -r requirements.txt"
    if (root / "pyproject.toml").is_file():
        return "python -m pip install --disable-pip-version-check ."
    return "true"


def _node_baseline(root: Path) -> tuple[str, str]:
    package_path = root / "package.json"
    try:
        package = json.loads(package_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise RuntimeDetectionError(f"Invalid package.json: {error}") from error
    scripts = package.get("scripts") if isinstance(package, dict) else None
    has_test_script = isinstance(scripts, dict) and isinstance(scripts.get("test"), str)
    baseline = "CI=1 npm test" if has_test_script else "node --test"
    if (root / "npm-shrinkwrap.json").is_file() or (
        root / "package-lock.json"
    ).is_file():
        bootstrap = "npm ci --ignore-scripts --no-audit --no-fund"
    else:
        bootstrap = "npm install --ignore-scripts --no-audit --no-fund"
    return baseline, bootstrap


def _compiled_adapter(root: Path, runtime: str, test_directory: str) -> RuntimeAdapter:
    common = dict(
        id=runtime, solver_guidance="Repair existing application source only; do not edit tests, build scripts, manifests, or lockfiles.",
        test_directory=test_directory,
    )
    if runtime == "go":
        directory = root / test_directory
        if not any(p for p in directory.glob("*.go") if not p.name.endswith("_test.go")):
            raise RuntimeDetectionError("Go needs a package with source files. Set test_directory in patchproof.json (for example internal/wifi).")
        return RuntimeAdapter(**common, display_name="Go modules", application_languages=("Go",),
            test_runtime="go-test", source_extensions=frozenset({".go"}),
            context_extensions=frozenset({".go"}), context_names=frozenset({"go.mod", "go.sum"}),
            test_suffix="_test.go", baseline_command="go test -json -count=1 ./...",
            bootstrap_command="go mod download", preflight_command="go version",
            verifier_guidance=f"Write a native Go testing test in package directory {test_directory or '.'}. Match that package declaration. Name every test TestPatchProofIssue<identifier> or TestPatchProofIssue<identifier>_<suffix>, where identifier is the issue identifier in the required filename. Use t.Errorf or t.Fatalf on observable wrong results; no network, skips, source edits, or build tags.")
    if runtime == "rust":
        import tomllib
        manifest = tomllib.loads((root / "Cargo.toml").read_text())
        if "package" not in manifest or manifest.get("package", {}).get("autotests") is False:
            raise RuntimeDetectionError("Rust requires a root Cargo package with automatic integration tests enabled; virtual workspaces are not yet supported.")
        return RuntimeAdapter(**common, display_name="Rust / Cargo", application_languages=("Rust",),
            test_runtime="cargo-test", source_extensions=frozenset({".rs"}),
            context_extensions=frozenset({".rs"}), context_names=frozenset({"Cargo.toml", "Cargo.lock"}),
            test_suffix=".rs", baseline_command="cargo test --locked --offline",
            bootstrap_command="cargo fetch --locked" if (root / "Cargo.lock").exists() else "cargo generate-lockfile && cargo fetch --locked",
            preflight_command="rustc --version && cargo --version",
            verifier_guidance="Write a Rust integration test using #[test] and assert_eq!/assert!. Import the public library crate; for a binary-only crate use std::process::Command and env!(\"CARGO_BIN_EXE_<binary-name>\"). No include! of copied source, ignored tests, source edits, network, or custom harness.")
    tool = ""
    if runtime == "java-maven":
        tool = "sh ./mvnw" if (root / "mvnw").is_file() else "mvn"
        baseline, bootstrap = f"{tool} -B clean test", f"{tool} -B -DskipTests test-compile"
    elif runtime == "java-gradle":
        if not (root / "gradlew").is_file():
            raise RuntimeDetectionError("Gradle requires the committed gradlew, wrapper JAR, and wrapper properties; a system Gradle may be incompatible.")
        for name in ("gradle/wrapper/gradle-wrapper.jar", "gradle/wrapper/gradle-wrapper.properties"):
            if not (root / name).is_file():
                raise RuntimeDetectionError(f"Missing Gradle wrapper file: {name}")
        tool = "sh ./gradlew"
        baseline = f"{tool} --no-daemon --console=plain cleanTest test --rerun-tasks"
        bootstrap = f"{tool} --no-daemon testClasses"
    else:
        if not (root / "src/main/java").is_dir():
            raise RuntimeDetectionError("Plain Java requires src/main/java; use Maven or Gradle for custom layouts or dependencies.")
        baseline, bootstrap = "python /patchproof/java_check.py", "true"
    return RuntimeAdapter(**common, display_name={"java-maven": "Java / Maven", "java-gradle": "Java / Gradle", "java-junit": "Java / JUnit standalone"}[runtime],
        application_languages=("Java",), test_runtime="junit", source_extensions=frozenset({".java"}),
        context_extensions=frozenset({".java", ".gradle", ".kts"}),
        context_names=frozenset({"pom.xml", "build.gradle", "build.gradle.kts", "settings.gradle", "settings.gradle.kts"}),
        test_suffix=".java", baseline_command=baseline, bootstrap_command=bootstrap,
        preflight_command="java -version && javac -version" + (f" && {tool} --version" if tool else ""),
        tool_command=tool,
        verifier_guidance="Write one JUnit test class whose class name exactly matches the required filename, with no package declaration. Import application classes by fully qualified name and test public behavior with assertions. For Maven/Gradle reuse the existing JUnit version; do not add dependencies. Plain Java supplies JUnit Jupiter. Never skip tests or edit the build configuration.")


def detect_runtime(root: Path) -> RuntimeAdapter:
    root = root.resolve()
    config_path = root / "patchproof.json"
    try:
        config = json.loads(config_path.read_text()) if config_path.is_file() else {}
    except (OSError, ValueError) as error:
        raise RuntimeDetectionError(f"Invalid patchproof.json: {error}") from error
    if not isinstance(config, dict) or set(config) - {"runtime", "test_directory"}:
        raise RuntimeDetectionError("patchproof.json accepts only runtime and test_directory.")
    requested = config.get("runtime")
    if requested is not None and not isinstance(requested, str):
        raise RuntimeDetectionError("runtime must be a string adapter ID.")
    directory = config.get("test_directory", "")
    if not isinstance(directory, str) or Path(directory).is_absolute() or ".." in Path(directory).parts or not (root / directory).resolve().is_relative_to(root):
        raise RuntimeDetectionError("test_directory must stay inside the repository.")
    markers = {"java-maven": "pom.xml", "java-gradle": "build.gradle", "go": "go.mod", "rust": "Cargo.toml", "node-package": "package.json"}
    found = [key for key, name in markers.items() if (root / name).is_file()]
    if (root / "build.gradle.kts").is_file() and "java-gradle" not in found:
        found.append("java-gradle")
    if requested is None and len(found) > 1:
        raise RuntimeDetectionError("Multiple runtime manifests found; select runtime in patchproof.json: " + ", ".join(found))
    selected = requested or (found[0] if found else None)
    compiled = {"java-maven", "java-gradle", "java-junit", "go", "rust"}
    if selected in compiled:
        if selected != "java-junit" and selected not in found:
            raise RuntimeDetectionError(f"Missing manifest for selected runtime {selected}.")
        return _compiled_adapter(root, selected, directory)
    if selected is None and any((root / "src/main/java").rglob("*.java")):
        return _compiled_adapter(root, "java-junit", directory)
    adapter = _detect_script_runtime(root, requested)
    if requested is not None and requested != adapter.id:
        raise RuntimeDetectionError(f"Requested runtime {requested!r} does not match detected {adapter.id!r}.")
    return adapter


def _detect_script_runtime(root: Path, requested: str | None = None) -> RuntimeAdapter:
    root = root.resolve()
    has_html = any(
        path.is_file() for path in (root / "index.html", root / "src" / "index.html")
    )

    if requested in (None, "web-playwright") and has_html and _contains_playwright(root):
        bootstrap = _python_bootstrap(root)
        if (root / "tests/requirements.txt").is_file():
            bootstrap += " && python -m pip install -r tests/requirements.txt"
        return RuntimeAdapter(
            id="web-playwright",
            display_name="Web application + Python Playwright",
            application_languages=("HTML", "CSS", "JavaScript"),
            test_runtime="pytest-playwright",
            source_extensions=frozenset({".html", ".css", ".js", ".mjs", ".cjs"}),
            context_extensions=frozenset(
                {".html", ".css", ".js", ".mjs", ".cjs", ".py"}
            ),
            context_names=frozenset({"requirements.txt", "pyproject.toml"}),
            test_suffix=".py",
            baseline_command="PLAYWRIGHT_BROWSERS_PATH=0 python -m pytest -q tests",
            bootstrap_command=(
                f"{bootstrap} && "
                "PLAYWRIGHT_BROWSERS_PATH=0 python -m playwright install chromium"
            ),
            preflight_command=(
                "python -c \"import pytest, playwright; print('Playwright ready')\""
            ),
            verifier_guidance=(
                "Return a pytest Playwright regression that exercises observable browser "
                "behavior. Reuse fixtures from tests/conftest.py when present. Keep it "
                "offline and deterministic; do not change application source."
            ),
            solver_guidance=(
                "Repair only HTML, CSS, or JavaScript application source. Preserve the "
                "existing UI and unrelated behavior."
            ),
        )

    if requested in (None, "node-package") and (root / "package.json").is_file():
        baseline, bootstrap = _node_baseline(root)
        return RuntimeAdapter(
            id="node-package",
            display_name="Node.js / JavaScript / TypeScript",
            application_languages=("JavaScript", "TypeScript"),
            test_runtime="node-test",
            source_extensions=frozenset({".js", ".mjs", ".cjs", ".jsx", ".ts", ".tsx"}),
            context_extensions=frozenset(
                {".js", ".mjs", ".cjs", ".jsx", ".ts", ".tsx", ".json"}
            ),
            context_names=frozenset({"package.json", "tsconfig.json"}),
            test_suffix=".test.mjs",
            baseline_command=baseline,
            bootstrap_command=bootstrap,
            preflight_command="node --version && npm --version",
            verifier_guidance=(
                "Return an offline deterministic test using node:test and node:assert. "
                "The test may import project modules but must not modify the repository."
            ),
            solver_guidance=(
                "Repair existing JavaScript or TypeScript application files only. "
                "Keep module format and public APIs compatible."
            ),
        )

    if requested in (None, "static-web") and has_html:
        entry = "index.html" if (root / "index.html").is_file() else "src/index.html"
        return RuntimeAdapter(
            id="static-web",
            display_name="Static HTML / CSS / JavaScript",
            application_languages=("HTML", "CSS", "JavaScript"),
            test_runtime="node-test",
            source_extensions=frozenset({".html", ".css", ".js", ".mjs", ".cjs"}),
            context_extensions=frozenset({".html", ".css", ".js", ".mjs", ".cjs"}),
            context_names=frozenset(),
            test_suffix=".test.mjs",
            baseline_command=f"node /patchproof/static_web_check.mjs {entry}",
            bootstrap_command="true",
            preflight_command="node --version && node -e \"require('/opt/patchproof/node/node_modules/jsdom')\"",
            verifier_guidance=(
                "Return one offline node:test regression for this static web app. Use "
                "the real DOM via preinstalled jsdom: import {createRequire} from 'node:module'; "
                "const {JSDOM} = createRequire('/opt/patchproof/node/package.json')('jsdom'); "
                "Load the actual HTML from disk and exercise its functions/events. Use runScripts: 'outside-only' "
                "and window.eval for relevant actual inline scripts. Do not enable external resources, "
                "network access, install packages, or reproduce the application algorithm in the test. "
                "jsdom is not a real browser: layout/canvas/visual behavior requires Playwright."
            ),
            solver_guidance=(
                "Repair existing HTML, CSS, or inline/external JavaScript only. Preserve "
                "the single-page app structure and unrelated UI behavior."
            ),
        )

    python_markers = (
        root / "pyproject.toml",
        root / "requirements.txt",
        root / "setup.py",
        root / "pytest.ini",
    )
    has_application_python = any(
        path.is_file()
        and "tests" not in {part.lower() for part in path.relative_to(root).parts}
        and not path.name.startswith("test_")
        and path.name not in {"proof.py", "runtimes.py", "apply_fix.py"}
        and "patchproof_runtime" not in path.relative_to(root).parts
        for path in root.rglob("*.py")
    )
    if requested in (None, "python-pytest") and (any(path.is_file() for path in python_markers) or has_application_python):
        return RuntimeAdapter(
            id="python-pytest",
            display_name="Python + pytest",
            application_languages=("Python",),
            test_runtime="pytest",
            source_extensions=frozenset({".py"}),
            context_extensions=frozenset({".py", ".toml"}),
            context_names=frozenset(
                {"requirements.txt", "pyproject.toml", "pytest.ini"}
            ),
            test_suffix=".py",
            baseline_command="python -m pytest -q --ignore=regression",
            bootstrap_command=_python_bootstrap(root),
            preflight_command="python -m pytest --version",
            verifier_guidance=(
                "Return one deterministic pytest regression. It must fail through a "
                "normal assertion on the reported behavior, not collection or import errors."
            ),
            solver_guidance=(
                "Repair existing Python application source only and preserve public APIs."
            ),
        )

    raise RuntimeDetectionError(
        "Unsupported repository. Supported: Python, Node, static web, Python Playwright, "
        "Java/JUnit, Maven, Gradle, Go modules, and Rust/Cargo."
    )
