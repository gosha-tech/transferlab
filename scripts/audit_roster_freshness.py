#!/usr/bin/env python3
"""Find mismatched active clubs, wrong position groups and incomplete starts.
Runs on saved provider snapshots; no live API calls, no fabricated facts.
"""
from pathlib import Path
import json,re,collections
ROOT=Path(__file__).resolve().parents[1]
pitch=json.loads((ROOT/'data/pitchapi.json').read_text())
pl=json.loads((ROOT/'data/pl_current.json').read_text())
hist=json.loads((ROOT/'data/historical_stats.json').read_text())
market=json.loads((ROOT/'data/market_history.json').read_text())
html=(ROOT/'_site/index.html').read_text()
root=json.loads(re.search(r'<script id="embeddedData" type="application/json">(.*?)</script>',html,re.S).group(1))
players=root['players']
current=[m for m in pitch['matches'].values() if m.get('season') in ('2026/27','2026')]
teamplayers=collections.defaultdict(lambda:collections.Counter())
startkeys=collections.Counter()
sample={}
for m in current:
  for p in m.get('players',[]):
    pid=str(p['player_id'])
    teamplayers[pid][p.get('team')]+=1
    for k in p.get('stats',{}):startkeys[k]+=1
    sample.setdefault(pid,p)
print('== STAT INPUT FIELDS ==',startkeys.most_common(35))
print('== PITCH CURRENT MATCHES ==',len(current),'players',len(teamplayers))
lookups=('lookman','salah','hakimi','omur','ö mür','fatawu','foden','khusanov','abner')
for p in players:
 if any(x in p['name'].casefold() for x in lookups):
  pid=str(p['id'])
  summ=root.get('liveIndexStats',{}).get('2026/27',{}).get(pid)
  print('PROFILE',pid,p['name'],'TEAM',p['team'],'LEAGUE',p.get('league'),'POS',p.get('pos'),'ROLE',p.get('scoutRole'),p.get('displayPosition'),
        'NEWTEAMS',teamplayers.get(pid), 'STATS',summ,'LAST YEAR',root.get('liveIndexStats',{}).get('2024/25',{}).get(pid),
        'MARKET', (market.get('series') or {}).get(pid,[])[-2:])
print('== MULTIPLE CURRENT TEAMS ==', [(pid,list(teams.items())) for pid,teams in teamplayers.items() if len(teams)>1][:12])
print('== ROLE INCONSISTENCY ==',[(p['id'],p['name'],p['pos'],p.get('displayPosition')) for p in players if p.get('displayPosition') in ('AM','CM','DM') and p.get('pos')=='Defender'][:25])
print('== SOURCE OF CURRENT TOURNAMENTS ==',collections.Counter(str(x.get('league')) for x in current).most_common(28))
