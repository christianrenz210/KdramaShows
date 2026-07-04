import json, sys, re, time, traceback
from urllib.parse import urlparse, parse_qs
from playwright.sync_api import sync_playwright

KISSKH_BASE = 'https://kisskh.nl'

def sanitize_slug(title):
    slug = re.sub(r'[^a-zA-Z0-9\s-]', '', title).strip()
    slug = re.sub(r'\s+', '-', slug)
    return slug

def main():
    browser = None
    context = None
    page = None

    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch(
                headless=True,
                args=['--no-sandbox', '--disable-setuid-sandbox', '--disable-dev-shm-usage',
                      '--disable-accelerated-2d-canvas', '--disable-gpu', '--window-size=1280,720']
            )
            context = browser.new_context(
                viewport={'width': 1280, 'height': 720},
                user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            )
            page = context.new_page()

            try:
                page.goto(KISSKH_BASE, wait_until='domcontentloaded', timeout=30000)
            except Exception:
                pass

            sys.stdout.write(json.dumps({'type': 'ready'}) + '\n')
            sys.stdout.flush()

            for line in sys.stdin:
                line = line.strip()
                if not line:
                    continue
                try:
                    cmd = json.loads(line)
                except json.JSONDecodeError as e:
                    sys.stdout.write(json.dumps({'type': 'error', 'error': f'Invalid JSON: {e}'}) + '\n')
                    sys.stdout.flush()
                    continue

                if cmd.get('type') == 'shutdown':
                    break
                elif cmd.get('type') == 'get_stream':
                    drama_id = cmd.get('drama_id')
                    episode_id = cmd.get('episode_id')
                    ep_num = cmd.get('ep_num')
                    title = cmd.get('title', '')
                    try:
                        slug = sanitize_slug(title)
                        alt_slug = re.sub(r'\s*\(.*?\)\s*', '', slug).strip()
                        alt_slug = re.sub(r'\s+', '-', alt_slug)
                        slugs_to_try = list(dict.fromkeys([slug, alt_slug]))

                        found_stream = None
                        found_kkey = None
                        found_sub_kkey = None

                        def on_request(request):
                            nonlocal found_kkey, found_sub_kkey
                            if found_stream:
                                return
                            url = request.url
                            parsed = urlparse(url)
                            params = parse_qs(parsed.query)
                            if '/api/DramaList/Episode/' in url and 'kkey' in params:
                                if not found_kkey:
                                    found_kkey = params['kkey'][0]
                            if '/api/Sub/' in url and 'kkey' in params:
                                if not found_sub_kkey:
                                    found_sub_kkey = params['kkey'][0]

                        def on_response(response):
                            nonlocal found_stream
                            if found_stream:
                                return
                            url = response.url
                            if '.m3u8' in url.lower():
                                found_stream = url

                        page.on('request', on_request)
                        page.on('response', on_response)

                        nav_urls = []
                        for try_slug in slugs_to_try:
                            if ep_num is not None:
                                nav_urls.append(f'{KISSKH_BASE}/Drama/{try_slug}/Episode-{ep_num}?id={drama_id}&ep={episode_id}')
                            nav_urls.append(f'{KISSKH_BASE}/Drama/{try_slug}?id={drama_id}&ep={episode_id}')

                        for nav_url in nav_urls[:4]:
                            if found_stream:
                                break
                            sep = '&' if '?' in nav_url else '?'
                            nav_url_full = nav_url + sep + 'page=0&pageSize=100'
                            try:
                                page.goto(nav_url_full, wait_until='domcontentloaded', timeout=20000)
                                page.wait_for_timeout(1500)
                                if found_stream:
                                    break

                                ep_label = str(int(float(ep_num))) if ep_num is not None else ''
                                ep_btns = page.locator('button.mat-raised-button')
                                for i in range(ep_btns.count()):
                                    btn_text = (ep_btns.nth(i).text_content() or '').strip()
                                    if re.match(rf'^{ep_label}\s', btn_text):
                                        ep_btns.nth(i).click()
                                        break
                                page.wait_for_timeout(1500)

                                for _ in range(20):
                                    if found_stream:
                                        break
                                    if found_kkey:
                                        kkey_url = f'{KISSKH_BASE}/api/DramaList/Episode/{episode_id}.png?kkey={found_kkey}'
                                        try:
                                            r = page.request.get(kkey_url)
                                            if r.ok and len(r.text()) > 100:
                                                found_stream = kkey_url
                                                break
                                        except Exception:
                                            pass
                                    page.wait_for_timeout(500)
                            except Exception as e:
                                continue

                        page.remove_listener('request', on_request)
                        page.remove_listener('response', on_response)

                        sub_data = None
                        if found_sub_kkey:
                            try:
                                sub_resp = page.request.get(f'{KISSKH_BASE}/api/Sub/{episode_id}?kkey={found_sub_kkey}')
                                if sub_resp.ok:
                                    sub_data = sub_resp.json()
                            except Exception:
                                pass

                        if found_stream:
                            sys.stdout.write(json.dumps({
                                'type': 'result',
                                'data': {
                                    'stream_url': found_stream,
                                    'slug': slug,
                                    'sub_data': sub_data,
                                    'sub_kkey': found_sub_kkey
                                }
                            }) + '\n')
                        else:
                            sys.stdout.write(json.dumps({
                                'type': 'error',
                                'error': 'No stream URL found'
                            }) + '\n')
                    except Exception as e:
                        sys.stdout.write(json.dumps({
                            'type': 'error', 'error': str(e), 'traceback': traceback.format_exc()
                        }) + '\n')

                    sys.stdout.flush()

    except Exception as e:
        sys.stdout.write(json.dumps({'type': 'error', 'error': f'Fatal: {e}'}) + '\n')
        sys.stdout.flush()
    finally:
        if browser:
            browser.close()

if __name__ == '__main__':
    main()
