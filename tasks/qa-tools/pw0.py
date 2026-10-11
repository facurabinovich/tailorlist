from playwright.sync_api import sync_playwright
with sync_playwright() as p:
    b=p.chromium.launch(channel='msedge'); pg=b.new_page(viewport={'width':1400,'height':900})
    pg.goto('http://localhost:8599'); pg.wait_for_timeout(8000)
    print(pg.inner_text('body')[:2500])
    pg.screenshot(path='baseline/_probe.png')
    print([ (a.inner_text(), a.get_attribute('href')) for a in pg.query_selector_all('a')][:30])
