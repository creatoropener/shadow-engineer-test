with open("calculator.py") as f:
    content = f.read()

old_line = '    return 0 # This should raise a ValueError instead!'
new_line = '    raise ValueError("Cannot divide by zero")'

if old_line not in content:
    raise SystemExit("Could not find the buggy line - calculator.py may have changed.")

fixed = content.replace(old_line, new_line)

with open("calculator.py", "w") as f:
    f.write(fixed)

print("✅ PatchProof successfully applied fix to calculator.py")
