#!/usr/bin/env python3
"""Keep broad and detailed player roles consistent across the WHOLE registry.

A displayed 'AM' with broad group 'Defender' is a real data quality failure,
not a translation issue. Only explicit known role codes justify repairs; never
guess a role from goals, team, photographs or an unverified name match.
"""
from collections import Counter

ROLE_GROUPS={
    'GK':'Goalkeeper','GOALKEEPER':'Goalkeeper',
    'CB':'Defender','RB':'Defender','LB':'Defender',
    'RWB':'Defender','LWB':'Defender','LB/RB':'Defender',
    'DM':'Midfielder','CDM':'Midfielder','CM':'Midfielder',
    'AM':'Midfielder','CAM':'Midfielder','LM':'Midfielder',
    'RM':'Midfielder','MID':'Midfielder',
    'LW':'Forward','RW':'Forward','LW/RW':'Forward',
    'ST':'Forward','CF':'Forward','SS':'Forward','FWD':'Forward'
}
BROAD=('Goalkeeper','Defender','Midfielder','Forward')
def canonical_group(p):
    role=str(p.get('displayPosition') or '').strip().upper()
    if role in ROLE_GROUPS:return ROLE_GROUPS[role]
    role=str(p.get('scoutRole') or '').strip().upper()
    if role in ROLE_GROUPS:return ROLE_GROUPS[role]
    return None

def reconcile(players):
    checked=0;fixed=0;examples=[]
    for player in players:
        group=canonical_group(player)
        if group is None:continue
        checked+=1
        before=player.get('pos')
        if before==group:continue
        player['pos']=group
        fixed+=1
        if len(examples)<35:
            examples.append({'id':str(player.get('id')),
                'name':player.get('name'),'previous_group':before,
                'corrected_group':group,
                'role':player.get('displayPosition') or player.get('scoutRole')})
    return {'checked_explicit_roles':checked,'repaired_broad_positions':fixed,
            'sample_repairs':examples,'role_mapping':'explicit_role_to_broad_position',
            'guessed_positions':0}

def selftest():
    people=[
      {'id':'1','name':'Florian Wirtz','pos':'Defender',
       'displayPosition':'AM','scoutRole':'AM'},
      {'id':'2','name':'Achraf Hakimi','pos':'Midfielder','displayPosition':'RB'},
      {'id':'3','name':'Nuno Mendes','pos':'Defender','displayPosition':'LB'},
      {'id':'4','name':'Unknown','pos':'Defender'},
      {'id':'5','name':'Forward','pos':'Midfielder','displayPosition':'LW'}
    ]
    report=reconcile(people)
    assert report['repaired_broad_positions']==3,report
    assert [p['pos'] for p in people]==[
      'Midfielder','Defender','Defender','Defender','Forward']
    assert reconcile(people)['repaired_broad_positions']==0
    print('Global explicit role to broad-position consistency PASS')

if __name__=='__main__':selftest()
