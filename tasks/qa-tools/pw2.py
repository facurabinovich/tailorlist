import sys
from playwright.sync_api import sync_playwright
mode=sys.argv[1]
label={'FC':'Demo Collection','YC':'Your Collection'}[mode]
with sync_playwright() as p:
    b=p.chromium.launch(channel='msedge'); pg=b.new_page(viewport={'width':1400,'height':900})
    pg.goto('http://localhost:8599'); pg.wait_for_timeout(7000)
    pg.locator('[data-testid="stSidebar"] label',has_text=label).first.click(); pg.wait_for_timeout(5000)
    pg.locator('a',has_text='My Clusters').first.click(); pg.wait_for_timeout(9000)
    pg.get_by_role('button',name='Run Clustering').click()
    for i in range(24):
        pg.wait_for_timeout(5000)
        if 'Cluster Results' in pg.url or 'Cluster_Results' in pg.url: break
    pg.wait_for_timeout(8000)
    print(pg.url)
    pg.screenshot(path=f'baseline/{mode}_9_cluster_results.png',full_page=True)
    t=pg.inner_text('body'); open(f'baseline/{mode}_9_cluster_results.txt','w',encoding='utf-8').write(t)
    print(len(t),'EXC',len(pg.query_selector_all('[data-testid="stException"]')))
    b.close()
