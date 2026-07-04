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

    # Capture ALL API responses
    api_calls = []
    def on_resp(response):
        url = response.url
        if '/api/' in url:
            api_calls.append({'url': url, 'status': response.status})
            print(f'API: [{response.status}] {url[:120]}', file=sys.stderr)

    page.on('response', on_resp)

    # Navigate to the movie page
    nav_url = f'{KISSKH_BASE}/Drama/spider-man-no-way-home?id=6653&ep=113513&page=0&pageSize=100'
    print(f'Navigating to: {nav_url}', file=sys.stderr)
    page.goto(nav_url, wait_until='networkidle', timeout=30000)

    print(f'Page title: {page.title()}', file=sys.stderr)
    print(f'Page URL: {page.url}', file=sys.stderr)

    time.sleep(5)
    print(f'API calls captured: {len(api_calls)}', file=sys.stderr)
    for c in api_calls:
        print(f'  [{c["status"]}] {c["url"][:120]}', file=sys.stderr)

    # Check for iframes
    iframes = page.frames
    print(f'Frames: {len(iframes)}', file=sys.stderr)
    for i, f in enumerate(iframes):
        print(f'  Frame {i}: {f.url[:100]}', file=sys.stderr)

    # Check what's visible on the page
    visible_text = page.evaluate('''() => {
        const body = document.body;
        return body ? body.innerText.substring(0, 2000) : 'no body';
    }''')
    print(f'Page text: {visible_text[:1000]}', file=sys.stderr)

    browser.close()
