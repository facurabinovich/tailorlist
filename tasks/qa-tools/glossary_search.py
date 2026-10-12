import sys, os
from playwright.sync_api import sync_playwright
# Glossary default view and a few searches. usage: glossary_search.py <base_url> <outdir>
base, outdir = sys.argv[1], sys.argv[2]
os.makedirs(outdir, exist_ok=True)
with sync_playwright() as p:
    b = p.chromium.launch(channel='msedge'); pg = b.new_page(viewport={'width': 1400, 'height': 900})
    pg.goto(base); pg.wait_for_timeout(8000)
    pg.locator('a', has_text='Glossary').first.click(); pg.wait_for_timeout(6000)
    open(f'{outdir}/glossary_default.txt', 'w', encoding='utf-8').write(pg.inner_text('body'))
    for q in ['valence', 'clusters', 'zzzz']:
        box = pg.locator('[data-testid="stTextInput"] input').first
        box.fill(q); box.press('Enter'); pg.wait_for_timeout(4000)
        t = pg.inner_text('body')
        open(f'{outdir}/glossary_{q}.txt', 'w', encoding='utf-8').write(t)
        print(q, len(t), 'EXC', len(pg.query_selector_all('[data-testid="stException"]')), flush=True)
    b.close()
