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
        assert count==1352, ('Wrong player count',count)
        cards=page.locator('.card-name').all_text_contents()
        assert cards and cards[0].casefold().startswith('aaron'),('Alphabetical sort not applied',cards[:5])
        page.screenshot(path=str(screenshot/'catalog-desktop.png'))
        page.locator('#filterLeague').select_option('Primeira Liga')
        assert page.locator('.player-card').count()>0,'Portugal filter returned no cards'
        page.locator('#filterLeague').select_option('')
        page.locator('#search').fill('Messi')
        page.locator('#suggestions [data-suggest]').first.wait_for(timeout=5000)
        page.locator('#suggestions [data-suggest]').first.click()
        assert 'Messi' in page.locator('#pName').inner_text(),'Search did not navigate to Messi'
        page.screenshot(path=str(screenshot/'profile-desktop.png'))
        page.set_viewport_size({'width':390,'height':844})
        page.locator('#navCatalog').click()
        assert page.locator('.player-card').count()>0,'Mobile catalog empty'
        page.screenshot(path=str(screenshot/'catalog-mobile.png'))
        browser.close()
    server.shutdown()
    assert not errors,'Browser runtime errors: '+str(errors[:4])
    print('Browser smoke PASS: profiles, sorting, Portugal, search, responsive view; players='+str(count))

if __name__=='__main__':main()
