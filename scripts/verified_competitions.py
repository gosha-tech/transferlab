"""Join independently documented competition totals, avoiding duplicate match rows.

A sourced aggregate is not an inferred match report. Only exact unique player
name + club matches can attach it, and more recent real data always supersede it.
"""
from __future__ import annotations
import datetime as dt
import json
import pathlib
from collections import defaultdict
from sync_pitchapi import team_norm
from player_competitions import norm

ROOT=pathlib.Path(__file__).resolve().parents[1]
MANIFEST=ROOT/'data'/'verified_competition_totals.json'
SUPER_CUP_IDS={'uefa-super-cup','fr-super-cup','es-super-cup',
'it-super-cup','de-super-cup','pt-super-cup','tr-super-cup',
'bel-super-cup','sa-super-cup','nl-super-cup',
'fifa-intercontinental','fifa-club-world-cup'}
CUP_IDS=SUPER_CUP_IDS | {'45','48','143','137','81','66','cup-turkey',
'cup-portugal','cup-belgium','cup-saudi','cup-brazil','cup-netherlands',
'2','3','848'}

def add_verified_competitions(players,by_season,manifest):
    by_name=defaultdict(list)
    for p in players:
        by_name[norm(p.get('name'))].append(p)
    count=0
    provenance=[]
    for entry in manifest.get('players') or []:
        named=by_name.get(norm(entry.get('name')),[])
        if len(named)!=1:continue
        person=named[0]
        if team_norm(person.get('team'))!=team_norm(entry.get('club')):
            continue
        pid=str(person.get('id'))
        season=str(entry.get('season') or '')
        if season not in ('2024/25','2025/26','2026/27','2024','2025','2026'):
            continue
        for item in entry.get('competition_totals') or []:
            code=str(item.get('id') or '')
            if not code:continue
            stats=item.get('stats') or {}
            if int(stats.get('matches') or 0)<1 or int(stats.get('minutes') or 0)<1:
                continue
            rows=by_season.setdefault(season,{}).setdefault(pid,[])
            current=next((r for r in rows if str(r.get('id'))==code),None)
            # A later provider match cannot be erased by a 22 November 2026
            # sourced historical snapshot.
            last=str(current.get('last_match_date') or '')[:10] if current else ''
            if last and last>str(manifest.get('as_of') or '')[:10]:continue
            if current:
                existing=int((current.get('stats') or {}).get('matches') or 0)
                if existing>int(stats['matches']):continue
                # If current was already complete and accurate, avoid
                # needlessly replacing other provider-backed advanced stats.
                if (existing==int(stats['matches']) and
                    all((current.get('stats') or {}).get(k)==v for k,v in stats.items())):
                    continue
                current.clear()
            row={'id':item['id'],'name':item.get('name') or code,
                 'stats':dict(stats),'source':'externally_verified_competition_total',
                 'team_verified':True,'is_complete':False,'as_of':manifest.get('as_of'),
                 'last_match_date':item.get('last_match_date') or manifest.get('as_of'),
                 'matches_loaded':int(stats['matches']),
                 'source_url':manifest.get('source_primary'),
                 'verification':'published season-by-competition aggregate, not inferred fixture list'}
            if current is None:rows.append(row)
            else:current.update(row)
            count+=1
            provenance.append({'name':entry['name'],'competition':code,'matches':stats['matches']})
    return {'rows_verified':count,'source':manifest.get('source_primary'),
            'source_as_of':manifest.get('as_of'),'rows':provenance}

def self_test():
    people=[{'id':'a','name':'Achraf Hakimi','team':'Paris Saint-Germain'}]
    first={'players':[{'name':'Achraf Hakimi','club':'Paris Saint-Germain',
      'season':'2026/27','competition_totals':[
       {'id':61,'name':'Ligue 1','stats':{'matches':9,'minutes':659,'goals':3,'assists':3}},
       {'id':'uefa-super-cup','name':'UEFA Super Cup',
        'stats':{'matches':1,'minutes':90,'goals':0,'assists':0}}]}],
      'as_of':'2026-11-22'}
    src={'2026/27':{'a':[{'id':61,'name':'Ligue 1','stats':{'matches':8,'minutes':570},
                         'source':'pitchapi_partial','last_match_date':'2026-10-30'}]}}
    changes=add_verified_competitions(people,src,first)
    x=src['2026/27']['a']
    assert changes['rows_verified']==2 and sum(v['stats']['matches'] for v in x)==10,x
    assert add_verified_competitions(people,src,first)['rows_verified']==0
    x[0]['stats']['matches']=11;x[0]['last_match_date']='2026-11-26'
    assert add_verified_competitions(people,src,first)['rows_verified']==0
    print('Verified competition snapshots, dates and dedup PASS')

if __name__=='__main__':self_test()
