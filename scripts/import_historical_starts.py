#!/usr/bin/env python3
"""Backfill observed starting lineups for archival seasons without guessing.

The frozen dataset holds game_lineups (starters + substitutes) and player
appearances. A full-season starts count is reported only if every appearance
has a lineup record; otherwise a confirmed lower bound is stored.
"""
from __future__ import annotations
import argparse,collections,datetime as dt,json,pathlib
from import_historical_appearances import (
    BASE,ROOT,PROFILES,stream_rows,season_for
)
OUT=ROOT/'data/historical_starts.json'
SEASONS={'2023/24','2024/25','2025/26','2024','2025','2026'}
def ids_map():
    profiles=json.loads(PROFILES.read_text(encoding='utf-8'))
    result=collections.defaultdict(list)
    for pid,profile in profiles.get('profiles',{}).items():
        tm=str(profile.get('tm_player_id') or '')
        if tm.isdigit() and profile.get('match_confidence') in ('name+club','unique-name-only'):
            result[tm].append(pid)
    return {pid:pids[0] for pid,pids in result.items() if len(pids)==1}

def summarize(lineups,appearances,matched_ids):
    lineup_types=collections.defaultdict(set)
    valid_types={'starting_lineup','substitutes','substitute','starting','substitutes_bench'}
    for row in lineups:
        tm=str(row.get('player_id') or '')
        match=str(row.get('game_id') or '')
        if tm not in matched_ids or not match:continue
        kind=str(row.get('type') or '').lower().replace(' ','_')
        if kind in valid_types:
            lineup_types[(tm,match)].add('start' if kind in ('starting_lineup','starting') else 'bench')
    data=collections.defaultdict(lambda:{'matches':set(),'observed':set(),'started':set()})
    for row in appearances:
        tm=str(row.get('player_id') or '')
        if tm not in matched_ids:continue
        match=str(row.get('game_id') or '')
        comp=str(row.get('competition_id') or '')
        date=str(row.get('date') or '')
        if not match or not comp or not date:continue
        try:season=season_for(date,comp)
        except ValueError:continue
        if season not in SEASONS:continue
        key=(season,matched_ids[tm],'tm-'+comp)
        group=data[key]
        group['matches'].add(match)
        types=lineup_types.get((tm,match)) or set()
        if types:
            group['observed'].add(match)
            if 'start' in types:group['started'].add(match)
    seasons=collections.defaultdict(lambda:collections.defaultdict(dict))
    for (season,pid,comp),group in data.items():
        observed=len(group['observed'])
        if not observed:continue
        matches=len(group['matches'])
        counts={'starts_verified_matches':observed,
                'starts_source':'Transfermarkt archived game_lineups'}
        if observed==matches:
            counts['starts']=len(group['started'])
        else:
            counts['starts_min']=len(group['started'])
        seasons[season][pid][comp]=counts
    return {season:dict(rows) for season,rows in seasons.items()}
def download():
    if OUT.exists():
        old=json.loads(OUT.read_text(encoding='utf-8'))
        if old.get('by_season'):
            print('Frozen historical starts retained:',old.get('matched_player_seasons'))
            return
    ids=ids_map()
    if not ids:raise RuntimeError('No verified identities for historical lineups')
    rows=summarize(stream_rows(BASE+'game_lineups.csv.gz'),
                   stream_rows(BASE+'appearances.csv.gz'),ids)
    if not rows:raise RuntimeError('No historical starting-XI observations matched')
    count=sum(len(comp) for ids in rows.values() for comp in ids.values())
    payload={'source':'dcaribou/transfermarkt-datasets game_lineups.csv.gz',
             'source_as_of':'2026-06','matched_player_seasons':count,
             'imported_at':dt.datetime.now(dt.timezone.utc).isoformat(),
             'by_season':rows}
    OUT.parent.mkdir(exist_ok=True,parents=True)
    tmp=OUT.with_suffix('.tmp')
    tmp.write_text(json.dumps(payload,ensure_ascii=False,separators=(',',':'))+'\n',encoding='utf-8')
    tmp.replace(OUT)
    print('Historical verified starts imported:',count)
def selftest():
    ids={'12':'p1'}
    lines=[
       {'player_id':'12','game_id':'1','type':'starting_lineup'},
       {'player_id':'12','game_id':'2','type':'substitutes'},
       {'player_id':'12','game_id':'3','type':'starting_lineup'}]
    games=[{'player_id':'12','game_id':g,'date':'2025-11-21','competition_id':'CL'} for g in ('1','2','3')]
    result=summarize(lines,games,ids)
    x=result['2025/26']['p1']['tm-CL']
    assert x['starts']==2 and x['starts_verified_matches']==3,x
    games.append({'player_id':'12','game_id':'4','date':'2025-11-21','competition_id':'CL'})
    x=summarize(lines,games,ids)['2025/26']['p1']['tm-CL']
    assert x['starts_min']==2 and 'starts' not in x,x
    print('Historical match lineup counting and missing-coverage tests PASS')
if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--download',action='store_true')
    parser.add_argument('--self-test',action='store_true')
    args=parser.parse_args()
    if args.self_test:selftest()
    elif args.download:download()
