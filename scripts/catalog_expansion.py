#!/usr/bin/env python3
"""Source-linked archival profiles for a 10,000+ player TransferLab catalogue.

Each addition needs an exact provider player ID, DOB, position, dated roster
source and real match appearances. Higher-minute players come first; low-minute
players remain labelled as limited-evidence rather than receiving fabricated
statistics or full-confidence indices. Market values and contract expiries from
the archive do not prove a current valuation or valid 2026/27 contract.
"""
from __future__ import annotations
from collections import defaultdict,Counter
from datetime import date,datetime,timezone
from pathlib import Path
import argparse,csv,gzip,io,json,re,unicodedata,urllib.request
from zipfile import ZipFile

ROOT=Path(__file__).resolve().parents[1]
CACHE=ROOT/'data'/'catalog_expansion.json'
BASE='https://pub-e682421888d945d684bcae8890b0ec20.r2.dev/data/'
SOURCE='dcaribou/transfermarkt-datasets; last observed appearances 2026-06-28'
CACHE_VERSION=3
TARGET_TOTAL=10500
MAX_NEW=12500
MIN_MINUTES=1
MIN_SOLID_MINUTES=450
# Transfermarkt competition IDs. A league label is assigned ONLY from a
# stable, known ID; unsupported IDs are skipped rather than guessed.
LEAGUES={
 'GB1':'Premier League','ES1':'La Liga','L1':'Bundesliga',
 'IT1':'Serie A','FR1':'Ligue 1','PO1':'Primeira Liga',
 'BE1':'Belgian Pro League','TR1':'Süper Lig','SA1':'Saudi Pro League',
 'MLS1':'MLS','BRA1':'Brasileirão','NL1':'Eredivisie',
 'A1':'Austrian Bundesliga','DK1':'Danish Superliga',
 'C1':'Swiss Super League','GR1':'Greek Super League',
 'SC1':'Scottish Premiership','GB2':'EFL Championship',
 'ES2':'Segunda División','L2':'2. Bundesliga',
 'IT2':'Serie B','FR2':'Ligue 2',
 # Exact codes cross-checked against dcaribou/transfermarkt-datasets'
 # published competitions.json (not inferred from club names).
 'TS1':'Czech First League','PL1':'Ekstraklasa',
 'KR1':'Croatian HNL','SER1':'Serbian SuperLiga',
 'RO1':'Romanian SuperLiga','UKR1':'Ukrainian Premier League',
 'RU1':'Russian Premier League','MEX1':'Liga MX',
 'AUS1':'A-League Men',
 # Calendar-year domestic competitions verified against competitions.json.
 'ARG1':'Argentine Primera División',
 'NO1':'Eliteserien','SE1':'Allsvenskan',
 'JAP1':'J1 League','RSK1':'K League 1'
}
CUP_CODES={'CL','EL','ECL','DFB','FAC','CGB','CDR','NLP','USC','POCP'}
CALENDAR={'MLS1','BRA1','ARG1','NO1','SE1','JAP1','RSK1'}
CALENDAR_NAMES={LEAGUES[code] for code in CALENDAR}
POSITION={
 'Goalkeeper':('Goalkeeper','GK','GK'),
 'Centre-Back':('Defender','CB','CB'),
 'Left-Back':('Defender','LB/RB','LB'),
 'Right-Back':('Defender','LB/RB','RB'),
 'Defensive Midfield':('Midfielder','DM','DM'),
 'Central Midfield':('Midfielder','CM','CM'),
 'Attacking Midfield':('Midfielder','AM','AM'),
 'Right Midfield':('Midfielder','LW/RW','RM'),
 'Left Midfield':('Midfielder','LW/RW','LM'),
 'Right Winger':('Forward','LW/RW','RW'),
 'Left Winger':('Forward','LW/RW','LW'),
 'Centre-Forward':('Forward','ST','ST'),
 'Second Striker':('Forward','ST','SS')
}
def norm(s):
    s=unicodedata.normalize('NFKD',str(s or '').casefold())
    return re.sub('[^a-z0-9а-я]','', ''.join(c for c in s if not unicodedata.combining(c)))
def stream(filename):
    req=urllib.request.Request(BASE+filename,headers={'User-Agent':'TransferLab/catalog-expansion-1.0 (archived data)'})
    with urllib.request.urlopen(req,timeout=130) as response:
        with gzip.GzipFile(fileobj=response) as archive:
            with io.TextIOWrapper(archive,encoding='utf-8-sig',newline='') as f:
                yield from csv.DictReader(f)
def parse_day(s):
    try:return date.fromisoformat(str(s or '')[:10])
    except (ValueError,TypeError):return None
def numeric(s):
    try:return max(0,int(float(s or 0)))
    except (ValueError,TypeError,OverflowError):return 0
def profile(row):
    pid=str(row.get('player_id') or '').strip()
    birth=parse_day(row.get('date_of_birth'))
    name=str(row.get('name') or '').strip()
    club=str(row.get('current_club_name') or '').strip()
    league=LEAGUES.get(str(row.get('current_club_domestic_competition_id') or '').strip())
    role=POSITION.get(str(row.get('sub_position') or '').strip())
    year=numeric(row.get('last_season'))
    if (not pid.isdigit() or not (1<=len(name)<=105) or not club or
        not birth or not (1987<=birth.year<=2011) or
        birth>date(2026,7,6) or (year not in (2023,2024,2025,2026) if league in CALENDAR_NAMES else year not in (2023,2024,2025)) or
        not league or not role):
        return None
    # Known snapshot is 2025/26; never relabel club as a verified Nov-2026 roster.
    p={'id':'tm-player-'+pid,'tm_player_id':pid,
       'name':name,'web':name.split()[-1],'team':club,
       'league':league,'pos':role[0],'scoutRole':role[1],
       'displayPosition':role[2],'position_source':SOURCE,
       'positionAsOf':'2026-07','birth':birth.isoformat(),
       'season':'2025' if league in CALENDAR_NAMES else '2025/26',
       'origin':'transfermarkt_archived_2026',
       'teamArchiveAsOf':'2026-07','originSource':SOURCE,
       'clubLastObservedSeason':year}
    foot=str(row.get('foot') or '').strip().lower()
    if foot in ('left','right','both'):p['foot']=foot
    height=numeric(row.get('height_in_cm'))
    if 145<=height<=220:p['height']=height
    expiry=parse_day(row.get('contract_expiration_date'))
    if expiry:
        p['contractUntilArchive']=expiry.isoformat()
        p['contractArchiveAsOf']='2026-07'
    value=numeric(row.get('market_value_in_eur'))
    if 0<value<=500_000_000:p['marketValueArchiveEUR']=value
    return p
def season_of(day,comp):
    if comp in CALENDAR:return str(day.year)
    y=day.year if day.month>=7 else day.year-1
    return str(y)+'/'+str((y+1)%100).zfill(2)
def aggregate(profiles, rows):
    totals=defaultdict(dict)
    seen=set()
    for a in rows:
        pid=str(a.get('player_id') or '').strip()
        if pid not in profiles:continue
        day=parse_day(a.get('date'))
        comp=str(a.get('competition_id') or '')
        gid=str(a.get('game_id') or a.get('appearance_id') or '')
        if (day is None or not (date(2023,7,1)<=day<=date(2026,6,28)) or
            (comp not in LEAGUES and comp not in CUP_CODES) or not gid):
            continue
        season=season_of(day,comp)
        if season not in ('2023/24','2024/25','2025/26','2023','2024','2025','2026'):continue
        marker=(pid,gid,comp)
        if marker in seen:continue
        seen.add(marker)
        bucket=totals[pid].setdefault((season,comp),
                   {'id':'tm-'+comp,'name':LEAGUES.get(comp,comp),
                    'source':'historical_appearances','source_as_of':'2026-06-28',
                    'stats':{'matches':0,'minutes':0,'goals':0,'assists':0,
                             'yellow_cards':0,'red_cards':0}})
        stats=bucket['stats']
        stats['matches']+=1
        for dst,src in (('minutes','minutes_played'),('goals','goals'),
                        ('assists','assists'),('yellow_cards','yellow_cards'),
                        ('red_cards','red_cards')):
            stats[dst]+=numeric(a.get(src))
    return totals
def select(profiles, totals, limit=MAX_NEW, exclude_tm=None, exclude_names=None):
    eligible=[]
    known_tm=set(str(x) for x in (exclude_tm or set()))
    known_names=set(exclude_names or set())
    for tm,p in profiles.items():
        if tm in known_tm or norm(p['name']) in known_names:
            continue
        stats=totals.get(tm,{})
        # Use the most recent historically evidenced domestic season. Teams
        # from these snapshots are not proof of current squad membership.
        candidates=('2025','2024','2023') if p['league'] in CALENDAR_NAMES else (
            '2025/26','2024/25','2023/24')
        reference=next((year for year in candidates if sum(
            v['stats']['minutes'] for (season,comp),v in stats.items()
            if season==year and comp in LEAGUES)>=MIN_MINUTES),None)
        if reference is None:continue
        minutes=sum(v['stats']['minutes'] for (season,comp),v in stats.items()
                    if season==reference and comp in LEAGUES)
        older_only=reference!=candidates[0]
        # 2024/25-only profiles are last in the catalogue priority, and
        # never passed off as having played in 2025/26 or 2026/27.
        quality_tier=0 if minutes>=450 else 1 if minutes>=180 else 2 if minutes>=90 else 3
        tier=(4 if reference==candidates[1] else 8) + quality_tier if older_only else quality_tier
        age=2026-int(p['birth'][:4])
        p['season']=reference
        p['archiveReferenceSeason']=reference
        p['archiveLastSeasonMinutes']=minutes
        p['archiveStatEvidence']='older_archival' if older_only else (
            'regular' if tier==0 else ('limited' if tier<=2 else 'very_limited'))
        eligible.append((tier,int(age>23),int(age>27),int(not bool(p.get('contractUntilArchive'))),-minutes,tm,p,stats))
    eligible.sort(key=lambda r:r[:6])
    chosen=[]
    for item in eligible:
        tm,p=item[5],item[6]
        key=norm(p['name'])
        if key in known_names:continue
        known_names.add(key)
        chosen.append(item)
        if len(chosen)>=limit:break
    result_players=[]
    by_season=defaultdict(lambda:defaultdict(list))
    for _,_,_,_,_,tm,p,history in chosen:
        result_players.append(p)
        for (season,comp),row in sorted(history.items()):
            by_season[season][p['id']].append(row)
    return result_players,{k:dict(v) for k,v in by_season.items()}
def build(profiles_rows,appearance_rows,limit=MAX_NEW,exclude_tm=None,exclude_names=None):
    profiles={}
    for row in profiles_rows:
        p=profile(row)
        if p:profiles[p['tm_player_id']]=p
    totals=aggregate(profiles,appearance_rows)
    # Report real-source expansion opportunities, not fabricated profiles.
    possible_previous=0
    for tm,p in profiles.items():
        if tm in set(str(x) for x in (exclude_tm or ())) or norm(p['name']) in (exclude_names or set()):
            continue
        history=totals.get(tm) or {}
        old='2024' if p['league'] in CALENDAR_NAMES else '2024/25'
        cur='2025' if p['league'] in CALENDAR_NAMES else '2025/26'
        old_minutes=sum(v['stats']['minutes'] for (season,comp),v in history.items()
                        if season==old and comp in LEAGUES)
        cur_minutes=sum(v['stats']['minutes'] for (season,comp),v in history.items()
                        if season==cur and comp in LEAGUES)
        if old_minutes>0 and cur_minutes==0:possible_previous+=1
    players,by_season=select(profiles,totals,limit,exclude_tm,exclude_names)
    return {'version':CACHE_VERSION,'source':SOURCE,'archived_through':'2026-06-28',
            'players':players,'by_season':by_season,'profiles_eligible':len(profiles),
            'stat_verified_profiles':len(players),
            'possible_previous_season_only':possible_previous,
            'included_by_league':dict(Counter(p['league'] for p in players)),
            'evidence':{
                'last_season_minutes_450':sum(p['archiveLastSeasonMinutes']>=450 for p in players),
                'last_season_minutes_180':sum(p['archiveLastSeasonMinutes']>=180 for p in players),
                'last_season_minutes_90':sum(p['archiveLastSeasonMinutes']>=90 for p in players),
                'last_season_minutes_under_90':sum(p['archiveLastSeasonMinutes']<90 for p in players)
            }}
def seed_identifiers():
    # Do not spend slots on profiles already in the site's seed or enriched
    # identities. Keep their existing IDs, contracts and indexed statistics.
    with ZipFile(ROOT/'TransferLab_RESTORED_2026-11-16.zip') as archive:
        html=archive.read('index.html').decode('utf-8')
    m=re.search(r'<script id="embeddedData" type="application/json">(.*?)</script>',html,re.S)
    if not m:raise RuntimeError('Cannot load original TransferLab catalogue')
    base=json.loads(m.group(1)).get('players') or []
    names={norm(p.get('name')) for p in base if p.get('name')}
    tmids={str(p['tm_player_id']) for p in base if p.get('tm_player_id')}
    try:
        enrichment=json.loads((ROOT/'data'/'profile_enrichment.json').read_text(encoding='utf-8'))
        tmids.update(str(v['tm_player_id']) for v in
            (enrichment.get('profiles') or {}).values() if v.get('tm_player_id'))
    except (OSError,ValueError):pass
    return len(base),names,tmids

def download():
    if CACHE.exists():
        cached=json.loads(CACHE.read_text(encoding='utf-8'))
        if cached.get('version')==CACHE_VERSION and cached.get('players'):
            print('Reusing archival expansion cache:',len(cached['players']))
            return cached
    base_size,names,tmids=seed_identifiers()
    data=build(stream('players.csv.gz'),stream('appearances.csv.gz'),
               limit=max(0,TARGET_TOTAL-base_size),
               exclude_tm=tmids,exclude_names=names)
    data['seed_count']=base_size
    data['target_total']=TARGET_TOTAL
    print('SOURCE ELIGIBLE:',len(data['players']),'previous-only candidates:',data['possible_previous_season_only'],
          'league counts:',data['included_by_league'])
    if base_size+len(data['players'])<10000:
        raise RuntimeError('Verified source-backed candidates below 10000 target: '+
            str(base_size+len(data['players']))+
            '; do not publish a fabricated 10k catalogue')
    data['built_at_utc']=datetime.now(timezone.utc).isoformat(timespec='seconds')
    CACHE.parent.mkdir(parents=True,exist_ok=True)
    tmp=CACHE.with_suffix('.tmp')
    tmp.write_text(json.dumps(data,ensure_ascii=False,separators=(',',':'))+'\n',encoding='utf-8')
    tmp.replace(CACHE)
    print('Verified archival expansion:',len(data['players']),'players,',
          len(data['by_season']),'seasons')
    return data
def inject(page):
    content=page.read_text(encoding='utf-8')
    match=re.search(r'(<script id="embeddedData" type="application/json">)(.*?)(</script>)',content,re.S)
    if not match:raise RuntimeError('Cannot find embedded player registry')
    root=json.loads(match.group(2))
    try:cache=json.loads(CACHE.read_text(encoding='utf-8'))
    except (OSError,ValueError):cache={}
    original=root.get('players') or []
    # Reject any linked original Transfermarkt player. Also avoid name/DOB
    # duplicates where an original record carries another provider ID.
    existing_tm={str(p.get('tm_player_id')) for p in original if p.get('tm_player_id')}
    try:
        old=json.loads((ROOT/'data'/'profile_enrichment.json').read_text(encoding='utf-8'))
        existing_tm.update(str(v.get('tm_player_id')) for v in old.get('profiles',{}).values()
                           if v.get('tm_player_id'))
    except (OSError,ValueError):pass
    existing_names={norm(p.get('name')) for p in original if p.get('name')}
    existing_ids={str(p.get('id')) for p in original}
    fresh=[]
    for p in cache.get('players') or []:
        if (not isinstance(p,dict) or str(p.get('id')) in existing_ids or
            str(p.get('tm_player_id')) in existing_tm or
            norm(p.get('name')) in existing_names):
            continue
        fresh.append(p);existing_ids.add(str(p['id']))
        existing_names.add(norm(p['name']))
    root['players'].extend(fresh)
    root['catalogueExpansion']={
        'added':len(fresh),'source':SOURCE,'archive_as_of':'2026-07',
        'archive_minimum_real_minutes':MIN_MINUTES,
        'archive_evidence':cache.get('evidence') or {},
        'target_total':cache.get('target_total'),
        'source_profiles':len(cache.get('players') or []),
        'note':'Historical roster, never independently verified as November 2026 current club'
    }
    root['leagueCatalog']=list(dict.fromkeys(
        root.get('leagueCatalog',[])+[p['league'] for p in fresh]))
    payload=json.dumps(root,ensure_ascii=False,separators=(',',':')).replace('</','<\\/')
    page.write_text(content[:match.start(2)]+payload+content[match.end(2):],encoding='utf-8')
    print('Expanded visible TransferLab roster by',len(fresh),
          'to',len(root['players']),'profiles')
    if len(root['players'])<10000:
        raise RuntimeError('Expanded published catalogue below requested 10000 profiles')
    return len(fresh)
def selftest():
    def test_profile(i,age=2003,league='NL1',club='Ajax'):
        return {'player_id':str(i),'name':f'Player {i}','current_club_name':club,
                'current_club_domestic_competition_id':league,
                'date_of_birth':f'{age}-03-01','sub_position':'Left-Back',
                'last_season':'2025'}
    one=test_profile(1)
    assert profile(one)['league']=='Eredivisie'
    assert profile(dict(one,current_club_domestic_competition_id='PL1'))['league']=='Ekstraklasa'
    assert profile(dict(one,current_club_domestic_competition_id='TS1'))['league']=='Czech First League'
    assert profile(dict(one,current_club_domestic_competition_id='KR1'))['league']=='Croatian HNL'
    assert profile(dict(one,current_club_domestic_competition_id='ARG1'))['season']=='2025'
    assert profile(dict(one,current_club_domestic_competition_id='ARG1',last_season='2026'))['season']=='2025'
    assert profile(dict(one,current_club_domestic_competition_id='NO1'))['league']=='Eliteserien'
    assert profile(dict(one,last_season='2024'))['clubLastObservedSeason']==2024
    assert profile(dict(one,last_season='2022')) is None
    assert season_of(date(2025,3,15),'ARG1')=='2025'
    assert season_of(date(2025,3,15),'NO1')=='2025'
    assert profile({**one,'sub_position':'Unknown'}) is None
    assert profile({**one,'date_of_birth':'abc'}) is None
    appearances=[
     {'player_id':'1','game_id':'100','date':'2025-10-05',
      'competition_id':'NL1','minutes_played':'90','goals':'2','assists':'1'},
     {'player_id':'1','game_id':'100','date':'2025-10-05',
      'competition_id':'NL1','minutes_played':'90','goals':'2','assists':'1'},
     *[{'player_id':'1','game_id':str(i),'date':'2025-10-06',
        'competition_id':'NL1','minutes_played':'90'} for i in range(101,106)],
     {'player_id':'2','game_id':'200','date':'2025-11-08',
      'competition_id':'NL1','minutes_played':'30'}]
    data=build([one,test_profile(2)],appearances)
    assert len(data['players'])==2
    season=data['by_season']['2025/26']['tm-player-1'][0]
    assert season['stats']['minutes']==540
    assert season['stats']['goals']==2
    assert season['stats']['matches']==6
    assert len({p['id'] for p in data['players']})==len(data['players'])
    assert data['players'][0]['archiveLastSeasonMinutes']==540
    assert data['players'][0]['archiveStatEvidence']=='regular'
    data_small=build([one,test_profile(2)],[{'player_id':'2','game_id':'201',
        'date':'2025-11-08','competition_id':'NL1','minutes_played':'65'}])
    assert len(data_small['players'])==1
    assert data_small['players'][0]['archiveStatEvidence']=='very_limited'
    assert data_small['players'][0]['archiveLastSeasonMinutes']==65
    prev=build([test_profile(3,league='NL1')],[{'player_id':'3','game_id':'300',
        'date':'2024-10-07','competition_id':'NL1','minutes_played':'90',
        'goals':'1','assists':'1'}])
    assert len(prev['players'])==1
    assert prev['players'][0]['season']=='2024/25'
    assert prev['players'][0]['archiveStatEvidence']=='older_archival'
    assert prev['by_season']['2024/25']['tm-player-3'][0]['stats']['minutes']==90
    early=build([test_profile(4)],[{'player_id':'4','game_id':'400',
        'date':'2023-10-07','competition_id':'NL1','minutes_played':'95'}])
    assert early['players'][0]['archiveReferenceSeason']=='2023/24'
    assert early['players'][0]['archiveStatEvidence']=='older_archival'
    data_excluded=build([one,test_profile(2)],appearances,exclude_names={norm(one['name'])})
    assert all(norm(p['name'])!=norm(one['name']) for p in data_excluded['players'])
    assert data['version']==CACHE_VERSION
    print('Historical expansion exact-ID joins, minutes and dedup PASS')
def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--download',action='store_true')
    parser.add_argument('--embed',default=None)
    parser.add_argument('--self-test',action='store_true')
    args=parser.parse_args()
    if args.self_test:selftest()
    if args.download:download()
    if args.embed:inject(ROOT/args.embed)
if __name__=='__main__':main()
