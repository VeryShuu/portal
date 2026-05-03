import subprocess, sys

repo = r'C:\Users\admin\Documents\zen\portal'

files = ['frontend/src/pages/admin/tabs/KeycloakTab.vue']

r1 = subprocess.run(['git', '-C', repo, 'add'] + files, capture_output=True)
sys.stdout.buffer.write(r1.stdout)
sys.stdout.buffer.write(r1.stderr)

msg = "fix(keycloak): poll sync status after triggering manual sync\n\nPreviously syncUsers() called loadKcSyncStatus() immediately after\nenqueuing the job, but the worker runs asynchronously so the status\nwasn't updated yet — user had to refresh the page manually.\n\nNow polls GET /admin/keycloak/sync/status every 2s until last_run_at\nchanges from the value before the sync was triggered, or 60s timeout."
r2 = subprocess.run(['git', '-C', repo, 'commit', '-m', msg], capture_output=True)
sys.stdout.buffer.write(r2.stdout)
sys.stdout.buffer.write(r2.stderr)

r3 = subprocess.run(['git', '-C', repo, 'push'], capture_output=True)
sys.stdout.buffer.write(r3.stdout)
sys.stdout.buffer.write(r3.stderr)
