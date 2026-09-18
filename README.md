# Shadow Engineer — PatchProof multi-runtime MVP

This repository demonstrates **Shadow Engineer v0.5**: an issue-to-PR workflow
whose repair is accepted only after adversarial verification in isolated Nebius
Token Factory Sandboxes.

v0.4 separates three concerns that v0.3 incorrectly treated as one:

- the application language being repaired;
- the framework used to verify it;
- the prepared Sandbox image that supplies those runtimes.

## Supported runtime adapters

| Adapter | Application source | Verification runtime | Detection |
| --- | --- | --- | --- |
| `python-pytest` | Python | pytest | Python markers or application `.py` files |
| `node-package` | JavaScript/TypeScript | package tests + `node:test` | `package.json` |
| `static-web` | HTML/CSS/JavaScript | Node syntax gate + `node:test` | standalone `index.html` |
| `web-playwright` | HTML/CSS/JavaScript | Python pytest + Playwright | web source plus Playwright tests |
| `java-junit` | Java | javac + standalone JUnit | `src/main/java` without a build manifest |
| `java-maven` | Java | Maven Surefire + JUnit XML | `pom.xml` |
| `java-gradle` | Java | Gradle test + JUnit XML | `build.gradle` / `build.gradle.kts` and committed wrapper |
| `go` | Go | `go test -json -count=1` | `go.mod` |
| `rust` | Rust | Cargo integration tests | root-package `Cargo.toml` |

QRcrafts is detected as `static-web` on its original one-file revision or
`web-playwright` when its browser verification suite is present. Its `index.html`
is now a valid repair target even though the orchestrator is written in Python.

New ecosystems can be added as adapters in `runtimes.py` without rewriting the
verification pipeline.

The static-web verifier can use preinstalled **jsdom 24.1.3** to load the actual
HTML and exercise DOM behavior. It is no longer forced to use hand-written DOM
stubs. jsdom is not a browser; layout, Canvas rendering, and visual checks still
need the Playwright path. A syntax gate alone never counts as regression proof.

### Explicit selection and scope

If multiple root build manifests exist, create `patchproof.json` with an explicit
selection, for example:

```json
{"runtime": "go", "test_directory": "internal/wifi"}
```

`test_directory` selects the Go package receiving the regression. It must already
contain Go source. Other adapters use conventional test locations. A root Go
package needs no configuration. Maven plus Node, for example, needs an explicit
`runtime`; selecting Maven does not also verify the Node application.

Current boundaries:

- One build root per run, not cross-language or multi-module orchestration.
- Maven/Gradle require an existing working JUnit setup and standard test/report
  directories. Gradle requires the wrapper script, JAR, and properties. Its pinned
  distribution is downloaded during dependency preparation, not supplied by a
  guessed system Gradle version. No Android, Kotlin-source repair, custom test tasks,
  package-private Java API testing, or multi-module JVM support is claimed.
- Plain Java supports `src/main/java` and `src/test/java`, no external dependencies
  other than the supplied JUnit runner. Custom Java layouts need a build adapter.
- Rust supports a root Cargo package with normal integration-test discovery; virtual
  workspaces and custom harnesses are rejected/unsupported. Inline Rust test suffixes
  are conservatively protected from edits. Existing lockfiles are honored; otherwise
  dependency preparation generates one independently in each Sandbox. For reproducible
  dependency versions across replay, commit the lockfile before running PatchProof.
- Node uses the project's npm test script plus a separate `node:test` regression.
  TypeScript application edits are allowed, but directly importing uncompiled TS/TSX
  requires a project-provided loader or compiled JS entry. This release does not
  automatically install a universal TypeScript/React test environment.
- Toolchain versions come from the prepared Debian image, not arbitrary project
  version files. A project requiring another JDK, Go, Rust, or Node version needs
  a compatible runtime-specific image. Use preparation logs to check actual versions.

## Verification contract

1. Detect the repository runtime without executing repository code.
2. Generate a runtime-appropriate regression test before requesting repairs.
3. Confirm the unfixed revision produces a normal test failure.
4. Give three solvers the issue and application context, but never the verifier test.
5. Apply small exact-match edits to existing application files; tests, workflows,
   manifests, and PatchProof infrastructure remain protected.
6. Evaluate all three candidates from the same immutable ConTree snapshot.
7. Verify the regression-test SHA-256 before and after every candidate run.
8. Select the smallest passing repair and replay it from the clean base image.
9. Only after replay succeeds, write the repair, regression test, `proof.json`, and
   `verification-report.md` to the Pull Request branch.

Candidate-generated code never executes on the GitHub runner. Human merge approval
remains required.

Compilation, missing dependencies, missing/empty test reports, skipped JVM tests,
and zero passing regressions cannot earn a verified verdict. JVM failures are
classified from fresh XML; Go uses named test events; Rust requires assertion
failure evidence, not merely Cargo's nonzero exit status. Candidate/replay counts
refer to the explicit regression; the baseline suite is a separate required gate.

These are verification safeguards, not a formal proof or tamper-proof security
boundary against arbitrary malicious code running in the same Sandbox. The verifier
is a separate model call that does not see candidate fixes; this is process separation,
not necessarily a different model. Candidates are evaluated sequentially on independent
branches, not raced concurrently. Human review remains necessary.

## Repository configuration

Create these Actions secrets:

- `NEBIUS_PROJECT_ID` — project with Sandbox access.
- `NEBIUS_API_KEY` — inference and Sandbox IAM authentication.
- `CONTREE_IMAGE` — UUID produced by **Prepare Sandbox Image**.

Create an Actions variable named `NEBIUS_MODEL` containing the selected NVIDIA open
model identifier. A secret with the same name is also accepted.

For larger deployments, `CONTREE_IMAGE` can be overridden per adapter with:

- `CONTREE_IMAGE_PYTHON_PYTEST`
- `CONTREE_IMAGE_NODE_PACKAGE`
- `CONTREE_IMAGE_STATIC_WEB`
- `CONTREE_IMAGE_WEB_PLAYWRIGHT`
- `CONTREE_IMAGE_JAVA_JUNIT`
- `CONTREE_IMAGE_JAVA_MAVEN`
- `CONTREE_IMAGE_JAVA_GRADLE`
- `CONTREE_IMAGE_GO`
- `CONTREE_IMAGE_RUST`

Run **Prepare Sandbox Image** with profile **all** and replace `CONTREE_IMAGE`
with the returned UUID. This is required even if you previously prepared a v0.4
image: v0.5 adds jsdom, JDK/JUnit/Maven, Go, Rust/Cargo, and native build tools.
Alternatively prepare profiles `python`, `web`, `jvm`, `go`, or `rust` separately;
the workflow summary names the corresponding image secrets. A nonempty per-runtime
secret takes precedence over `CONTREE_IMAGE`: update or remove stale overrides.
Profiles still include Python because the verification helpers use it.

## Deploying into QRcrafts

Until the central GitHub App milestone, the workflow remains repository-embedded.
Copy these paths into the QRcrafts default branch:

```text
.github/workflows/shadow-fix.yml
.github/workflows/prepare-image.yml
proof.py
runtimes.py
patchproof_runtime/static_web_check.mjs
patchproof_runtime/junit_check.py
patchproof_runtime/java_check.py
requirements-patchproof.txt
```

For the strongest QRcrafts demo, also bring the browser characterization harness
from the `patchproof/qr-wifi-tests` commit into the unfixed base branch. Do **not**
bring either repair commit. PatchProof will then select `web-playwright`, preserve
the nine existing browser checks, and create its own separately protected regression.
Without that harness, the original one-file repository uses the lighter
`static-web` adapter.

Create an issue such as:

```text
WiFi QR codes do not escape reserved characters

SSID and password values containing semicolons, commas, colons, quotes, or
backslashes produce an invalid WiFi QR payload. Escape reserved characters with a
backslash while preserving ordinary credentials and spaces.
```

Add `shadow-fix` and watch **Actions → Shadow Fix**. The report records the adapter,
application languages, test runtime, candidate branches, protected-test hashes, and
clean replay result.

## Local checks

Pure adapter, policy, JSON, and report tests need no Nebius credentials:

```bash
python -m unittest -v test_proof.py test_runtimes.py test_integration.py
python -m py_compile proof.py runtimes.py
node --check patchproof_runtime/static_web_check.mjs
```

Running `python proof.py` requires the configured environment values plus a GitHub
issue event payload, or the manual arguments shown by `python proof.py --help`.

The local suite includes nine adapters × four mocked orchestration scenarios
(success, compiler failure, zero tests, changed test hash). It does **not** execute
Nebius or prove the new images/native toolchains build successfully. Run the image
workflow and an actual labelled issue in each ecosystem before claiming live support.

## Runner references

- [Maven Surefire single-test selection](https://maven.apache.org/surefire/maven-surefire-plugin/examples/single-test.html)
- [Gradle JVM test filtering](https://docs.gradle.org/current/userguide/java_testing.html)
- [Go command documentation](https://pkg.go.dev/cmd/go)
- [Cargo test command](https://doc.rust-lang.org/cargo/commands/cargo-test.html)
- [jsdom usage and browser limitations](https://github.com/jsdom/jsdom)
