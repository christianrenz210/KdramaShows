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

    page.on('response', lambda r: print(f'API: [{r.status}] {r.url[:120]}', file=sys.stderr) if '/api/' in r.url else None)
    page.on('request', lambda r: print(f'REQ: {r.url[:120]}', file=sys.stderr) if 'kkey' in r.url or 'm3u8' in r.url.lower() else None)

    page.goto(KISSKH_BASE, wait_until='domcontentloaded', timeout=30000)

    nav_url = f'{KISSKH_BASE}/Drama/spider-man-no-way-home?id=6653&page=0&pageSize=100'
    page.goto(nav_url, wait_until='networkidle', timeout=30000)
    time.sleep(2)

    # Find episode elements
    episode_info = page.evaluate('''() => {
        const eps = document.querySelectorAll('[class*="episode"], [class*="Episode"], .ep-item, [class*="ep-item"], a[href*="ep="], [class*="ep_"], li[class*="ep"]');
        const results = [];
        eps.forEach((el, i) => {
            results.push({
                index: i,
                tag: el.tagName,
                className: el.className,
                text: el.textContent.trim().substring(0, 50),
                href: el.href || '',
                onclick: el.getAttribute('onclick') || '',
                rect: el.getBoundingClientRect()
            });
        });
        return results;
    }''')
    print(f'Episode elements found: {len(episode_info)}', file=sys.stderr)
    for e in episode_info:
        print(f'  [{e["index"]}] <{e["tag"]} class="{e["className"]}"> text="{e["text"]}"', file=sys.stderr)

    # Try to find ANY clickable element with "0" (the episode number)
    clickable = page.evaluate('''() => {
        const all = document.querySelectorAll('a, button, [role="button"], [onclick], .cursor-pointer');
        const res = [];
        all.forEach(el => {
            const text = el.textContent.trim();
            if (text === '0' || text.match(/^0$/) || el.querySelector('[class*="ep"]') || (text.length < 5 && text.match(/^[\d.]+$/))) {
                const rect = el.getBoundingClientRect();
                res.push({
                    tag: el.tagName,
                    class: el.className.substring(0, 60),
                    text: text,
                    rect: { top: rect.top, left: rect.left, width: rect.width, height: rect.height }
                });
            }
        });
        return res;
    }''')
    print(f'Clickable with "0": {len(clickable)}', file=sys.stderr)
    for c in clickable:
        print(f'  <{c["tag"]}> class="{c["class"]}" text="{c["text"]}"', file=sys.stderr)

    browser.close()
