import json, sys, re, time
from playwright.sync_api import sync_playwright

KISSKH_BASE = 'https://kisskh.nl'

with sync_playwright() as pw:
    browser = pw.chromium.launch(
        headless=True,
        args=['--no-sandbox', '--disable-setuid-sandbox']
    )
    context = browser.new_context(
        viewport={'width': 1280, 'height': 720},
        user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
    )
    page = context.new_page()

    # Warm up
    page.goto(KISSKH_BASE, wait_until='domcontentloaded', timeout=30000)

    # Try navigating to episode page
    nav_url = f'{KISSKH_BASE}/Drama/spider-man-no-way-home?id=6653&ep=113513&page=0&pageSize=100'
    print(f'Navigating to: {nav_url}', file=sys.stderr)

    # Capture requests
    requests_captured = []
    def on_req(request):
        url = request.url
        requests_captured.append(url)
        if 'kkey' in url or 'm3u8' in url.lower() or 'DramaList/Episode' in url:
            print(f'REQUEST: {url}', file=sys.stderr)

    def on_resp(response):
        url = response.url
        if 'kkey' in url or 'm3u8' in url.lower() or 'DramaList/Episode' in url:
            print(f'RESPONSE: {url} [{response.status}]', file=sys.stderr)

    page.on('request', on_req)
    page.on('response', on_resp)

    page.goto(nav_url, wait_until='domcontentloaded', timeout=30000)
    print(f'Page title: {page.title()}', file=sys.stderr)
    print(f'Page URL: {page.url}', file=sys.stderr)

    # Wait and try clicking
    time.sleep(3)
    print('After 3s wait...', file=sys.stderr)

    # Check for video elements
    try:
        has_video = page.evaluate('document.querySelectorAll("video").length')
        print(f'Video elements: {has_video}', file=sys.stderr)
    except Exception as e:
        print(f'Video check error: {e}', file=sys.stderr)

    # Click play buttons
    for sel in ['.vjs-big-play-button', 'button[aria-label="Play"]',
                '.play-button', '[class*="play"] button', 'video']:
        try:
            btn = page.locator(sel)
            count = btn.count()
            print(f'Selector "{sel}": {count} found', file=sys.stderr)
            if count > 0:
                btn.first.click(timeout=2000)
                print(f'Clicked: {sel}', file=sys.stderr)
        except Exception as e:
            print(f'Error clicking {sel}: {e}', file=sys.stderr)

    time.sleep(5)
    print(f'After click wait. Total requests: {len(requests_captured)}', file=sys.stderr)

    # Check page content for API URLs
    try:
        html = page.content()
        # Find all script contents
        scripts = page.evaluate('''() => {
            const scripts = document.querySelectorAll('script');
            return Array.from(scripts).map(s => s.src || s.textContent.substring(0, 500));
        }''')
        print(f'Scripts: {len(scripts)}', file=sys.stderr)
        for i, s in enumerate(scripts[:10]):
            if isinstance(s, str) and ('kkey' in s.lower() or 'm3u8' in s.lower() or 'episode' in s.lower()):
                print(f'Script {i}: {s[:200]}', file=sys.stderr)
    except Exception as e:
        print(f'Content check error: {e}', file=sys.stderr)

    browser.close()
