#!/usr/bin/env python3
"""Find genuinely free, identity-verified football portraits on Wikimedia Commons.

No name-only image assignment: require exact birth date and normalized identity
in Wikidata. Only accept Commons files with machine-readable open-image licence
and keep author, licence URL and file page for clickable attribution.

Progressively inspect a subset of profiles each daily run; never pretend that
an unlicensed or unidentified picture is the player.
"""
import argparse,datetime as dt,html as entities,json,os,pathlib,re,time,unicodedata,urllib.parse,urllib.error,urllib.request
from zipfile import ZipFile

ROOT=pathlib.Path(__file__).resolve().parents[1]
OUT=ROOT/'data'/'commons_photos.json'
PROFILE_CACHE=ROOT/'data'/'profile_enrichment.json'
API_WD='https://www.wikidata.org/w/api.php'
API_COMMONS='https://commons.wikimedia.org/w/api.php'
UA='TransferLab/6.1 (noncommercial football portraits; github.com/gosha-tech/transferlab)'
BIRTH_FIELD='P569'
IMAGE_FIELD='P18'
LAST_REQUEST=0.0
class Quota(Exception):pass
def norm(v):
    t=unicodedata.normalize('NFKD',str(v or '').lower())
    return re.sub(r'[^a-z0-9а-я]','', ''.join(c for c in t if not unicodedata.combining(c)))
def get(url,params):
    global LAST_REQUEST
    wait=float(os.getenv('WIKIMEDIA_REQUEST_INTERVAL','2.0'))-(time.monotonic()-LAST_REQUEST)
    if LAST_REQUEST and wait>0:time.sleep(wait)
    LAST_REQUEST=time.monotonic()
    uri=url+'?'+urllib.parse.urlencode(params)
    req=urllib.request.Request(uri,headers={'User-Agent':UA,'Accept':'application/json'})
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req,timeout=22) as resp:return json.load(resp)
        except urllib.error.HTTPError as e:
            if e.code not in (429,503):raise
            if attempt==2:raise Quota('Wikimedia rate limit or service unavailability') from e
            # Respect Retry-After when provided; avoid hammering the API.
            header=e.headers.get('Retry-After') or ''
            seconds=float(header) if re.fullmatch(r'\d{1,2}',header) else 6.0*(attempt+1)
            time.sleep(min(20,max(3,seconds)))
def claim_value(item,prop):
    for snak in item.get('claims',{}).get(prop,[]) or []:
        try:
            v=snak['mainsnak']['datavalue']['value']
            if v is not None:return v
        except (TypeError,KeyError):pass
    return None
def wikidata_match(name,birth,search,entities_dict):
    candidates=[]
    for result in search.get('search',[]) or []:
        iid=result.get('id')
        item=entities_dict.get(iid) or {}
        if not item.get('claims'):continue
        born=claim_value(item,BIRTH_FIELD)
        if not isinstance(born,dict):continue
        timestamp=str(born.get('time') or '')
        m=re.search(r'(\d{4})-(\d{2})-(\d{2})',timestamp)
        if not m or '-'.join(m.groups())!=str(birth):continue
        possible=[result.get('label'),result.get('display',{}).get('label',{}).get('value')]
        possible.extend(x.get('value') for xs in item.get('aliases',{}).values() for x in xs)
        if norm(name) not in {norm(x) for x in possible if x}:continue
        file=claim_value(item,IMAGE_FIELD)
        if not isinstance(file,str) or not file.strip():continue
        candidates.append((iid,file))
    # If two different same-name/same-birthday people were found, do not guess.
    return candidates[0] if len(set(x[0] for x in candidates))==1 else None
def plain(v):
    return entities.unescape(re.sub('<[^>]+>','',str(v or ''))).strip()[:170]
def licence_ok(meta):
    value=lambda key:str((meta.get(key) or {}).get('value') or '').strip()
    licence=value('LicenseShortName').lower()
    license_url=value('LicenseUrl')
    if not licence:return None
    allowed=licence.startswith(('cc by ','cc by-sa ','cc0','public domain')) or licence=='pd'
    if not allowed:return None
    if licence.startswith('cc by ') or licence.startswith('cc by-sa '):
        if 'creativecommons.org/licenses/' not in license_url:return None
    artist=plain(value('Artist') or value('Credit') or '')
    if (licence.startswith('cc by ') or licence.startswith('cc by-sa ')) and not artist:return None
    if not license_url and licence not in ('pd','public domain'):return None
    return {'licence':value('LicenseShortName'),'licence_url':license_url or 'https://commons.wikimedia.org/wiki/Commons:Licensing',
            'artist':artist or 'Public-domain contributor'}
def verify_commons(filename,qid):
    if not filename or len(filename)>180: return None
    data=get(API_COMMONS,{
      'action':'query','titles':'File:'+filename,'format':'json',
      'prop':'imageinfo','iiprop':'url|extmetadata|mime','iiurlwidth':'240'
    })
    pages=(data.get('query') or {}).get('pages') or {}
    for p in pages.values():
        for info in p.get('imageinfo',[]) or []:
            rights=licence_ok(info.get('extmetadata') or {})
            url=info.get('thumburl') or info.get('url')
            if rights and isinstance(url,str) and url.startswith('https://upload.wikimedia.org/'):
                return {'wikidata_id':qid,'url':url,
                        'file_page':info.get('descriptionurl') or ('https://commons.wikimedia.org/wiki/File:'+urllib.parse.quote(filename.replace(' ','_'))),
                        'file':filename,**rights,'identity_proof':'Wikidata DOB+name+P18'}
    return None
def read_players():
    with ZipFile(ROOT/'TransferLab_RESTORED_2026-11-16.zip') as z:
        raw=z.read('index.html').decode('utf-8')
    found=re.search(r'<script id="embeddedData" type="application/json">(.*?)</script>',raw,re.S)
    if not found:raise RuntimeError('No player registry')
    players=json.loads(found.group(1))['players']
    try:
        cache=json.loads(PROFILE_CACHE.read_text(encoding='utf-8'))
        enrichment=cache.get('profiles') or {}
    except (OSError,ValueError):enrichment={}
    for p in players:
        info=enrichment.get(str(p.get('id'))) or {}
        if not p.get('birth') and info.get('birth'):p['birth']=info['birth']
    # New archived players also have verified date-of-birth + immutable TM ID.
    # Wikimedia still requires an independent Wikidata identity and open license.
    try:
        expanded=json.loads((ROOT/'data'/'catalog_expansion.json').read_text(encoding='utf-8'))
        names={norm(p.get('name')) for p in players}
        for p in expanded.get('players') or []:
            if p.get('name') and norm(p['name']) not in names:
                players.append(p);names.add(norm(p['name']))
    except (OSError,ValueError):
        pass
    return players
def lookup(p):
    name=p.get('name') or ''
    birth=str(p.get('birth') or '')[:10]
    if not name or not re.fullmatch(r'\d{4}-\d\d-\d\d',birth):return None
    search=get(API_WD,{'action':'wbsearchentities','search':name,'language':'en','type':'item','format':'json','limit':'4'})
    qids=[x.get('id') for x in search.get('search',[]) if re.fullmatch(r'Q\d+',str(x.get('id') or ''))]
    if not qids:return None
    response=get(API_WD,{'action':'wbgetentities','ids':'|'.join(qids),'props':'claims|aliases','languages':'en','format':'json'})
    possible=wikidata_match(name,birth,search,response.get('entities') or {})
    if not possible:return None
    return verify_commons(possible[1],possible[0])
def sync(batch=75):
    players=read_players()
    try:cache=json.loads(OUT.read_text(encoding='utf-8'))
    except (OSError,ValueError):cache={}
    previous={str(k):v for k,v in (cache.get('photos') or {}).items() if isinstance(v,dict)}
    missed={str(k):v for k,v in (cache.get('checked') or {}).items()}
    # Never run exhaustive sweeps after a rate limit. Increment cursor only on actual checks.
    start=int(cache.get('cursor') or 0)%len(players)
    today=dt.datetime.now(dt.timezone.utc).date()
    successes=0;checked=0;rate_limited=None
    for i in range(min(max(0,batch),len(players))):
        p=players[(start+i)%len(players)]
        pid=str(p['id'])
        if pid in previous:
            checked+=1
            continue
        # Retry unsuccessful identity/photo searches after two weeks. New photos,
        # corrected birth dates and improvements in Wikimedia metadata can appear.
        if pid in missed:
            try:
                last_checked=dt.date.fromisoformat(str(missed[pid])[:10])
                if 0 <= (today-last_checked).days < 14:
                    checked+=1
                    continue
            except ValueError:
                pass
        try:
            photo=lookup(p)
        except Quota as exc:
            rate_limited=str(exc)
            # Do not retry the same first rate-limited player forever. Move the
            # cursor to a different player for the next scheduled run.
            checked+=1
            break
        except (OSError,ValueError,RuntimeError):
            checked+=1
            missed[pid]=dt.datetime.now(dt.timezone.utc).date().isoformat()
            continue
        if photo:
            previous[pid]=photo;successes+=1
        else:missed[pid]=dt.datetime.now(dt.timezone.utc).date().isoformat()
        checked+=1
    output={'source':'Wikidata + Wikimedia Commons image metadata',
            'checked_at':dt.datetime.now(dt.timezone.utc).isoformat(timespec='seconds'),
            'photos':previous,'checked':missed,'cursor':(start+checked)%len(players),
            'matched':len(previous),'rate_limited':rate_limited,
            'roster_total':len(players),'new_this_run':successes}
    OUT.parent.mkdir(exist_ok=True,parents=True)
    temp=OUT.with_suffix('.tmp')
    temp.write_text(json.dumps(output,ensure_ascii=False,separators=(',',':'))+'\n',encoding='utf-8')
    temp.replace(OUT)
    print('Wikimedia verified photos:',len(previous),'new:',successes,
          'checked_this_run:',checked,'rate_limited:',bool(rate_limited))
def selftest():
    item={'claims':{'P569':[{'mainsnak':{'datavalue':{'value':{'time':'+2000-05-28T00:00:00Z'}}}}],
                    'P18':[{'mainsnak':{'datavalue':{'value':'Foden photo.jpg'}}}]},
          'aliases':{'en':[{'value':'Phil Foden'}]}}
    result=wikidata_match('Phil Foden','2000-05-28',{'search':[{'id':'Q123','label':'Phil Foden'}]},{'Q123':item})
    assert result==('Q123','Foden photo.jpg')
    assert wikidata_match('Phil Foden','2000-05-29',{'search':[{'id':'Q123','label':'Phil Foden'}]},{'Q123':item}) is None
    rights={'LicenseShortName':{'value':'CC BY-SA 4.0'},
            'LicenseUrl':{'value':'https://creativecommons.org/licenses/by-sa/4.0/'},
            'Artist':{'value':'<a>A Photographer</a>'}}
    assert licence_ok(rights)['artist']=='A Photographer'
    assert licence_ok({'LicenseShortName':{'value':'All rights reserved'}}) is None
    assert licence_ok({'LicenseShortName':{'value':'CC BY 4.0'}}) is None
    print('Wikidata player identity / Commons license parsing PASS')
def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--self-test',action='store_true')
    parser.add_argument('--batch',type=int,default=int(os.getenv('WIKIMEDIA_BATCH','75')))
    args=parser.parse_args()
    if args.self_test:selftest()
    else:sync(batch=args.batch)
if __name__=='__main__':main()
