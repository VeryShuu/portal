import ast, sys

files = [
    "backend/tests/unit/test_nextcloud.py",
    "backend/tests/unit/test_branding.py",
    "backend/tests/unit/test_modules.py",
    "backend/tests/unit/test_search.py",
    "backend/tests/unit/test_keycloak_service.py",
    "backend/tests/unit/test_photos_storage.py",
    "backend/tests/unit/test_files_acl_persistence.py",
    "backend/tests/unit/test_core_utils.py",
    "backend/tests/unit/test_worker_tasks.py",
]

all_ok = True
for f in files:
    try:
        src = open(f, encoding="utf-8").read()
        ast.parse(src)
        print(f"OK: {f}")
    except SyntaxError as e:
        print(f"SYNTAX ERROR in {f}: {e}")
        all_ok = False

sys.exit(0 if all_ok else 1)
