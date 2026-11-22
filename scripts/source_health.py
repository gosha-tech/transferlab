#!/usr/bin/env python3
"""Truthful snapshot freshness diagnostics for TransferLab published data.

A built site can be green while an optional match provider is absent or stale.
Never expose environment credentials; check only last published evidence.
"""
from __future__ import annotations
from datetime import datetime,timezone
import json,pathlib

ROOT=pathlib.Path(__file__).resolve().parents[1]
SITE=ROOT/'_site'

def read_json(path):
    try:
        obj=json.loads(path.read_text(encoding='utf-8'))
        return obj if isinstance(obj,dict) else {}
    except (OSError,ValueError):return {}

def parse_day(s):
    if not s:return None
    try:
        v=datetime.fromisoformat(str(s).replace('Z','+00:00'))
        return v if v.tzinfo else v.replace(tzinfo=timezone.utc)
    except (TypeError,ValueError):return None

def inspect(as_of,inputs):
    out={}
    descriptors={
        'premier_league':('pl_current','retrieved_at',7),
        'pitchapi':('pitchapi','updated_at',4),
        'open_and_community_sources':('free_sources','retrieved_at',8),
        'contract_enrichment':('contract_enrichment','updated_at',30),
    }
    for name,(key,field,limit) in descriptors.items():
        obj=inputs.get(key) or {}
        observed=parse_day(obj.get(field))
        if not observed:
            for alternate in ('last_sync','as_of','generated_at','published_at','last_updated'):
                observed=parse_day(obj.get(alternate))
                if observed:break
        age=round(max(0,(as_of-observed).total_seconds())/86400,1) if observed else None
        status='no_source_timestamp' if age is None else ('stale' if age>limit else 'recent')
        out[name]={'status':status,'as_of':observed.isoformat() if observed else None,
          'age_days':age,'freshness_target_days':limit}
        if key=='pitchapi':
            out[name]['matches_cached']=len(obj.get('matches') or {})
            out[name]['players_by_season']=obj.get('season_player_coverage') or {}
            out[name]['backfill_incomplete']=bool(obj.get('backfill_incomplete'))
            out[name]['errors_reported']=len(obj.get('errors') or [])
            out[name]['status']=(
                'provider_not_configured' if obj.get('key_configured') is False else status)
        if key=='premier_league':
            out[name]['players_with_snapshot']=len(obj.get('players') or {})
            out[name]['source_terms']=obj.get('license') or None
    bad=[k for k,v in out.items() if v['status'] not in ('recent',)]
    return {'schema_version':1,'as_of':as_of.date().isoformat(),
      'providers':out,'need_attention':bad,
      'interpretation':'Snapshot timestamp is not proof that every player has full current-season statistics. Import failures do not become zeroes.',
      'commercial_terms':'Review all source/image licences before selling or sublicensing any dataset.'}

def selftest():
    now=datetime(2026,11,22,tzinfo=timezone.utc)
    x={'pl_current':{'retrieved_at':'2026-11-20T12:00:00Z','players':{'p':{}}},
       'pitchapi':{'updated_at':'2026-11-01','key_configured':True,
                   'matches':{'m':{}},'backfill_incomplete':True}}
    r=inspect(now,x)
    assert r['providers']['premier_league']['status']=='recent'
    assert r['providers']['pitchapi']['status']=='stale'
    assert r['providers']['pitchapi']['matches_cached']==1
    assert 'pitchapi' in r['need_attention']
    print('Source freshness and provenance health check PASS')

def main():
    now=datetime.now(timezone.utc)
    data={name:read_json(ROOT/'data'/(name+'.json')) for name in
          ('pl_current','pitchapi','free_sources','contract_enrichment')}
    report=inspect(now,data)
    site=SITE/'data'
    site.mkdir(exist_ok=True,parents=True)
    (site/'source_health.json').write_text(json.dumps(report,ensure_ascii=False,
        indent=2)+'\n',encoding='utf-8')
    print('Source health:',{k:v['status'] for k,v in report['providers'].items()})

if __name__=='__main__':
    import sys
    if '--self-test' in sys.argv:selftest()
    else:main()
