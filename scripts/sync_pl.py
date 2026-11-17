#!/usr/bin/env python3
"""Free, explicitly non-commercial Premier League 2026/27 season player totals.

Source: oladeeayo/pl-catalogue (weekly), FPL/Opta, repo-specific non-commercial
use and attribution. Match via Premier League official 'code' AND player name.
Do not infer stats from team scores; do not turn blank metrics into zeroes.
"""
from __future__ import annotations
import csv,datetime as dt,io,json,pathlib,re,unicodedata,urllib.request
ROOT=pathlib.Path(__file__).resolve().parents[1]
DEST=ROOT/'data'/'pl_current.json'
BASE='https://raw.githubusercontent.com/oladeeayo/pl-catalogue/main/data/2026-27/'
SOURCE='https://github.com/oladeeayo/pl-catalogue'
METRIC_MAP={
 'season_minutes':'minutes','season_starts':'starts','season_goals':'goals',
 'season_assists':'assists','season_xg':'xg','season_xa':'xa',
 'season_clean_sheets':'clean_sheets','season_saves':'saves',
 'opta_shots':'shots','opta_shots_on_target':'shots_on_target',
 'opta_passes':'passes','opta_chances_created':'key_passes',
 'opta_tackles':'tackles','opta_interceptions':'interceptions',
 'opta_recoveries':'recoveries','opta_yellows':'yellow_cards','opta_reds':'red_cards',
 'opta_progressive_carries':'progressive_carries','opta_blocks':'blocks',
 'opta_aerial_duels_won':'aerial_duels_won','opta_ground_duels_won':'ground_duels_won'}
def norm(v):
    x=unicodedata.normalize('NFKD',str(v or '').lower())
    return re.sub(r'[^a-z0-9а-я]+','', ''.join(c for c in x if not unicodedata.combining(c)))
def number(v):
    if v in ('',None,'nan','NaN'):return None
    try:
        f=float(v)
        if f<0 or f>100000 or f!=f:return None
        return round(f,3) if f%1 else int(f)
    except (ValueError,TypeError):return None
def match(row,known):
    # The public code is the Premier League identity, not FPL's changing season ID.
    code=str(row.get('code') or '')
    p=known.get(code)
    if not p:return None
    if p.get('league')!='Premier League':return None
    name=norm(p.get('name'))
    candidates=[norm(row.get('full_name')),norm((row.get('first_name') or '')+' '+(row.get('second_name') or '')),
                norm(row.get('known_name'))]
    if not name:return None
    if any(v and (name==v or (len(name)>6 and (name in v or v in name))) for v in candidates):
        return p
    # Short display surname is still acceptable with an immutable code.
    last=norm(p.get('web'))
    if len(last)>=5 and any(last in c for c in candidates if c):return p
    return None
def parse(rows,players,as_of):
    known={str(p['id']):p for p in players if str(p.get('id') or '').isdigit()}
    result={};skipped=0
    for row in rows:
        p=match(row,known)
        if not p:skipped+=1;continue
        key=str(p['id'])
        m={}
        for source,target in METRIC_MAP.items():
            v=number(row.get(source))
            if v is not None:m[target]=v
        if not any(k in m for k in ('minutes','goals','assists')):continue
        if key in result:raise ValueError('Duplicate Premier League identity '+key)
        info={'player_id':key,'name':p['name'],'team':row.get('team') or p.get('team'),
              'as_of':as_of,'season':'2026/27','source':SOURCE,'minutes_confirmed':m.get('minutes') is not None,
              'stats':m,'position_detail':row.get('position_detail') or None,
              'position':row.get('position') or None,'foot':row.get('foot') or None,
              'height_cm':number(row.get('height_cm')),
              'dob':row.get('date_of_birth') or row.get('dob_tm') or None,
              'market_value_eur':number(row.get('market_value_eur')),
              'market_value_source':SOURCE,
              'contract_until':row.get('contract_until') or None,
              'pl_code':row.get('code')}
        result[key]=info
    return result,skipped
def read_players():
    import zipfile
    with zipfile.ZipFile(ROOT/'TransferLab_RESTORED_2026-11-16.zip') as z:
        html=z.read('index.html').decode('utf-8')
    match=re.search(r'<script id="embeddedData" type="application/json">(.*?)</script>',html,re.S)
    return json.loads(match.group(1))['players']
def download_json(url):
    req=urllib.request.Request(url,headers={'User-Agent':'TransferLab/6.1 (noncommercial; GitHub project)','Accept':'application/json'})
    with urllib.request.urlopen(req,timeout=30) as resp:return json.load(resp)
def download_csv(url):
    req=urllib.request.Request(url,headers={'User-Agent':'TransferLab/6.1 (noncommercial; GitHub project)'})
    with urllib.request.urlopen(req,timeout=45) as resp:
        raw=resp.read(4_000_000)
        if resp.read(1):raise ValueError('Data exceeds download limit')
    return list(csv.DictReader(io.StringIO(raw.decode('utf-8-sig'))))
def sync():
    manifest=download_json(BASE+'manifest.json')
    as_of=manifest.get('exported_at') or ''
    # Manifest age must be visible — a daily download is not a daily player update.
    if not re.match(r'^20\d\d-\d\d-\d\dT',as_of):raise ValueError('PL manifest has no timestamp')
    rows=download_csv(BASE+'players.csv')
    players=read_players()
    result,skipped=parse(rows,players,as_of)
    if len(result)<200:raise RuntimeError('Only '+str(len(result))+' player IDs matched; refusing to overwrite last good snapshot')
    obj={'source':SOURCE,'license':'non-commercial, attribution required','published_at':as_of,
         'retrieved_at':dt.datetime.now(dt.timezone.utc).isoformat(timespec='seconds'),
         'matched_players':len(result),'excluded_unmatched_rows':skipped,'competition':'Premier League',
         'season':'2026/27','players':result}
    DEST.parent.mkdir(exist_ok=True,parents=True)
    tmp=DEST.with_suffix('.tmp')
    tmp.write_text(json.dumps(obj,ensure_ascii=False,separators=(',',':'))+'\n',encoding='utf-8')
    tmp.replace(DEST)
    print('Current PL 2026/27:',len(result),'verified matches; provider export',as_of)
def selftest():
    people=[{'id':'209244','name':'Phil Foden','web':'Foden','team':'Manchester City','league':'Premier League'},
            {'id':'3','name':'Different Name','league':'Premier League'}]
    rows=[
     {'code':'209244','full_name':'Phil Foden','first_name':'Phil','second_name':'Foden',
      'team':'Manchester City','season_minutes':'510','season_starts':'6',
      'season_goals':'2','season_assists':'3','season_xg':'1.31','season_xa':'1.8',
      'opta_tackles':'','foot':'left','position_detail':'Right Winger'},
     {'code':'3','full_name':'Not The Same Person','season_minutes':'800'}]
    o,sk=parse(rows,people,'2026-11-10T10:26:32')
    assert len(o)==1 and sk==1 and o['209244']['stats']['xg']==1.31
    assert 'tackles' not in o['209244']['stats']
    assert o['209244']['stats']['goals']==2
    print('Premier League current-season ID/name/metrics self-test PASS')
if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser();parser.add_argument('--self-test',action='store_true')
    args=parser.parse_args()
    if args.self_test:selftest()
    else:
        try:sync()
        except (OSError,ValueError,RuntimeError) as exc:
            print('Current PL feed unavailable; preserving previous verified snapshot',type(exc).__name__,str(exc)[:180])
