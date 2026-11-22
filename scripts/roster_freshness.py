#!/usr/bin/env python3
"""Refresh current player clubs from verified current-season match membership.

Immutable published transfers take priority. Unlisted transfers are accepted
only after two played matches at the same new club in a current domestic league.
No transfers inferred from a name alone or from UEFA/national-team fixtures.
"""
from __future__ import annotations
from collections import Counter,defaultdict
import datetime as dt
import json,pathlib,unicodedata,re
from sync_pitchapi import team_norm

ROOT=pathlib.Path(__file__).resolve().parents[1]
VERIFIED=ROOT/'data/verified_roster.json'
LEAGUE_NAMES={
 'Premier League':'Premier League','La Liga':'La Liga','Bundesliga':'Bundesliga',
 'Serie A':'Serie A','Ligue 1':'Ligue 1','Primeira Liga':'Primeira Liga',
 'Belgian Pro League':'Belgian Pro League','Süper Lig':'Süper Lig',
 'Saudi Pro League':'Saudi Pro League','MLS':'MLS','Brasileirão':'Brasileirão',
 'Eredivisie':'Eredivisie',
 'Russian Premier League':'Russian Premier League',
 'Ukrainian Premier League':'Ukrainian Premier League',
 'Ekstraklasa':'Ekstraklasa',
 'Czech First League':'Czech First League',
 'Croatian HNL':'Croatian HNL',
 'Serbian SuperLiga':'Serbian SuperLiga',
 'Romanian SuperLiga':'Romanian SuperLiga',
 'Greek Super League':'Greek Super League',
 'Scottish Premiership':'Scottish Premiership',
 'Austrian Bundesliga':'Austrian Bundesliga',
 'Danish Superliga':'Danish Superliga',
 'Swiss Super League':'Swiss Super League',
 'EFL Championship':'EFL Championship',
 'Segunda División':'Segunda División',
 '2. Bundesliga':'2. Bundesliga',
 'Serie B':'Serie B',
 'Ligue 2':'Ligue 2',
 'Liga MX':'Liga MX',
 'A-League Men':'A-League Men',
 'Argentine Primera División':'Argentine Primera División',
 'Eliteserien':'Eliteserien',
 'Allsvenskan':'Allsvenskan',
 'J1 League':'J1 League',
 'K League 1':'K League 1'
}
ROLE_POS={'GK':'Goalkeeper','CB':'Defender','RB':'Defender','LB':'Defender',
 'AM':'Midfielder','CM':'Midfielder','DM':'Midfielder','RW':'Forward',
 'LW':'Forward','ST':'Forward','LW/RW':'Forward'}
def normalize(value):
    return ''.join(x for x in unicodedata.normalize('NFKD',str(value or '').casefold())
                   if x.isalnum() and not unicodedata.combining(x))
def reliable_current_membership(matches,as_of=None):
    """Return strongly verified recent-team observations keyed by player ID."""
    today=as_of or dt.date.today()
    by_id=defaultdict(list)
    for m in (matches or {}).values():
        if not isinstance(m,dict) or m.get('league') not in LEAGUE_NAMES:
            continue
        league=m['league']
        season='2026' if league in ('MLS','Brasileirão','Argentine Primera División',
             'Eliteserien','Allsvenskan','J1 League','K League 1') else '2026/27'
        if m.get('season')!=season:continue
        try:
            day=dt.date.fromisoformat(str(m.get('date'))[:10])
        except ValueError:continue
        if day>today or day<today-dt.timedelta(days=115):continue
        for row in m.get('players') or []:
            if not row.get('team') or not row.get('player_id') or not isinstance(row.get('stats'),dict):continue
            metrics=row['stats']
            if float(metrics.get('minutes') or 0)<=0 and not any(metrics.get(k) for k in ('goals','assists')):
                continue
            by_id[str(row['player_id'])].append((day,team_norm(row['team']),row['team'],league))
    trusted={}
    for pid,events in by_id.items():
        newest=max(events,key=lambda row:row[0])
        _,club_norm,club,league=newest
        same=[row for row in events if row[1]==club_norm and row[3]==league]
        # Two separate match dates; duplicate fixture reports cannot verify a transfer.
        if len({row[0] for row in same})<2:continue
        if newest[0]<today-dt.timedelta(days=45):continue
        trusted[pid]={'team':club,'league':league,'last_match':newest[0].isoformat(),
                      'games':len(same),'source':'PitchAPI: current domestic match team'}
    return trusted
def apply_verified(players,match_cache,config,as_of=None):
    by_name=defaultdict(list)
    for p in players:by_name[normalize(p.get('name'))].append(p)
    manual={}
    for name,fields in (config.get('players') or {}).items():
        matches=by_name.get(normalize(name),[])
        if len(matches)!=1:continue
        p=matches[0]
        if fields.get('birth') and p.get('birth') and str(p['birth'])[:10]!=fields['birth']:continue
        manual[str(p['id'])]=fields
    current=reliable_current_membership(match_cache,as_of)
    count=0
    for p in players:
        pid=str(p.get('id'))
        evidence=current.get(pid)
        fields=manual.get(pid)
        if evidence and not fields:
            moved=team_norm(evidence['team'])!=team_norm(p.get('team'))
            # An archive team matching two recent fixtures is now verifiable,
            # even when the player did not transfer. Never infer from one match.
            if moved or (p.get('origin')=='transfermarkt_archived_2026' and
                         not p.get('clubSource')):
                p['team']=evidence['team']
                p['league']=evidence['league']
                p['clubSource']=evidence['source']
                p['clubSourceAsOf']=evidence['last_match']
                count+=1
        if not fields:continue
        if fields.get('club'):
            p['team']=fields['club']
            p['league']=fields['league']
            p['clubSource']=fields.get('source')
            p['clubSourceAsOf']=fields.get('source_as_of')
            p['clubVerifiedAsOf']=config.get('as_of')
        if fields.get('position'):
            p['pos']=fields['position']
            if fields.get('scoutRole'):p['scoutRole']=fields['scoutRole']
            if fields.get('displayPosition'):p['displayPosition']=fields['displayPosition']
            p['positionVerified']=True
            p['position_source']=fields.get('source')
        if fields.get('foot'):p['foot']=fields['foot']
        if fields.get('contractUntil'):
            p['contractUntilCurrent']=fields['contractUntil']
            p['contractSource']=fields.get('source')
            p['contractSourceAsOf']=fields.get('source_as_of')
        if fields.get('contractThrough'):
            p['contractThroughYear']=fields['contractThrough']
            p['contractSource']=fields.get('source')
            p['contractSourceAsOf']=fields.get('source_as_of')
        count+=1
    return count

def selftest():
    roster=[{'id':'1','name':'Ademola Lookman','team':'Atalanta','league':'Serie A'},
            {'id':'2','name':'Unchanged Player','team':'Old Club','league':'Premier League'}]
    matches={}
    for i,day in enumerate(['2026-11-01','2026-11-09']):
        matches['m'+str(i)]={'season':'2026/27','league':'Premier League','date':day,
             'players':[{'player_id':'2','team':'New Club','stats':{'minutes':90}}]}
    cfg={'as_of':'2026-11-22','players':{'Ademola Lookman':{
        'club':'Atlético Madrid','league':'La Liga','position':'Forward',
        'scoutRole':'LW/RW','displayPosition':'LW/RW','contractUntil':'2030-06-30'}}}
    count=apply_verified(roster,matches,cfg,dt.date(2026,11,22))
    assert count==2,(count,roster)
    assert roster[0]['team']=='Atlético Madrid' and roster[0]['contractUntilCurrent']=='2030-06-30'
    assert roster[1]['team']=='New Club'
    # Current RPL appearances should correct a stale archived club, not get
    # silently discarded because the domestic league was absent from the map.
    rpl=[{'id':'tm-player-909','name':'Test Russian League Player','team':'Archive Club',
          'league':'Russian Premier League','origin':'transfermarkt_archived_2026'}]
    fixtures={}
    for i,day in enumerate(('2026-10-21','2026-11-10')):
        fixtures[str(i)]={'season':'2026/27','league':'Russian Premier League',
            'date':day,'players':[{'player_id':'tm-player-909','team':'Confirmed Team',
                                   'stats':{'minutes':90}}]}
    assert apply_verified(rpl,fixtures,{'players':{}},dt.date(2026,11,22))==1
    assert rpl[0]['team']=='Confirmed Team' and rpl[0]['clubSourceAsOf']=='2026-11-10'
    for m in fixtures.values():m['season']='2025/26'
    rpl[0]['team']='Archive Club';rpl[0].pop('clubSource',None)
    assert apply_verified(rpl,fixtures,{'players':{}},dt.date(2026,11,22))==0
    assert rpl[0]['team']=='Archive Club'
    for m in fixtures.values():
        m['season']='2026/27';m['date']='2026-11-10'
    assert apply_verified(rpl,fixtures,{'players':{}},dt.date(2026,11,22))==0
    assert rpl[0]['team']=='Archive Club', 'duplicate match day cannot prove transfer'

    print('Verified transfer overrides and recent match-team reconciliation PASS')

if __name__=='__main__':selftest()
