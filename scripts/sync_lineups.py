#!/usr/bin/env python3
"""Backfill verified starting-XI counts from PitchAPI lineups.

GET /matches/{id}/players does not include starts. Confirmed lineups provide
a separate source. Never treat a predicted lineup or an unavailable lineup
as evidence of zero starts. Backfill is incremental and persists to pitchapi.
"""
from __future__ import annotations
import datetime as dt
import json,os,pathlib,re,time,urllib.error
from sync_pitchapi import OUT,get

def enrich_from_lineup(match,lineup):
    if not isinstance(lineup,dict):return 0
    home,away=lineup.get('home') or {},lineup.get('away') or {}
    if home.get('confirmed') is not True or away.get('confirmed') is not True:
        return 0
    starters=set()
    for side in (home,away):
        for player in side.get('starters') or []:
            if isinstance(player,dict) and re.fullmatch(r'p_[A-Za-z0-9]{6}',str(player.get('player_id') or '')):
                starters.add(player['player_id'])
    # A match must have plausible real starting XIs for both sides before
    # we use it as evidence of a non-start or a zero.
    if len(starters)<16:return 0
    count=0
    for row in match.get('players') or []:
        pid=row.get('pitch_id')
        if not pid or not isinstance(row.get('stats'),dict):continue
        row['stats']['starts']=1 if pid in starters else 0
        row['starts_source']='PitchAPI confirmed starting XI'
        count+=1
    if count:
        match['lineup_confirmed']=True
        match['lineup_observed_players']=count
        match['lineup_source']='https://pitchapi.dev/'
    return count

def candidates(cache,now):
    priority={'2026/27':0,'2026':1,'2025/26':2,'2025':3,'2024/25':4,'2024':5}
    matches=[]
    for mid,match in (cache.get('matches') or {}).items():
        if not isinstance(match,dict) or not match.get('players'):
            continue
        if not re.fullmatch(r'm_[A-Za-z0-9]{6}',str(mid)):continue
        if match.get('lineup_confirmed'):continue
        try:
            last=dt.datetime.fromisoformat(str(match.get('lineup_checked_at') or '').replace('Z','+00:00'))
            if last.tzinfo is None:last=last.replace(tzinfo=dt.timezone.utc)
        except (ValueError,TypeError):
            last=now-dt.timedelta(days=15)
        if now-last<dt.timedelta(days=14):continue
        matches.append((priority.get(str(match.get('season')),20),
                        -(int(str(match.get('date') or '0000')[:4]) if str(match.get('date') or '')[:4].isdigit() else 0),
                        mid))
    # Fair rotation by season: current is first; missing older games continue
    # automatically on future runs, not all in one provider burst.
    return [mid for _,_,mid in sorted(matches)]

def sync():
    key=os.getenv('PITCHAPI_KEY','').strip()
    if not key:
        if os.getenv('PITCHAPI_REQUIRED')=='1':
            raise RuntimeError('PITCHAPI_KEY is required to load real starting XIs')
        print('No PITCHAPI_KEY: leaving saved starts unchanged')
        return
    cache=json.loads(OUT.read_text(encoding='utf-8'))
    now=dt.datetime.now(dt.timezone.utc)
    budget=max(1,min(int(os.getenv('PITCHAPI_LINEUP_BUDGET','550')),2500))
    checked=confirmed=matched=0
    errors=[]
    for mid in candidates(cache,now)[:budget]:
        match=cache['matches'][mid]
        try:
            obj=get('/matches/'+mid+'/lineups',key)
            checked+=1
            observed=enrich_from_lineup(match,obj)
            if observed:confirmed+=1;matched+=observed
            match['lineup_checked_at']=dt.datetime.now(dt.timezone.utc).isoformat(timespec='seconds')
        except urllib.error.HTTPError as exc:
            errors.append(str(mid)+': HTTP '+str(exc.code))
            if exc.code in (401,403,429):
                if exc.code in (401,403):raise RuntimeError('PitchAPI lineup access denied') from exc
                break
        except (ValueError,RuntimeError,OSError) as exc:
            errors.append(str(mid)+': '+type(exc).__name__)
        time.sleep(max(.08,min(2.0,float(os.getenv('PITCHAPI_PAUSE','0.18')))))
    cache['lineup_sync_at']=dt.datetime.now(dt.timezone.utc).isoformat(timespec='seconds')
    cache['lineup_refresh_stats']={'checked':checked,'confirmed_matches':confirmed,
         'player_start_flags_set':matched,'remaining':len(candidates(cache,dt.datetime.now(dt.timezone.utc))),
         'errors':errors[:25]}
    temp=OUT.with_suffix('.lineups.tmp')
    temp.write_text(json.dumps(cache,ensure_ascii=False,separators=(',',':'))+'\n',encoding='utf-8')
    temp.replace(OUT)
    print('Confirmed lineups:',confirmed,'matched player starts:',matched,
          'remaining:',cache['lineup_refresh_stats']['remaining'],'errors:',len(errors))

def self_test():
    match={'players':[{'pitch_id':'p_ABC123','stats':{'minutes':90}},
        {'pitch_id':'p_DEF456','stats':{'minutes':30}}]}
    home={'confirmed':True,'starters':[{'player_id':'p_ABC123'}]+
          [{'player_id':'p_ABC'+str(i).zfill(3)} for i in range(10)]}
    away={'confirmed':True,'starters':[{'player_id':'p_XYZ'+str(i).zfill(3)} for i in range(11)]}
    assert enrich_from_lineup(match,{'home':dict(home,confirmed=False),'away':away})==0
    assert match['players'][0]['stats'].get('starts') is None
    assert enrich_from_lineup(match,{'home':home,'away':away})==2
    assert match['players'][0]['stats']['starts']==1
    assert match['players'][1]['stats']['starts']==0
    now=dt.datetime(2026,11,22,tzinfo=dt.timezone.utc)
    old={'matches':{'m_ABC123':dict(match,season='2026/27',date='2026-11-01',lineup_confirmed=False),
                    'm_DEF456':dict(match,season='2025/26',date='2025-10-01',lineup_confirmed=False)}}
    assert candidates(old,now)==['m_ABC123','m_DEF456']
    print('PitchAPI confirmed lineup parser and incremental starts tests PASS')

if __name__=='__main__':
    import sys
    if '--self-test' in sys.argv:self_test()
    else:sync()
