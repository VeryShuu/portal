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
        results.append(("OK", f, 0, 0, ""))
    except SyntaxError as e:
        results.append(("ERROR", f, e.lineno or 0, e.offset or 0, str(e.msg)))
    except Exception as e:
        results.append(("FAIL", f, 0, 0, type(e).__name__ + ": " + str(e)))

with open("syntax_results.txt", "w", encoding="utf-8") as out:
    for status, fname, line, col, msg in results:
        if status == "OK":
            out.write(f"OK: {fname}\n")
        else:
            out.write(f"{status}: {fname} line={line} col={col} msg={msg}\n")
