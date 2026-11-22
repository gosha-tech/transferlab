#!/usr/bin/env python3
"""Archive *actual* TransferLab browser model forecasts, never future realized fees.

Only run on scheduled/manual builds after `tournaments_build.py`. Each capture
contains the UTC day, model version, revision and observed player club; values
are generated from the same pricedPlayer() function visitors see.
"""
import datetime as dt
import functools
import http.server
import json
import os
import pathlib
import re
import shutil
import threading

ROOT=pathlib.Path(__file__).resolve().parents[1]
OUTPUT=ROOT/'data'/'valuation_forecast_snapshots.json'
SITE=ROOT/'_site'

class QuietHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self,*args):pass

def record(value,archive):
    day=str(value.get('as_of') or '')
    if not re.fullmatch(r'20\d{2}-\d{2}-\d{2}',day):
        raise RuntimeError('Model did not return a dated forecast')
    if day!=dt.datetime.now(dt.timezone.utc).date().isoformat():
        raise RuntimeError('Cannot archive forecasts under a different date')
    rows=value.get('forecasts') or {}
    if len(rows)<300:
        raise RuntimeError('Suspiciously few model forecasts; refusing to save')
    if int(value.get('errors') or 0)>25:
        raise RuntimeError('Many player pricing errors; refusing snapshot')
    clean={}
    for pid,entry in rows.items():
        if not isinstance(entry,dict):continue
        amount=entry.get('eur_m')
        if not isinstance(amount,(int,float)) or isinstance(amount,bool) or not 0<float(amount)<=500:
            continue
        if not entry.get('club'):continue
        clean[str(pid)]={'eur_m':round(float(amount),2),
            'index':entry.get('index'),
            'club':str(entry['club'])}
    if len(clean)<300:raise RuntimeError('Too few validated forecasts')
    one={'as_of':day,'model_version':str(value.get('model_version') or ''),
         'model_commit':os.getenv('GITHUB_SHA','')[:12],
         'forecasts':clean}
    snapshots=[x for x in (archive.get('snapshots') or [])
        if isinstance(x,dict) and x.get('as_of')!=day]
    snapshots.append(one)
    snapshots=sorted(snapshots,key=lambda s:str(s.get('as_of') or ''))[-730:]
    return {'schema_version':1,'snapshots':snapshots}

def capture():
    from playwright.sync_api import sync_playwright
    if not (SITE/'index.html').exists():raise RuntimeError('Built site missing')
    handler=functools.partial(QuietHandler,directory=str(SITE))
    server=http.server.ThreadingHTTPServer(('127.0.0.1',0),handler)
    threading.Thread(target=server.serve_forever,daemon=True).start()
    with sync_playwright() as playwright:
        chrome=shutil.which('google-chrome') or shutil.which('chromium') or shutil.which('chromium-browser')
        launch={'headless':True,'args':['--no-sandbox','--disable-dev-shm-usage']}
        if chrome:launch['executable_path']=chrome
        browser=playwright.chromium.launch(**launch)
        page=browser.new_page()
        page.route('**/*',lambda route:route.abort()
            if route.request.url.startswith(('http://','https://'))
            and '127.0.0.1' not in route.request.url else route.continue_())
        page.goto('http://127.0.0.1:'+str(server.server_port),wait_until='domcontentloaded',timeout=30000)
        page.wait_for_function('typeof window.transferLabForecastExport==="function"',timeout=15000)
        result=page.evaluate('window.transferLabForecastExport()')
        browser.close()
    server.shutdown()
    try:old=json.loads(OUTPUT.read_text(encoding='utf-8'))
    except (OSError,ValueError):old={}
    saved=record(result,old)
    OUTPUT.parent.mkdir(parents=True,exist_ok=True)
    tmp=OUTPUT.with_suffix('.tmp')
    tmp.write_text(json.dumps(saved,ensure_ascii=False,separators=(',',':'))+'\n',encoding='utf-8')
    tmp.replace(OUTPUT)
    print('Archived live model forecasts:',len(saved['snapshots']),
          'days,',len(saved['snapshots'][-1]['forecasts']),'player quotes; version',
          saved['snapshots'][-1]['model_version'])

def selftest():
    today=dt.datetime.now(dt.timezone.utc).date().isoformat()
    rows={str(i):{'eur_m':30+i*.01,'club':'West Ham United','index':70}
          for i in range(350)}
    one=record({'as_of':today,'forecasts':rows,'errors':0,'model_version':'beta'},
               {'snapshots':[]})
    assert len(one['snapshots'])==1
    twice=record({'as_of':today,'forecasts':rows,'errors':0,'model_version':'beta'},
                 one)
    assert len(twice['snapshots'])==1
    print('Dated model forecast capture: no invented historical values PASS')

if __name__=='__main__':
    import sys
    if '--self-test' in sys.argv:selftest()
    else:capture()
