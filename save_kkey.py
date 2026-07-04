"""Generate KissKh kkey tokens and save them to .env file."""
import os, sys, traceback, time, re
from urllib.parse import urlparse, parse_qs
from kisskh_downloader.kisskh_api import KissKHApi

def main():
    # Clear env so generate_kkeys doesn't return stale cached keys
    os.environ.pop('KISSKH_STREAM_KEY', None)
    os.environ.pop('KISSKH_SUB_KEY', None)

    api = KissKHApi(base_url='https://kisskh.nl')

    drama_id = int(sys.argv[1]) if len(sys.argv) > 1 else 12864
    episode_id = int(sys.argv[2]) if len(sys.argv) > 2 else 217432
    episode_number = int(sys.argv[3]) if len(sys.argv) > 3 else 1
    drama_title = sys.argv[4] if len(sys.argv) > 4 else 'Drama'

    # Get actual title from API for correct slug
    try:
        resp = api._request(api._drama_api_url(drama_id))
        drama_data = resp.json()
        actual_title = drama_data.get('title', '') or drama_title
        if actual_title:
            drama_title = actual_title
    except Exception:
        pass

    # Build slug: remove special chars that break Angular routing
    title_slug = re.sub(r'[^a-zA-Z0-9\s-]', '', drama_title).strip()
    title_slug = re.sub(r'\s+', '-', title_slug)
    episode_page_url = (
        f'{api.site_domain}/Drama/{title_slug}/Episode-{episode_number}'
        f'?id={drama_id}&ep={episode_id}&page=0&pageSize=100'
    )

    print(f'Generating kkey for drama={drama_id} episode={episode_id} ep_num={episode_number} title="{drama_title}"...')
    print(f'URL: {episode_page_url}')

    # Use Playwright directly — wait for DOM, not networkidle (which hangs)
    from playwright.sync_api import sync_playwright
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            locale='en-US',
        )
        page = context.new_page()

        captured = {}

        def intercept(request):
            url = request.url
            parsed = urlparse(url)
            params = parse_qs(parsed.query)
            if '/api/DramaList/Episode/' in url and 'kkey' in params:
                captured['stream'] = params['kkey'][0]
                print(f'  Captured stream kkey: {captured["stream"][:40]}...')
            elif '/api/Sub/' in url and 'kkey' in params:
                captured['sub'] = params['kkey'][0]
                print(f'  Captured sub kkey: {captured["sub"][:40]}...')

        page.on('request', intercept)
        page.goto(episode_page_url, timeout=120000, wait_until='domcontentloaded')
        print('  Page DOM loaded, waiting for API calls...')

        # Wait up to 60s for API calls to appear
        timeout_at = time.time() + 60
        while len(captured) < 2 and time.time() < timeout_at:
            if not captured:
                # Try clicking the episode button
                btn = page.locator(f'button:has-text("{episode_number}")')
                if btn.count() > 0:
                    btn.first.click()
                    print(f'  Clicked episode {episode_number} button')
            page.wait_for_timeout(2000)

        page.close()
        browser.close()

    if not captured.get('stream'):
        raise RuntimeError(f'Failed to capture kkey for episode {episode_id}')

    print(f'Stream key: {captured.get("stream", "(empty)")}')
    print(f'Sub key: {captured.get("sub", "(empty)")}')
    stream_key = captured.get('stream', '')
    sub_key = captured.get('sub', '')

    # Save to .env
    env_path = os.path.join(os.path.dirname(__file__), '.env')
    # Read existing lines (create file if missing)
    try:
        with open(env_path, 'r') as f:
            lines = f.readlines()
    except FileNotFoundError:
        lines = []

    new_lines = []
    stream_set = sub_set = False
    for line in lines:
        if line.startswith('KISSKH_STREAM_KEY='):
            new_lines.append(f'KISSKH_STREAM_KEY={stream_key}\n')
            stream_set = True
        elif line.startswith('KISSKH_SUB_KEY='):
            if sub_key:
                new_lines.append(f'KISSKH_SUB_KEY={sub_key}\n')
                sub_set = True
            else:
                continue  # drop the line if no sub key
        else:
            new_lines.append(line)

    if not stream_set:
        new_lines.append(f'KISSKH_STREAM_KEY={stream_key}\n')
    if sub_key and not sub_set:
        new_lines.append(f'KISSKH_SUB_KEY={sub_key}\n')

    with open(env_path, 'w') as f:
        f.writelines(new_lines)

    print(f'Saved to {env_path}')
    api.cleanup()

if __name__ == '__main__':
    try:
        main()
    except Exception as e:
        print(f'ERROR: {e}', file=sys.stderr)
        traceback.print_exc(file=sys.stderr)
        sys.exit(1)
