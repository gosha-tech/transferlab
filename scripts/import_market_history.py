#!/usr/bin/env python3
"""Five-year observed player value history from the frozen 2026 Transfermarkt archive.

Only source-observed market valuations are included. There is no extrapolation,
no replacement of missing observations and NO claim that June 2026 is current.
Profiles are joined by the verified Transfermarkt player ID, never by name.
"""
from __future__ import annotations
import argparse
from collections import defaultdict
import csv
import datetime as dt
import gzip
import io
import json
import pathlib
import urllib.request

ROOT=pathlib.Path(__file__).resolve().parents[1]
PROFILES=ROOT/'data'/'profile_enrichment.json'
CACHE=ROOT/'data'/'market_history.json'
SOURCE='https://pub-e682421888d945d684bcae8890b0ec20.r2.dev/data/player_valuations.csv.gz'
ATTRIBUTION='https://github.com/dcaribou/transfermarkt-datasets'
# Frozen snapshot does NOT contain later market observations. Date is
# always displayed in charts alongside each value.
SOURCE_LAST_REPORTED='2026-06-12'
WINDOW_END='2026-11-22'
WINDOW_START='2021-11-22'
MAX_POINTS_PER_PLAYER=120

def parse_record(row):
    tm=str(row.get('player_id') or '').strip()
    day=str(row.get('date') or '').strip()[:10]
    if not tm.isdigit() or not (WINDOW_START<=day<=WINDOW_END):
        return None
    try:
        if dt.date.fromisoformat(day).isoformat()!=day:return None
        euros=int(float(row.get('market_value_in_eur')))
    except (TypeError,ValueError,OverflowError):
        return None
    if euros<=0 or euros>500_000_000:return None
    return tm,day,euros

def index_profiles(profile_cache):
    ix=defaultdict(list)
    for player_id,entry in (profile_cache.get('profiles') or {}).items():
        tm=str(entry.get('tm_player_id') or '')
        if tm.isdigit() and entry.get('match_confidence') in ('name+club','unique-name-only'):
            ix[tm].append(str(player_id))
    # Reject a TM identity linked to two TransferLab records.
    return {tm:pid[0] for tm,pid in ix.items() if len(pid)==1}

def collect(records,identities):
    data=defaultdict(dict)
    for row in records:
        parsed=parse_record(row)
        if parsed is None:continue
        tm,day,euros=parsed
        player_id=identities.get(tm)
        if player_id:
            data[player_id][day]=euros
    out={}
    for player_id,by_day in data.items():
        events=sorted(by_day.items())
        # All real dated observations retained. Most careers have only a few
        # per season; the cap prevents pathological chart payloads.
        if len(events)>MAX_POINTS_PER_PLAYER:
            events=events[-MAX_POINTS_PER_PLAYER:]
        out[player_id]=[[day,round(euros/1_000_000,5)] for day,euros in events]
    return out

def stream_rows():
    req=urllib.request.Request(SOURCE,headers={'User-Agent':'TransferLab/5.3 (historical market data)'})
    resp=urllib.request.urlopen(req,timeout=120)
    archive=gzip.GzipFile(fileobj=resp)
    with resp,archive,io.TextIOWrapper(archive,encoding='utf-8-sig',newline='') as reader:
        for row in csv.DictReader(reader):
            yield row

def save(data):
    if not data:raise RuntimeError('No safely joined valuations; refusing to erase cache')
    covered_two=sum(len(x)>=2 for x in data.values())
    latest=max((point[0] for values in data.values() for point in values),default=None)
    payload={'source':ATTRIBUTION,'download':SOURCE,
             'source_status':'Frozen historical market observations; NOT current prices',
             'source_last_reported':SOURCE_LAST_REPORTED,
             'latest_observation':latest,
             'window_start':WINDOW_START,'window_end':WINDOW_END,
             'units':'EUR millions',
             'retrieved_at':dt.datetime.now(dt.timezone.utc).isoformat(timespec='seconds'),
             'players_with_observations':len(data),
             'players_with_two_or_more':covered_two,'series':data}
    CACHE.parent.mkdir(parents=True,exist_ok=True)
    tmp=CACHE.with_suffix('.tmp')
    tmp.write_text(json.dumps(payload,ensure_ascii=False,separators=(',',':'))+'\n',encoding='utf-8')
    tmp.replace(CACHE)
    print('Five-year actual market valuations:',len(data),'profiles; >=2:',covered_two,
          'latest source observation',latest)
    return payload

def self_test():
    profiles={'profiles':{'1':{'tm_player_id':'100','match_confidence':'name+club'},
                          '2':{'tm_player_id':'101','match_confidence':'unique-name-only'},
                          '3':{'tm_player_id':'200','match_confidence':'name+club'},
                          '4':{'tm_player_id':'200','match_confidence':'name+club'}}}
    ix=index_profiles(profiles)
    assert ix=={'100':'1','101':'2'}
    rows=[{'player_id':'100','date':'2021-11-21','market_value_in_eur':'1000000'},
          {'player_id':'100','date':'2022-05-09','market_value_in_eur':'10000000'},
          {'player_id':'100','date':'2024-03-19','market_value_in_eur':'30000000'},
          {'player_id':'100','date':'2024-03-19','market_value_in_eur':'35000000'},
          {'player_id':'101','date':'2025-06-10','market_value_in_eur':'3000000'},
          {'player_id':'200','date':'2025-06-10','market_value_in_eur':'9999999999'}]
    result=collect(rows,ix)
    assert result=={'1':[['2022-05-09',10.0],['2024-03-19',35.0]],
                    '2':[['2025-06-10',3.0]]},result
    print('Historical 5-year valuation identity and date tests PASS')

def main():
    cli=argparse.ArgumentParser()
    cli.add_argument('--download',action='store_true')
    cli.add_argument('--self-test',action='store_true')
    args=cli.parse_args()
    if args.self_test:return self_test()
    if not args.download: return
    if CACHE.exists():
        cached=json.loads(CACHE.read_text(encoding='utf-8'))
        if cached.get('series'):
            print('Retained frozen five-year value history:',len(cached['series']))
            return
    profile=json.loads(PROFILES.read_text(encoding='utf-8'))
    identities=index_profiles(profile)
    if not identities:raise RuntimeError('Verified Transfermarkt identities unavailable')
    save(collect(stream_rows(),identities))
if __name__=='__main__':main()
