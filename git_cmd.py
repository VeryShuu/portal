import subprocess, sys

repo = r'C:\Users\admin\Documents\zen\portal'

files = [
    'frontend/src/pages/HomePage.vue',
]

r1 = subprocess.run(['git', '-C', repo, 'add'] + files, capture_output=True)
sys.stdout.buffer.write(r1.stdout)
sys.stdout.buffer.write(r1.stderr)

msg = "feat(home): move latest-news header full-width above grid so sidebar aligns with news cards"

r2 = subprocess.run(['git', '-C', repo, 'commit', '-m', msg], capture_output=True)
sys.stdout.buffer.write(r2.stdout)
sys.stdout.buffer.write(r2.stderr)

r3 = subprocess.run(['git', '-C', repo, 'push'], capture_output=True)
sys.stdout.buffer.write(r3.stdout)
sys.stdout.buffer.write(r3.stderr)
