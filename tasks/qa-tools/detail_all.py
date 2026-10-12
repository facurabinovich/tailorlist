import sys, os
from playwright.sync_api import sync_playwright
# Playlist Detail text for every playlist in the selector.
# usage: detail_all.py <base_url> <outdir>
base, outdir = sys.argv[1], sys.argv[2]
os.makedirs(outdir, exist_ok=True)
with sync_playwright() as p:
    b = p.chromium.launch(channel='msedge')
    pg = b.new_page(viewport={'width': 1400, 'height': 900})
    pg.goto(base); pg.wait_for_timeout(8000)
    pg.locator('a', has_text='Playlist Detail').first.click(); pg.wait_for_timeout(9000)
    sel = pg.locator('[data-testid="stSelectbox"]').first
    sel.click(); pg.wait_for_timeout(1500)
    names = [o.inner_text() for o in pg.locator('[role="option"]').all()]
    pg.keyboard.press('Escape'); pg.wait_for_timeout(1000)
    print('playlists', len(names), flush=True)
    for i, name in enumerate(names):
        sel.click(); pg.wait_for_timeout(1500)
        pg.locator('[role="option"]').nth(i).click(); pg.wait_for_timeout(9000)
        t = pg.inner_text('body')
        open(f'{outdir}/detail_{i}.txt', 'w', encoding='utf-8').write(t)
        pg.screenshot(path=f'{outdir}/detail_{i}.png', full_page=True)
        print(i, len(t), 'EXC', len(pg.query_selector_all('[data-testid="stException"]')), flush=True)
    b.close()
