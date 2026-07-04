import json, requests, re, hashlib, time, os, logging, sys, subprocess
from urllib.parse import urlparse, urljoin, quote
from concurrent.futures import ThreadPoolExecutor, as_completed
from threading import Lock, Thread, Event
from flask import Flask, render_template, request, redirect, url_for, session, jsonify, Response
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

logging.basicConfig(level=logging.DEBUG)
logging.getLogger('urllib3.connectionpool').setLevel(logging.WARNING)
logging.getLogger('werkzeug').setLevel(logging.INFO)
logger = logging.getLogger(__name__)
from config import Config
from models import db, User, ContactMessage, VidSrcItem
from datetime import timedelta, datetime

app = Flask(__name__)
app.config.from_object(Config)
app.permanent_session_lifetime = timedelta(days=7)
db.init_app(app)

VIDSRC_BASE = 'https://vidsrcme.su'
KISSKH_BASE = 'https://kisskh.nl'

# -- Persistent Playwright Daemon --
# -- Persistent Playwright Daemon --
_daemon_proc = None
_daemon_lock = Lock()
_daemon_ready = Event()

def _start_daemon():
    global _daemon_proc
    script = os.path.join(os.path.dirname(__file__), 'playwright_daemon.py')
    try:
        _daemon_stderr = open(os.path.join(os.path.dirname(__file__), 'daemon_stderr.txt'), 'a', encoding='utf-8')
        _daemon_proc = subprocess.Popen(
            [sys.executable, script],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=_daemon_stderr,
            text=True,
            bufsize=1
        )
        # Wait for "ready" signal
        line = _daemon_proc.stdout.readline().strip()
        if line:
            msg = json.loads(line)
            if msg.get('type') == 'ready':
                logger.info('Playwright daemon ready')
                _daemon_ready.set()
                return
        logger.error('Daemon failed to send ready signal')
    except Exception as e:
        logger.error('Failed to start daemon: %s', e)
    _daemon_proc = None

def _daemon_send(cmd, timeout=120):
    """Send JSON command to daemon, read JSON response."""
    global _daemon_proc
    if not _daemon_ready.is_set() or not _daemon_proc or _daemon_proc.poll() is not None:
        logger.warning('Daemon not running, waiting...')
        _daemon_ready.clear()
        _start_daemon()
        if not _daemon_proc:
            return {'type': 'error', 'error': 'Daemon unavailable'}
    with _daemon_lock:
        try:
            _daemon_proc.stdin.write(json.dumps(cmd) + '\n')
            _daemon_proc.stdin.flush()
            result = [None]
            def _reader():
                try:
                    line = _daemon_proc.stdout.readline()
                    if line:
                        result[0] = json.loads(line.strip())
                except Exception:
                    pass
            t = Thread(target=_reader, daemon=True)
            t.start()
            t.join(timeout=timeout)
            if result[0] is None:
                logger.error('Daemon response timeout after %ss', timeout)
                try:
                    _daemon_proc.kill()
                except Exception:
                    pass
                _daemon_proc = None
                _daemon_ready.clear()
                return {'type': 'error', 'error': 'Daemon timeout'}
            return result[0]
        except Exception as e:
            logger.error('Daemon communication error: %s', e)
            _daemon_proc = None
            _daemon_ready.clear()
            return {'type': 'error', 'error': str(e)}

def _daemon_get_stream(drama_id, episode_id, ep_num, title):
    return _daemon_send({
        'type': 'get_stream',
        'drama_id': drama_id,
        'episode_id': episode_id,
        'ep_num': ep_num,
        'title': title
    })

def init_db():
    with app.app_context():
        db.create_all()

def fetch_json(url):
    try:
        resp = requests.get(url, timeout=15)
        return resp.json() if resp.status_code == 200 else None
    except:
        return None

COLORS = ['#e74c6f', '#8e44ad', '#3498db', '#2ecc71', '#f39c12', '#1abc9c', '#e67e22', '#9b59b6']

def item_color(title):
    h = int(hashlib.md5((title or '').encode()).hexdigest()[:8], 16)
    return COLORS[h % len(COLORS)]

def extract_year(text):
    m = re.search(r'\b(19\d\d|20\d\d)\b', text or '')
    return m.group(1) if m else ''

EMBED_SOURCES = [
    {'name': '2Embed', 'url_tmpl': 'https://www.2embed.cc/embed/{imdb}', 'tv_ep_fmt': 'flat'},
    {'name': 'VidSrc', 'url_tmpl': 'https://vidsrcme.su/embed/{type}', 'tv_ep_fmt': 'query'},
    {'name': 'Embed.su', 'url_tmpl': 'https://embed.su/embed/{type}/{imdb}', 'tv_ep_fmt': 'path'},
]

def build_embed_url(imdb_id, mtype, source_idx=0, season=None, episode=None):
    t = 'movie' if mtype == 'movie' else 'tv'
    tmpl = EMBED_SOURCES[source_idx]['url_tmpl']
    fmt = EMBED_SOURCES[source_idx].get('tv_ep_fmt', 'query')

    if fmt == 'flat':
        return tmpl.replace('{imdb}', imdb_id)

    base = tmpl.replace('{type}', t)
    has_imdb = '{imdb}' in base
    if has_imdb:
        base = base.replace('{imdb}', imdb_id)

    if mtype == 'movie' or fmt == 'flat':
        if not has_imdb and fmt == 'query':
            return base + '?imdb=' + imdb_id
        return base

    if season is None and episode is None:
        sep = '&' if '?' in base else '?'
        if not has_imdb:
            base += sep + 'imdb=' + imdb_id
            sep = '&'
        return base

    if fmt == 'path':
        if not has_imdb:
            return base + '/' + imdb_id + '/' + str(season or 1) + '-' + str(episode or 1)
        return base + '/' + str(season or 1) + '-' + str(episode or 1)

    sep = '&' if '?' in base else '?'
    if not has_imdb:
        base += sep + 'imdb=' + imdb_id
        sep = '&'
    return base + sep + 'season=' + str(season or 1) + '&episode=' + str(episode or 1)

def all_source_urls(imdb_id, mtype):
    urls = []
    for i, s in enumerate(EMBED_SOURCES):
        url = build_embed_url(imdb_id, mtype, i, season=1, episode=1)
        base = build_embed_url(imdb_id, mtype, i)
        ok = False
        try:
            r = requests.get(url, timeout=5, allow_redirects=True)
            content = r.text.strip()
            ok = r.status_code == 200 and len(content) > 200
        except:
            pass
        urls.append({'name': s['name'], 'url': url, 'base': base, 'imdb': imdb_id, 'idx': i, 'fmt': s.get('tv_ep_fmt', 'query'), 'mtype': mtype, 'ok': ok})
    return urls

def search_tvmaze(query):
    data = fetch_json(f'https://api.tvmaze.com/search/shows?q={requests.utils.quote(query)}')
    if not data:
        return []
    results = []
    for entry in data:
        show = entry.get('show', {})
        externals = show.get('externals', {}) or {}
        imdb_id = externals.get('imdb', '') or ''
        if not imdb_id:
            continue
        image = show.get('image') or {}
        results.append({
            'imdb_id': imdb_id,
            'tmdb_id': '',
            'title': show.get('name', ''),
            'year': (show.get('premiered') or '')[:4],
            'poster': image.get('medium') or image.get('original') or '',
            'rating': show.get('rating', {}).get('average') or '',
            'genres': show.get('genres', []),
            'summary': (show.get('summary') or '').replace('<p>', '').replace('</p>', '').replace('<b>', '').replace('</b>', '').replace('<i>', '').replace('</i>', '')[:300],
            'language': show.get('language', ''),
            'status': show.get('status', ''),
            'color': item_color(show.get('name', '')),
        })
    return results

def search_kisskh(query):
    data = fetch_json(f'{KISSKH_BASE}/api/DramaList/Search?q={requests.utils.quote(query)}')
    if not data:
        return []
    results = []
    for entry in data if isinstance(data, list) else []:
        results.append({
            'kisskh_id': entry.get('id', ''),
            'title': entry.get('title', ''),
            'poster': entry.get('thumbnail', ''),
            'episodes_count': entry.get('episodesCount', 0),
            'label': entry.get('label', ''),
            'color': item_color(entry.get('title', '')),
        })
    return results

def get_kisskh_drama(kisskh_id):
    data = fetch_json(f'{KISSKH_BASE}/api/DramaList/Drama/{kisskh_id}?isq=false')
    if not data:
        return None
    episodes = data.get('episodes', [])
    return {
        'title': data.get('title', ''),
        'description': data.get('description', ''),
        'thumbnail': data.get('thumbnail', ''),
        'release_date': data.get('releaseDate', ''),
        'country': data.get('country', ''),
        'status': data.get('status', ''),
        'type': data.get('type', ''),  # 'Drama', 'Movie', etc.
        'episodes_count': data.get('episodesCount', 0),
        'episodes': [{'id': e['id'], 'number': e['number'], 'sub': e.get('sub', 0)} for e in episodes],
    }

# --- Background Catalog Builder ---

catalog_progress = {'pages_crawled': 0, 'total_pages': 0, 'done': False}

def build_catalog():
    global catalog_progress
    with app.app_context():
        for mtype, endpoint_key in [('movie', 'movies'), ('tv', 'tvshows')]:
            first = fetch_json(f'{VIDSRC_BASE}/{endpoint_key}/latest/page-1.json')
            if not first:
                continue
            total = first.get('pages', 0)
            catalog_progress['total_pages'] += total
            for page in range(1, min(total + 1, 101)):
                data = first if page == 1 else fetch_json(f'{VIDSRC_BASE}/{endpoint_key}/latest/page-{page}.json')
                if not data:
                    continue
                for item in data.get('result', []):
                    imdb = item.get('imdb_id', '')
                    if imdb and not VidSrcItem.query.filter_by(imdb_id=imdb).first():
                        entry = VidSrcItem(
                            imdb_id=imdb,
                            tmdb_id=item.get('tmdb_id', '') or 0,
                            title=item.get('title', ''),
                            media_type=mtype,
                            quality=item.get('quality', ''),
                            year=extract_year(item.get('title', '')),
                            color=item_color(item.get('title', '')),
                        )
                        db.session.add(entry)
                db.session.commit()
                catalog_progress['pages_crawled'] += 1
                time.sleep(0.3)
        catalog_progress['done'] = True

def start_catalog_builder():
    from threading import Thread
    t = Thread(target=build_catalog, daemon=True)
    t.start()

def _start_background_services():
    """Start daemon threads on boot."""
    # Start catalog builder in background
    t = Thread(target=build_catalog, daemon=True)
    t.start()
    # Start Playwright daemon synchronously (wait for ready)
    # This takes ~15-30s on first boot but ensures fast stream requests
    _start_daemon()

# --- AUTH ---

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        email = request.form.get('email', '').strip()
        password = request.form.get('password', '')
        confirm = request.form.get('confirm_password', '')
        if not username or not email or not password:
            return render_template('register.html', error='All fields are required.')
        if password != confirm:
            return render_template('register.html', error='Passwords do not match.')
        if User.query.filter((User.username == username) | (User.email == email)).first():
            return render_template('register.html', error='Username or email already taken.')
        user = User(username=username, email=email)
        user.set_password(password)
        db.session.add(user)
        db.session.commit()
        session['user_id'] = user.id
        session['username'] = user.username
        return redirect(url_for('index'))
    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form.get('email', '').strip()
        password = request.form.get('password', '')
        user = User.query.filter_by(email=email).first()
        if not user or not user.check_password(password):
            return render_template('login.html', error='Invalid email or password.')
        session['user_id'] = user.id
        session['username'] = user.username
        return redirect(url_for('index'))
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('index'))

# --- PAGES ---

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/browse')
def browse():
    media_type = request.args.get('type', 'movie')
    page = request.args.get('page', 1, type=int)
    query = request.args.get('q', '').strip()
    return render_template('browse.html', media_type=media_type, page=page, query=query)

@app.route('/detail/<media_type>/<imdb_id>')
def detail(media_type, imdb_id):
    item = VidSrcItem.query.filter_by(imdb_id=imdb_id).first()
    sources = all_source_urls(imdb_id, media_type)
    return render_template('detail.html', media_type=media_type, imdb_id=imdb_id, item=item, sources=sources)

@app.route('/how-it-works')
def how_it_works():
    return render_template('how-it-works.html')

@app.route('/faq')
def faq():
    return render_template('faq.html')

@app.route('/about')
def about():
    return render_template('about.html')

@app.route('/contact', methods=['GET', 'POST'])
def contact():
    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        email = request.form.get('email', '').strip()
        subject = request.form.get('subject', '').strip()
        message = request.form.get('message', '').strip()
        if not all([name, email, subject, message]):
            return render_template('contact.html', error='All fields are required.')
        msg = ContactMessage(name=name, email=email, subject=subject, message=message)
        db.session.add(msg)
        db.session.commit()
        return render_template('contact.html', success='Message sent successfully!')
    return render_template('contact.html')

# --- API ---

@app.route('/api/latest/<media_type>')
def api_latest(media_type):
    queries = ['a', 'e', 'ko', '2025', '2026', 'love', 'man', 'king', 'day', 'night']
    seen = set()
    all_results = []
    for q in queries:
        data = fetch_json(f'{KISSKH_BASE}/api/DramaList/Search?q={requests.utils.quote(q)}')
        if not data:
            continue
        for entry in data if isinstance(data, list) else []:
            kid = entry.get('id')
            if not kid or kid in seen:
                continue
            seen.add(kid)
            all_results.append({
                'kisskh_id': kid,
                'title': entry.get('title', ''),
                'poster': entry.get('thumbnail', ''),
                'episodes_count': entry.get('episodesCount', 0),
                'label': entry.get('label', ''),
                'color': item_color(entry.get('title', '')),
            })
            if len(all_results) >= 60:
                break
        if len(all_results) >= 60:
            break
    # Split: <=1 ep → movie, >1 ep → tv
    if media_type == 'movie':
        results = [r for r in all_results if r['episodes_count'] <= 1][:30]
    else:
        results = [r for r in all_results if r['episodes_count'] > 1][:30]
    if not results:
        results = all_results[:30]
    return jsonify({'result': results})

@app.route('/api/search')
def api_search():
    query = request.args.get('q', '').strip().lower()
    media_type = request.args.get('type', 'movie')

    if not query:
        return jsonify({'result': []})

    # For TV shows, use TVmaze
    if media_type == 'tv':
        tvmaze_results = search_tvmaze(query)
        if tvmaze_results:
            return jsonify({'result': tvmaze_results})

    # Check local cache
    local = VidSrcItem.query.filter(
        VidSrcItem.media_type == media_type,
        VidSrcItem.title.ilike(f'%{query}%')
    ).limit(50).all()

    if local:
        results = [{
            'imdb_id': item.imdb_id,
            'tmdb_id': item.tmdb_id,
            'title': item.title,
            'year': item.year,
            'quality': item.quality,
            'color': item.color,
            'genres': [],
            'rating': '',
        } for item in local]
        return jsonify({'result': results})

    # Fallback: crawl VidSrc API live
    seen = set()
    results = []
    MAX_PAGES = 15 if media_type == 'movie' else 10

    def fetch_page(p):
        ep = '/movies/latest/page-' if media_type == 'movie' else '/tvshows/latest/page-'
        return fetch_json(f'{VIDSRC_BASE}{ep}{p}.json')

    executor = ThreadPoolExecutor(max_workers=5)
    futures = {executor.submit(fetch_page, p): p for p in range(1, MAX_PAGES + 1)}
    for future in as_completed(futures):
        data = future.result()
        if not data:
            continue
        for item in data.get('result', []):
            imdb = item.get('imdb_id', '')
            if imdb in seen:
                continue
            if query in item.get('title', '').lower():
                seen.add(imdb)
                results.append({
                    'imdb_id': imdb,
                    'tmdb_id': item.get('tmdb_id', ''),
                    'title': item.get('title', ''),
                    'year': extract_year(item.get('title', '')),
                    'quality': item.get('quality', ''),
                    'color': item_color(item.get('title', '')),
                })
        if len(results) >= 30:
            break
    executor.shutdown(wait=False, cancel_futures=True)

    results.sort(key=lambda x: x.get('title', ''))
    return jsonify({'result': results[:30]})

@app.route('/api/tvmaze/<imdb_id>')
def api_tvmaze_lookup(imdb_id):
    data = fetch_json(f'https://api.tvmaze.com/lookup/shows?imdb={imdb_id}')
    if not data:
        return jsonify({'error': 'Not found'}), 404
    image = data.get('image') or {}
    return jsonify({
        'title': data.get('name', ''),
        'year': (data.get('premiered') or '')[:4],
        'poster': image.get('medium') or image.get('original') or '',
        'rating': data.get('rating', {}).get('average') or '',
        'genres': data.get('genres', []),
        'summary': (data.get('summary') or '').replace('<p>', '').replace('</p>', '').replace('<b>', '').replace('</b>', '').replace('<i>', '').replace('</i>', '')[:500],
        'status': data.get('status', ''),
        'network': (data.get('network') or {}).get('name') or (data.get('webChannel') or {}).get('name') or '',
        'language': data.get('language', ''),
    })

@app.route('/proxy/embed/<path:url>')
def proxy_embed(url):
    target = f'https://{url}'
    try:
        resp = requests.get(target, timeout=15, stream=True, headers={
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Accept': '*/*',
        })
        excluded_headers = ['content-encoding', 'content-length', 'transfer-encoding', 'connection']
        headers = {k: v for k, v in resp.headers.items() if k.lower() not in excluded_headers}
        return resp.content, resp.status_code, headers
    except Exception as e:
        return jsonify({'error': str(e)}), 502

@app.route('/api/catalog-status')
def catalog_status():
    return jsonify(catalog_progress)

@app.route('/api/kisskh/search')
def api_kisskh_search():
    query = request.args.get('q', '').strip()
    if not query:
        return jsonify({'result': []})
    results = search_kisskh(query)
    return jsonify({'result': results})

@app.route('/api/kisskh/drama/<int:kisskh_id>')
def api_kisskh_drama(kisskh_id):
    data = get_kisskh_drama(kisskh_id)
    if not data:
        return jsonify({'error': 'Not found'}), 404
    return jsonify(data)

# Stream URL cache (key: episode_id, value: stream_url)
_stream_url_cache = {}

def _get_cached_stream_url(episode_id):
    return _stream_url_cache.get(episode_id)

# Subtitle data cache (key: episode_id, value: sub_data list)
_sub_cache = {}

def _get_cached_sub_data(episode_id):
    return _sub_cache.get(episode_id)

_kisskh_stream_cache = {}

def _kisskh_headers(referer='https://kisskh.nl/'):
    return {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
        'Referer': referer,
        'Origin': 'https://kisskh.nl',
    }

def _save_kkey_to_env(stream_key, sub_key):
    if not stream_key or not sub_key:
        return
    dotenv_path = os.path.join(os.path.dirname(__file__), '.env')
    try:
        lines = []
        if os.path.exists(dotenv_path):
            with open(dotenv_path, 'r', encoding='utf-8') as f:
                lines = f.readlines()
        with open(dotenv_path, 'w', encoding='utf-8') as f:
            for line in lines:
                if line.strip().startswith('KISSKH_STREAM_KEY=') or line.strip().startswith('KISSKH_SUB_KEY='):
                    continue
                f.write(line)
            f.write(f'KISSKH_STREAM_KEY={stream_key}\n')
            f.write(f'KISSKH_SUB_KEY={sub_key}\n')
    except Exception:
        pass

@app.route('/proxy/kisskh/video/<int:episode_id>/<path:subpath>')
def proxy_kisskh_video(episode_id, subpath):
    info = _kisskh_stream_cache.get(episode_id)
    if not info:
        return jsonify({'error': 'Stream not found'}), 404

    stream_url = info['url']
    m3u8_base = stream_url[:stream_url.rfind('/') + 1]

    if subpath == 'playlist.m3u8':
        target = stream_url
    elif subpath.endswith('.m3u8'):
        target = urljoin(m3u8_base, subpath)
    else:
        return jsonify({'error': 'Invalid subpath'}), 400

    logger.info('Proxying m3u8: %s', target)
    try:
        resp = requests.get(target, headers=info['headers'], timeout=30, verify=False)
        resp.raise_for_status()
        content = resp.text
    except Exception as e:
        logger.error('Failed to fetch m3u8 %s: %s', target[:80], e)
        return jsonify({'error': f'Failed to fetch m3u8: {e}'}), 502

    new_lines = []
    for line in content.split('\n'):
        stripped = line.strip()
        if stripped and not stripped.startswith('#'):
            if stripped.startswith('http://') or stripped.startswith('https://'):
                abs_url = stripped
            elif stripped.startswith('//'):
                abs_url = 'https:' + stripped
            else:
                abs_url = urljoin(m3u8_base, stripped)
                if abs_url.startswith('//'):
                    abs_url = 'https:' + abs_url
            new_lines.append('/proxy/raw?url=' + quote(abs_url, safe=''))
        else:
            new_lines.append(line)

    fr = Response('\n'.join(new_lines), mimetype='application/vnd.apple.mpegurl')
    fr.headers['Access-Control-Allow-Origin'] = '*'
    fr.headers['Access-Control-Allow-Methods'] = 'GET, OPTIONS'
    fr.headers['Access-Control-Allow-Headers'] = '*'
    return fr

@app.route('/proxy/raw')
def proxy_raw():
    url = request.args.get('url', '')
    if not url:
        return jsonify({'error': 'Missing url'}), 400
    if url.startswith('//'):
        url = 'https:' + url
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
        'Referer': 'https://kisskh.nl/',
        'Origin': 'https://kisskh.nl',
    }
    try:
        upstream = requests.get(url, headers=headers, timeout=30, verify=False, stream=True)
        upstream.raise_for_status()
        ct = upstream.headers.get('Content-Type', 'application/octet-stream')
        def generate():
            for chunk in upstream.iter_content(chunk_size=65536):
                if chunk:
                    yield chunk
        fr = Response(generate(), mimetype=ct)
        fr.headers['Access-Control-Allow-Origin'] = '*'
        fr.headers['Access-Control-Allow-Methods'] = 'GET, OPTIONS'
        fr.headers['Access-Control-Allow-Headers'] = '*'
        return fr
    except Exception as e:
        logger.error('Proxy failed %s: %s', url[:60], e)
        return Response('', status=502)

def _safe_int(val):
    try:
        return int(float(val))
    except (ValueError, TypeError):
        return None

@app.route('/api/kisskh/stream/<int:episode_id>')
def api_kisskh_stream(episode_id):
    drama_id = _safe_int(request.args.get('drama_id'))
    ep_num = _safe_int(request.args.get('ep_num'))
    title = request.args.get('title', '')

    if drama_id is None or ep_num is None:
        logger.warning('Stream request missing drama_id or ep_num for ep %d', episode_id)
        return jsonify({'error': 'Missing drama_id or ep_num parameter'}), 400

    url = None

    # Check cache first
    url = _get_cached_stream_url(episode_id)
    if url:
        logger.info('Cache hit for ep %d', episode_id)
    else:
        # Use persistent Playwright daemon to get stream URL directly
        logger.info('Getting stream for drama=%s ep=%s via daemon...', drama_id, episode_id)
        try:
            resp = _daemon_get_stream(drama_id, episode_id, ep_num, title)
            if resp.get('type') == 'result':
                data = resp.get('data', {})
                url = data.get('stream_url')
                if url:
                    _stream_url_cache[episode_id] = url
                sub_data = data.get('sub_data')
                if sub_data:
                    _sub_cache[episode_id] = sub_data
                logger.info('Daemon returned stream URL: %s', (url or '')[:80])
            else:
                error = resp.get('error', 'Unknown daemon error')
                logger.error('Daemon error for ep %d: %s', episode_id, error)
                # Check if episode is beyond available episodes
                drama_data = get_kisskh_drama(drama_id) if drama_id else None
                if drama_data and drama_data.get('episodes'):
                    max_ep = max(e['number'] for e in drama_data['episodes'])
                    if ep_num > max_ep:
                        return jsonify({'error': 'not_released', 'ep_num': ep_num, 'max_ep': max_ep}), 404
                return jsonify({'error': error}), 500
        except Exception as e:
            logger.error('Daemon get_stream failed for ep %d: %s', episode_id, e)
            return jsonify({'error': f'Stream extraction failed: {e}'}), 500

    if not url:
        return jsonify({'error': 'No stream URL returned from server'}), 404

    # Store stream info for proxy
    _kisskh_stream_cache[episode_id] = {
        'url': url,
        'headers': _kisskh_headers(),
    }

    is_mp4 = '.mp4' in url.lower()
    is_kkey = 'kkey=' in url
    if is_mp4:
        return jsonify({'url': url, 'direct': url, 'proxy': url, 'type': 'direct'})
    if is_kkey:
        logger.info('kkey stream, serving via proxy playlist for ep %d', episode_id)
    proxy_url = url_for('proxy_kisskh_video', episode_id=episode_id, subpath='playlist.m3u8', _external=False)
    return jsonify({'url': proxy_url, 'direct': url, 'proxy': proxy_url, 'type': 'hls'})


def _convert_to_webvtt(sub_data):
    lines = ['WEBVTT', '']
    cues = []
    if isinstance(sub_data, list):
        cues = sub_data
    elif isinstance(sub_data, dict):
        # Try common keys
        for key in ('subtitles', 'cues', 'data', 'items', 'captions'):
            if key in sub_data and isinstance(sub_data[key], list):
                cues = sub_data[key]
                break
    for cue in cues:
        start = cue.get('start', cue.get('from', cue.get('begin', 0)))
        end = cue.get('end', cue.get('to', cue.get('until', 0)))
        text = cue.get('text', cue.get('content', cue.get('caption', '')))
        if not text:
            continue
        def fmt_ts(secs):
            h = int(secs // 3600)
            m = int((secs % 3600) // 60)
            s = secs % 60
            return f'{h:02d}:{m:02d}:{s:06.3f}'.replace('.', ',')
        lines.append(f'{fmt_ts(start)} --> {fmt_ts(end)}')
        lines.append(text)
        lines.append('')
    return '\n'.join(lines)


@app.route('/api/kisskh/sub/<int:episode_id>')
def api_kisskh_sub(episode_id):
    language = request.args.get('language', 'en')
    data = _get_cached_sub_data(episode_id)
    if data is None:
        return jsonify({'subtitles': False, 'error': 'No subtitles available'}), 404
    webvtt = _convert_to_webvtt(data)
    fr = Response(webvtt, mimetype='text/vtt')
    fr.headers['Access-Control-Allow-Origin'] = '*'
    fr.headers['Access-Control-Allow-Methods'] = 'GET, OPTIONS'
    fr.headers['Access-Control-Allow-Headers'] = '*'
    fr.headers['Content-Type'] = 'text/vtt; charset=utf-8'
    return fr

@app.route('/detail/kisskh/<int:kisskh_id>')
def detail_kisskh(kisskh_id):
    drama = get_kisskh_drama(kisskh_id)
    if not drama:
        return render_template('detail.html', media_type='movie', imdb_id='', item=None, sources=[], kisskh_error='Drama not found')
    raw_type = drama.get('type', '').lower()
    mtype = 'tv' if raw_type in ('drama', 'tvseries', 'tv') else 'movie'
    title = drama.get('title', '')
    slug = re.sub(r'[^a-zA-Z0-9\s-]', '', title).strip()
    slug = re.sub(r'\s+', '-', slug)
    return render_template('detail.html', media_type=mtype, imdb_id='',
                           item=None, sources=[], kisskh_drama=drama,
                           kisskh_id=kisskh_id, kisskh_slug=slug)

# --- EMBED ROUTES (no header/footer) ---

@app.route('/embed/<media_type>/<imdb_id>')
def embed(media_type, imdb_id):
    item = VidSrcItem.query.filter_by(imdb_id=imdb_id).first()
    sources = all_source_urls(imdb_id, media_type)
    return render_template('embed.html', media_type=media_type, imdb_id=imdb_id, item=item, sources=sources, embed=True)

@app.route('/embed/kisskh/<int:kisskh_id>')
def embed_kisskh(kisskh_id):
    drama = get_kisskh_drama(kisskh_id)
    if not drama:
        return render_template('embed.html', media_type='movie', imdb_id='', item=None, sources=[], kisskh_error='Drama not found', embed=True)
    raw_type = drama.get('type', '').lower()
    mtype = 'tv' if raw_type in ('drama', 'tvseries', 'tv') else 'movie'
    return render_template('embed.html', media_type=mtype, imdb_id='',
                           item=None, sources=[], kisskh_drama=drama,
                           kisskh_id=kisskh_id, embed=True)

if __name__ == '__main__':
    init_db()
    _start_background_services()
    app.run(debug=True, port=5001, threaded=True)
