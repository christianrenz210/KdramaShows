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

    page.goto(KISSKH_BASE, wait_until='domcontentloaded', timeout=30000)

    nav_url = f'{KISSKH_BASE}/Drama/spider-man-no-way-home?id=6653&page=0&pageSize=100'
    page.goto(nav_url, wait_until='networkidle', timeout=30000)
    time.sleep(3)

    # Dump all elements that contain "0" as text
    all_zero = page.evaluate('''() => {
        const walker = document.createTreeWalker(document.body, 4, null, false);
        const res = [];
        let node;
        while (node = walker.nextNode()) {
            const text = node.textContent.trim();
            if (text === '0') {
                const parent = node.parentElement;
                if (parent) {
                    res.push({
                        tag: parent.tagName,
                        class: parent.className.substring(0, 80),
                        id: parent.id,
                        parentTag: parent.parentElement ? parent.parentElement.tagName : '',
                        html: parent.outerHTML.substring(0, 300)
                    });
                }
            }
        }
        return res;
    }''')
    print(f'Elements containing "0": {len(all_zero)}', file=sys.stderr)
    for e in all_zero:
        print(f'  <{e["tag"]}> id="{e["id"]}" class="{e["class"]}" parent=<{e["parentTag"]}>', file=sys.stderr)
        print(f'  HTML: {e["html"]}', file=sys.stderr)
        print(file=sys.stderr)

    # Also dump full HTML around where episode list should be
    html = page.content()
    # Find where Episode/0 appears
    idx = html.find('Episode')
    if idx >= 0:
        print(f'Found "Episode" at pos {idx}', file=sys.stderr)
        print(f'Context: ...{html[max(0,idx-200):idx+500]}...', file=sys.stderr)

    browser.close()
