import sys, os, re
from playwright.sync_api import sync_playwright
base, outdir, mode = sys.argv[1], sys.argv[2], sys.argv[3]
only = sys.argv[4] if len(sys.argv) > 4 else 'abc'
label = {'FC': 'Demo Collection', 'YC': 'Your Collection'}[mode]
os.makedirs(outdir, exist_ok=True)

def cap(pg, step):
    pg.wait_for_timeout(2500)
    pg.screenshot(path=f'{outdir}/{mode}_{step}.png', full_page=True)
    t = pg.inner_text('body')
    open(f'{outdir}/{mode}_{step}.txt', 'w', encoding='utf-8').write(t)
    exc = len(pg.query_selector_all('[data-testid="stException"]'))
    print(mode, step, len(t), 'EXC', exc, pg.url, flush=True)

def new_session(b):
    ctx = b.new_context(viewport={'width': 1400, 'height': 900})
    pg = ctx.new_page()
    pg.goto(base); pg.wait_for_timeout(7000)
    # The mode radio is gone since R1 (YC only); click it only where it still exists
    radio = pg.locator('[data-testid="stSidebar"] label', has_text=label)
    if radio.count():
        radio.first.click(); pg.wait_for_timeout(5000)
    return ctx, pg

def goto_clusters(pg):
    pg.locator('a', has_text='My Clusters').first.click(); pg.wait_for_timeout(9000)

def click_radio(pg, text):
    pg.locator('[data-testid="stRadio"] label', has_text=text).first.click(); pg.wait_for_timeout(4000)

def run_and_wait(pg, name):
    pg.get_by_role('button', name=re.compile(name)).first.click()
    for i in range(30):
        pg.wait_for_timeout(4000)
        if 'Cluster_Results' in pg.url or 'Cluster Results' in pg.url: break
    pg.wait_for_timeout(8000)

with sync_playwright() as p:
    b = p.chromium.launch(channel='msedge')
    if 'a' in only:
        ctx, pg = new_session(b); goto_clusters(pg)
        click_radio(pg, 'Manual')
        cap(pg, 'a_0_kmeans_manual_config')
        # slider: focus thumb, move to 4 (default 4 already); assert
        print('slider', pg.locator('[data-testid="stSlider"] [role="slider"]').first.get_attribute('aria-valuenow'))
        run_and_wait(pg, 'Run Clustering')
        cap(pg, 'a_1_results')
        # d: assign first unmatched track
        sel = pg.locator('[class*="st-key-assign_"]')
        print('assign selectboxes', sel.count())
        if sel.count():
            sel.first.scroll_into_view_if_needed(); sel.first.click(); pg.wait_for_timeout(1500)
            opts = pg.locator('[role="option"]')
            print('options', [o.inner_text() for o in opts.all()])
            opts.nth(1).click(); pg.wait_for_timeout(2000)
            cap(pg, 'd_0_assigned_unsaved')
            pg.locator('[class*="st-key-save_assignments"] button').first.scroll_into_view_if_needed()
            pg.locator('[class*="st-key-save_assignments"] button').first.click(); pg.wait_for_timeout(5000)
            cap(pg, 'd_1_after_save')
        pg.locator('[class*="st-key-back_to_configure"] button').first.scroll_into_view_if_needed()
        pg.locator('[class*="st-key-back_to_configure"] button').first.click(); pg.wait_for_timeout(10000)
        cap(pg, 'e_0_my_clusters_after')
        ctx.close()
    if 'b' in only:
        ctx, pg = new_session(b); goto_clusters(pg)
        click_radio(pg, 'By category')
        click_radio(pg, 'Both')
        cap(pg, 'b_0_category_config')
        run_and_wait(pg, 'Group Tracks')
        pg.wait_for_timeout(8000)
        cap(pg, 'b_1_results')
        ctx.close()
    if 'c' in only:
        ctx, pg = new_session(b); goto_clusters(pg)
        click_radio(pg, 'By specific genre')
        pg.wait_for_timeout(3000)
        cap(pg, 'c_0_specific_default')
        keys = [c for c in (pg.locator('[class*="st-key-sgl_none_"]').evaluate_all(
            "els=>els.map(e=>[...e.classList].find(c=>c.startsWith('st-key-sgl_none_')))"))]
        print('none keys', keys)
        for k in keys:
            btn = pg.locator(f'.{k} button').first
            if btn.is_visible():
                btn.click(); pg.wait_for_timeout(5000)
        for _ in range(5):
            if '0 selected' in pg.inner_text('body') and 'Pick genres to cluster — 0 selected' in pg.inner_text('body'): break
            for k in keys:
                btn = pg.locator(f'.{k} button').first
                if btn.is_visible():
                    btn.click(); pg.wait_for_timeout(5000)
        cap(pg, 'c_1_specific_none')
        # open first family expander having checkboxes and tick 3 genres
        cbs = pg.locator('[class*="st-key-sgl_cb_"]')
        print('checkbox count', cbs.count(), 'visible', sum(1 for c in cbs.all() if c.is_visible()))
        fam = pg.locator('summary', has_text='Rock — ').first
        print('summary', fam.inner_text())
        fam.click(); pg.wait_for_timeout(2000)
        det = fam.locator('xpath=..')
        done = 0
        for c in det.locator('[class*="st-key-sgl_cb_"]').all():
            if c.is_visible():
                c.locator('label').first.click(); pg.wait_for_timeout(2500); done += 1
                print('ticked', c.inner_text())
            if done == 3: break
        cap(pg, 'c_2_specific_3_selected')
        run_and_wait(pg, 'Group Tracks')
        cap(pg, 'c_3_results')
        ctx.close()
    b.close()
