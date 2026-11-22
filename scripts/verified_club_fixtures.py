#!/usr/bin/env python3
"""Verified one-off club fixtures: season-club eligibility plus exact match appearances.

Do not mistake the absence of a player record for a missing club fixture.
All players with a current club in the supported fixture get an explicit
0/0/0 row unless a match report documents an appearance. A roster can have
players who transferred after the fixture; those did not appear in this match.
Never invent minutes or advanced actions from a team line-up.
"""
from player_competitions import norm
from sync_pitchapi import team_norm

SHIELD_ID='eng-community-shield'
SOURCE='https://www.mancity.com/news/mens/arsenal-manchester-city-community-shield-match-report-63922483'
MATCH_DATE='2026-08-16'
# 11 confirmed starters + 6 used substitutes on each team.
# All goals/assists follow the match report and Opta's coverage.
CITY_STARTERS=('Gianluigi Donnarumma','Abdukodir Khusanov','Ruben Dias',
 'Josko Gvardiol','Nico OReilly','Mateo Kovacic','Elliot Anderson',
 'Antoine Semenyo','Phil Foden','Jeremy Doku','Erling Haaland')
CITY_SUBS=('Marc Guehi','Nico Gonzalez','Rico Lewis',
 'Rayan Cherki','Jack Grealish','Omar Marmoush')
ARSENAL_STARTERS=('David Raya','Ben White','Gabriel Magalhaes',
 'Cristhian Mosquera','Riccardo Calafiori','Myles Lewis-Skelly',
 'Bruno Guimaraes','Martin Odegaard','Noni Madueke',
 'Christos Tzolis','Kai Havertz')
ARSENAL_SUBS=('Piero Hincapie','Martin Zubimendi','Declan Rice',
 'Eberechi Eze','Bukayo Saka','Viktor Gyokeres')

# Normalized exact identifiers, including spellings used in club catalogues.
ALIASES={
 'ruben dias':('rubendias','rubendossantosgatoalvesdias'),
 'nico oreilly':('nicooreilly','nicolasoreilly'),
 'gabriel magalhaes':('gabrielmagalhaes','gabrieldossantosmagalhaes','gabriel'),
 'martin odegaard':('martinodegaard','martinødegaard'),
 'viktor gyokeres':('viktorgyokeres','viktorgyökeres'),
 'nicogonzalez':('nicogonzalez','nicolasgonzalez')
}
def keys(name):
    value=norm(name)
    for v in ALIASES.values():
        if value in v:return set(v)
    return {value}

def map_participants(starters,substitutes):
    result={}
    for name in starters:
        for key in keys(name):
            if key in result:raise ValueError('Duplicate player key '+key)
            result[key]=1
    for name in substitutes:
        for key in keys(name):
            if key in result:raise ValueError('Duplicate player key '+key)
            result[key]=0
    return result

CITY=map_participants(CITY_STARTERS,CITY_SUBS)
ARSENAL=map_participants(ARSENAL_STARTERS,ARSENAL_SUBS)
ARSENAL_GOALS={norm(n):1 for n in ('Riccardo Calafiori','Kai Havertz','Martin Odegaard')}
ARSENAL_ASSISTS={norm('Myles Lewis-Skelly'):1,norm('Christos Tzolis'):2}

def club_key(team):
    value=team_norm(team)
    if value in {team_norm('Manchester City'),team_norm('Man City'),team_norm('Manchester City FC')}:
        return 'city'
    if value in {team_norm('Arsenal'),team_norm('Arsenal FC')}:
        return 'arsenal'
    return None

def inject(rows,players):
    """Add a source-backed shield record to every player of both competing clubs.

    Return counts, for explicit audit. Existing match evidence is never replaced.
    """
    counters={'city_players':0,'arsenal_players':0,'city_appearances':0,
              'arsenal_appearances':0,'zero_appearances':0,'existing':0,
              'unmatched_known_players':[]}
    for p in players:
        club=club_key(p.get('team'))
        if club is None or p.get('league')!='Premier League':continue
        counters[club+'_players']+=1
        pid=str(p['id'])
        current=rows.setdefault('2026/27',{}).setdefault(pid,[])
        if any(str(r.get('id'))==SHIELD_ID for r in current):
            counters['existing']+=1
            continue
        participants=CITY if club=='city' else ARSENAL
        identity=norm(p.get('name'))
        appeared=identity in participants
        played=1 if appeared else 0
        if played:counters[club+'_appearances']+=1
        else:counters['zero_appearances']+=1
        stats={'matches':played,'goals':0,'assists':0}
        if played:
            stats['starts']=participants[identity]
        else:
            stats['starts']=0
            stats['minutes']=0
        if club=='arsenal':
            stats['goals']=ARSENAL_GOALS.get(identity,0)
            stats['assists']=ARSENAL_ASSISTS.get(identity,0)
        if identity==norm('Phil Foden') and club=='city':
            stats['minutes']=59  # Match log: substituted in the 60th minute
        current.append({'id':SHIELD_ID,'name':'FA Community Shield',
                        'source':'official_club_match_report',
                        'source_url':SOURCE,'team_verified':True,
                        'is_complete':True,'last_match_date':MATCH_DATE,
                        'club_fixture_completed':True,
                        'participation_verified':True,
                        'stats':stats})
    return counters

def selftest():
    assert len(CITY)==17 and len(ARSENAL)==17
    assert CITY[norm('Phil Foden')]==1 and CITY[norm('Rayan Cherki')]==0
    d={}
    roster=[{'id':str(i),'team':'Manchester City','league':'Premier League','name':n}
         for i,n in enumerate(CITY_STARTERS+CITY_SUBS)]
    roster += [{'id':'not-played','team':'Manchester City','league':'Premier League','name':'Unused Player'}]
    report=inject(d,roster)
    assert report['city_players']==18 and report['city_appearances']==17
    assert report['zero_appearances']==1
    assert len(d['2026/27'])==18
    assert d['2026/27']['not-played'][0]['stats']=={
        'matches':0,'goals':0,'assists':0,'starts':0,'minutes':0}
    print('Verified Community Shield club-player coverage PASS')
if __name__=='__main__':selftest()
