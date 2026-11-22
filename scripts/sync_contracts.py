#!/usr/bin/env python3
"""Daily, cautious contract expiry enrichment using TheSportsDB public API.

TheSportsDB contract data specify a YEAR, not a precise expiry date.
Never manufacture 30 June. A contract is published only if the source
player identity AND the latest verified team agree. All other responses stay
unconfirmed. Rate limited, resumable and licensed-source attributed.
"""
from __future__ import annotations
import datetime as dt
import json,os,pathlib,re,time,unicodedata,urllib.error,urllib.parse,urllib.request
from collections import defaultdict
from zipfile import ZipFile
from roster_freshness import apply_verified,normalize
from sync_pitchapi import team_norm

ROOT=pathlib.Path(__file__).resolve().parents[1]
OUT=ROOT/'data/contract_enrichment.json'
SOURCE='https://www.thesportsdb.com/api/v1/json/123/'
def input_roster():
    with ZipFile(ROOT/'TransferLab_RESTORED_2026-11-16.zip') as z:
        html=z.read('index.html').decode('utf-8')
    match=re.search(r'<script id="embeddedData" type="application/json">(.*?)</script>',html,re.S)
    if not match:raise RuntimeError('No verified original roster')
    players=json.loads(match.group(1))['players']
    extra=ROOT/'data/verified_roster.json'
    cfg=json.loads(extra.read_text()) if extra.exists() else {}
    try:
        pitch=json.loads((ROOT/'data/pitchapi.json').read_text())
        matches=pitch.get('matches') or {}
    except (OSError,ValueError):matches={}
    apply_verified(players,matches,cfg)
    return players

def parse_birth(value):
    value=str(value or '')[:10]
    try:return dt.date.fromisoformat(value).isoformat()
    except ValueError:return None

def get(url,params):
    request=urllib.request.Request(url+'?'+urllib.parse.urlencode(params),
       headers={'User-Agent':'TransferLab/5.3 (contact: GitHub gosha-tech/transferlab)',
                'Accept':'application/json'})
    with urllib.request.urlopen(request,timeout=18) as response:
        content=response.read(600_000)
    return json.loads(content)

def match_identity(results,player,tm_id):
    target=normalize(player.get('name'))
    candidates=[r for r in (results or []) if isinstance(r,dict) and
        normalize(r.get('strPlayer'))==target and
        str(r.get('strSport') or 'Soccer').lower() in ('soccer','football')]
    if not candidates:return None
    confirmed=[]
    for r in candidates:
        tm=str(r.get('idTransferMkt') or '')
        by_tm=bool(tm_id and tm==str(tm_id))
        dob=parse_birth(r.get('dateBorn'))
        by_birth=bool(player.get('birth') and parse_birth(player['birth'])==dob)
        # Some public profiles have no DOB/TM ID. A UNIQUE exact full name
        # and exact verified current team is sufficiently strong identity
        # evidence for a year-only contract lookup (never name alone).
        by_club=len(candidates)==1 and r.get('strTeam') and team_norm(r['strTeam'])==team_norm(player.get('team'))
        if by_tm or by_birth or by_club:confirmed.append(r)
    return confirmed[0] if len(confirmed)==1 else None

def parse_contract(payload,player,player_id,today):
    candidates=[]
    for r in (payload or {}).get('contracts') or []:
        if not isinstance(r,dict) or str(r.get('idPlayer'))!=str(player_id):
            continue
        if str(r.get('strSport') or 'Soccer').lower() not in ('soccer','football'):
            continue
        club=str(r.get('strTeam') or '')
        if not club or team_norm(club)!=team_norm(player.get('team')):
            continue
        start,end=str(r.get('strYearStart') or ''),str(r.get('strYearEnd') or '')
        if not re.fullmatch(r'20\d{2}',end):continue
        year=int(end)
        if not today.year+1<=year<=today.year+10:continue
        if start and (not re.fullmatch(r'20\d{2}',start) or int(start)>today.year):
            continue
        candidates.append((year,club))
    if not candidates:return None
    year,club=max(candidates)
    return {'team':club,'contractThroughYear':str(year),'as_of':today.isoformat(),
            'provider':'TheSportsDB',
            'source':'https://www.thesportsdb.com/api/v1/json/123/lookupcontracts.php?id='+str(player_id),
            'precision':'year_only'}

def process(players,cache,today,lookup,limit):
    profiles=cache.setdefault('profiles',{})
    matched=skipped=checked=0
    ix={}
    try:
        enrichment=json.loads((ROOT/'data/profile_enrichment.json').read_text())
        ix={str(k):v for k,v in (enrichment.get('profiles') or {}).items()}
    except (OSError,ValueError):pass
    free={}
    try:
        free=json.loads((ROOT/'data/free_sources.json').read_text()).get('players') or {}
    except (OSError,ValueError):pass
    selected=[]
    for p in players:
        pid=str(p['id'])
        archived=ix.get(pid) or {}
        tm=archived.get('tm_player_id')
        if not tm and not p.get('birth'):continue
        record=profiles.get(pid) or {}
        stamp=record.get('checked_at')
        try:date=dt.date.fromisoformat(str(stamp)[:10])
        except (ValueError,TypeError):date=today-dt.timedelta(days=61)
        if (today-date).days<60:continue
        selected.append((pid,p,tm,free.get(pid) or {}))
    offset=int(cache.get('cursor') or 0)
    if selected:
        selected=selected[offset%len(selected):]+selected[:offset%len(selected)]
    for pid,p,tm,existing in selected:
        if checked>=limit:break
        checked+=1
        try:
            sportsdb=existing.get('sportsdb_id')
            if sportsdb:
                name_data=lookup('lookupplayer.php',{'id':str(sportsdb)}).get('players') or []
            else:
                name_data=lookup('searchplayers.php',{'p':p['name']}).get('player') or []
            profile=match_identity(name_data,p,tm)
            if not profile:
                profiles[pid]={'checked_at':today.isoformat(),'status':'unmatched'}
                skipped+=1
                continue
            external=str(profile['idPlayer'])
            contract_data=lookup('lookupcontracts.php',{'id':external})
            selected_contract=parse_contract(contract_data,p,external,today)
            profiles[pid]=dict(selected_contract or {'status':'missing_contract'},
                               checked_at=today.isoformat(),sportsdb_id=external)
            if selected_contract:matched+=1
        except urllib.error.HTTPError as exc:
            if exc.code in (401,403,429):
                profiles[pid]={'checked_at':(today-dt.timedelta(days=58)).isoformat(),
                               'status':'rate_limited','http':exc.code}
                break
            profiles[pid]={'checked_at':today.isoformat(),'status':'provider_error'}
        except (OSError,ValueError,RuntimeError,KeyError,TypeError):
            profiles[pid]={'checked_at':today.isoformat(),'status':'provider_error'}
        time.sleep(max(.3,min(2.0,float(os.getenv('SPORTSDB_CONTRACT_PAUSE','0.9')))))
    cache['cursor']=offset+checked
    cache['last_check']=today.isoformat()
    cache['latest_batch']={'checked':checked,'verified':matched,'unmatched':skipped}
    return cache

def sync():
    try:cache=json.loads(OUT.read_text(encoding='utf-8'))
    except (OSError,ValueError):cache={'profiles':{},'source':'TheSportsDB verified player contracts'}
    today=dt.date.today()
    players=input_roster()
    limit=max(1,min(100,int(os.getenv('SPORTSDB_CONTRACT_BATCH','30'))))
    def lookup(endpoint,params):return get(SOURCE+endpoint,params)
    cache=process(players,cache,today,lookup,limit)
    OUT.parent.mkdir(parents=True,exist_ok=True)
    temp=OUT.with_suffix('.tmp')
    temp.write_text(json.dumps(cache,ensure_ascii=False,separators=(',',':'))+'\n',encoding='utf-8')
    temp.replace(OUT)
    print('Contract evidence:',cache['latest_batch'],
          'total verified:',sum('contractThroughYear' in r for r in cache['profiles'].values()),
          'out of',len(players),'players')

def selftest():
    p={'id':'1','name':'Lucas Digne','birth':'1993-07-20','team':'Aston Villa'}
    profile={'idPlayer':'34152565','strPlayer':'Lucas Digne','dateBorn':'1993-07-20',
             'strSport':'Soccer','idTransferMkt':'126664'}
    assert match_identity([profile],p,'126664')==profile
    assert match_identity([dict(profile,dateBorn='1988-01-01',idTransferMkt='',strTeam='Chelsea')],p,'126664') is None
    assert match_identity([dict(profile,dateBorn='',idTransferMkt='',strTeam='Aston Villa')],p,None) is not None
    payload={'contracts':[{'idPlayer':'34152565','strTeam':'Aston Villa',
                           'strSport':'Soccer','strYearStart':'2025','strYearEnd':'2028'}]}
    c=parse_contract(payload,p,'34152565',dt.date(2026,11,22))
    assert c['contractThroughYear']=='2028' and c['precision']=='year_only'
    assert parse_contract(payload,dict(p,team='Chelsea'),'34152565',dt.date(2026,11,22)) is None
    assert parse_contract({'contracts':[dict(payload['contracts'][0],strYearEnd='2024')]},p,
                          '34152565',dt.date(2026,11,22)) is None
    print('Verified team + identity contract sourcing tests PASS')

if __name__=='__main__':
    import sys
    if '--self-test' in sys.argv:selftest()
    else:sync()
