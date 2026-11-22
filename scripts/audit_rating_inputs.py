#!/usr/bin/env python3
"""Read-only rating formula and PSG fullback source diagnosis from built artifact."""
import json,re
from pathlib import Path
html=Path('_site/index.html').read_text(encoding='utf-8')
m=re.search(r'<script id="embeddedData" type="application/json">(.*?)</script>',html,re.S)
d=json.loads(m.group(1))
for player in ('Nuno Mendes','Achraf Hakimi'):
    p=next(x for x in d['players'] if x.get('name')==player)
    print('RATING AUDIT',player,'id',p['id'],'role',p.get('scoutRole'),
          'contract',p.get('contractUntilCurrent') or p.get('contractUntilArchive'))
    for year in ('2023/24','2024/25','2025/26','2026/27'):
        x=d.get('liveIndexStats',{}).get(year,{}).get(p['id'])
        if x:print('RATING SEASON',player,year,json.dumps(
            {k:x.get(k) for k in ('minutes','matches','goals','assists','xg','xa','recoveries',
              'tackles','interceptions','source','advancedPartial')},ensure_ascii=False))
script=html[html.find('</script>',m.end()):]
for phrase in ('function calcDraftIndex(', 'function projectedIndex(', 'function monetaryModel(',
               'const MONETARY_MODEL=', 'function buildFormula('):
    i=script.find(phrase)
    if i>=0:
        print('RATING CODE',phrase,script[i:i+6000])
