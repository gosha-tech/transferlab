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
    profile=root.get('profileCoverage') or {}
    result={
      'built_at_utc':datetime.now(timezone.utc).isoformat(timespec='seconds'),
      'source':'TransferLab built site: embedded, provider-backed player statistics',
      'players_total':len(players),
      'seasons':seasons,
      'leagues':{key:{'players':v['players'],'seasons':dict(v['seasons'])}
                 for key,v in sorted(leagues.items())},
      'profiles':profile,
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
