# Changelog

## 0.5 — Multi-runtime integration bundle

- Ships the connected `proof.py`, `runtimes.py`, both Actions workflows, and all
  runtime helpers together to prevent an adapter-only deployment.
- Adds Java/JUnit, Maven, Gradle, Go modules, and Rust/Cargo adapters.
- Adds explicit selection for ambiguous root manifests and nested Go test packages.
- Enables preinstalled jsdom for static-web regression tests; Playwright detection
  still requires browser-test markers, not simply an HTML file.
- Adds fresh JUnit XML classification, Go test events, Rust assertion evidence,
  explicit regression execution, nonzero test-count gates, and native test protection.
- Adds image preparation profiles and corresponding runtime-specific secret wiring.
- Adds offline integration tests covering all nine runtimes and rejection paths.
- Documents unsupported layouts, version constraints, and the limits of verification.

Migration: replace every file in this bundle, prepare a v0.5 image, update its UUID,
then run a fresh labelled issue. Do not reuse a Python-only v0.3 image. Repository
changes have not been pushed automatically, and live Nebius runs are not claimed.
