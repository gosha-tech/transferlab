#!/usr/bin/env python3
"""Auditable season/competition coherence checks across the whole player registry.

Some providers have partial fixture coverage. Their matches and minutes must
not be presented as exact if the numbers are incompatible. This audit flags
source coverage and never fabricates missing appearances or actions.
"""
import json
import math
import pathlib
import re
from collections import Counter,defaultdict

ROOT=pathlib.Path(__file__).resolve().parents[1]
SITE=ROOT/'_site'/'index.html'
OUT=ROOT/'_site'/'data'/'match_consistency.json'

def numeric(value):
    if isinstance(value,bool) or value is None:return None
    try:
        v=float(value)
        return v if math.isfinite(v) and v>=0 else None
    except (ValueError,TypeError):
        return None

def audit(data):
    players=data.get('players') or []
    valid={str(p['id']):p for p in players}
    rows=(data.get('liveTournamentStats') or {})
    inconsistent=[]
    per_source=Counter()
    checked=0
    missing=0
    for season,pool in rows.items():
        if not isinstance(pool,dict):continue
        for pid,entries in pool.items():
            if str(pid) not in valid or not isinstance(entries,list):continue
            for row in entries:
                if not isinstance(row,dict):continue
                stats=row.get('stats')
                if not isinstance(stats,dict):continue
                minutes=numeric(stats.get('minutes'))
                appearances=numeric(stats.get('matches'))
                starts=numeric(stats.get('starts'))
                checked+=1
                source=str(row.get('source') or 'unknown')
                if minutes is None or appearances is None:
                    missing+=1
                    per_source[source]+=1
                    continue
                impossible=minutes>appearances*130+1e-6
                bad_starts=starts is not None and starts>appearances
                if impossible or bad_starts:
                    if len(inconsistent)<1000:
                        inconsistent.append({
                           'id':str(pid),'player':valid[str(pid)].get('name'),
                           'season':season,'competition':str(row.get('name') or row.get('id')),
                           'source':source,'matches_reported':appearances,
                           'minutes_reported':minutes,'starts_reported':starts,
                           'min_by_minutes':math.ceil(minutes/130),
                           'why':'minutes_exceed_match_cap' if impossible else 'starts_exceed_matches'})
    return {'schema_version':1,'registry':len(valid),
        'tournament_rows_checked':checked,'rows_missing_match_or_minutes_count':missing,
        'inconsistent_rows':len(inconsistent),
        'sample_inconsistencies':inconsistent,
        'source_missing_count':dict(per_source),
        'interpretation':'A reported source is incomplete if games and minutes disagree. Show an appearance lower bound; do not invent exact games.'}

def selftest():
    base={'players':[{'id':'1','name':'Example AM','pos':'Midfielder','displayPosition':'AM'}],
        'liveTournamentStats':{'2026/27':{'1':[
           {'name':'Premier League','source':'official',
            'stats':{'matches':4,'minutes':1040,'starts':3}},
           {'name':'UEFA Champions League','source':'partial',
            'stats':{'matches':None,'minutes':249}}]}}}
    r=audit(base)
    assert r['inconsistent_rows']==1 and r['rows_missing_match_or_minutes_count']==1
    assert r['sample_inconsistencies'][0]['min_by_minutes']==8
    base['liveTournamentStats']['2026/27']['1'][0]['stats']['matches']=14
    assert audit(base)['inconsistent_rows']==0
    print('Match/fixture coherence audit PASS')

if __name__=='__main__':
    import sys
    if '--self-test' in sys.argv:
        selftest()
    else:
        text=SITE.read_text(encoding='utf-8')
        found=re.search(r'<script id="embeddedData" type="application/json">(.*?)</script>',text,re.S)
        if not found:raise RuntimeError('Missing embedded registry')
        report=audit(json.loads(found.group(1)))
        OUT.parent.mkdir(parents=True,exist_ok=True)
        OUT.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
        print('Match coherence: checked',report['tournament_rows_checked'],
              'sourced tournament rows;',report['inconsistent_rows'],
              'rows with contradictory games and minutes;',
              report['rows_missing_match_or_minutes_count'],
              'rows lacking complete appearance count or minutes')
