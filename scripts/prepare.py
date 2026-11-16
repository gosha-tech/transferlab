#!/usr/bin/env python3
"""Build TransferLab from the user's uploaded ZIP; preserve sourced football data."""
from pathlib import Path
from zipfile import ZipFile
import re,json
archive=Path('TransferLab_RESTORED_2026-11-16.zip')
out=Path('_site')
def change(s,old,new):
    if s.count(old)!=1:raise RuntimeError('Expected one marker: '+old[:65]+'; got '+str(s.count(old)))
    return s.replace(old,new,1)
def replace_between(s,start,end,new):
    a=s.find(start);b=s.find(end,a+len(start))
    if a<0 or b<0:raise RuntimeError('Missing code section '+start)
    return s[:a]+new+s[b:]
with ZipFile(archive) as z:s=z.read('index.html').decode('utf-8')
m=re.search(r'<script id="embeddedData" type="application/json">(.*?)</script>',s,re.S)
if not m:raise RuntimeError('Embedded registry missing')
d=json.loads(m.group(1))
# Prepare archival seed players once in the build instead of injecting them on page load.
# This fixes the old 1352/1353 discrepancy and prevents a late-changing catalog count.
import unicodedata,hashlib
def canonical_name(v):
    return ''.join(c for c in unicodedata.normalize('NFKD',str(v).casefold()) if not unicodedata.combining(c)).strip()
p=[v for v in d['players'] if str(v.get('id'))!='seed-0217']
existing={canonical_name(v['name']) for v in p}
for row in d.get('sampleStats25_26',[]):
    name=str(row.get('name') or '')
    if not name or canonical_name(name) in existing:continue
    code=hashlib.sha1((str(row.get('league'))+'|'+str(row.get('team'))+'|'+name).encode()).hexdigest()[:14]
    p.append({'id':'archive-'+code,'name':name,'web':name.split()[-1],'team':row.get('team') or '—',
      'pos':'Unknown','league':row.get('league'),'season':'2025/26',
      'origin':'2025/26 historical seed; current club unverified'})
    existing.add(canonical_name(name))
d['players']=p
if len(p)<1300 or len({str(v['id']) for v in p})!=len(p):raise RuntimeError('Player registry malformed')
d['leagueCatalog']=[l for l in ['Premier League','La Liga','Bundesliga','Serie A','Ligue 1','Primeira Liga','Belgian Pro League','Süper Lig','Saudi Pro League','MLS','Brasileirão'] if any(x.get('league')==l for x in p)]
d['site_build']='TransferLab 5.0 — архивная версия'
s=s[:m.start(1)]+json.dumps(d,ensure_ascii=False,separators=(',',':')).replace('</','<\\/')+s[m.end(1):]
s=re.sub(r'<title>.*?</title>','<title>TransferLab — футбол и аналитика</title>',s,count=1)
s=change(s,'</head>','<link rel="stylesheet" href="assets/site.css">\n<meta name="theme-color" content="#071321">\n</head>')
s=change(s,'</body>','<script src="assets/site.js" defer></script>\n</body>')
s=change(s,'<section id="viewCatalog" class="hidden">','<section id="viewCatalog" class="hidden"><div class="quality-note">Архивная база · данные не обновляются в реальном времени · клубы и контракты могут измениться.</div>')
s=change(s,'<span class="pill" id="visibleCount">0</span>','<select id="sortBy" class="filter" aria-label="Сортировка"><option value="name">По алфавиту</option><option value="position">По позиции</option><option value="minutes">По минутам</option></select><span class="pill" id="visibleCount">0</span>')
# Describe the actual number of leagues instead of the older five-league scope.
s=change(s,"directoryDesc:'Пять лиг: поиск, позиции, контракты и статистика по сезонам.'","directoryDesc:'11 лиг: поиск, позиции, контракты и статистика по доступным сезонам.'")
s=change(s,"sideFoot:'Статистика пяти ведущих лиг. Без выдуманных оценок.'","sideFoot:'Архивные данные 11 лиг. Недостающие показатели не придуманы.'")
s=change(s,"sideFoot:'Statistics from five major leagues. No invented valuations.'","sideFoot:'Historical data from 11 leagues. Missing data is not fabricated.'")
s=change(s,"$('dataState').textContent=players.length+' · '+(masterReady?'Top 5':'offline');","$('dataState').textContent=players.length+' профилей · архив';")
s=change(s,"$('valueMain').textContent=euroM(model.estimate);","$('valueMain').textContent=model.index.proxy?(ru?'Нет данных':'No data'):euroM(model.estimate);")
tick=chr(96); dollar=chr(36)
price_expression=tick+dollar+'{euroM(model.lo)} – '+dollar+'{euroM(model.hi)}'+tick
s=change(s,"$('valueRange').textContent="+price_expression+";","$('valueRange').textContent=model.index.proxy?'—':"+price_expression+";")

s=change(s,"$('playerIndexBadge').textContent=(ru?'Индекс ':'Index ')+(model.index.proxy?'—':((model.rolling.approximate?'≈':'')+model.index.score))+'/100';","$('playerIndexBadge').textContent=model.index.proxy?(ru?'Индекс: нет данных':'Index: no data'):(ru?'Индекс ':'Index ')+(model.rolling.approximate?'≈':'')+model.index.score+'/100';")
s=change(s,"$('filterLeague').onchange=e=>{setLeague(e.target.value)};","$('sortBy').onchange=e=>{state.filters.sort=e.target.value;state.shown=30;renderCatalog()};$('filterLeague').onchange=e=>{setLeague(e.target.value)};")
s=replace_between(s,'  function filterAll(){','  function showView(',r"""  const sortNames=new Intl.Collator('ru',{sensitivity:'base',numeric:true});
  const sortRoles={Goalkeeper:0,Defender:1,Midfielder:2,Forward:3};
  function filterAll(){
    const q=normalize(state.search),f=state.filters;
    const list=players.filter(p=>(!q||textIndex(p).includes(q))&&(!f.league||p.league===f.league)&&(!f.club||p.team===f.club)&&(!f.pos||p.pos===f.pos)&&
      (f.data!=='stats'||['2026/27','2025/26','2024/25','2026'].some(y=>statsBySeason[y]?.[p.id]))&&(f.data!=='contract'||contract(p)));
    list.sort((a,b)=>{
      if(f.sort==='position'||(f.club&&f.sort!=='minutes')){const n=(sortRoles[a.pos]??9)-(sortRoles[b.pos]??9);if(n)return n;}
      if(f.sort==='minutes'){
        const get=p=>{for(const y of ['2026/27','2025/26','2024/25','2026']){const v=statsBySeason[y]?.[p.id]?.minutes;if(v!=null)return Number(v)||0;}return -1};
        const n=get(b)-get(a);if(n)return n;
      }
      return sortNames.compare(a.name,b.name)||String(a.id).localeCompare(String(b.id));
    });return list;
  }
""")
# Render sourced advanced metrics in four readable groups.
s=replace_between(s,'  function renderAdvanced(s){','  const FORMULA_DRAFT=',r"""  function renderAdvanced(s){
    const ru=state.language==='ru';
    const per90=k=>s?.minutes>0&&s[k]!=null?Number(s[k])*90/Number(s.minutes):null;
    const groups=[
      [ru?'Атака и xG':'Attack and xG',[[ru?'Голы / 90':'Goals / 90',per90('goals')],['xG',s?.xg],['xG / 90',per90('xg')],['npxG',s?.npxg],[ru?'Удары':'Shots',s?.shots],[ru?'Удары в створ':'Shots on target',s?.shots_on_target]]],
      [ru?'Передачи и создание моментов':'Passing and creation',[[ru?'Ассисты / 90':'Assists / 90',per90('assists')],['xA',s?.xa],['xA / 90',per90('xa')],[ru?'Ключевые передачи':'Key passes',s?.key_passes],['xGChain',s?.xg_chain],['xGBuildup',s?.xg_buildup]]],
      [ru?'Оборона':'Defense',[[ru?'Отборы':'Tackles',s?.tackles],[ru?'Перехваты':'Interceptions',s?.interceptions],[ru?'Возвраты':'Recoveries',s?.recoveries],[ru?'Выносы':'Clearances',s?.clearances],[ru?'Блоки':'Blocks',s?.blocks]]],
      [ru?'Участие и дисциплина':'Minutes and discipline',[[ru?'Матчи':'Matches',s?.matches],[ru?'Минуты':'Minutes',s?.minutes],[ru?'Старты':'Starts',s?.starts],[ru?'Сухие матчи':'Clean sheets',s?.clean_sheets],[ru?'Жёлтые':'Yellow cards',s?.yellow_cards],[ru?'Красные':'Red cards',s?.red_cards]]]
    ];
    const fmt=v=>v==null||!Number.isFinite(Number(v))?'—':nf(Number(v),Number(v)%1===0?0:2);
    $('advancedRows').className='advanced-sections';
    $('advancedRows').innerHTML=groups.map(g=>'<section class="advanced-group"><h3>'+esc(g[0])+'</h3>'+g[1].map(m=>'<div class="metric-row"><span>'+esc(m[0])+'</span><strong>'+fmt(m[1])+'</strong></div>').join('')+'</section>').join('');
    $('advancedWrap').hidden=!state.statsExpanded;
    $('detailsButton').textContent=state.statsExpanded?(ru?'Свернуть ↑':'Less ↑'):(ru?'Подробнее ↗':'Details ↗');
  }

""")
s=replace_between(s,'  function setupCards(host){','  function renderCoverage(){',r"""  const cardObserver=window.IntersectionObserver?new IntersectionObserver(entries=>{
    for(const x of entries){if(!x.isIntersecting)continue;const avatar=x.target;cardObserver.unobserve(avatar);
      const img=avatar.querySelector('[data-photo]'),fb=avatar.querySelector('[data-pfallback]');if(img&&fb)attachPhoto(img,fb,img.dataset.photo);
    }
  },{rootMargin:'140px'}):null;
  function setupCards(host){host.querySelectorAll('[data-open]').forEach(el=>el.onclick=()=>choosePlayer(el.dataset.open));
    host.querySelectorAll('[data-favorite]').forEach(el=>el.onclick=()=>toggleFavorite(el.dataset.favorite));
    host.querySelectorAll('[data-photo]').forEach(img=>{const fb=img.closest('.avatar')?.querySelector('[data-pfallback]');if(cardObserver)cardObserver.observe(img.closest('.avatar'));else if(fb)attachPhoto(img,fb,img.dataset.photo)});
  }
""")
s=change(s,"    if(!masterReady)setTimeout(()=>restoreMasterArchive(),650);","    // Archive importer remains manual; never block initial render.")
s=change(s,"    if(!ROOT.offlineTopFiveCsv)setTimeout(()=>loadFiveLeagues().catch(()=>{}),950);","    // No automatic network import of historical data.")
s=change(s,"    if(!masterReady)setTimeout(()=>fetch24Fallback().catch(()=>{}),1600);","    // No automatic replacement of archived rosters.")
s=change(s,"    setTimeout(()=>updateLive(),1200);","    // Live statistics require an authenticated scheduled backend.")
s=change(s,"    setTimeout(()=>['2025/26','2024/25','2023/24'].forEach(season=>loadOldSeason(season)),2000);","    // Show only bundled season stats on launch.")
s=change(s,"const defs={\n      'Premier League':{flag:'🏴',label:'Premier League'},","const defs={\n      'Primeira Liga':{flag:'🇵🇹',label:'Португалия'},'Belgian Pro League':{flag:'🇧🇪',label:'Бельгия'},'Süper Lig':{flag:'🇹🇷',label:'Турция'},\n      'Premier League':{flag:'🏴',label:'Premier League'},")
out.mkdir(exist_ok=True)
(out/'index.html').write_text(s,encoding='utf-8')
(out/'.nojekyll').write_text('',encoding='utf-8')
print('TransferLab build:',len(p),'players and',len(d['leagueCatalog']),'leagues')
