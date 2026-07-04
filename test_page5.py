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

    # Capture all API calls with kkey or m3u8
    found = []
    def on_req(request):
        url = request.url
        if 'kkey' in url or 'm3u8' in url.lower() or '/api/DramaList/Episode/' in url:
            found.append(('REQ', url))
            print(f'>> REQ: {url}', file=sys.stderr)
    def on_resp(response):
        url = response.url
        if 'kkey' in url or 'm3u8' in url.lower() or '/api/DramaList/Episode/' in url:
            found.append(('RES', url))
            print(f'>> RES: {url} [{response.status}]', file=sys.stderr)

    page.on('request', on_req)
    page.on('response', on_resp)

    page.goto(KISSKH_BASE, wait_until='domcontentloaded', timeout=30000)

    nav_url = f'{KISSKH_BASE}/Drama/spider-man-no-way-home?id=6653&page=0&pageSize=100'
    page.goto(nav_url, wait_until='networkidle', timeout=30000)
    time.sleep(3)

    # Click the episode button
    btn = page.locator('button.mat-raised-button').first
    print(f'Button found: {btn.count() > 0}', file=sys.stderr)
    if btn.count() > 0:
        print(f'Button text: "{btn.text_content()}"', file=sys.stderr)
        btn.click()
        print('Clicked episode button', file=sys.stderr)

    time.sleep(5)
    print(f'Found {len(found)} kkey/m3u8 events', file=sys.stderr)

    # Check for video elements
    has_video = page.evaluate('document.querySelectorAll("video").length')
    print(f'Video elements: {has_video}', file=sys.stderr)

    # Check page URL
    print(f'Final URL: {page.url}', file=sys.stderr)

    browser.close()
