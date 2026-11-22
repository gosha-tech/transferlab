#!/usr/bin/env python3
"""Publish measured coverage of each season and league; never fill gaps with 0.

This is generated from the exact HTML delivered to visitors, so the report
cannot claim more player coverage than the actual built site.
"""
from __future__ import annotations
from collections import Counter,defaultdict
from datetime import datetime,timezone
import json,pathlib,re,sys

ROOT=pathlib.Path(__file__).resolve().parents[1]
SEASONS=('2024/25','2025/26','2026/27')
CALENDAR_SEASONS=('2024','2025','2026')

def load_site(path):
    txt=path.read_text(encoding='utf-8')
    m=re.search(r'<script id="embeddedData" type="application/json">(.*?)</script>',txt,re.S)
    if not m:
        raise RuntimeError('Embedded player data missing')
    return json.loads(m.group(1))

def summarize(root):
    players=root.get('players') or []
    ids=[str(p['id']) for p in players]
    if len(ids)!=len(set(ids)) or len(ids)<1300:
        raise RuntimeError('Incomplete or duplicate player registry')
    index=root.get('liveIndexStats') or {}
    events=root.get('liveTournamentStats') or {}
    expected=set(ids)
    seasons={}
    for season in (*SEASONS,*CALENDAR_SEASONS):
        pool=events.get(season) or {}
        actual={str(pid) for pid,rows in pool.items()
                if str(pid) in expected and isinstance(rows,list) and
                any(isinstance(r,dict) and isinstance(r.get('stats'),dict) and
                    any(v is not None for v in r['stats'].values()) for r in rows)}
        from_index={str(pid) for pid,v in (index.get(season) or {}).items()
                    if str(pid) in expected and isinstance(v,dict) and
                    v.get('minutes') is not None}
        source_counts=Counter()
        for pid in actual:
            source_counts.update({str(r.get('source') or 'unknown')
                for r in pool.get(pid,[]) if isinstance(r,dict) and r.get('stats')})
        seasons[season]={
            'with_verified_player_stats':len(actual),
            'with_minutes_for_index':len(from_index),
            'without_verified_stats':len(expected-actual),
            'source_profiles':dict(source_counts),
        }
    leagues=defaultdict(lambda:{'players':0,'seasons':defaultdict(int)})
    for p in players:
        pid=str(p['id'])
        league=str(p.get('league') or 'Unknown')
        leagues[league]['players']+=1
        for season in (CALENDAR_SEASONS if league in ('MLS','Brasileirão') else SEASONS):
            if pid in (events.get(season) or {}) and any(
                 isinstance(r,dict) and r.get('stats') for r in events[season][pid]):
                leagues[league]['seasons'][season]+=1
    competitions={}
    for season in (*SEASONS,*CALENDAR_SEASONS):
        by_comp=defaultdict(lambda:{'players':set(),'with_minutes':set(),'sources':Counter()})
        for pid,rows in (events.get(season) or {}).items():
            if str(pid) not in expected or not isinstance(rows,list):continue
            for record in rows:
                if not isinstance(record,dict) or not isinstance(record.get('stats'),dict):
                    continue
                if not record['stats']:continue
                key=str(record.get('id') or '')+' · '+str(record.get('name') or '?')
                row=by_comp[key]
                row['players'].add(str(pid))
                if float(record['stats'].get('minutes') or 0)>0:
                    row['with_minutes'].add(str(pid))
                row['sources'][str(record.get('source') or 'unknown')]+=1
        competitions[season]={key:{
            'players':len(val['players']),
            'with_minutes':len(val['with_minutes']),
            'source_rows':dict(val['sources'])}
            for key,val in sorted(by_comp.items())}
    market=root.get('marketHistory5Y') or {}
    market_count=len(market)
    profile=root.get('profileCoverage') or {}
    photo_candidates={
      'api_football_id':sum(bool(p.get('apiPhoto')) for p in players),
      'wikimedia_commons_licensed':sum(bool(p.get('commonsPhoto')) for p in players),
      'sofascore_matched_id':sum(bool(p.get('sofaId')) for p in players),
      'premier_league_identity_candidate':sum(bool(str(p.get('id') or '').isdigit()) and
          p.get('league')=='Premier League' for p in players),
    }
    any_photo_candidate=sum(any((
      bool(p.get('apiPhoto')),bool(p.get('commonsPhoto')),
      bool(p.get('sofaId')),
      bool(str(p.get('id') or '').isdigit()) and p.get('league')=='Premier League'
    )) for p in players)
    current_year={'2026/27':set(), '2026':set()}
    previous_year={'2025/26':set(), '2025':set()}
    for group,target in ((current_year,current_year),(previous_year,previous_year)):
      for season in group:
        for pid,rows in (events.get(season) or {}).items():
          if str(pid) in expected and any(isinstance(r,dict) and
             isinstance(r.get('stats'),dict) and
             any(r['stats'].get(k) is not None for k in ('goals','assists','minutes','matches'))
             for r in rows):
            group[season].add(str(pid))
    any_current=len(current_year['2026/27']|current_year['2026'])
    any_last_two=len(current_year['2026/27']|current_year['2026']|
                     previous_year['2025/26']|previous_year['2025'])
    result={
      'built_at_utc':datetime.now(timezone.utc).isoformat(timespec='seconds'),
      'source':'TransferLab built site: embedded, provider-backed player statistics',
      'players_total':len(players),
      'seasons':seasons,
      'leagues':{key:{'players':v['players'],'seasons':dict(v['seasons'])}
                 for key,v in sorted(leagues.items())},
      'profiles':profile,
      'photo_candidate_coverage':{
        'candidates_by_provider':photo_candidates,
        'players_with_id_backed_candidates':any_photo_candidate,
        'players_without_id_backed_candidates':len(players)-any_photo_candidate,
        'note':'These are portrait URL candidates, NOT confirmed loaded or licensed images. Generic verified photographs may be available for additional players.'
      },
      'catalog_stat_coverage':{
        'players_with_verified_current_season':any_current,
        'players_with_current_or_explicit_previous_season':any_last_two,
        'players_with_neither':len(players)-any_last_two,
        'note':'Previous-season stats are labeled archive; missing current-season values are never replaced with zero.'
      },
      'competition_coverage':competitions,
      'five_year_market_values':{
        'players_with_actual_observations':market_count,
        'players_with_two_or_more':sum(len(v)>=2 for v in market.values()),
        'last_real_market_date':root.get('marketHistoryLastObserved'),
        'source':root.get('marketHistorySource'),
        'observations':sum(len(v) for v in market.values()),
      },
      'pitchapi':{
         'key_configured_on_last_successful_sync':root.get('pitchAPIKeyConfigured',False),
         'source_last_sync':root.get('pitchAPILastSync'),
         'players_by_season':root.get('pitchAPISeasonCoverage') or {},
         'backfill_incomplete':root.get('pitchAPIBackfillIncomplete',True),
         'errors':(root.get('pitchAPIErrors') or [])[:30],
      },
      'interpretation':'Partial coverage is not zero appearances. A value is only supplied when its provider backed data exists.'
    }
    return result

def main():
    site=ROOT/'_site'/'index.html'
    output=ROOT/'_site'/'data'/'coverage.json'
    report=summarize(load_site(site))
    output.parent.mkdir(parents=True,exist_ok=True)
    output.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print('Three-season player coverage:',{s:(v['with_verified_player_stats'],
          v['with_minutes_for_index']) for s,v in report['seasons'].items()})
    print('Coverage report:',output)

if __name__=='__main__':
    main()
