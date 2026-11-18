#!/usr/bin/env python3
"""Optional FREE PitchAPI ingestion: match-by-match season statistics for 77 leagues.

Requires a free PITCHAPI_KEY secret, never a card or paid subscription.
No guessing: names must match within the confirmed match team and be unique.
Match ids are stable; re-fetching cannot double-count. Missing values are None,
never zero. Photos returned by the CDN are saved as references only until
separate display rights have been verified.
"""
from __future__ import annotations
import datetime as dt
import json
import os
import pathlib
import re
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from collections import defaultdict

ROOT=pathlib.Path(__file__).resolve().parents[1]
OUT=ROOT/'data'/'pitchapi.json'
API='https://api.pitchapi.dev/v1'
# Include league and UEFA names; actual league IDs always come from /leagues.
TARGETS={
 'Premier League':['premier league','english premier league'],
 'La Liga':['la liga','primera division'],
 'Bundesliga':['bundesliga'],
 'Serie A':['serie a','italian serie a'],
 'Ligue 1':['ligue 1','french ligue 1'],
 'Primeira Liga':['primeira liga','liga portugal'],
 'Belgian Pro League':['belgian pro league','jupiler pro league'],
 'Süper Lig':['super lig','süper lig','turkish super lig'],
 'Saudi Pro League':['saudi pro league','saudi professional league'],
 'MLS':['mls','major league soccer'],
 'Brasileirão':['brasileirao','brasileirão','brasileirao serie a','brasileirão série a','brazilian serie a'],
 'UEFA Champions League':['champions league','uefa champions league'],
 'UEFA Europa League':['europa league','uefa europa league'],
 'UEFA Conference League':['conference league','uefa conference league'],
 'FA Cup':['fa cup','english fa cup'],
 'EFL Cup':['efl cup','carabao cup','league cup','efl carabao cup'],
 'Copa del Rey':['copa del rey'],
 'Coppa Italia':['coppa italia'],
 'DFB Pokal':['dfb pokal','dfb-pokal'],
 'Coupe de France':['coupe de france'],
 'Taça de Portugal':['taca de portugal','taça de portugal'],
 'KNVB Cup':['knvb beker','knvb cup'],
 'Eredivisie':['eredivisie']
}
# Directly mapped internal competition ids, no cross-league conflation.
LEAGUE_IDS={'Premier League':39,'La Liga':140,'Bundesliga':78,'Serie A':135,
 'Ligue 1':61,'Primeira Liga':94,'Belgian Pro League':144,'Süper Lig':203,
 'Saudi Pro League':307,'MLS':253,'Brasileirão':'br-league','UEFA Champions League':2,
 'UEFA Europa League':3,'UEFA Conference League':848,'FA Cup':45,
 'EFL Cup':48,'Copa del Rey':143,'Coppa Italia':137,'DFB Pokal':81,
 'Coupe de France':66}
# PitchAPI documents grouped values with a metric key and a stat.value.
METRICS={'goals':'goals','assists':'assists','minutes_played':'minutes',
 'total_shots':'shots','shots_on_target':'shots_on_target','key_passes':'key_passes',
 'tackles':'tackles','interceptions':'interceptions','recoveries':'recoveries',
 'clearances':'clearances','blocks':'blocks','touches':'touches',
 'successful_dribbles':'dribbles','xg':'xg','xa':'xa','expected_goals':'xg',
 'expected_assists':'xa','yellow_cards':'yellow_cards','red_cards':'red_cards',
 'progressive_passes':'progressive_passes','progressive_carries':'progressive_carries'}
def norm(v):
    text=unicodedata.normalize('NFKD',str(v or '').casefold())
    return re.sub(r'[^a-z0-9а-я]','', ''.join(c for c in text if not unicodedata.combining(c)))
def team_norm(v):
    v=norm(v)
    # Known official/short-name variants, not arbitrary fuzzy team matching.
    v={'mancity':'manchestercity','manutd':'manchesterunited',
       'psg':'parissaintgermain','parissg':'parissaintgermain',
       'atleticomadrid':'atleticodemadrid','intermilan':'internazionale',
       'inter':'internazionale','bayernmunchen':'bayernmunich',
       'barca':'barcelona','fcbarcelona':'barcelona',
       'borussiadortmund':'dortmund','bvb':'dortmund'}.get(v,v)
    for prefix in ('fc','cf','ac','sc'):
        if v.startswith(prefix) and len(v)>6:v=v[len(prefix):]
    for suffix in ('fc','cf','afc','sc'):
        if v.endswith(suffix) and len(v)>6:v=v[:-len(suffix)]
    v={'bayernmunchen':'bayernmunich','bayernmunchen1900':'bayernmunich',
       'internazionalemilano':'internazionale',
       'rbleipzig':'leipzig','rasenballsportleipzig':'leipzig',
       'sportinglisbon':'sportingcp',
       'realbetisbalompie':'realbetis',
       'acmilan':'milan','milanac':'milan',
       'athleticclub':'athleticbilbao','athleticdebilbao':'athleticbilbao',
       'tottenhamhotspur':'tottenham',
       'borussiadortmund':'dortmund'}.get(v,v)
    return v
def aliases(name):
    name=str(name or '').replace('.',' ').replace('-',' ')
    words=[norm(x) for x in name.split() if x]
    out={norm(name)}
    if len(words)>=2:
        out.add(words[-1]+words[0][:1])
        out.add(words[0][:1]+words[-1])
        # Compound surnames: Kevin De Bruyne -> K. De Bruyne.
        out.add(words[0][:1]+''.join(words[1:]))
        # Initial-only matches still require the exact verified team.
    return out
def roster_match(name,team,roster):
    candidates=[p for p in roster if team_norm(p.get('team'))==team_norm(team) and
                (norm(name) in aliases(p.get('name')) or
                 norm(name) in aliases(p.get('web')))]
    return candidates[0] if len(candidates)==1 else None
def parse_groups(groups):
    data={}
    for group in groups or []:
        for part in (group.get('stats') or {}).values():
            if not isinstance(part,dict):continue
            key=METRICS.get(str(part.get('key') or '').lower())
            stat=part.get('stat') or {}
            value=stat.get('value')
            if not key or value is None:continue
            try:
                v=float(value)
                if v!=v or v<0 or v>100000:continue
            except (ValueError,TypeError):continue
            data[key]=round(v,3) if v%1 else int(v)
    return data
def get(path,key,params=None):
    uri=API+path+(('?'+urllib.parse.urlencode(params)) if params else '')
    req=urllib.request.Request(uri,headers={'X-API-KEY':key,'Accept':'application/json',
                                            'User-Agent':'TransferLab/6.1 (GitHub Pages)'})
    with urllib.request.urlopen(req,timeout=30) as response:obj=json.load(response)
    if not isinstance(obj,dict) or obj.get('error'):raise RuntimeError('Unexpected PitchAPI response')
    return obj.get('data')
def discover(catalogue):
    """All actually available seasons, not only the current one."""
    selected=[]
    seen=set()
    for league in (catalogue or {}).get('leagues',[]):
        name=norm(league.get('name'))
        for canonical,variants in TARGETS.items():
            if name not in {norm(x) for x in variants} or not league.get('id'):
                continue
            calendar=canonical in ('MLS','Brasileirão')
            requested=('2026','2025','2024') if calendar else (
                '2026/2027','2025/2026','2024/2025')
            seasons=set(str(x) for x in (league.get('seasons') or []))
            for season in requested:
                key=(canonical,str(league['id']),season)
                if season in seasons and key not in seen:
                    seen.add(key)
                    selected.append(key)
            break
    return selected

def canonical_season(provider_season):
    return provider_season if len(provider_season)==4 else (
        provider_season[:4]+'/'+provider_season[-2:])

def safe_fullname_match(fullname,roster):
    """A verified PitchAPI full name can bridge a historical transfer.
    Abbreviated names and duplicated names are deliberately rejected.
    """
    name=str(fullname or '').strip()
    if len(name.split())<2 or re.search(r'(^|\\s)[A-Za-zÀ-ÿ]\\.',name):
        return None
    matches=[p for p in roster if norm(p.get('name'))==norm(name)]
    return matches[0] if len(matches)==1 else None

def aggregate_match_rows(match_rows,teams,roster,known,detail_cache,api_key,
                         can_request_details):
    """Only confirmed team + unique person; never infer missing stats."""
    processed=[]
    details_called=0
    for entry in match_rows:
        if not isinstance(entry,dict):
            continue
        player=entry.get('player') or {}
        pid=str(player.get('id') or '')
        team=teams.get(str(entry.get('team_id')))
        if not re.fullmatch(r'p_[A-Za-z0-9]{6}',pid) or not team:
            continue
        current=next((p for p in roster if str(p.get('id'))==str(known.get(pid))),None) if known.get(pid) else None
        if current is None:
            current=roster_match(player.get('name'),team,roster)
        # Exact verified full name is sufficient across a historical transfer,
        # unlike an initial+surname match (which is not identity proof).
        if current is None:
            full=detail_cache.get(pid)
            if full is None and can_request_details():
                try:
                    full=get('/players/'+pid,api_key)
                    details_called+=1
                except (OSError,ValueError,RuntimeError):
                    full={}
                detail_cache[pid]=full if isinstance(full,dict) else {}
            if isinstance(full,dict):
                current=safe_fullname_match(full.get('name'),roster)
        if current is None:
            continue
        sid=str(current['id'])
        metrics=parse_groups(entry.get('stats'))
        if not metrics:
            continue
        known[pid]=sid
        processed.append({'player_id':sid,'pitch_id':pid,'team':team,
                          'stats':metrics})
    return processed,details_called

def read_roster():
    from zipfile import ZipFile
    with ZipFile(ROOT/'TransferLab_RESTORED_2026-11-16.zip') as archive:
        html=archive.read('index.html').decode('utf-8')
    m=re.search(r'<script id="embeddedData" type="application/json">(.*?)</script>',html,re.S)
    if not m:raise RuntimeError('No embedded roster')
    return json.loads(m.group(1))['players']
def sync():
    key=os.getenv('PITCHAPI_KEY','').strip()
    if not key:
        print('PITCHAPI_KEY absent: match-player importer not activated')
        return
    try:
        prior=json.loads(OUT.read_text(encoding='utf-8'))
    except (OSError,ValueError):
        prior={}
    cached=dict(prior.get('matches') or {})
    known=dict(prior.get('pitch_id_matches') or {})
    details=dict(prior.get('player_details') or {})
    roster=read_roster()
    leagues=discover(get('/leagues',key))
    if not leagues:
        raise RuntimeError('No provider-supported target seasons found; keeping cache')
    # Fair-use guard, not a billed API quota. Incrementally backfill all 3
    # seasons across every league while revisiting newer games daily.
    budget=max(50,min(int(os.getenv('PITCHAPI_REQUEST_BUDGET','1600')),5000))
    detail_budget=max(0,min(int(os.getenv('PITCHAPI_DETAIL_BUDGET','160')),1000))
    max_report_size=max(50,min(int(os.getenv('PITCHAPI_MAX_CACHE_MATCHES','50000')),100000))
    requests=1
    detail_requests=0
    fetched=0
    checked=0
    errors=[]
    # Fetch every league-season match index; one API call per supported season.
    tasks=[]
    initial_cursor=int(prior.get('league_cursor') or 0)
    order=leagues[initial_cursor%len(leagues):]+leagues[:initial_cursor%len(leagues)]
    for canonical,league_id,season in order:
        if requests>=budget:
            break
        try:
            data=get('/leagues/'+urllib.parse.quote(league_id)+'/matches',key,
                     {'season':season})
            requests+=1
            if not isinstance(data,dict):
                errors.append(canonical+' '+season+': unexpected league response')
                continue
            matches=data.get('matches')
            if not isinstance(matches,list):
                errors.append(canonical+' '+season+': match list missing')
                continue
            pending=[m for m in matches if isinstance(m,dict)
                     and m.get('status')=='finished'
                     and re.fullmatch(r'm_[A-Za-z0-9]{6}',str(m.get('id') or ''))
                     and str(m['id']) not in cached]
            # Newer games before older: today's stats first, backfill follows.
            pending.sort(key=lambda m:(str(m.get('date') or ''),str(m.get('id'))),reverse=True)
            tasks.append({'canonical':canonical,'league_id':league_id,
                          'season':season,'pending':pending,'cursor':0,
                          'indexed_matches':len(matches)})
        except urllib.error.HTTPError as exc:
            errors.append(canonical+' '+season+': HTTP '+str(exc.code))
            if exc.code in (401,403):
                raise RuntimeError('PitchAPI key rejected (HTTP '+str(exc.code)+')') from exc
        except (OSError,ValueError,RuntimeError) as exc:
            errors.append(canonical+' '+season+': '+type(exc).__name__)
    # Interleave leagues and seasons. One long-running league must not use the
    # entire run while other countries receive no data.
    active=[t for t in tasks if t['pending']]
    denied=False
    pause=max(.08,min(2.0,float(os.getenv('PITCHAPI_PAUSE','0.18'))))
    while active and requests<budget and len(cached)<max_report_size and not denied:
        next_active=[]
        for task in active:
            if requests>=budget or denied:
                break
            if task['cursor']>=len(task['pending']):
                continue
            match=task['pending'][task['cursor']]
            task['cursor']+=1
            mid=str(match['id'])
            home=match.get('home_team') or {}
            away=match.get('away_team') or {}
            teams={str(x.get('id')):x.get('name') for x in (home,away)
                   if x.get('id') and x.get('name')}
            if len(teams)!=2:
                continue
            try:
                rows=get('/matches/'+mid+'/players',key)
                requests+=1
                checked+=1
                if not isinstance(rows,list):
                    errors.append(task['canonical']+': invalid player stat payload')
                    continue
                def detail_allowed():
                    return requests+detail_requests<budget and detail_requests<detail_budget
                processed,spent=aggregate_match_rows(rows,teams,roster,known,
                                                       details,key,detail_allowed)
                requests+=spent
                detail_requests+=spent
                cached[mid]={'id':mid,'date':match.get('date'),
                             'season':canonical_season(task['season']),
                             'league':task['canonical'],
                             'league_id':task['league_id'],
                             'competition_id':LEAGUE_IDS.get(task['canonical']),
                             'players':processed,'source':'PitchAPI'}
                fetched+=1
            except urllib.error.HTTPError as exc:
                errors.append(task['canonical']+': HTTP '+str(exc.code))
                if exc.code in (401,403,429):
                    denied=True
            except (ValueError,OSError,RuntimeError) as exc:
                errors.append(task['canonical']+': '+type(exc).__name__)
            finally:
                time.sleep(pause)
            if task['cursor']<len(task['pending']):
                next_active.append(task)
        active=next_active
    coverage=defaultdict(set)
    for m in cached.values():
        if not isinstance(m,dict):
            continue
        for row in m.get('players') or []:
            if row.get('player_id'):
                coverage[str(m.get('season'))].add(str(row['player_id']))
    payload={'provider':'PitchAPI','source':'https://pitchapi.dev/',
             'updated_at':dt.datetime.now(dt.timezone.utc).isoformat(timespec='seconds'),
             'key_configured':True,'requests_used':requests,'matches_fetched':fetched,
             'leagues_available':len(leagues),'league_cursor':initial_cursor+1,
             'match_stats_checked':checked,'matches':cached,
             'pitch_id_matches':known,'player_details':details,
             'season_player_coverage':{k:len(v) for k,v in sorted(coverage.items())},
             'catalogue_seasons':[{'name':name,'season':canonical_season(season)}
                                  for name,_,season in leagues],
             'errors':errors,'backfill_incomplete':bool(active),
             'match_cache_limit_reached':len(cached)>=max_report_size}
    OUT.parent.mkdir(exist_ok=True,parents=True)
    tmp=OUT.with_suffix('.tmp')
    tmp.write_text(json.dumps(payload,ensure_ascii=False,separators=(',',':'))+'\n',encoding='utf-8')
    tmp.replace(OUT)
    print('PitchAPI: '+str(fetched)+' new match reports; '+str(len(known))+
          ' identified players; seasons '+str(payload['season_player_coverage'])+
          '; '+str(requests)+' HTTP requests; errors '+str(len(errors)))
def test():
    assert parse_groups([{'key':'top_stats','stats':{
        'Goals':{'key':'goals','stat':{'type':'integer','value':2}},
        'xG':{'key':'xg','stat':{'type':'double','value':1.32}},
        'Missing':{'key':'assists','stat':{'type':'integer','value':None}}}}])=={'goals':2,'xg':1.32}
    roster=[{'id':'9','name':'Erling Haaland','team':'Manchester City'},
            {'id':'10','name':'Phil Foden','team':'Manchester City'},
            {'id':'99','name':'Erling Haaland','team':'Paris Saint-Germain'}]
    assert roster_match('E. Haaland','Manchester City',roster)['id']=='9'
    assert roster_match('E. Haaland','Paris Saint-Germain',roster)['id']=='99'
    assert roster_match('P. Foden','Manchester City',roster)['id']=='10'
    assert roster_match('E. Haaland','Unknown Club',roster) is None
    assert roster_match('K. De Bruyne','Manchester City',
        roster+[{'id':'77','name':'Kevin De Bruyne','team':'Manchester City'}])['id']=='77'
    assert team_norm('Man City')==team_norm('Manchester City')
    assert team_norm('Bayern München')==team_norm('FC Bayern Munich')
    assert roster_match('P. Foden','Man City',roster)['id']=='10'
    assert discover({'leagues':[{'id':'l_ABC123','name':'Premier League',
                                 'seasons':['2024/2025','2025/2026','2026/2027']},
                                {'id':'l_DEF456','name':'Serie A',
                                 'seasons':['2023/2024']}]})==[
        ('Premier League','l_ABC123','2026/2027'),
        ('Premier League','l_ABC123','2025/2026'),
        ('Premier League','l_ABC123','2024/2025')]
    assert discover({'leagues':[{'id':'l_Zy12Ab','name':'Brasileirão',
                                  'seasons':['2026']}]})==[('Brasileirão','l_Zy12Ab','2026')]
    assert canonical_season('2024/2025')=='2024/25'
    assert canonical_season('2025')=='2025'
    assert safe_fullname_match('Erling Haaland',roster) is None
    assert safe_fullname_match('K. De Bruyne',roster) is None
    assert safe_fullname_match('Phil Foden',roster)['id']=='10'
    print('PitchAPI unique club/player matches, three seasons, typed metrics PASS')
if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser();p.add_argument('--self-test',action='store_true')
    args=p.parse_args()
    if args.self_test:test()
    else:sync()
