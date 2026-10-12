import sys, os
from playwright.sync_api import sync_playwright
# YC-only capture of the 10 static pages (no mode radio to click any more).
# usage: r1_pages.py <base_url> <outdir> [query]
base, outdir = sys.argv[1], sys.argv[2]
query = sys.argv[3] if len(sys.argv) > 3 else ''
os.makedirs(outdir, exist_ok=True)
pages = [('0_home', None), ('1_overview', 'Overview'), ('2_playlist_detail', 'Playlist Detail'),
         ('3_artist_album', 'Artist / Album'), ('4_comparison', 'Playlist Comparison'),
         ('5_audio_dna', 'Audio DNA'), ('6_my_clusters', 'My Clusters'),
         ('7_glossary', 'Glossary'), ('8_contact', 'Contact')]
with sync_playwright() as p:
    b = p.chromium.launch(channel='msedge')
    pg = b.new_page(viewport={'width': 1400, 'height': 900})
    pg.goto(base + query); pg.wait_for_timeout(8000)
    print('radios in sidebar:', pg.locator('[data-testid="stSidebar"] [data-testid="stRadio"]').count())
    for n, l in pages:
        if l:
            pg.locator('a', has_text=l).first.click(); pg.wait_for_timeout(9000)
        pg.screenshot(path=f'{outdir}/YC_{n}.png', full_page=True)
        t = pg.inner_text('body')
        open(f'{outdir}/YC_{n}.txt', 'w', encoding='utf-8').write(t)
        print(n, len(t), 'EXC', len(pg.query_selector_all('[data-testid="stException"]')), flush=True)
    b.close()
