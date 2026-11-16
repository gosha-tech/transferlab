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
d=json.loads(m.group(1));p=d['players']
if len(p)<1300 or len({str(v['id']) for v in p})!=len(p):raise RuntimeError('Player registry malformed')
d['leagueCatalog']=[l for l in ['Premier League','La Liga','Bundesliga','Serie A','Ligue 1','Primeira Liga','Belgian Pro League','Süper Lig','Saudi Pro League','MLS','Brasileirão'] if any(x.get('league')==l for x in p)]
d['site_build']='TransferLab 5.0 — архивная версия'
s=s[:m.start(1)]+json.dumps(d,ensure_ascii=False,separators=(',',':')).replace('</','<\\/')+s[m.end(1):]
s=re.sub(r'<title>.*?</title>','<title>TransferLab — футбол и аналитика</title>',s,count=1)
s=change(s,'</head>','<link rel="stylesheet" href="assets/site.css">\n<meta name="theme-color" content="#071321">\n</head>')
s=change(s,'</body>','<script src="assets/site.js" defer></script>\n</body>')
s=change(s,'<section id="viewCatalog" class="hidden">','<section id="viewCatalog" class="hidden"><div class="quality-note">Архивный каталог TransferLab: составы и статистика могут быть устаревшими. Пустые показатели не заменяются выдуманными значениями. Клубы и контракты требуют проверки.</div>')
s=change(s,'<span class="pill" id="visibleCount">0</span>','<select id="sortBy" class="filter" aria-label="Сортировка"><option value="name">По алфавиту</option><option value="position">По позиции</option><option value="minutes">По минутам</option></select><span class="pill" id="visibleCount">0</span>')
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
