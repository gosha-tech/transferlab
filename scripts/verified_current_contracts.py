#!/usr/bin/env python3
"""Attach independently verified current player contracts, without fabricating expiries.

Sources must verify the exact player and current team. The archival contract
field remains separately visible if a live official source is unavailable.
"""
import datetime as dt
import json
import pathlib
import re
from collections import defaultdict
from player_competitions import norm
from sync_pitchapi import team_norm

ROOT=pathlib.Path(__file__).resolve().parents[1]
MANIFEST=ROOT/'data'/'verified_current_contracts.json'

def apply(players,manifest):
    names=defaultdict(list)
    for p in players:
        names[norm(p.get('name'))].append(p)
    verified=skipped=0
    for entry in manifest.get('players') or []:
        candidates=names.get(norm(entry.get('name')),[])
        if len(candidates)!=1:
            skipped+=1
            continue
        p=candidates[0]
        source=str(entry.get('source_url') or '')
        club=str(entry.get('club') or '')
        expiry=str(entry.get('expires_on') or '')
        as_of=str(entry.get('verified_as_of') or '')
        if (not source.startswith('https://') or
            not club or team_norm(club)!=team_norm(p.get('team')) or
            not re.fullmatch(r'20\d{2}-\d{2}-\d{2}',expiry)):
            skipped+=1
            continue
        try:
            if dt.date.fromisoformat(expiry)<dt.date.today() or (
                as_of and dt.date.fromisoformat(as_of)>dt.date.today()):
                skipped+=1
                continue
        except ValueError:
            skipped+=1
            continue
        if p.get('contractUntilCurrent'):
            # Never replace newer club-certified evidence.
            continue
        p['contractUntilCurrent']=expiry
        p['contractSource']=source
        p['contractSourceAsOf']=as_of
        p['contractPrecision']='day_verified'
        verified+=1
    return {'added_current_verified':verified,'rejected_or_unmatched':skipped}

def selftest():
    ppl=[{'id':'a','name':'Nuno Mendes','team':'Paris Saint-Germain'},
         {'id':'b','name':'Another','team':'Arsenal'}]
    example={'players':[
        {'name':'Nuno Mendes','club':'Paris Saint-Germain','expires_on':'2029-06-30',
         'verified_as_of':'2026-11-22','source_url':'https://www.psg.fr/en/example'},
        {'name':'Another','club':'PSG','expires_on':'2028-06-30',
         'verified_as_of':'2026-11-22','source_url':'https://example.com'}]}
    report=apply(ppl,example)
    assert report['added_current_verified']==1 and report['rejected_or_unmatched']==1
    assert ppl[0]['contractUntilCurrent']=='2029-06-30' and 'contractUntilCurrent' not in ppl[1]
    print('Unique identity + verified current club contract checks PASS')
if __name__=='__main__':selftest()
