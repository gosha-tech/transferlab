#!/usr/bin/env python3
"""Scheduled PitchAPI freshness check: fail the Action instead of showing a fake live badge."""
from __future__ import annotations
import datetime as dt
import json
import pathlib
import sys

PATH=pathlib.Path(__file__).resolve().parents[1]/'data'/'pitchapi.json'

def validate(snapshot,now=None):
    now=now or dt.datetime.now(dt.timezone.utc)
    if not snapshot.get('key_configured'):
        raise RuntimeError('PITCHAPI_KEY missing: no daily statistics refresh')
    raw=str(snapshot.get('updated_at') or '')
    try:
        updated=dt.datetime.fromisoformat(raw.replace('Z','+00:00'))
        if updated.tzinfo is None:
            raise ValueError('Missing timezone')
    except (ValueError,TypeError) as exc:
        raise RuntimeError('Missing timestamp of successful PitchAPI sync') from exc
    lag=(now-updated).total_seconds()
    if lag < -300 or lag > 3*3600:
        raise RuntimeError('PitchAPI last successful sync is older than 3 hours')
    coverage=snapshot.get('season_player_coverage') or {}
    count=int(coverage.get('2026/27') or 0)
    if count < 100:
        raise RuntimeError('Current player statistics missing: only '+str(count)+' matched players')
    matches=snapshot.get('matches') or {}
    if not any(m.get('season')=='2026/27' and m.get('players')
               for m in matches.values() if isinstance(m,dict)):
        raise RuntimeError('No current 2026/27 match-player rows')
    return {'last_sync':raw,'current_season_pitchapi_players':count,
            'total_cached_matches':len(matches),
            'backfill_incomplete':bool(snapshot.get('backfill_incomplete'))}

def selftest():
    now=dt.datetime(2026,11,22,7,30,tzinfo=dt.timezone.utc)
    ok={'key_configured':True,'updated_at':'2026-11-22T07:29:00+00:00',
        'season_player_coverage':{'2026/27':300},
        'matches':{'m_AB12cd':{'season':'2026/27','players':[{'player_id':'10'}]}}}
    assert validate(ok,now)['current_season_pitchapi_players']==300
    for patch in ({'key_configured':False},
                  {'updated_at':'2026-11-19T07:29:00+00:00'},
                  {'season_player_coverage':{'2026/27':0}},
                  {'matches':{}}):
        stale=dict(ok,**patch)
        try:
            validate(stale,now)
        except RuntimeError:
            continue
        raise AssertionError('Stale or empty refresh was incorrectly accepted')
    print('PitchAPI scheduled refresh freshness tests PASS')

if __name__=='__main__':
    if '--self-test' in sys.argv:
        selftest()
    else:
        result=validate(json.loads(PATH.read_text(encoding='utf-8')))
        print('Scheduled current-season player stat refresh verified:',result)
