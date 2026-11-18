#!/usr/bin/env python3
"""Conservative offline player-profile enrichment for TransferLab.

Public Transfermarkt-derived *historical* player profiles; never overwrite
club or assert that historical data are current-season truth.
Player photographs are NOT rehosted because dataset reuse rights do not
grant copyright in portraits. API-Football player-ID images are handled separately.
"""
import argparse,csv,datetime as dt,gzip,io,json,pathlib,re,unicodedata,urllib.request
from collections import defaultdict

ROOT=pathlib.Path(__file__).resolve().parents[1]
SOURCE='https://pub-e682421888d945d684bcae8890b0ec20.r2.dev/data/players.csv.gz'
CACHE=ROOT/'data'/'profile_enrichment.json'
FULL_MAP={
 'Goalkeeper':('Goalkeeper','GK','Goalkeeper'),
 'Centre-Back':('Defender','CB','CB'),
 'Right-Back':('Defender','LB/RB','RB'),
 'Left-Back':('Defender','LB/RB','LB'),
 'Right Midfield':('Midfielder','LW/RW','RM'),
 'Left Midfield':('Midfielder','LW/RW','LM'),
 'Defensive Midfield':('Midfielder','DM','DM'),
 'Central Midfield':('Midfielder','CM','CM'),
 'Attacking Midfield':('Midfielder','AM','AM'),
 'Right Winger':('Forward','LW/RW','RW'),
 'Left Winger':('Forward','LW/RW','LW'),
 'Centre-Forward':('Forward','ST','ST'),
 'Second Striker':('Forward','ST','SS')
}
MANUAL={
 'achrafhakimi':{'name':'Achraf Hakimi','role':'LB/RB','display':'RB','pos':'Defender',
                 'source':'https://www.psg.fr/en/players/achraf-hakimi',
                 'verified':'official-club-profile'}
}
def normalize(x):
    text=unicodedata.normalize('NFKD',str(x or '').casefold())
    return re.sub('[^a-z0-9а-я]','', ''.join(c for c in text if not unicodedata.combining(c)))
def normalized_broad(v):
    return {'Forward':'Forward','Defender':'Defender','Midfielder':'Midfielder','Goalkeeper':'Goalkeeper',
            'Нападающий':'Forward','Защитник':'Defender','Полузащитник':'Midfielder',
            'Вратарь':'Goalkeeper'}.get(v)
def valid_date(value):
    try:
        return dt.date.fromisoformat(str(value)[:10]).isoformat()
    except (ValueError,TypeError):return None
def valid_cm(value):
    try:
        n=int(value)
        return n if 145<=n<=220 else None
    except (ValueError,TypeError):return None
def rank(row):
    try:year=int(row.get('last_season') or 0)
    except ValueError:year=0
    return year
def convert(row):
    sub=(row.get('sub_position') or '').strip()
    out={'tm_player_id':str(row.get('player_id') or '').strip(),
         'source':'https://github.com/dcaribou/transfermarkt-datasets',
         'source_url':row.get('url') or '',
         'archive_as_of':'2026-07',
         'last_season':rank(row)}
    if sub in FULL_MAP:
        out['pos'],out['scoutRole'],out['displayPosition']=FULL_MAP[sub]
    birth=valid_date(row.get('date_of_birth'))
    height=valid_cm(row.get('height_in_cm'))
    foot=(row.get('foot') or '').strip().lower()
    if birth:out['birth']=birth
    if height:out['height']=height
    if foot in ('left','right','both'):out['foot']=foot
    # The underlying July-2026 archive contains contract_expiration_date.
    # This date is a historical observation, not proof of a live contract.
    expiry=valid_date(row.get('contract_expiration_date'))
    if expiry:
        out['contract_until_archive']=expiry
        out['contract_source_as_of']='2026-07'
    value=row.get('market_value_in_eur')
    try:
        euros=int(float(value)) if value not in ('',None) else None
        if euros is not None and 0<=euros<=500_000_000:
            out['market_value_archive_eur']=euros
    except (TypeError,ValueError,OverflowError):
        pass
    return out
def map_profiles(players,rows):
    candidates=defaultdict(list)
    for row in rows:
        name=normalize(row.get('name'))
        if name and rank(row)>=2024:
            candidates[name].append(row)
    result={}; skipped=0
    for p in players:
        name=normalize(p.get('name'))
        options=candidates.get(name,[])
        if not options:continue
        # Exact name + exact club is safer. With a single unique recent profile,
        # accept identity but DO NOT replace an archive club with the dataset club.
        club=normalize(p.get('team'))
        matches=[r for r in options if normalize(r.get('current_club_name'))==club and club]
        if len(matches)==1:
            row=matches[0];confidence='name+club'
        elif len(options)==1 and not matches:
            row=options[0];confidence='unique-name-only'
        else:
            skipped+=1;continue
        info=convert(row)
        info['match_confidence']=confidence
        # A unique name across the entire historical archive is not sufficient
        # to reverse a conflicting broad role. Name + same club is stronger
        # identity evidence and may correct a wrong archive seed position.
        broad=normalized_broad(p.get('pos'))
        if info.get('pos') and broad and broad!=info['pos'] and confidence!='name+club':
            for key in ('pos','scoutRole','displayPosition'):info.pop(key,None)
            info['position_conflict']=True
        result[str(p['id'])]=info
    return result,skipped
def load_rows(source):
    with urllib.request.urlopen(urllib.request.Request(source,headers={'User-Agent':'TransferLab/5.2'}),timeout=80) as resp:
        raw=resp.read(24_000_000)
        if resp.read(1):raise RuntimeError('Enrichment dataset exceeds configured size limit')
    with gzip.GzipFile(fileobj=io.BytesIO(raw)) as z:
        return list(csv.DictReader(io.TextIOWrapper(z,encoding='utf-8-sig')))
def enrich(players,cache):
    mapped={str(k):v for k,v in (cache.get('profiles') or {}).items() if isinstance(v,dict)}
    count=0
    for p in players:
        fields=mapped.get(str(p.get('id'))) or {}
        if fields:
            for k in ('birth','height','foot','source_url','archive_as_of','match_confidence'):
                if fields.get(k) is not None and not p.get(k):p[k]=fields[k]
            if fields.get('contract_until_archive'):
                p['contractUntilArchive']=fields['contract_until_archive']
                p['contractArchiveAsOf']=fields.get('contract_source_as_of','2026-07')
            if fields.get('market_value_archive_eur') is not None:
                p['marketValueArchiveEUR']=fields['market_value_archive_eur']
            trusted_role=fields.get('match_confidence')=='name+club'
            if not p.get('positionVerified') and (trusted_role or not p.get('displayPosition')):
                for k in ('scoutRole','displayPosition'):
                    if fields.get(k):p[k]=fields[k]
                if fields.get('pos') and (trusted_role or p.get('pos') in ('Unknown','Не указана','Other',None)):
                    p['pos']=fields['pos']
                if fields.get('displayPosition'):
                    p['position_source']=fields.get('source_url') or fields.get('source')
                    p['positionAsOf']=fields.get('archive_as_of')
            if any(fields.get(k) for k in ('birth','height','foot','scoutRole')):count+=1
        override=MANUAL.get(normalize(p.get('name')))
        if override:
            if normalized_broad(p.get('pos')) not in (override['pos'],None):continue
            p['pos']=override['pos'];p['scoutRole']=override['role']
            p['displayPosition']=override['display']
            p['position_source']=override['source']
            p['positionVerified']=True
    return count
def get_or_update(players,download=False):
    cache={}
    if CACHE.exists():
        try:cache=json.loads(CACHE.read_text(encoding='utf-8'))
        except (OSError,ValueError):pass
    if download and cache.get('profiles') and int(cache.get('schema_version') or 0)>=2:
        # The snapshot is historical, not live; no need to redownload daily.
        return enrich(players,cache)
    if download:
        try:
            rows=load_rows(SOURCE)
            mapped,skipped=map_profiles(players,rows)
            if not mapped:raise RuntimeError('No safely matched profiles; refusing to clear cache')
            cache={'schema_version':2,'provider':'Transfermarkt datasets — archive, not current rosters',
                   'refreshed_at':dt.datetime.now(dt.timezone.utc).isoformat(),
                   'archive_as_of':'2026-07','source':SOURCE,
                   'ambiguous_skipped':skipped,'profiles':mapped}
            CACHE.parent.mkdir(parents=True,exist_ok=True)
            CACHE.write_text(json.dumps(cache,ensure_ascii=False,separators=(',',':'))+'\n',encoding='utf-8')
            print('Downloaded and matched',len(mapped),'historical player profiles; ambiguous',skipped)
        except (OSError,ValueError,RuntimeError) as exc:
            print('Archive unavailable, keeping cached profiles:',type(exc).__name__,str(exc)[:120])
    return enrich(players,cache)
def self_test():
    entries=[{'id':'7','name':'Achraf Hakimi','team':'Paris Saint-Germain','pos':'Defender'},
             {'id':'8','name':'Different User','team':'Manchester City','pos':'Defender'}]
    rows=[{'name':'Achraf Hakimi','current_club_name':'Paris Saint-Germain',
           'sub_position':'Right-Back','foot':'right','height_in_cm':'181',
           'date_of_birth':'1998-11-04','last_season':'2025','url':'https://example.org'},
          {'name':'Different User','current_club_name':'Manchester City',
           'sub_position':'Centre-Forward','last_season':'2025'}]
    mapped,skipped=map_profiles(entries,rows)
    assert mapped['7']['displayPosition']=='RB'
    assert mapped['7']['height']==181
    assert mapped['8']['displayPosition']=='ST' and not mapped['8'].get('position_conflict')
    n=enrich(entries,{'profiles':mapped})
    assert n==2 and entries[0]['displayPosition']=='RB' and entries[0]['positionVerified']
    assert entries[1]['displayPosition']=='ST' and entries[1]['pos']=='Forward'
    test=convert({'player_id':'42','sub_position':'Right-Back','foot':'left',
                  'contract_expiration_date':'2028-06-30',
                  'market_value_in_eur':'17000000'})
    assert test['displayPosition']=='RB' and test['foot']=='left'
    assert test['contract_until_archive']=='2028-06-30'
    assert test['market_value_archive_eur']==17000000
    assert valid_date('not-a-date') is None
    print('Position enrichment unit tests passed')
def main():
    p=argparse.ArgumentParser();p.add_argument('--download',action='store_true')
    p.add_argument('--self-test',action='store_true');p.add_argument('--source-html',default='_site/index.html')
    args=p.parse_args()
    if args.self_test:return self_test()
    path=ROOT/args.source_html
    s=path.read_text(encoding='utf-8')
    match=re.search(r'(<script id="embeddedData" type="application/json">)(.*?)(</script>)',s,re.S)
    if not match:raise RuntimeError('Missing embedded player data')
    data=json.loads(match.group(2))
    covered=get_or_update(data['players'],download=args.download)
    data['profile_enrichment_coverage']=covered
    new=json.dumps(data,ensure_ascii=False,separators=(',',':')).replace('</','<\\/')
    path.write_text(s[:match.start(2)]+new+s[match.end(2):],encoding='utf-8')
    print('Profiles enriched in build:',covered,'of',len(data['players']))
if __name__=='__main__':main()
