import json, sys, time
import subprocess

script = r'C:\Users\LEDESMA\Downloads\KdramaShows\playwright_daemon.py'

print('Starting daemon...', flush=True)
proc = subprocess.Popen(
    [sys.executable, script],
    stdin=subprocess.PIPE,
    stdout=subprocess.PIPE,
    stderr=subprocess.PIPE,
    text=True,
    bufsize=1
)

# Read ready signal with timeout
import select
import os

ready_line = None
start = time.time()
while time.time() - start < 60:
    if select.select([proc.stdout], [], [], 1)[0]:
        line = proc.stdout.readline().strip()
        if line:
            ready_line = line
            print(f'Got: {line}', flush=True)
            break
    else:
        print(f'Waiting for ready... ({int(time.time()-start)}s)', flush=True)

if not ready_line:
    print('No ready signal received within 60s', flush=True)
    # Check stderr
    try:
        stderr_data = proc.stderr.read()
        if stderr_data:
            print(f'STDERR: {stderr_data[:1000]}', flush=True)
    except:
        pass
    proc.kill()
    exit(1)

print('Sending command...', flush=True)
cmd = {
    'type': 'get_stream',
    'drama_id': 6653,
    'episode_id': 113513,
    'ep_num': 0,
    'title': 'Spider-Man: No Way Home'
}
proc.stdin.write(json.dumps(cmd) + '\n')
proc.stdin.flush()

print('Waiting for result...', flush=True)
result = None
start = time.time()
while time.time() - start < 90:
    if select.select([proc.stdout], [], [], 1)[0]:
        line = proc.stdout.readline().strip()
        if line:
            result = line
            print(f'Result: {line}', flush=True)
            break
    else:
        elapsed = int(time.time() - start)
        if elapsed % 10 == 0:
            print(f'Still waiting... ({elapsed}s)', flush=True)

if not result:
    print('No result received within 90s', flush=True)

# Get stderr
time.sleep(1)
try:
    stderr_data = proc.stderr.read()
    if stderr_data:
        print(f'STDERR: {stderr_data[:2000]}', flush=True)
except:
    pass

proc.kill()
