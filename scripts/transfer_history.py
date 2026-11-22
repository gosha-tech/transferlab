#!/usr/bin/env python3
"""Verified transfers and strictly pre-deal TransferLab valuations.

Do not treat a present-day estimate as a prediction made before a transfer.
Fees come from dated sources and remain reported values unless the selling or
buying club explicitly discloses exact consideration.
"""
from __future__ import annotations
from collections import defaultdict
import datetime as dt
import json
import pathlib
import re
from player_competitions import norm
from sync_pitchapi import team_norm

ROOT=pathlib.Path(__file__).resolve().parents[1]
MANIFEST=ROOT/'data'/'verified_transfers.json'
SNAPSHOTS=ROOT/'data'/'valuation_forecast_snapshots.json'
PROFILES=ROOT/'data'/'profile_enrichment.json'

def load(path):
    try:
        return json.loads(path.read_text(encoding='utf-8')) if path.exists() else {}
    except (OSError,ValueError):
        return {}

def day(value):
    s=str(value or '')[:10]
    if not re.fullmatch(r'20\d{2}-\d{2}-\d{2}',s):
        return None
    try:
        dt.date.fromisoformat(s)
    except ValueError:
        return None
    return s

def before_transfer(history,pid,deal_date,from_club,max_age_days=45):
    """Find a real prediction strictly BEFORE the deal, never post-deal."""
    winner=None
    deal=dt.date.fromisoformat(deal_date)
    for snapshot in history.get('snapshots') or []:
        captured=day(snapshot.get('as_of'))
        if not captured or not captured<deal_date:continue
        if (deal-dt.date.fromisoformat(captured)).days>max_age_days:continue
        prediction=(snapshot.get('forecasts') or {}).get(str(pid))
        if not isinstance(prediction,dict):continue
        if team_norm(prediction.get('club'))!=team_norm(from_club):continue
        amount=prediction.get('eur_m')
        if not isinstance(amount,(int,float)) or isinstance(amount,bool) or not 0<amount<=500:continue
        if not winner or captured>winner['as_of']:
            winner={'as_of':captured,'eur_m':round(float(amount),2),
                'model_version':str(snapshot.get('model_version') or 'undated-model'),
                'model_commit':str(snapshot.get('model_commit') or ''),
                'rating_index':prediction.get('index')}
    return winner

def attach(players,transfers,history,profiles,now=None):
    now=now or dt.date.today()
    by_name=defaultdict(list)
    for p in players:
        by_name[norm(p.get('name'))].append(p)
    by_tm={}
    for p in players:
        profile=(profiles.get('profiles') or {}).get(str(p.get('id'))) or {}
        tm=str(profile.get('tm_player_id') or '')
        if tm:
            by_tm.setdefault(tm,[]).append(p)
    results={}
    accepted=0; rejected=0
    for item in (transfers.get('transfers') or []):
        name=str(item.get('player_name') or '')
        tm=str(item.get('tm_player_id') or '')
        candidates=by_tm.get(tm,[]) if tm else by_name.get(norm(name),[])
        if len(candidates)!=1 or norm(candidates[0].get('name'))!=norm(name):
            rejected+=1;continue
        player=candidates[0]
        event_day=day(item.get('date'))
        fee=item.get('reported_fee_eur_m')
        from_club=str(item.get('from_club') or '')
        to_club=str(item.get('to_club') or '')
        source=str(item.get('fee_source') or '')
        official=str(item.get('official_transfer_source') or '')
        if (not event_day or dt.date.fromisoformat(event_day)>now or
            not isinstance(fee,(int,float)) or isinstance(fee,bool) or
            not 0<float(fee)<=500 or not from_club or not to_club or
            not source.startswith('https://') or not official.startswith('https://') or
            item.get('status')!='completed'):
            rejected+=1;continue
        previous=before_transfer(history,player['id'],event_day,from_club)
        results.setdefault(str(player['id']),[]).append({
            'event_id':str(item.get('id') or ''),
            'date':event_day,'from_club':from_club,'to_club':to_club,
            'reported_fee_eur_m':round(float(fee),2),
            'fee_status':str(item.get('fee_status') or 'reported'),
            'fee_qualifier':str(item.get('fee_qualifier') or ''),
            'fee_source':source,'official_source':official,
            'fee_structure_source':str(item.get('fee_structure_source') or ''),
            'guaranteed_gbp_m':item.get('guaranteed_gbp_m'),
            'maximum_addons_gbp_m':item.get('maximum_addons_gbp_m'),
            'pre_transfer_prediction':previous})
        accepted+=1
    for rows in results.values():
        rows.sort(key=lambda r:r['date'],reverse=True)
    return results,{'accepted':accepted,'rejected':rejected,
                    'with_genuine_pre_transfer_forecast':sum(
                        r['pre_transfer_prediction'] is not None for rows in results.values() for r in rows)}

def selftest():
    people=[{'id':'p1','name':'Crysencio Summerville','team':'Al-Hilal'}]
    profiles={'profiles':{'p1':{'tm_player_id':'474701'}}}
    deal={'transfers':[{'id':'s','player_name':'Crysencio Summerville',
        'tm_player_id':'474701','date':'2026-07-24','from_club':'West Ham United',
        'to_club':'Al-Hilal','reported_fee_eur_m':70,
        'fee_source':'https://example.com/report',
        'official_transfer_source':'https://example.com/official',
        'status':'completed'}]}
    history={'snapshots':[
        {'as_of':'2026-07-20','model_version':'v1',
         'forecasts':{'p1':{'club':'West Ham United','eur_m':30,'index':79}}},
        {'as_of':'2026-07-24','model_version':'v2',
         'forecasts':{'p1':{'club':'Al-Hilal','eur_m':80,'index':89}}},
        {'as_of':'2026-07-25','model_version':'v3',
         'forecasts':{'p1':{'club':'Al-Hilal','eur_m':90,'index':95}}}]}
    rows,info=attach(people,deal,history,profiles,dt.date(2026,11,22))
    assert info['with_genuine_pre_transfer_forecast']==1
    assert rows['p1'][0]['pre_transfer_prediction']['eur_m']==30
    assert rows['p1'][0]['pre_transfer_prediction']['as_of']=='2026-07-20'
    rows,_=attach(people,deal,{'snapshots':history['snapshots'][1:]},profiles,dt.date(2026,11,22))
    assert rows['p1'][0]['pre_transfer_prediction'] is None
    duplicate=[people[0],dict(people[0],id='p2')]
    rows,info=attach(duplicate,deal,history,profiles,dt.date(2026,11,22))
    assert not rows and info['rejected']==1
    print('Transfer evidence: identity checks + no post-deal hindsight PASS')

if __name__=='__main__':
    selftest()
