import ast
import sys

files = [
    "app/api/photos.py",
    "app/models/photos.py",
    "app/schemas/photos.py",
    "app/worker/tasks/photos.py",
    "app/worker/main.py",
]

results = []
for f in files:
    try:
        src = open(f, encoding="utf-8").read()
        compile(src, f, "exec")
        results.append(f"OK: {f}")
    except SyntaxError as e:
        results.append(f"ERROR: {f} line={e.lineno} col={e.offset} msg={e.msg}")
    except Exception as e:
        results.append(f"FAIL: {f} {type(e).__name__}: {e}")

output = "\n".join(results)
print(output)
with open("syntax_results.txt", "w", encoding="utf-8") as out:
    out.write(output + "\n")
