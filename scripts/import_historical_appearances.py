#!/usr/bin/env python3
"""Historical minutes/goals/assists per competition for matching TransferLab players.

Uses a July-2026 *archive*, NOT live data. Joins only through Transfermarkt IDs
which were obtained by conservative profile identity matching. Rows from the
same match never count twice.
"""
from __future__ import annotations
import collections,csv,datetime as dt,gzip,io,json,pathlib,urllib.request

ROOT=pathlib.Path(__file__).resolve().parents[1]
CACHE=ROOT/'data'/'historical_stats.json'
PROFILES=ROOT/'data'/'profile_enrichment.json'
AS_OF='2026-06-28'
BASE='https://pub-e682421888d945d684bcae8890b0ec20.r2.dev/data/'
KNOWN={'GB1':'Premier League','ES1':'La Liga','L1':'Bundesliga','IT1':'Serie A',
       'FR1':'Ligue 1','PO1':'Primeira Liga','BE1':'Belgian Pro League',
       'TR1':'Süper Lig','SA1':'Saudi Pro League','MLS1':'MLS',
       'CL':'UEFA Champions League','EL':'UEFA Europa League',
       'ECL':'UEFA Conference League','DFB':'DFB Pokal','FAC':'FA Cup',
       'CGB':'EFL Cup','CDR':'Copa del Rey'}
CALI={'MLS1','FIWC','WMLS','US1'}
def season_for(date,comp):
    day=dt.date.fromisoformat(date[:10])
    if comp in CALI:return str(day.year)
    start=day.year if day.month>=7 else day.year-1
    return str(start)+'/'+str((start+1)%100).zfill(2)
def parse_count(v):
    try:return max(0,int(v))
    except (TypeError,ValueError):return 0
def stream_rows(url):
    req=urllib.request.Request(url,headers={'User-Agent':'TransferLab/5.2'})
    resp=urllib.request.urlopen(req,timeout=110)
    file=gzip.GzipFile(fileobj=resp)
    with resp,file,io.TextIOWrapper(file,encoding='utf-8-sig',newline='') as reader:
        for row in csv.DictReader(reader):yield row
def competition_names():
    names=KNOWN.copy()
    try:
        for r in stream_rows(BASE+'competitions.csv.gz'):
            key=(r.get('competition_id') or '').strip()
            if key and r.get('name'):names[key]=r['name']
    except Exception as exc:
        print('Competition labels fallback:',type(exc).__name__)
    return names
def aggregate(rows,player_ids,compnames):
    # Indices are immutable player identifiers, not fuzzy name matching.
    accumulator={}
    unique=set()
    for r in rows:
        tm=(r.get('player_id') or '').strip()
        ids=player_ids.get(tm)
        if not ids:continue
        date=r.get('date') or ''
        comp=(r.get('competition_id') or '').strip()
        if not comp or not date or date[:4]<'2023' or date[:4]>'2026':continue
        try:season=season_for(date,comp)
        except ValueError:continue
        if season not in ('2023/24','2024/25','2025/26','2024','2025','2026'):continue
        game=(r.get('game_id') or r.get('appearance_id') or '').strip()
        if not game:continue
        for id in ids:
            key=(season,id,comp)
            seen=(game,tm)
            if (key,seen) in unique:continue
            unique.add((key,seen))
            o=accumulator.setdefault(key,{'id':'tm-'+comp,'name':compnames.get(comp,comp),
                                          'source':'historical_appearances','source_as_of':AS_OF,
                                          'stats':{'matches':0,'minutes':0,'goals':0,'assists':0,
                                                   'yellow_cards':0,'red_cards':0}})
            g=o['stats']
            g['matches']+=1
            g['minutes']+=parse_count(r.get('minutes_played'))
            g['goals']+=parse_count(r.get('goals'))
            g['assists']+=parse_count(r.get('assists'))
            g['yellow_cards']+=parse_count(r.get('yellow_cards'))
            g['red_cards']+=parse_count(r.get('red_cards'))
    by_season={}
    for (season,id,_),value in accumulator.items():
        by_season.setdefault(season,{}).setdefault(id,[]).append(value)
    for pool in by_season.values():
        for records in pool.values():records.sort(key=lambda r:r['name'])
    return by_season
def index_ids():
    if not PROFILES.exists():return {}
    cache=json.loads(PROFILES.read_text(encoding='utf-8'))
    out=collections.defaultdict(list)
    for pid,data in cache.get('profiles',{}).items():
        tm=(data.get('tm_player_id') or '').strip()
        if tm.isdigit():out[tm].append(pid)
    return out
def run_download():
    ids=index_ids()
    if not ids:
        print('Historical appearances import: no safely identified Transfermarkt IDs yet')
        return
    labels=competition_names()
    data=aggregate(stream_rows(BASE+'appearances.csv.gz'),ids,labels)
    if not data:raise RuntimeError('No supported historical appearances found')
    total=sum(len(v) for pool in data.values() for v in pool.values())
    obj={'source':'dcaribou/transfermarkt-datasets appearances.csv.gz',
         'as_of':AS_OF,'imported_at':dt.datetime.now(dt.timezone.utc).isoformat(),
         'covered_players':len({pid for pool in data.values() for pid in pool}),
         'competition_player_seasons':total,'by_season':data}
    CACHE.parent.mkdir(parents=True,exist_ok=True)
    temp=CACHE.with_suffix('.tmp')
    temp.write_text(json.dumps(obj,ensure_ascii=False,separators=(',',':'))+'\n',encoding='utf-8')
    temp.replace(CACHE)
    print('Imported historical performance:',obj['covered_players'],'players,',total,'competition-player-seasons')
def self_test():
    ids={'99':['seed-hakimi'],'100':['seed-other']}
    rows=[
      {'player_id':'99','game_id':'a','date':'2025-11-12','competition_id':'CL',
       'minutes_played':'90','goals':'1','assists':'1'},
      {'player_id':'99','game_id':'a','date':'2025-11-12','competition_id':'CL',
       'minutes_played':'90','goals':'1','assists':'1'}, # duplicate should not count
      {'player_id':'99','game_id':'b','date':'2025-11-20','competition_id':'FR1',
       'minutes_played':'75','goals':'0','assists':'2'},
      {'player_id':'100','game_id':'c','date':'2024-09-12','competition_id':'GB1',
       'minutes_played':'45','goals':'0','assists':'0'}]
    obj=aggregate(rows,ids,KNOWN)
    v=obj['2025/26']['seed-hakimi'];assert len(v)==2
    assert sum(x['stats']['goals'] for x in v)==1
    assert sum(x['stats']['minutes'] for x in v)==165
    assert len(obj['2024/25']['seed-other'])==1
    print('Historical match dedup and season/competition grouping passed')
def main():
    import argparse
    parser=argparse.ArgumentParser()
    parser.add_argument('--self-test',action='store_true')
    parser.add_argument('--download',action='store_true')
    args=parser.parse_args()
    if args.self_test:self_test()
    elif args.download:
        try:run_download()
        except (OSError,ValueError,RuntimeError) as exc:
            print('Historical dataset unavailable: using previous cache, error:',repr(exc)[:240])
if __name__=='__main__':main()
