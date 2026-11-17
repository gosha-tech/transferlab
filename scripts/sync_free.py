#!/usr/bin/env python3
"""Fetch what public football feeds REALLY provide, without fabricating player stats.

OpenFootball: current fixtures/results by league (NO individual footballer stats).
TheSportsDB v1: community player details and at most 10 returned stats records
per lookup. Verified identity is mandatory and free stats are always flagged
as partial. football-data.org token is optional for delayed fixtures/results.
"""
from __future__ import annotations
import argparse,datetime as dt,hashlib,json,os,pathlib,re,time,unicodedata
import urllib.error,urllib.parse,urllib.request

ROOT=pathlib.Path(__file__).resolve().parents[1]
OUT=ROOT/'data'/'free_sources.json'
PROFILE_CACHE=ROOT/'data'/'profile_enrichment.json'
ARCHIVE='https://raw.githubusercontent.com/openfootball/football.json/master/'
SPORTSDB='https://www.thesportsdb.com/api/v1/json/123/'
FDORG='https://api.football-data.org/v4/'
SEASONS={'Premier League':'2026-27/en.1.json','Bundesliga':'2026-27/de.1.json',
         'La Liga':'2026-27/es.1.json','Serie A':'2026-27/it.1.json',
         'Ligue 1':'2026-27/fr.1.json','Primeira Liga':'2026-27/pt.1.json',
         'Eredivisie':'2026-27/nl.1.json','Brazilian Serie A':'2026/br.1.json'}
FD_COMP={'PL':'Premier League','BL1':'Bundesliga','SA':'Serie A','PD':'La Liga',
         'FL1':'Ligue 1','PPL':'Primeira Liga','CL':'Champions League',
         'BSA':'Brazilian Serie A'}
METRICS={'appearances':'matches','mins played':'minutes','minutes played':'minutes',
         'goals':'goals','assists':'assists','yellow cards':'yellow_cards',
         'red cards':'red_cards','shots':'shots','shots on target':'shots_on_target',
         'key passes':'key_passes','tackles':'tackles','interceptions':'interceptions'}
CURRENT_SEASONS={'2026/27','2026'}
UA='TransferLab/6.0 (public-data integration; daily cache; contact via GitHub repo)'
LAST_SPORTSDB_REQUEST=0.0
class SportsDBAccessLimited(Exception):pass
def norm(v):
    text=unicodedata.normalize('NFKD',str(v or '').casefold())
    return re.sub('[^a-z0-9а-я]','', ''.join(c for c in text if not unicodedata.combining(c)))
def json_get(url,headers=None,timeout=22):
    global LAST_SPORTSDB_REQUEST
    sports=url.startswith(SPORTSDB)
    if sports:
        # The public endpoint rate-limits heavy concurrent use.
        minimum=float(os.getenv('SPORTSDB_REQUEST_INTERVAL_SEC','2.2'))
        gap=minimum-(time.monotonic()-LAST_SPORTSDB_REQUEST)
        if LAST_SPORTSDB_REQUEST and gap>0:time.sleep(gap)
        LAST_SPORTSDB_REQUEST=time.monotonic()
    req=urllib.request.Request(url,headers={'User-Agent':UA,'Accept':'application/json',**(headers or {})})
    try:
        with urllib.request.urlopen(req,timeout=timeout) as resp:
            if resp.status!=200:raise RuntimeError('HTTP '+str(resp.status))
            result=json.load(resp)
    except urllib.error.HTTPError as exc:
        if sports and exc.code in (403,429,503):
            raise SportsDBAccessLimited('HTTP '+str(exc.code)+' rate/access restriction') from exc
        raise
    if not isinstance(result,(list,dict)):raise ValueError('Unexpected source JSON root')
    return result
def dated(v):
    try:return dt.date.fromisoformat(str(v or '')[:10])
    except ValueError:return None
def persist(obj):
    OUT.parent.mkdir(parents=True,exist_ok=True)
    tmp=OUT.with_suffix('.tmp')
    tmp.write_text(json.dumps(obj,ensure_ascii=False,separators=(',',':'))+'\n',encoding='utf-8')
    tmp.replace(OUT)
def old_snapshot():
    try:return json.loads(OUT.read_text(encoding='utf-8'))
    except (ValueError,OSError):return {}
def parse_openfootball(payload,league,today):
    if not isinstance(payload,dict):return []
    matches={}
    for row in payload.get('matches',[]):
        if not isinstance(row,dict):continue
        day=dated(row.get('date'))
        if not day or day>today:continue
        home=str(row.get('team1') or '').strip()
        away=str(row.get('team2') or '').strip()
        score=(row.get('score') or {}).get('ft') if isinstance(row.get('score'),dict) else None
        if not home or not away or not isinstance(score,list) or len(score)!=2:continue
        if any(not isinstance(v,int) or v<0 for v in score):continue
        key='|'.join([str(day),norm(home),norm(away)])
        matches[key]={'id':key,'league':league,'date':str(day),'home':home,'away':away,
                      'home_goals':score[0],'away_goals':score[1],
                      'provider':'OpenFootball','source':'https://github.com/openfootball/football.json',
                      'is_player_stat':False}
    return sorted(matches.values(),key=lambda r:(r['date'],r['home']),reverse=True)[:450]
def parse_football_data(rows,league,today):
    result=[]
    for row in rows:
        if not isinstance(row,dict) or row.get('status')!='FINISHED':continue
        day=dated(row.get('utcDate'))
        score=(row.get('score') or {}).get('fullTime') or {}
        home=(row.get('homeTeam') or {}).get('name')
        away=(row.get('awayTeam') or {}).get('name')
        if not home or not away or not day or day>today:continue
        if not isinstance(score.get('home'),int) or not isinstance(score.get('away'),int):continue
        result.append({'id':'fd-'+str(row.get('id')),'league':league,'date':str(day),
                       'home':home,'away':away,'home_goals':score['home'],
                       'away_goals':score['away'],'provider':'football-data.org',
                       'source':'https://www.football-data.org/','is_player_stat':False})
    return sorted(result,key=lambda r:(r['date'],r['home']),reverse=True)[:450]
def season(v):
    raw=str(v or '').strip()
    if re.fullmatch(r'20\d\d',raw):return raw
    nums=re.findall(r'\d{2,4}',raw)
    if len(nums)>=2 and len(nums[0])==4:
        y=int(nums[0]);next_y=int(nums[1])%100
        if next_y==(y+1)%100:return str(y)+'/'+str(next_y).zfill(2)
    return None
def numeric(v):
    if v is None:return None
    try:
        val=float(str(v).replace(',','').strip())
        if val<0 or val>100000 or not val.is_integer():return None
        return int(val)
    except (ValueError,TypeError):return None
def parse_sportsdb_stats(rows,playerid):
    grouped={}
    for r in rows or []:
        if not isinstance(r,dict) or str(r.get('idPlayer'))!=str(playerid):continue
        ss=season(r.get('strSeason'))
        if ss not in ('2026/27','2026','2025/26','2025'):continue
        metric=METRICS.get(str(r.get('strStatistic') or '').strip().lower())
        val=numeric(r.get('strValue'))
        if metric is None or val is None:continue
        cid=str(r.get('idLeague') or '')
        if not cid.isdigit():continue
        key=(ss,cid)
        data=grouped.setdefault(key,{'id':'tsdb-'+cid,'name':str(r.get('strLeague') or 'Unknown competition'),
                   'season':ss,'source':'thesportsdb_sample','is_complete':False,
                   'stats':{},'attribution':'TheSportsDB.com'})
        data['stats'][metric]=val
    return list(grouped.values())
def verify_identity(profile,player,tmid=None):
    """A name on its own is NOT sufficient to identify a footballer."""
    if profile.get('strSport') not in ('Soccer','Football'):return False
    names=[profile.get('strPlayer'),profile.get('strPlayerAlternate')]
    if not any(norm(player.get('name'))==norm(name) for name in names if name):return False
    external=str(profile.get('idTransferMkt') or '').strip()
    if tmid and external and str(tmid)==external:return True
    birth=str(player.get('birth') or '').strip()
    if birth and str(profile.get('dateBorn') or '').strip()==birth:return True
    return False
def licensed_photo(profile):
    # A Creative Commons "Yes" flag applies to a record and is NOT proof
    # that a particular cutout or thumb is cleared for redistribution.
    # Do not publish unverified portraits; use the existing verified ID-based
    # provider photos or a later per-image rights allowlist instead.
    if str(profile.get('strCreativeCommons') or '').strip().lower()!='yes':return None
    if not profile.get('verified_image_rights'):return None
    for field in ('strCutout','strThumb'):
        uri=str(profile.get(field) or '')
        if re.fullmatch(r'https://r2\.thesportsdb\.com/images/media/player/(?:cutout|thumb)/[a-zA-Z0-9._-]+\.(?:png|jpg|webp)',uri):
            return uri
    return None
def history_ids():
    try:data=json.loads(PROFILE_CACHE.read_text(encoding='utf-8'))
    except (OSError,ValueError):return {}
    return {str(pid):str(info.get('tm_player_id') or '') for pid,info in data.get('profiles',{}).items()}
def source_profiles():
    from zipfile import ZipFile
    archive=ROOT/'TransferLab_RESTORED_2026-11-16.zip'
    with ZipFile(archive) as z:
        text=z.read('index.html').decode('utf-8')
    m=re.search(r'<script id="embeddedData" type="application/json">(.*?)</script>',text,re.S)
    if not m:raise RuntimeError('No embedded players')
    data=json.loads(m.group(1))
    return [p for p in data.get('players',[]) if p.get('name') and p.get('id')]
def collect(today=None,batch=48):
    today=today or dt.datetime.now(dt.timezone.utc).date()
    previous=old_snapshot()
    now=dt.datetime.now(dt.timezone.utc).isoformat(timespec='seconds')
    result={'schema_version':1,'last_attempt_at':now,'last_success_at':previous.get('last_success_at'),
      'free_sources':{'OpenFootball':'fixtures and scores only',
                      'TheSportsDB':'partial player stats; photos require image-specific license verification',
                      'football-data.org':'fixtures/standings with optional free token'},
      'matches':dict(previous.get('matches') or {}),
      'players':dict(previous.get('players') or {}),
      'issues':[],'status':'partial','rotation_cursor':int(previous.get('rotation_cursor') or 0)}
    successes=0
    # OpenFootball - leagues with verified JSON paths.
    for league,path in SEASONS.items():
        try:
            payload=json_get(ARCHIVE+path)
            result['matches'][league]=parse_openfootball(payload,league,today)
            successes+=1
        except (OSError,ValueError,RuntimeError) as exc:
            result['issues'].append('OpenFootball '+league+': '+type(exc).__name__)
    # football-data.org: token is optional; the free tier has no per-player box scores.
    token=os.getenv('FOOTBALL_DATA_ORG_KEY','').strip()
    if token:
        for code,league in FD_COMP.items():
            try:
                payload=json_get(FDORG+'competitions/'+code+'/matches?status=FINISHED',
                    {'X-Auth-Token':token},timeout=28)
                if not isinstance(payload,dict) or not isinstance(payload.get('matches'),list):continue
                parsed=parse_football_data(payload['matches'],league,today)
                if parsed:result['matches'][league]=parsed
                successes+=1
                time.sleep(6.2)  # football-data.org free: at most 10 calls per minute
            except (OSError,ValueError,RuntimeError) as exc:
                result['issues'].append('football-data.org '+code+': '+type(exc).__name__)
    # TheSportsDB: resolve a rotating subset of 1,353 IDs each day.
    players=source_profiles()
    playerids=history_ids()
    # Use a stable order. Never assume search result belongs to a player solely by name.
    players=sorted(players,key=lambda p:str(p['id']))
    cursor=int(result['rotation_cursor'])%max(1,len(players))
    batch=max(0,min(int(batch),100))
    done=0;matched=0;fresh_stats=0
    for delta in range(min(batch,len(players))):
        p=players[(cursor+delta)%len(players)]
        pid=str(p['id'])
        cached=result['players'].get(pid,{})
        if not isinstance(cached,dict):cached={}
        try:
            dbid=cached.get('sportsdb_id')
            if dbid:
                info=cached
            else:
                name=urllib.parse.quote(str(p['name']),safe='')
                response=json_get(SPORTSDB+'searchplayers.php?p='+name)
                people=response.get('player') if isinstance(response,dict) else []
                if not isinstance(people,list):people=[]
                if not people:continue
                # Some free search responses are reduced and lack IDs/identity proof.
                full=people[0]
                if not full.get('idPlayer'):continue
                response=json_get(SPORTSDB+'lookupplayer.php?id='+str(full['idPlayer']))
                details=response.get('players') or response.get('player') or []
                if not isinstance(details,list) or not details:continue
                candidate=details[0]
                if not verify_identity(candidate,p,playerids.get(pid)):continue
                dbid=str(candidate['idPlayer'])
                info={'sportsdb_id':dbid,'name':candidate.get('strPlayer'),
                      'birth':candidate.get('dateBorn'),
                      'tm_id':candidate.get('idTransferMkt'),
                      'profile_verified_at':now,'provider':'TheSportsDB',
                      'photo':licensed_photo(candidate),
                      'photo_attribution':candidate.get('strCreativeCommonsAttribution') if licensed_photo(candidate) else None,
                      'position_source':candidate.get('strPosition')}
                matched+=1
            stats_obj=json_get(SPORTSDB+'lookupplayerstats.php?id='+str(dbid))
            stats_rows=stats_obj.get('playerstats') if isinstance(stats_obj,dict) else []
            if not isinstance(stats_rows,list):stats_rows=[]
            infos=parse_sportsdb_stats(stats_rows,dbid)
            info['stats']=infos
            info['stats_checked_at']=now
            info['stats_free_limit']=10
            result['players'][pid]=info
            fresh_stats+=len(infos)
            successes+=1
        except SportsDBAccessLimited as exc:
            result['issues'].append('TheSportsDB rate/access restriction: '+str(exc))
            result['sportsdb_blocked']=str(exc)
            # Avoid 40 further calls while a free-service limit is active.
            break
        except (OSError,ValueError,RuntimeError) as exc:
            result['issues'].append('TheSportsDB player '+pid+': '+type(exc).__name__+
                                     (' HTTP '+str(exc.code) if isinstance(exc,urllib.error.HTTPError) else ''))
        finally:
            done+=1
            time.sleep(float(os.getenv('SPORTSDB_PAUSE_SEC','0.25')))
    result['rotation_cursor']=(cursor+done)%max(1,len(players))
    result['roster_size']=len(players)
    result['profiles_verified']=sum(1 for x in result['players'].values() if isinstance(x,dict) and x.get('sportsdb_id'))
    result['players_with_current_stats']=sum(1 for x in result['players'].values() if isinstance(x,dict)
                 and any(a.get('season') in CURRENT_SEASONS for a in x.get('stats',[])))
    result['recent_matches']=sum(len(x) for x in result['matches'].values() if isinstance(x,list))
    result['sportsdb_last_batch']={'processed':done,'new_identified':matched,'season_competition_rows':fresh_stats}
    if successes:result['last_success_at']=now
    if not successes and not result['last_success_at']:
        raise RuntimeError('All public source reads failed; no new data may be published')
    persist(result)
    print('OpenFootball and optional football-data.org matches:',result['recent_matches'])
    print('TheSportsDB verified profiles:',result['profiles_verified'],'current-season player coverage:',result['players_with_current_stats'])
    print('TheSportsDB scanned this run:',done,'matched newly:',matched,'issues:',len(result['issues']))
def selftest():
    today=dt.date(2026,11,17)
    rows={'matches':[{'date':'2026-11-10','team1':'A','team2':'B','score':{'ft':[2,1]}},
                     {'date':'2026-11-19','team1':'C','team2':'D','score':{'ft':[1,0]}},
                     {'date':'2026-11-02','team1':'E','team2':'F','score':{'ft':[]}}]}
    assert len(parse_openfootball(rows,'Premier League',today))==1
    player={'id':'p123','name':'John A Player','birth':'2000-01-01'}
    assert verify_identity({'strSport':'Soccer','strPlayer':'John A Player','dateBorn':'2000-01-01'},player)
    assert not verify_identity({'strSport':'Soccer','strPlayer':'John A Player','dateBorn':'2001-01-01'},player)
    assert not verify_identity({'strSport':'Soccer','strPlayer':'John A Player','dateBorn':'2000-01-01'},
                               {'name':'Somebody Else','birth':'2000-01-01'})
    stats=[{'idPlayer':'123','idLeague':'4328','strSeason':'2026-2027','strLeague':'English Premier League',
            'strStatistic':'Goals','strValue':'3'}]
    parsed=parse_sportsdb_stats(stats,'123')
    assert len(parsed)==1 and parsed[0]['stats']['goals']==3 and not parsed[0]['is_complete']
    assert not licensed_photo({'strCreativeCommons':'No','strCutout':'https://r2.thesportsdb.com/images/media/player/cutout/test.png'})
    print('Free-source parsers, identity constraints, future fixture and photo licence tests PASS')
def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--self-test',action='store_true')
    parser.add_argument('--batch',type=int,default=int(os.getenv('SPORTSDB_BATCH','48')))
    args=parser.parse_args()
    if args.self_test:selftest()
    else:collect(batch=args.batch)
if __name__=='__main__':main()
