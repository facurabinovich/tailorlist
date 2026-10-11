import sys
from playwright.sync_api import sync_playwright
mode=sys.argv[1]  # FC or YC
label={'FC':'Demo Collection','YC':'Your Collection'}[mode]
pages=[('home',None),('overview','Overview'),('playlist_detail','Playlist Detail'),('artist_album','Artist / Album'),('comparison','Playlist Comparison'),('audio_dna','Audio DNA'),('my_clusters','My Clusters'),('glossary','Glossary'),('contact','Contact')]
with sync_playwright() as p:
    b=p.chromium.launch(channel='msedge'); pg=b.new_page(viewport={'width':1400,'height':900})
    pg.goto('http://localhost:8599'); pg.wait_for_timeout(7000)
    pg.locator('[data-testid="stSidebar"] label',has_text=label).first.click(); pg.wait_for_timeout(5000)
    for i,(n,l) in enumerate(pages):
        if l:
            pg.locator('a',has_text=l).first.click(); pg.wait_for_timeout(9000)
        pg.screenshot(path=f'baseline/{mode}_{i}_{n}.png',full_page=True)
        t=pg.inner_text('body')
        open(f'baseline/{mode}_{i}_{n}.txt','w',encoding='utf-8').write(t)
        exc=pg.query_selector_all('[data-testid="stException"]')
        print(n,len(t),'EXCEPTIONS:',len(exc))
    b.close()
