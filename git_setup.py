import subprocess
import os
import sys

GIT = r"C:\Program Files\Git\cmd\git.exe"
REPO = r"C:\Users\admin\Documents\zen\portal"
REMOTE = "https://github.com/VeryShuu/portal.git"

def run(args, **kwargs):
    result = subprocess.run(
        [GIT] + args,
        cwd=REPO,
        capture_output=True,
        text=True,
        **kwargs
    )
    if result.stdout:
        print(result.stdout.strip())
    if result.stderr:
        print(result.stderr.strip(), file=sys.stderr)
    return result.returncode

print("=== git init ===")
run(["init"])

print("=== config ===")
run(["config", "user.email", "portal@company.local"])
run(["config", "user.name", "Portal Dev"])

print("=== removing setup-git.bat ===")
bat = os.path.join(REPO, "setup-git.bat")
if os.path.exists(bat):
    os.remove(bat)

script = os.path.join(REPO, "git_setup.py")

print("=== git add ===")
run(["add", "."])

print("=== status ===")
run(["status", "--short"])

print("=== commit ===")
msg = (
    "feat: Phase 0 — infrastructure skeleton\n\n"
    "- Docker Compose: postgres (hunspell), redis, backend, worker, frontend, nginx\n"
    "- FastAPI backend: config, logging (structlog), database (SQLAlchemy 2.x async)\n"
    "- Health endpoints: GET /health + GET /ready (DB + Redis checks)\n"
    "- Prometheus metrics, Sentry SDK, security headers middleware\n"
    "- Alembic migrations: users + idempotency_keys tables\n"
    "- audit_log partitioned table + ARQ worker (cron: flush, partition mgmt)\n"
    "- PostgreSQL FTS: russian_hunspell configuration in init.sql\n"
    "- Nginx: TLS 1.2+, HSTS, CSP, geo IP-whitelist, SSE location\n"
    "- Frontend: Vue 3 + Naive UI + TipTap v2 + vue-i18n v9 skeleton\n"
    "- i18n: ru.json + en.json full keys, CI parity check script\n"
    "- GitHub Actions: ci.yml (lint+test) + build.yml (GHCR images)\n"
    "- Tests: 29 cases (unit: config, health, audit_partitions; integration: migrations)"
)
run(["commit", "-m", msg])

print("=== remote add ===")
run(["remote", "add", "origin", REMOTE])

print("=== branch rename ===")
run(["branch", "-M", "main"])

print("=== push ===")
code = run(["push", "-u", "origin", "main"])
if code != 0:
    print("\n[!] Push failed — возможно нужна аутентификация.")
    print("Запустите вручную:")
    print(f"  cd {REPO}")
    print(f"  git push -u origin main")
else:
    print("\n=== Done! ===")
