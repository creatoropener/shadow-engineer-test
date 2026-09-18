"""Small dependency-free Java project runner; executes only inside Sandbox."""
import shutil
import subprocess
import sys
from pathlib import Path


def main():
    output = Path("/tmp/patchproof-java")
    if output.exists():
        shutil.rmtree(output)
    classes = output / "classes"
    classes.mkdir(parents=True)
    jar = "/opt/patchproof/java/junit-platform-console-standalone.jar"
    sources = [str(p) for folder in ("src/main/java", "src/test/java") for p in Path(folder).rglob("*.java")]
    if not sources:
        print("No Java sources found", file=sys.stderr)
        return 2
    compile_result = subprocess.run(["javac", "-cp", jar, "-d", str(classes), *sources], check=False)
    if compile_result.returncode:
        return 2
    command = ["java", "-jar", jar, "execute", "--disable-ansi-colors", "--class-path", str(classes),
               "--reports-dir", str(output / "reports")]
    if len(sys.argv) > 1:
        command += ["--select-class", sys.argv[1], "--fail-if-no-tests"]
    else:
        command += ["--scan-class-path"]
    return subprocess.run(command, check=False).returncode


if __name__ == "__main__":
    sys.exit(main())
