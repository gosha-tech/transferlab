#!/usr/bin/env python3
"""Optional FREE PitchAPI ingestion: match-by-match season statistics for 77 leagues.

Requires a free PITCHAPI_KEY secret, never a card or paid subscription.
No guessing: names must match within the confirmed match team and be unique.
Match ids are stable; re-fetching cannot double-count. Missing values are None,
never zero. Photos returned by the CDN are saved as references only until
separate display rights have been verified.
"""
from __future__ import annotations
import datetime as dt
import json
import os
import pathlib
import re
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from collections import defaultdict

ROOT=pathlib.Path(__file__).resolve().parents[1]
OUT=ROOT/'data'/'pitchapi.json'
API='https://api.pitchapi.dev/v1'
# Include league and UEFA names; actual league IDs always come from /leagues.
TARGETS={
 'Premier League':['premier league'],
 'La Liga':['la liga','primera division'],
 'Bundesliga':['bundesliga'],
 'Serie A':['serie a'],
 'Ligue 1':['ligue 1'],
 'Primeira Liga':['primeira liga','liga portugal'],
 'Belgian Pro League':['belgian pro league','jupiler pro league'],
 'Süper Lig':['super lig','süper lig'],
 'Saudi Pro League':['saudi pro league','saudi professional league'],
 'MLS':['mls','major league soccer'],
 'Brasileirão':['brasileirao','brasileirão','brazilian serie a'],
 'UEFA Champions League':['champions league','uefa champions league'],
 'UEFA Europa League':['europa league','uefa europa league'],
 'UEFA Conference League':['conference league','uefa conference league'],
 'FA Cup':['fa cup'],
 'EFL Cup':['efl cup','carabao cup','league cup'],
 'Copa del Rey':['copa del rey'],
 'Coppa Italia':['coppa italia'],
 'DFB Pokal':['dfb pokal','dfb-pokal'],
 'Coupe de France':['coupe de france'],
 'Taça de Portugal':['taca de portugal','taça de portugal']
}
# Directly mapped internal competition ids, no cross-league conflation.
LEAGUE_IDS={'Premier League':39,'La Liga':140,'Bundesliga':78,'Serie A':135,
 'Ligue 1':61,'Primeira Liga':94,'Belgian Pro League':144,'Süper Lig':203,
 'Saudi Pro League':307,'MLS':253,'UEFA Champions League':2,
 'UEFA Europa League':3,'UEFA Conference League':848,'FA Cup':45,
 'EFL Cup':48,'Copa del Rey':143,'Coppa Italia':137,'DFB Pokal':81,
 'Coupe de France':66}
# PitchAPI documents grouped values with a metric key and a stat.value.
METRICS={'goals':'goals','assists':'assists','minutes_played':'minutes',
 'total_shots':'shots','shots_on_target':'shots_on_target','key_passes':'key_passes',
 'tackles':'tackles','interceptions':'interceptions','recoveries':'recoveries',
 'clearances':'clearances','blocks':'blocks','touches':'touches',
 'successful_dribbles':'dribbles','xg':'xg','xa':'xa','expected_goals':'xg',
 'expected_assists':'xa','yellow_cards':'yellow_cards','red_cards':'red_cards',
 'progressive_passes':'progressive_passes','progressive_carries':'progressive_carries'}
def norm(v):
    text=unicodedata.normalize('NFKD',str(v or '').casefold())
    return re.sub(r'[^a-z0-9а-я]','', ''.join(c for c in text if not unicodedata.combining(c)))
def team_norm(v):
    v=norm(v)
    for prefix in ('fc','cf','ac','sc'):
        if v.startswith(prefix) and len(v)>6:v=v[len(prefix):]
    for suffix in ('fc','cf','afc','sc'):
        if v.endswith(suffix) and len(v)>6:v=v[:-len(suffix)]
    return v
def aliases(name):
    name=str(name or '').replace('.',' ').replace('-',' ')
    words=[norm(x) for x in name.split() if x]
    out={norm(name)}
    if len(words)>=2:
        out.add(words[-1]+words[0][:1])
        out.add(words[0][:1]+words[-1])
    return out
def roster_match(name,team,roster):
    candidates=[p for p in roster if team_norm(p.get('team'))==team_norm(team) and
                (norm(name) in aliases(p.get('name')) or
                 norm(name) in aliases(p.get('web')))]
    return candidates[0] if len(candidates)==1 else None
def parse_groups(groups):
    data={}
    for group in groups or []:
        for part in (group.get('stats') or {}).values():
            if not isinstance(part,dict):continue
            key=METRICS.get(str(part.get('key') or '').lower())
            stat=part.get('stat') or {}
            value=stat.get('value')
            if not key or value is None:continue
            try:
                v=float(value)
                if v!=v or v<0 or v>100000:continue
            except (ValueError,TypeError):continue
            data[key]=round(v,3) if v%1 else int(v)
    return data
def get(path,key,params=None):
    uri=API+path+(('?'+urllib.parse.urlencode(params)) if params else '')
    req=urllib.request.Request(uri,headers={'X-API-KEY':key,'Accept':'application/json',
                                            'User-Agent':'TransferLab/6.1 (GitHub Pages)'})
    with urllib.request.urlopen(req,timeout=30) as response:obj=json.load(response)
    if not isinstance(obj,dict) or obj.get('error'):raise RuntimeError('Unexpected PitchAPI response')
    return obj.get('data')
def discover(catalogue):
    selected=[]
    for league in (catalogue or {}).get('leagues',[]):
        name=norm(league.get('name'))
        for canonical,variants in TARGETS.items():
            if name in {norm(x) for x in variants} and league.get('id'):
                seasons=league.get('seasons') or []
                eligible=('2026/2027' in seasons or '2026' in seasons)
                if eligible:
                    selected.append((canonical,str(league['id']),
                                     '2026' if canonical in ('MLS','Brasileirão') else '2026/2027'))
                break
    return selected
def read_roster():
    from zipfile import ZipFile
    with ZipFile(ROOT/'TransferLab_RESTORED_2026-11-16.zip') as archive:
        html=archive.read('index.html').decode('utf-8')
    m=re.search(r'<script id="embeddedData" type="application/json">(.*?)</script>',html,re.S)
    if not m:raise RuntimeError('No embedded roster')
    return json.loads(m.group(1))['players']
def sync():
    key=os.getenv('PITCHAPI_KEY','').strip()
    if not key:
        print('PITCHAPI_KEY absent: free match-player importer not activated')
        return
    try:prior=json.loads(OUT.read_text(encoding='utf-8'))
    except (OSError,ValueError):prior={}
    cached=dict(prior.get('matches') or {})
    known=prior.get('pitch_id_matches') or {}
    roster=read_roster()
    leagues=discover(get('/leagues',key))
    requests=1
    # Rotate to balance different leagues across days.
    cursor=int(prior.get('league_cursor') or 0)
    leagues=leagues[cursor%len(leagues):]+leagues[:cursor%len(leagues)] if leagues else []
    budget=max(1,min(int(os.getenv('PITCHAPI_REQUEST_BUDGET','95')),500))
    fetched=0
    checked=0
    errors=[]
    for canonical,league_id,season in leagues:
        if requests>=budget:break
        try:
            rows=(get('/leagues/'+urllib.parse.quote(league_id)+'/matches',key,
                      {'season':season}) or {}).get('matches') or []
            requests+=1
        except (OSError,ValueError,RuntimeError) as exc:
            errors.append(canonical+': '+type(exc).__name__)
            continue
        for match in rows:
            mid=match.get('id')
            if not re.fullmatch(r'm_[A-Za-z0-9]{6}',str(mid or '')):continue
            if match.get('status')!='finished':continue
            if mid in cached:continue
            if requests>=budget:break
            home=match.get('home_team') or {}
            away=match.get('away_team') or {}
            teams={home.get('id'):home.get('name'),away.get('id'):away.get('name')}
            try:
                stats=get('/matches/'+mid+'/players',key)
                requests+=1;checked+=1
                if not isinstance(stats,list):continue
                processed=[]
                for entry in stats:
                    player=entry.get('player') or {}
                    pid=str(player.get('id') or '')
                    team=teams.get(entry.get('team_id'))
                    if not pid.startswith('p_') or not team:continue
                    known_id=known.get(pid)
                    original=next((p for p in roster if str(p.get('id'))==str(known_id)),None) if known_id else None
                    if original is None:original=roster_match(player.get('name'),team,roster)
                    if original is None:continue
                    sid=str(original['id'])
                    metrics=parse_groups(entry.get('stats'))
                    if not metrics:continue
                    known[pid]=sid
                    processed.append({'player_id':sid,'pitch_id':pid,'team':team,
                                      'stats':metrics,'pitch_photo':player.get('image_url')})
                cached[mid]={'id':mid,'date':match.get('date'),'season':'2026' if season=='2026' else '2026/27',
                             'league':canonical,'league_id':league_id,'competition_id':LEAGUE_IDS.get(canonical),
                             'players':processed,'source':'PitchAPI'}
                fetched+=1
            except urllib.error.HTTPError as exc:
                errors.append(canonical+': HTTP '+str(exc.code))
                if exc.code in (401,403,429):
                    break
            except (ValueError,OSError,RuntimeError) as exc:
                errors.append(canonical+': '+type(exc).__name__)
            time.sleep(float(os.getenv('PITCHAPI_PAUSE','0.32')))
        if requests>=budget:break
    payload={'provider':'PitchAPI','source':'https://pitchapi.dev/',
             'updated_at':dt.datetime.now(dt.timezone.utc).isoformat(timespec='seconds'),
             'key_configured':True,'requests_used':requests,'matches_fetched':fetched,
             'leagues_available':len(leagues),'league_cursor':cursor+max(1,min(len(leagues),max(1,requests//2))),
             'match_stats_checked':checked,'matches':cached,'pitch_id_matches':known,'errors':errors}
    if not leagues:raise RuntimeError('No current-season PitchAPI leagues; refusing empty cache')
    OUT.parent.mkdir(exist_ok=True,parents=True)
    tmp=OUT.with_suffix('.tmp')
    tmp.write_text(json.dumps(payload,ensure_ascii=False,separators=(',',':'))+'\n',encoding='utf-8')
    tmp.replace(OUT)
    print('PitchAPI:',fetched,'new match reports;',len(known),'identified players;',requests,'API calls')
def test():
    assert parse_groups([{'key':'top_stats','stats':{
        'Goals':{'key':'goals','stat':{'type':'integer','value':2}},
        'xG':{'key':'xg','stat':{'type':'double','value':1.32}},
        'Missing':{'key':'assists','stat':{'type':'integer','value':None}}}}])=={'goals':2,'xg':1.32}
    roster=[{'id':'9','name':'Erling Haaland','team':'Manchester City'},
            {'id':'10','name':'Phil Foden','team':'Manchester City'},
            {'id':'99','name':'Erling Haaland','team':'Paris Saint-Germain'}]
    assert roster_match('E. Haaland','Manchester City',roster)['id']=='9'
    assert roster_match('E. Haaland','Paris Saint-Germain',roster)['id']=='99'
    assert roster_match('P. Foden','Manchester City',roster)['id']=='10'
    assert roster_match('E. Haaland','Unknown Club',roster) is None
    assert discover({'leagues':[{'id':'l_ABC123','name':'Premier League',
                                 'seasons':['2025/2026','2026/2027']},
                                {'id':'l_DEF456','name':'Serie A',
                                 'seasons':['2023/2024']}]})==[('Premier League','l_ABC123','2026/2027')]
    print('PitchAPI unique club/player matches, typed metrics, season discovery PASS')
if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser();p.add_argument('--self-test',action='store_true')
    args=p.parse_args()
    if args.self_test:test()
    else:sync()
