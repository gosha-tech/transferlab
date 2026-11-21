#!/usr/bin/env python3
"""Temporary source audit of player-season provider coverage and valuation formula."""
from pathlib import Path
from zipfile import ZipFile
import re,json,collections

ROOT=Path(__file__).resolve().parents[1]
html=ZipFile(ROOT/'TransferLab_RESTORED_2026-11-16.zip').read('index.html').decode('utf-8')
print("=== Original rolling/index/value formula fragments ===")
for match in re.finditer(r'(?i)(function\s+(?:projectedIndex|rolling\w*|\w*[Vv]alu\w*|compute\w*|model\w*|\w*index\w*)\s*\(|const FORMULA_DRAFT|rolling36|seasonWeights|0\.5\s*\*|\*\s*0\.5|2026/27)',html):
    word=match.group(0)
    if '2026/27' in word:continue
    excerpt=html[max(0,match.start()-65):match.start()+1250]
    print(word,'@',match.start(),re.sub(r'\s+',' ',excerpt)[:1280])
print("=== Source ZIP embedded formula tokens ===")
m=re.search(r'<script id="embeddedData" type="application/json">(.*?)</script>',html,re.S)
root=json.loads(m.group(1))
for k in root.keys():
    if any(x in k.lower() for x in ('formula','model','index','season','weight','market')):
        v=root[k];print(k,str(v)[:650])
pitchfile=ROOT/'data/pitchapi.json'
if pitchfile.exists():
    pitch=json.loads(pitchfile.read_text())
    print('=== PitchAPI fresh cache status ===')
    print('updated_at',pitch.get('updated_at'),'configured',pitch.get('key_configured'),
          'matches',len(pitch.get('matches') or {}),'coverage',pitch.get('season_player_coverage'),
          'errors',(pitch.get('errors') or [])[:10])
    leagues=collections.Counter()
    recent=collections.Counter()
    for match in (pitch.get('matches') or {}).values():
        if match.get('season')=='2026/27':
            key=(str(match.get('league')),str(match.get('competition_id')))
            leagues[key]+=1
            recent[key]+=len(match.get('players') or [])
    print('2026/27 competition cached report counts and player rows:',leagues.most_common(35))
    print('2026/27 player rows by competition:',recent.most_common(35))
    for p in root['players']:
        if re.search('Mbapp|Foden|Haaland|Salah|Bellingham',p.get('name') or '',re.I):
            pid=str(p.get('id'))
            rows=[(m.get('season'),m.get('league'),m.get('date'),r.get('stats')) for m in (pitch.get('matches') or {}).values() for r in (m.get('players') or []) if str(r.get('player_id'))==pid]
            print('PROFILE:',p.get('name'),pid,p.get('team'),p.get('league'),'pitch matched',len(rows),'latest',sorted(rows,key=lambda r:str(r[2]),reverse=True)[:5])
