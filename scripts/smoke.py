#!/usr/bin/env python3
"""End-to-end browser checks for the published TransferLab build."""
import functools
import http.server
import os
import pathlib
import shutil
import threading
from playwright.sync_api import sync_playwright

class QuietHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, format, *args):
        pass

def main():
    root=pathlib.Path('_site')
    assert (root/'index.html').exists(), 'No built site'
    handler=functools.partial(QuietHandler,directory=str(root))
    server=http.server.ThreadingHTTPServer(('127.0.0.1',0),handler)
    threading.Thread(target=server.serve_forever,daemon=True).start()
    url='http://127.0.0.1:'+str(server.server_port)
    screenshot=pathlib.Path('smoke_screenshots');screenshot.mkdir(exist_ok=True)
    errors=[]
    chrome=shutil.which('google-chrome') or shutil.which('chromium') or shutil.which('chromium-browser')
    with sync_playwright() as playwright:
        options={'headless':True,'args':['--no-sandbox','--disable-dev-shm-usage']}
        if chrome:options['executable_path']=chrome
        browser=playwright.chromium.launch(**options)
        page=browser.new_page(viewport={'width':1440,'height':900})
        page.on('pageerror',lambda error:errors.append(str(error)))
        page.route('**/*',lambda route: route.abort() if route.request.url.startswith(('https://','http://')) and '127.0.0.1' not in route.request.url else route.continue_())
        page.goto(url,wait_until='domcontentloaded',timeout=25000)
        page.locator('#pName').wait_for(timeout=15000)
        page.locator('#navCatalog').click()
        page.locator('.player-card').first.wait_for(timeout=15000)
        count=int(page.locator('#kpiPlayers').inner_text().replace(' ',''))
        assert count>=1353, ('Unexpected shrinkage of player registry',count)
        assert page.locator('.player-index').count()>0,'Catalog indices must be shown'
        cards=page.locator('.card-name').all_text_contents()
        assert cards,'Catalog has no cards'
        assert page.evaluate("""() => {
          const names=[...document.querySelectorAll('#catalogGrid .card-name')].map(n=>n.textContent.trim());
          const cmp=new Intl.Collator('ru',{sensitivity:'base',numeric:true});
          return names.every((n,i)=>i===0 || cmp.compare(names[i-1],n)<=0);
        }"""),('Alphabetical sort not applied',cards[:5])
        board=page.locator('#freeMatchesPanel')
        assert board.count()==1,'Missing free match-results panel'
        board.locator('summary').click()
        if page.locator('#freeMatchLeague option').count()>0:
            assert page.locator('.free-match-row').count()>0,'Match results missing in visible scoreboard'
        page.screenshot(path=str(screenshot/'catalog-desktop.png'))
        page.locator('#filterLeague').select_option('Primeira Liga')
        assert page.locator('.player-card').count()>0,'Portugal filter returned no cards'
        page.locator('#filterLeague').select_option('')
        page.locator('#search').fill('Messi')
        page.locator('#suggestions [data-suggest]').first.wait_for(timeout=5000)
        page.locator('#suggestions [data-suggest]').first.click()
        assert 'Messi' in page.locator('#pName').inner_text(),'Search did not navigate to Messi'
        assert '2026' in page.locator('#currentSeasonBanner').inner_text(), 'MLS defaults to current 2026 season'
        # A Miami player must not show England's EPL / French Ligue 1.
        picker=page.locator('#competitionSelect')
        assert picker.count()==1
        assert picker.locator('option[value="39"]').count()==0,'MLS player shows English league'
        assert picker.locator('option[value="61"]').count()==0,'MLS player shows Ligue 1'
        page.locator('#search').fill('Phil Foden')
        page.locator('#suggestions [data-suggest]').first.wait_for(timeout=5000)
        page.locator('#suggestions [data-suggest]').first.click()
        available=picker.locator('option').evaluate_all('(nodes)=>nodes.map(x=>x.value)')
        assert available==['all','39','45','48','2'],('Foden competition list is incorrect',available)
        banner=page.locator('#currentSeasonBanner').inner_text()
        assert '2026/27' in banner,('Foden must open current season, not archive',banner)
        assert 'PitchAPI' in banner,('Current data synchronization date must be visible',banner)
        assert 'Статистика этого игрока ещё не получена' not in banner, ('Foden current data must display',banner)
        assert not any(x in available for x in ['61','66','3','140','135'])
        picker.select_option('45')
        assert 'нет' in page.locator('#competitionStatus').inner_text().lower() or 'получена' in page.locator('#competitionStatus').inner_text().lower()
        picker.select_option('2')
        assert 'Фоден' not in page.locator('#competitionStatus').inner_text() # does not claim unverified match scores
        picker.select_option('all')
        # Verify real PitchAPI UCL records remain attached to competition 2.
        page.locator('#search').fill('Mbapp')
        page.locator('#suggestions [data-suggest]').first.wait_for(timeout=5000)
        page.locator('#suggestions [data-suggest]').first.click()
        assert 'Mbapp' in page.locator('#pName').inner_text()
        picker.select_option('2')
        cl_minutes=page.locator('#statMinutes').inner_text().replace(' ','').replace('\\u00a0','')
        cl_goals=page.locator('#statGoals').inner_text().strip()
        assert cl_minutes not in ('—','0',''), ('Mbappe UCL minutes absent despite provider records',cl_minutes)
        assert cl_goals not in ('—','0',''), ('Mbappe UCL goals absent despite provider records',cl_goals)
        print('Mbappe UCL 2026/27:',cl_minutes,'minutes,',cl_goals,'goals;',
              'model value:',page.locator('#valueMain').inner_text(),
              'index:',page.locator('#playerIndexBadge').inner_text())
        picker.select_option('all')
        # Verify exact right-back classification from PSG, not generic CB.
        page.locator('#search').fill('Achraf Hakimi')
        page.locator('#suggestions [data-suggest]').first.wait_for(timeout=5000)
        page.locator('#suggestions [data-suggest]').first.click()
        assert 'Hakimi' in page.locator('#pName').inner_text()
        assert page.locator('#pPosition').inner_text()=='RB','Achraf Hakimi must be right-back'
        print('HAKIMI DIAGNOSTIC:',page.locator('#valueMain').inner_text(),
              page.locator('#playerIndexBadge').inner_text(),
              'quality:',page.locator('#modelQuality').inner_text(),
              'market dots:',page.locator('[data-value-kind=market]').count(),
              'chart:',page.locator('#chartSubtitle').inner_text())

        page.locator('#search').fill('Messi')
        page.locator('#suggestions [data-suggest]').first.wait_for(timeout=5000)
        page.locator('#suggestions [data-suggest]').first.click()
        page.locator('#detailsButton').click()
        page.locator('#advancedWrap').wait_for(state='visible',timeout=5000)
        assert page.locator('.advanced-group').count()==4,'Advanced stats grouping missing'
        page.screenshot(path=str(screenshot/'profile-desktop.png'))
        page.set_viewport_size({'width':390,'height':844})
        page.locator('#navCatalog').click()
        assert page.locator('.player-card').count()>0,'Mobile catalog empty'
        page.screenshot(path=str(screenshot/'catalog-mobile.png'))
        browser.close()
    server.shutdown()
    assert not errors,'Browser runtime errors: '+str(errors[:4])
    print('Browser smoke PASS: profiles, sorting, Portugal, search, Champions League & EPL selections, four advanced panels, mobile; players='+str(count))

if __name__=='__main__':main()
