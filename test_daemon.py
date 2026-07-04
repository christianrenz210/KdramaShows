import json, sys
import subprocess, time

script = r'C:\Users\LEDESMA\Downloads\KdramaShows\playwright_daemon.py'

proc = subprocess.Popen(
    [sys.executable, script],
    stdin=subprocess.PIPE,
    stdout=subprocess.PIPE,
    stderr=subprocess.PIPE,
    text=True,
    bufsize=1
)

line = proc.stdout.readline().strip()
print(f'Ready: {line}')

cmd = {
    'type': 'get_stream',
    'drama_id': 6653,
    'episode_id': 113513,
    'ep_num': 0,
    'title': 'Spider-Man: No Way Home'
}

proc.stdin.write(json.dumps(cmd) + '\n')
proc.stdin.flush()

line = proc.stdout.readline().strip()
print(f'Result: {line}')

# Get any remaining stderr
time.sleep(2)
stderr = proc.stderr.read()
if stderr:
    print(f'STDERR: {stderr[:500]}')

proc.kill()
