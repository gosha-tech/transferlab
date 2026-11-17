#!/usr/bin/env python3
"""Daily, quota-aware API-Football season player-statistics sync.

Never invent absent metrics. The free tier normally limits /players to pages 1-3;
a partial snapshot is explicitly marked as such.
"""
from __future__ import annotations
import argparse
import datetime as dt
import json
import os
import pathlib
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

ROOT=pathlib.Path(__file__).resolve().parents[1]
DEST=ROOT/'data'/'live.json'
API='https://v3.football.api-sports.io'
# id/name pairs are validated against the league object in each returned record.
COMPETITIONS=[
 (39,'АПЛ','Premier League'),(2,'Лига чемпионов','UEFA Champions League'),
 (45,'Кубок Англии','FA Cup'),(48,'Кубок лиги Англии','League Cup'),
 (140,'Ла Лига','La Liga'),(143,'Кубок Испании','Copa del Rey'),
 (78,'Бундеслига','Bundesliga'),(81,'Кубок Германии','DFB Pokal'),
 (135,'Серия А','Serie A'),(137,'Кубок Италии','Coppa Italia'),
 (61,'Лига 1','Ligue 1'),(66,'Кубок Франции','Coupe de France'),
 (94,'Португалия','Primeira Liga'),(144,'Бельгия','Jupiler Pro League'),
 (203,'Турция','Süper Lig'),(307,'Саудовская лига','Pro League'),
 (253,'MLS','Major League Soccer'),(3,'Лига Европы','UEFA Europa League'),
 (848,'Лига конференций','UEFA Europa Conference League')
]
CALENDAR_YEAR={253}
def season_key(cid,year):
    return str(year) if cid in CALENDAR_YEAR else str(year)+'/27' if year==2026 else str(year)+'/'+str((year+1)%100).zfill(2)
def number(value):
    if value is None or value=='':return None
    try:return int(value)
    except (ValueError,TypeError):return None
def extract_record(item,cid,year):
    player=item.get('player') or {}
    pid=number(player.get('id'))
    if pid is None:return []
    output=[]
    for st in item.get('statistics') or []:
        lg=st.get('league') or {}
        if number(lg.get('id'))!=cid:continue
        team=st.get('team') or {}
        tid=number(team.get('id'))
        g=st.get('games') or {}
        goals=st.get('goals') or {}
        shots=st.get('shots') or {}
        passes=st.get('passes') or {}
        tackles=st.get('tackles') or {}
        cards=st.get('cards') or {}
        drib=st.get('dribbles') or {}
        output.append({
            'api_id':pid,'name':str(player.get('name') or '').strip(),
            'first':str(player.get('firstname') or '').strip(),
            'last':str(player.get('lastname') or '').strip(),
            'birth':(player.get('birth') or {}).get('date'),
            'nationality':player.get('nationality'),
            'height':player.get('height'),
            'photo':player.get('photo'),
            'team':team.get('name'),'team_id':tid,
            'competition_id':cid,'competition':lg.get('name'),
            'season':season_key(cid,year),'season_year':year,
            'position':g.get('position'),
            'games':{'matches':number(g.get('appearences')),
                     'starts':number(g.get('lineups')),
                     'minutes':number(g.get('minutes')),
                     'goals':number(goals.get('total')),
                     'assists':number(goals.get('assists')),
                     'shots':number(shots.get('total')),
                     'shots_on_target':number(shots.get('on')),
                     'passes':number(passes.get('total')),
                     'key_passes':number(passes.get('key')),
                     'tackles':number(tackles.get('total')),
                     'interceptions':number(tackles.get('interceptions')),
                     'dribbles':number(drib.get('success')),
                     'yellow_cards':number(cards.get('yellow')),
                     'red_cards':number(cards.get('red'))}
        })
    return output
LAST_REQUEST_TIME=0.0
def get_api(path,params,key):
    global LAST_REQUEST_TIME
    # Free API-Football has a 10 requests/minute limit. Avoid bursts and 429s.
    interval=float(os.getenv('API_REQUEST_INTERVAL_SECONDS','6.5'))
    remaining=interval-(time.monotonic()-LAST_REQUEST_TIME)
    if LAST_REQUEST_TIME and remaining>0:time.sleep(remaining)
    LAST_REQUEST_TIME=time.monotonic()
    url=API+path+'?'+urllib.parse.urlencode(params)
    req=urllib.request.Request(url,headers={'x-apisports-key':key,'Accept':'application/json','User-Agent':'TransferLab/5.1'})
    with urllib.request.urlopen(req,timeout=35) as resp:
        result=json.load(resp)
    if result.get('errors'):
        raise RuntimeError('API-Football returned an error for '+path+' (check key, quota, and subscription)')
    if not isinstance(result.get('response'),list):raise RuntimeError('Unexpected API response: '+path)
    return result
def sync(key,year,request_limit=85,max_pages=3,sleep=0.15):
    current={}
    if DEST.exists():
        try:current=json.loads(DEST.read_text(encoding='utf-8'))
        except (json.JSONDecodeError,UnicodeDecodeError):current={}
    all_records={(r.get('api_id'),r.get('competition_id'),r.get('season_year'),r.get('team_id')):r
                 for r in current.get('records',[]) if isinstance(r,dict)}
    coverage={(c.get('id'),c.get('year')):c for c in current.get('coverage',[]) if isinstance(c,dict)}
    requests=0;errors=[];had_success=False
    for cid,label,_ in COMPETITIONS:
        if requests>=request_limit:break
        total=None;read_pages=0;new_for_comp={}
        for pg in range(1,max_pages+1):
            if requests>=request_limit:break
            try:
                response=get_api('/players',{'league':cid,'season':year,'page':pg},key)
            except (OSError,RuntimeError,ValueError) as exc:
                errors.append(str(cid)+': '+type(exc).__name__)
                break
            requests+=1;read_pages+=1;had_success=True
            paging=response.get('paging') or {}
            total=number(paging.get('total')) or 1
            for item in response['response']:
                for r in extract_record(item,cid,year):
                    new_for_comp[(r['api_id'],cid,year,r['team_id'])]=r
            if pg>=total:break
            if sleep:time.sleep(sleep)
        if read_pages:
            # Replace data only for this competition/season when a full response succeeded.
            # Keep older known data if a later daily run hits the quota and returns nothing.
            all_records.update(new_for_comp)
            coverage[(cid,year)]={'id':cid,'name':label,'year':year,
                                   'loaded_pages':read_pages,'total_pages':total,
                                   'complete':total is not None and read_pages>=total,
                                   'players_seen':len(new_for_comp)}
    if not had_success:
        raise RuntimeError('No competition was retrieved; preserving the previous good snapshot')
    now=dt.datetime.now(dt.timezone.utc).isoformat(timespec='seconds')
    payload={'schema_version':1,'updated_at':now,'provider':'API-Football',
             'status':'partial','season_year':year,'requests_used':requests,
             'coverage':sorted(coverage.values(),key=lambda r:(r['year'],r['id'])),
             'records':sorted(all_records.values(),key=lambda r:(r['season_year'],r['competition_id'],r['api_id'],r.get('team_id') or 0)),
             'errors':errors,'note':'Statistics reflect only fetched competitions, pages and available API metrics; not a full all-competitions season.'}
    DEST.parent.mkdir(exist_ok=True,parents=True)
    staging=DEST.with_suffix('.tmp')
    staging.write_text(json.dumps(payload,ensure_ascii=False,separators=(',',':'))+'\n',encoding='utf-8')
    staging.replace(DEST)
    print('Updated',len(payload['records']),'competition-player-team records;',
          requests,'requests;',len(errors),'competition failures')
def selftest():
    row={'player':{'id':42,'name':'Example Player','firstname':'Example','lastname':'Player'},
         'statistics':[{'team':{'id':5,'name':'Example FC'},'league':{'id':2,'name':'Champions League'},
                        'games':{'appearences':2,'lineups':1,'minutes':110,'position':'Attacker'},
                        'goals':{'total':1,'assists':0},'shots':{'total':3}}]}
    got=extract_record(row,2,2026)
    assert len(got)==1 and got[0]['games']['assists']==0 and got[0]['games']['minutes']==110
    assert extract_record(row,39,2026)==[]
    assert season_key(39,2026)=='2026/27' and season_key(253,2026)=='2026'
    print('API schema tests OK')
def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--self-test',action='store_true')
    parser.add_argument('--year',type=int,default=dt.datetime.now(dt.timezone.utc).year)
    args=parser.parse_args()
    if args.self_test:return selftest()
    key=os.getenv('API_FOOTBALL_KEY','').strip()
    if not key:
        print('API_FOOTBALL_KEY not set. No update performed; archived stats remain.')
        return
    sync(key,args.year,request_limit=int(os.getenv('API_REQUEST_BUDGET','85')),
         max_pages=int(os.getenv('API_MAX_PAGES','3')))
if __name__=='__main__':main()
