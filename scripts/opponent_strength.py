#!/usr/bin/env python3
"""2026/27 opponent strength from identifiable UEFA matches only.

A five-season UEFA club coefficient is not a match result or an Elo score.
It is used as a conservative dated opponent-strength *proxy*. No documented
opponent => no bonus. Pre-2026/27 matches are deliberately excluded because
this 2026 coefficient snapshot would leak future results into prior seasons.
"""
import json
import pathlib
import unicodedata
import re
from collections import defaultdict
from sync_pitchapi import team_norm

ROOT=pathlib.Path(__file__).resolve().parents[1]
COEFFICIENTS=ROOT/'data'/'uefa_coefficients_2026.json'
ALIASES={
 'bayernmunich':'bayernmunchen','fcbayernmunchen':'bayernmunchen',
 'parissg':'parissaintgermain','psg':'parissaintgermain',
 'intermilan':'inter','internazionale':'inter','fcinternazionale':'inter',
 'mancity':'manchestercity','manchestercityfc':'manchestercity',
 'fcbarcelona':'barcelona','barcelonafc':'barcelona',
 'sportinglisbon':'sportingcp','sportingcplisbon':'sportingcp',
 'atleticodemadrid':'atleticomadrid',
 'tottenham':'tottenhamhotspur',
 'porto':'fcporto','olympiquedemarseille':'marseille',
 'olympiquelyonnais':'olympiquelyon',
 'losclille':'lille',
 'asroma':'roma','asmonaco':'monaco',
 'clubbruggekv':'clubbrugge',
 'redbullsalzburg':'salzburg','fcsalzburg':'salzburg',
 'viktoriaplzen':'viktoriaplzen','kobenhavn':'copenhagen',
 'fckobenhavn':'copenhagen',
 'psveindhoven':'psveindhoven','psv':'psveindhoven',
 'galatasaraysk':'galatasaray','olympiakospiraeus':'olympiacos',
 'bragasc':'braga','sportingbraga':'braga',
 'rbslavia':'slaviaprague','slaviapraha':'slaviaprague',
 'bodoglimt':'bodoglimt',
}
def club_key(value):
    text=unicodedata.normalize('NFKD',str(value or '').casefold())
    key=re.sub(r'[^a-z0-9]','', ''.join(x for x in text if not unicodedata.combining(x)))
    return ALIASES.get(key,key)

def evaluate(players,matches,coefficients):
    points={club_key(name):float(value) for name,value in (coefficients.get('clubs') or {}).items()
        if isinstance(value,(float,int)) and not isinstance(value,bool) and 0<float(value)<=200}
    valid_ids={str(p['id']) for p in players}
    aggregate=defaultdict(lambda:{'weighted':0.0,'minutes':0.0,'matches':0,'opponents':set()})
    reviewed=set()
    for match in (matches or {}).values():
        if not isinstance(match,dict) or match.get('season')!='2026/27':continue
        if str(match.get('competition_id')) not in ('2','3','848'):continue
        entries=match.get('players') or []
        if not isinstance(entries,list):continue
        home=str(match.get('home_team_name') or '')
        away=str(match.get('away_team_name') or '')
        teamnames={club_key(r.get('team')):r.get('team') for r in entries
                   if isinstance(r,dict) and r.get('team')}
        if not home or not away:
            if len(teamnames)!=2:continue
            home,away=list(teamnames.values())
        if club_key(home)==club_key(away):continue
        mid=str(match.get('id') or '')
        for row in entries:
            if not isinstance(row,dict):continue
            pid=str(row.get('player_id') or '')
            club=club_key(row.get('team'))
            if pid not in valid_ids or club not in (club_key(home),club_key(away)):
                continue
            opponent=away if club==club_key(home) else home
            val=points.get(club_key(opponent))
            if val is None:continue
            try:minutes=float((row.get('stats') or {}).get('minutes') or 0)
            except (TypeError,ValueError):continue
            if not 0<minutes<=130:continue
            fingerprint=(pid,mid)
            if fingerprint in reviewed:continue
            reviewed.add(fingerprint)
            item=aggregate[pid]
            item['minutes']+=minutes
            item['weighted']+=minutes*val
            item['matches']+=1
            item['opponents'].add(club_key(opponent))
    result={}
    for pid,data in aggregate.items():
        result[pid]={
            'minutes':round(data['minutes']),
            'matches':data['matches'],
            'average_uefa_coefficient':round(data['weighted']/data['minutes'],2),
            'opponents_count':len(data['opponents']),
            'rank_as_of':str(coefficients.get('as_of') or ''),
            'source':str(coefficients.get('source') or '')}
    return result

def selftest():
    coeff={'as_of':'2026-07-03','source':'https://example.com',
           'clubs':{'Real Madrid':144.5,'Lille':68.75}}
    rows={'one':{'id':'one','season':'2026/27','competition_id':2,
        'home_team_name':'Paris Saint-Germain','away_team_name':'Real Madrid',
        'players':[{'player_id':'x','team':'Paris Saint-Germain',
                    'stats':{'minutes':90}},
                   {'player_id':'y','team':'Real Madrid','stats':{'minutes':90}}]},
          'old':{'id':'old','season':'2025/26','competition_id':2,
        'home_team_name':'Paris Saint-Germain','away_team_name':'Real Madrid',
        'players':[{'player_id':'x','team':'Paris Saint-Germain',
                    'stats':{'minutes':90}}]}}
    evidence=evaluate([{'id':'x'},{'id':'y'}],rows,coeff)
    assert evidence['x']['average_uefa_coefficient']==144.5
    assert 'y' not in evidence and evidence['x']['minutes']==90
    assert evidence['x']['matches']==1
    assert club_key('FC Bayern München')==club_key('Bayern Munich')
    print('Opponent strength: verified 2026/27 fixtures only, no unknown opponent boost PASS')

if __name__=='__main__':
    selftest()
