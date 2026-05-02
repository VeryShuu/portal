import subprocess, sys

repo = r'C:\Users\admin\Documents\zen\portal'

r1 = subprocess.run(['git', '-C', repo, 'add', '-A'], capture_output=True)
sys.stdout.buffer.write(r1.stdout)
sys.stdout.buffer.write(r1.stderr)

msg = "fix(p1): steps 7,41,42,44 - keycloak SSRF+RFC1918, notification N+1, async thumbnails, defusedxml for WebDAV"
r2 = subprocess.run(['git', '-C', repo, 'commit', '-m', msg], capture_output=True)
sys.stdout.buffer.write(r2.stdout)
sys.stdout.buffer.write(r2.stderr)
