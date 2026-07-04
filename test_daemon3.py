import json, sys, time, threading, subprocess

script = r'C:\Users\LEDESMA\Downloads\KdramaShows\playwright_daemon.py'

proc = subprocess.Popen(
    [sys.executable, script],
    stdin=subprocess.PIPE,
    stdout=subprocess.PIPE,
    stderr=subprocess.PIPE,
    text=True,
    bufsize=1
)

lines = []
def reader():
    while True:
        line = proc.stdout.readline()
        if not line:
            break
        lines.append(line.strip())

t = threading.Thread(target=reader, daemon=True)
t.start()

print('Waiting for ready...', flush=True)
t0 = time.time()
while time.time() - t0 < 60:
    if any('ready' in l for l in lines):
        print(f'Ready in {time.time()-t0:.1f}s', flush=True)
        break
    time.sleep(0.5)
else:
    print('Timeout waiting for ready', flush=True)
    try:
        stderr = proc.stderr.read()
        if stderr:
            print(f'STDERR: {stderr[:1000]}', flush=True)
    except Exception as e:
        print(f'Error reading stderr: {e}', flush=True)
    proc.kill()
    exit(1)

lines.clear()
cmd = {'type': 'get_stream', 'drama_id': 6653, 'episode_id': 113513, 'ep_num': 0, 'title': 'Spider-Man: No Way Home'}
proc.stdin.write(json.dumps(cmd) + '\n')
proc.stdin.flush()
print('Command sent, waiting for result...', flush=True)

t0 = time.time()
found = False
while time.time() - t0 < 90:
    for l in lines:
        if '"type":"result"' in l.replace(' ', '') or '"type":"error"' in l.replace(' ', ''):
            print(f'Result: {l}', flush=True)
            found = True
            break
    if found:
        break
    time.sleep(0.5)
else:
    print('No result within 90s', flush=True)
    for l in lines[-10:]:
        print(f'  Line: {l}', flush=True)

time.sleep(1)
try:
    proc.stderr.flush()
    stderr = proc.stderr.read()
    if stderr:
        print(f'STDERR ({len(stderr)} bytes):', flush=True)
        for line in stderr.split('\n')[-20:]:
            print(f'  {line}', flush=True)
except Exception as e:
    print(f'Error reading stderr: {e}', flush=True)
proc.kill()
