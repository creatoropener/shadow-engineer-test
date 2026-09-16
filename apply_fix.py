import re

with open("calculator.py") as f:
    content = f.read()

pattern = re.compile(r"^(\s*)return 0.*$", re.MULTILINE)
match = pattern.search(content)

if not match:
    print("Current calculator.py content:")
    print(content)
    raise SystemExit("Could not find a 'return 0' line to fix.")

indent = match.group(1)
fixed = pattern.sub(f'{indent}raise ValueError("Cannot divide by zero")', content, count=1)

with open("calculator.py", "w") as f:
    f.write(fixed)

print("✅ PatchProof successfully applied dynamic regex fix to calculator.py")
