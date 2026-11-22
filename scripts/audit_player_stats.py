#!/usr/bin/env python3
"""Honest, per-player breakdown of available current versus historical stats.

A 10k archive roster is not a 10k verified current-season database. This
report identifies actual gaps and which leagues the authenticated provider
declares to support, with no zero-filled invented player actions.
"""
from __future__ import annotations
from collections import Counter,defaultdict
import json
from pathlib import Path
from datetime import datetime,timezone
from audit_coverage import load_site
from beta_readiness import CALENDAR, fresh_current_row

ROOT=Path(__file__).resolve().parents[1]
SEASONS=('2023/24','2024/25','2025/26','2026/27','2024','2025','2026')

def count_positive(s,key):
    try:
        value=s.get(key)
        return value is not None and float(value)>0
    except (ValueError,TypeError):
        return False

def categorize(player,live):
    pid=str(player.get('id'))
    calendar=player.get('league') in CALENDAR
    now='2026' if calendar else '2026/27'
    row=(live.get(now) or {}).get(pid)
    history=[x for x in (('2024','2025') if calendar else
             ('2023/24','2024/25','2025/26')) if
             count_positive((live.get(x) or {}).get(pid) or {},'minutes')]
    basic=fresh_current_row(player,row)
    if basic:status='current_basics'
    elif row is not None and count_positive(row,'minutes'):status='current_partial'
    elif history:status='archival_only'
    else:status='no_measured_minutes'
    return now,status,history

def audit(root,pitch):
    live=root.get('liveIndexStats') or {}
    by_league=defaultdict(Counter)
    missing=[]
    totals=Counter()
    catalog={str(x.get('name')):set() for x in pitch.get('catalogue_seasons') or []
             if isinstance(x,dict)}
    for x in pitch.get('catalogue_seasons') or []:
        if isinstance(x,dict):catalog[str(x.get('name'))].add(str(x.get('season')))
    current_match_player_ids=defaultdict(set)
    for match in (pitch.get('matches') or {}).values():
        if not isinstance(match,dict):continue
        league=match.get('league')
        if match.get('season') not in ('2026/27','2026'):continue
        for row in match.get('players') or []:
            pid=str(row.get('player_id') or '')
            if pid:current_match_player_ids[str(league)].add(pid)
    for player in root.get('players') or []:
        league=str(player.get('league') or 'Unknown')
        season,status,history=categorize(player,live)
        totals[status]+=1
        by_league[league][status]+=1
        by_league[league]['profiles']+=1
        if status!='current_basics':
            missing.append({'id':str(player.get('id')),'name':player.get('name'),
                            'league':league,'current_season':season,
                            'status':status,'historical_seasons':history})
    league_rows=[]
    for league,cnt in sorted(by_league.items(),key=lambda kv:(-kv[1]['profiles'],kv[0])):
        now='2026' if league in CALENDAR else '2026/27'
        league_rows.append({'league':league,'total_profiles':cnt['profiles'],
          'complete_current_basics':cnt['current_basics'],
          'current_partial':cnt['current_partial'],
          'historical_only':cnt['archival_only'],
          'no_measured_minutes':cnt['no_measured_minutes'],
          'provider_lists_current_season':now in catalog.get(league,set()),
          'provider_cached_current_players':len(current_match_player_ids.get(league,set())),
          'current_basics_pct':round(100*cnt['current_basics']/cnt['profiles'],1)})
    return {'schema_version':1,
      'players':sum(totals.values()),'current_season_basics_verified':totals['current_basics'],
      'current_season_partial':totals['current_partial'],
      'historical_only':totals['archival_only'],
      'no_measured_minutes':totals['no_measured_minutes'],
      'by_league':league_rows,'missing_player_records':missing,
      'pitchapi':{'key_configured':pitch.get('key_configured'),
                  'last_sync':pitch.get('updated_at'),
                  'backfill_incomplete':pitch.get('backfill_incomplete'),
                  'cached_match_reports':len(pitch.get('matches') or {}),
                  'source':'https://pitchapi.dev/'},
      'note':'Current basic stats require matches, minutes, goals, assists, and source. Archive-only evidence does not qualify as current. Missing metrics are unknown, not zero. Provider league coverage may exclude a country.'}

def selftest():
    sample={'players':[{'id':'a','name':'A','league':'Premier League'},
       {'id':'b','name':'B','league':'Russian Premier League'},
       {'id':'c','name':'C','league':'Premier League'},
       {'id':'d','name':'D','league':'Premier League'}],
       'liveIndexStats':{
          '2026/27':{'a':{'matches':5,'minutes':450,'goals':0,'assists':0,'source':'pitchapi_partial'},
                     'c':{'minutes':220,'source':'pitchapi_partial'}},
          '2025/26':{'b':{'minutes':600,'goals':2}}}}
    report=audit(sample,{'catalogue_seasons':[{'name':'Premier League','season':'2026/27'}],
                         'matches':{}})
    assert report['current_season_basics_verified']==1
    assert report['current_season_partial']==1
    assert report['historical_only']==1 and report['no_measured_minutes']==1
    ru=next(x for x in report['by_league'] if x['league']=='Russian Premier League')
    assert ru['provider_lists_current_season'] is False
    assert report['missing_player_records'][0]['status']=='archival_only'
    print('All-player verified and historical-stat audit PASS')

def main():
    site=ROOT/'_site'
    root=load_site(site/'index.html')
    try:pitch=json.loads((ROOT/'data'/'pitchapi.json').read_text(encoding='utf-8'))
    except (ValueError,OSError):pitch={}
    report=audit(root,pitch)
    report['as_of']=datetime.now(timezone.utc).date().isoformat()
    path=site/'data'/'player_data_gaps.json'
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(report,ensure_ascii=False,separators=(',',':'))+'\n',encoding='utf-8')
    print('PLAYER-STAT COVERAGE:',{
      k:report[k] for k in ('players','current_season_basics_verified',
         'current_season_partial','historical_only','no_measured_minutes')})
    print('CURRENT-STAT LEAGUE GAPS:',
      [(x['league'],x['complete_current_basics'],x['total_profiles'],
        x['provider_lists_current_season']) for x in report['by_league'][:16]])

if __name__=='__main__':
    import sys
    if '--self-test' in sys.argv:selftest()
    else:main()
