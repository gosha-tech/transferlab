#!/usr/bin/env python3
"""Expand TransferLab with uniquely identified, match-backed ARCHIVAL players.

The upstream transfermarkt-datasets snapshot stops in June/July 2026. This is
NOT a 2026/27 roster source. A new player is included only after real appearances
with at least 450 minutes in 2025/26 (or 2025/2026 calendar season) and exact
TM-ID linkage. No image_url from the archive is used: portraits need separate
display rights. Duplicate or ambiguously identified player names are rejected.
"""
from __future__ import annotations
from collections import defaultdict
from datetime import date,datetime,timezone
from pathlib import Path
import argparse,csv,gzip,io,json,re,unicodedata,urllib.request

ROOT=Path(__file__).resolve().parents[1]
CACHE=ROOT/'data'/'catalog_expansion.json'
BASE='https://pub-e682421888d945d684bcae8890b0ec20.r2.dev/data/'
SOURCE='dcaribou/transfermarkt-datasets; last observed appearances 2026-06-28'
MAX_NEW=6000
MIN_MINUTES=450
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
 'IT2':'Serie B','FR2':'Ligue 2'
}
CUP_CODES={'CL','EL','ECL','DFB','FAC','CGB','CDR','NLP','USC','POCP'}
CALENDAR={'MLS1','BRA1'}
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
        not birth or not (1990<=birth.year<=2011) or
        birth>date(2026,7,6) or year!=2025 or not league or not role):
        return None
    # Known snapshot is 2025/26; never relabel club as a verified Nov-2026 roster.
    p={'id':'tm-player-'+pid,'tm_player_id':pid,
       'name':name,'web':name.split()[-1],'team':club,
       'league':league,'pos':role[0],'scoutRole':role[1],
       'displayPosition':role[2],'position_source':SOURCE,
       'positionAsOf':'2026-07','birth':birth.isoformat(),
       'season':'2025/26','origin':'transfermarkt_archived_2026',
       'teamArchiveAsOf':'2026-07','originSource':SOURCE}
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
        if (day is None or not (date(2024,7,1)<=day<=date(2026,6,28)) or
            (comp not in LEAGUES and comp not in CUP_CODES) or not gid):
            continue
        season=season_of(day,comp)
        if season not in ('2024/25','2025/26','2025','2026'):continue
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
def select(profiles, totals, limit=MAX_NEW):
    eligible=[]
    for tm,p in profiles.items():
        stats=totals.get(tm,{})
        # For calendar championships use the last actual full campaign 2025.
        # A 2026-only partial set cannot certify a complete 2026 season.
        reference='2025' if p['league'] in ('MLS','Brasileirão') else '2025/26'
        minutes=sum(v['stats']['minutes'] for (season,comp),v in stats.items()
                    if season==reference and comp in LEAGUES)
        if minutes<MIN_MINUTES:continue
        age=2026-int(p['birth'][:4])
        eligible.append((int(age>23),int(age>27),-minutes,tm,p,stats))
    eligible.sort(key=lambda r:r[:4])
    chosen=eligible[:limit]
    result_players=[]
    by_season=defaultdict(lambda:defaultdict(list))
    for _,_,_,tm,p,history in chosen:
        result_players.append(p)
        for (season,comp),row in sorted(history.items()):
            by_season[season][p['id']].append(row)
    return result_players,{k:dict(v) for k,v in by_season.items()}
def build(profiles_rows,appearance_rows,limit=MAX_NEW):
    profiles={}
    for row in profiles_rows:
        p=profile(row)
        if p:profiles[p['tm_player_id']]=p
    totals=aggregate(profiles,appearance_rows)
    players,by_season=select(profiles,totals,limit)
    return {'version':1,'source':SOURCE,'archived_through':'2026-06-28',
            'players':players,'by_season':by_season,'profiles_eligible':len(profiles),
            'stat_verified_profiles':len(players)}
def download():
    if CACHE.exists():
        cached=json.loads(CACHE.read_text(encoding='utf-8'))
        if cached.get('version')==1 and cached.get('players'):
            print('Reusing archival expansion cache:',len(cached['players']))
            return cached
    data=build(stream('players.csv.gz'),stream('appearances.csv.gz'))
    if len(data['players'])<600:
        raise RuntimeError('Refusing tiny, malformed historical expansion; minimum 600 players')
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
        'source_profiles':len(cache.get('players') or []),
        'note':'Historical roster, never independently verified as November 2026 current club'
    }
    root['leagueCatalog']=list(dict.fromkeys(
        root.get('leagueCatalog',[])+[p['league'] for p in fresh]))
    payload=json.dumps(root,ensure_ascii=False,separators=(',',':')).replace('</','<\\/')
    page.write_text(content[:match.start(2)]+payload+content[match.end(2):],encoding='utf-8')
    print('Expanded visible TransferLab roster by',len(fresh),
          'to',len(root['players']),'profiles')
    return len(fresh)
def selftest():
    def test_profile(i,age=2003,league='NL1',club='Ajax'):
        return {'player_id':str(i),'name':f'Player {i}','current_club_name':club,
                'current_club_domestic_competition_id':league,
                'date_of_birth':f'{age}-03-01','sub_position':'Left-Back',
                'last_season':'2025'}
    one=test_profile(1)
    assert profile(one)['league']=='Eredivisie'
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
    assert len(data['players'])==1
    season=data['by_season']['2025/26']['tm-player-1'][0]
    assert season['stats']['minutes']==540
    assert season['stats']['goals']==2
    assert season['stats']['matches']==6
    assert len({p['id'] for p in data['players']})==len(data['players'])
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
