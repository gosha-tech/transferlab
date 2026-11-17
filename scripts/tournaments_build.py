#!/usr/bin/env python3
"""Embed provider-backed tournament stats into TransferLab and add competition UI.

This transforms the generated site (not the immutable archived source ZIP).
Only documented API-Football player-season entries become current-season data.
"""
import json, pathlib, re, unicodedata
from collections import defaultdict

ROOT=pathlib.Path(__file__).resolve().parents[1]
DATA_PATH=ROOT/'data'/'live.json'
COMPETITIONS=[
 (39,'АПЛ'),(2,'Лига чемпионов'),(45,'Кубок Англии'),(48,'Кубок английской лиги'),
 (140,'Ла Лига'),(143,'Кубок Испании'),(78,'Бундеслига'),(81,'Кубок Германии'),
 (135,'Серия А'),(137,'Кубок Италии'),(61,'Лига 1'),(66,'Кубок Франции'),
 (94,'Португалия'),(144,'Бельгия'),(203,'Турция'),(307,'Саудовская лига'),
 (253,'MLS'),(3,'Лига Европы'),(848,'Лига конференций')
]
LEAGUES={39:'Premier League',140:'La Liga',78:'Bundesliga',135:'Serie A',61:'Ligue 1',
         94:'Primeira Liga',144:'Belgian Pro League',203:'Süper Lig',
         307:'Saudi Pro League',253:'MLS'}
POSITIONS={'Attacker':'Forward','Midfielder':'Midfielder','Defender':'Defender','Goalkeeper':'Goalkeeper'}
def norm(v):
    t=''.join(c for c in unicodedata.normalize('NFKD',str(v or '').casefold()) if not unicodedata.combining(c))
    return re.sub(r'[^a-zа-я0-9]','',t)
def patch(s,old,new):
    if s.count(old)!=1:raise RuntimeError('Tournament integration marker missing: '+old[:65]+' ('+str(s.count(old))+')')
    return s.replace(old,new,1)
def embed(html):
    m=re.search(r'(<script id="embeddedData" type="application/json">)(.*?)(</script>)',html,re.S)
    if not m:raise RuntimeError('No embedded data')
    root=json.loads(m.group(2))
    snapshot=json.loads(DATA_PATH.read_text(encoding='utf-8')) if DATA_PATH.exists() else {}
    hist_path=ROOT/'data'/'historical_stats.json'
    historical=json.loads(hist_path.read_text(encoding='utf-8')) if hist_path.exists() else {}
    original=root['players']
    match_by_name_club=defaultdict(list)
    for player in original:
        match_by_name_club[(norm(player.get('name')),norm(player.get('team')))].append(player)
    assigned={}
    records={}
    for r in snapshot.get('records',[]):
        if not isinstance(r,dict):continue
        api_id=r.get('api_id')
        cid=r.get('competition_id')
        season=r.get('season')
        if not isinstance(api_id,int) or cid is None or not season or not r.get('name'):continue
        if api_id not in assigned:
            choices=[]
            candidates=[r.get('first','')+' '+r.get('last',''),r['name']]
            for cand in candidates:
                choices.extend(match_by_name_club.get((norm(cand),norm(r.get('team'))),[]))
            choices={p['id']:p for p in choices}
            if len(choices)==1:
                p=next(iter(choices.values()))
            else:
                pid='api-football-'+str(api_id)
                p=next((x for x in original if x['id']==pid),None)
                if p is None:
                    p={'id':pid,'name':(r.get('first','')+' '+r.get('last','')).strip() or r['name'],
                       'web':r['name'],'team':r.get('team') or '—',
                       'league':LEAGUES.get(cid,'Other competitions'),'pos':POSITIONS.get(r.get('position'),'Midfielder'),
                       'season':season,'origin':'API-Football: competition team, not independently confirmed current club'}
                    original.append(p)
            assigned[api_id]=p
        player=assigned[api_id]
        if r.get('photo') and re.fullmatch(r'https://media\.api-sports\.io/football/players/\d+\.png',str(r['photo'])):
            player['apiPhoto']=r['photo']
        if r.get('birth') and not player.get('birth'):player['birth']=r['birth']
        if r.get('height') and not player.get('height'):player['height']=r['height']
        record={'id':int(cid),'name':r.get('competition') or dict(COMPETITIONS).get(int(cid),'Турнир'),
                'stats':r.get('games') or {}}
        # Multiple clubs from a transfer in the same tournament must be summed, not overwritten.
        key=(season,str(player['id']),int(cid))
        old=records.get(key)
        if old is None:records[key]=record
        else:
            for name,value in record['stats'].items():
                if value is not None:
                    previous=old['stats'].get(name)
                    old['stats'][name]=value+(previous or 0)
    by_season={}
    for (season,pid,_),entry in records.items():
        by_season.setdefault(season,{}).setdefault(pid,[]).append(entry)
    # Archive up to June 2026: authentic minutes/goals/assists, separately
    # labeled as old data, never presented as current 2026/27 statistics.
    # Avoid counting the same competition twice when a current API snapshot
    # overlaps with the older Transfermarkt archive (notably MLS 2026).
    api_to_tm={39:'GB1',140:'ES1',78:'L1',135:'IT1',61:'FR1',
               94:'PO1',144:'BE1',203:'TR1',307:'SA1',253:'MLS1',
               2:'CL',3:'EL',848:'ECL',45:'FAC',48:'CGB'}
    for season,player_map in (historical.get('by_season') or {}).items():
        for pid,history in player_map.items():
            recent=by_season.setdefault(season,{}).setdefault(pid,[])
            for record in history:
                archive_id=str(record['id'])
                def overlaps(q):
                    api_id=q.get('id')
                    return str(api_id)==archive_id or (
                        isinstance(api_id,int) and archive_id=='tm-'+api_to_tm.get(api_id,'-'))
                if not any(overlaps(q) for q in recent):
                    recent.append(record)
    # Feed competition totals into the existing 36-month index only when actual
    # minutes are available; never supply zeroes for unknown metrics.
    index_stats={}
    for season,players_map in by_season.items():
        for pid,events in players_map.items():
            collected={}
            for field in ('matches','starts','minutes','goals','assists','shots','shots_on_target',
                          'key_passes','tackles','interceptions','yellow_cards','red_cards'):
                valid=[item['stats'][field] for item in events if item.get('stats',{}).get(field) is not None]
                if valid:collected[field]=sum(valid)
            if collected.get('minutes',0)<180:continue
            archival=all(x.get('source')=='historical_appearances' for x in events)
            collected.update({'source':'transfermarkt_historical' if archival else 'api_football_partial',
                              'partial':True,
                              'as_of':historical.get('as_of') if archival else snapshot.get('updated_at'),
                              'source_url':'https://github.com/dcaribou/transfermarkt-datasets' if archival else 'https://www.api-football.com/documentation-v3'})
            index_stats.setdefault(season,{})[pid]=collected
    root['liveIndexStats']=index_stats
    root['liveTournamentStats']=by_season
    root['liveUpdatedAt']=snapshot.get('updated_at')
    root['liveCoverage']=snapshot.get('coverage',[])
    root['liveStatus']=snapshot.get('status','awaiting_api_key')
    root['historicalThrough']=historical.get('as_of')
    root['historicalCoveragePlayers']=historical.get('covered_players',0)
    root['liveCompetitionCatalog']=[{'id':cid,'name':name} for cid,name in COMPETITIONS]
    root['leagueCatalog']=list(dict.fromkeys(root.get('leagueCatalog',[])+[p.get('league') for p in original if p.get('league')]))
    # Write embedded JSON before modifying the runtime script.
    content=json.dumps(root,ensure_ascii=False,separators=(',',':')).replace('</','<\\/')
    html=html[:m.start(2)]+content+html[m.end(2):]
    # The public UI must never conflate a successful site deployment with
    # a successful current-season statistics sync.
    current_ids=set((root['liveTournamentStats'].get('2026/27') or {}).keys())
    current_ids.update((root['liveTournamentStats'].get('2026') or {}).keys())
    current_count=len(current_ids)
    if current_count:
        timestamp=snapshot.get('updated_at') or 'дата неизвестна'
        msg=('Статистика 2026/27: '+str(current_count)+' из '+str(len(original))+
             ' игроков имеют данные API · последнее получение '+timestamp[:10]+
             ' · по турнирам покрытие может быть неполным.')
    else:
        msg=('Статистика 2026/27 ещё не загружена: 0 из '+str(len(original))+
             ' игроков. Все показатели прошлых сезонов — архивные. '
             'Для свежих данных нужен подключённый API с доступом к сезону 2026/27.')
    html=html.replace('Архивная база · данные не обновляются в реальном времени · клубы и контракты могут измениться.',
                      msg,1)
    anchor='<div class="stat-grid">'
    toolbar='<div class="competition-toolbar"><label for="competitionSelect">Турнир</label><select id="competitionSelect" class="chart-switch" aria-label="Выбор турнира"><option value="all">Все загруженные турниры</option></select><span id="competitionStatus" class="competition-status">Статистика турниров пока не загружена</span></div>'
    html=patch(html,anchor,toolbar+anchor)
    html=patch(html,"const contracts = ROOT.contracts;",r"""const contracts = ROOT.contracts;
  const tournamentRows=ROOT.liveTournamentStats||{};
  // Sourced tournament totals may also improve the rolling index. Existing
  // league-only data are retained when the provider snapshot is less complete.
  for(const [season,map] of Object.entries(ROOT.liveIndexStats||{})){
    const target=statsBySeason[season]??={};
    for(const [id,v] of Object.entries(map)){
      const previous=target[id];
      if(!previous||Number(v.minutes)>=Number(previous.minutes||0))target[id]=v;
    }
  }
  const tournamentCatalogue=ROOT.liveCompetitionCatalog||[];
  const tournamentCoverage=ROOT.liveCoverage||[];
  const tournamentMetricKeys=['matches','starts','minutes','goals','assists','shots','shots_on_target',
    'passes','key_passes','tackles','interceptions','dribbles','yellow_cards','red_cards'];
  function tournamentSum(rows){
    const archived=rows.length>0&&rows.every(r=>r.source==='historical_appearances');
    const result={source:archived?'transfermarkt_historical':'api_football_partial',
      partial:true,updated_at:archived?ROOT.historicalThrough:ROOT.liveUpdatedAt};
    for(const key of tournamentMetricKeys){
      const vals=rows.map(x=>x.stats?.[key]).filter(x=>x!=null&&Number.isFinite(Number(x)));
      result[key]=vals.length?vals.reduce((sum,val)=>sum+Number(val),0):null;
    }
    return result;
  }""")
    html=patch(html,"favorites:[], timeline:{}, seasonLoading:{}, photoDisabled:false};",
               "favorites:[], timeline:{}, seasonLoading:{}, photoDisabled:false,competition:'all'};")
    html=patch(html,"function stat(p,season=state.season){return statsBySeason[season]?.[p.id]||null};",
               r"""function stat(p,season=state.season){
    const all=tournamentRows[season]?.[p.id]||[];
    const rows=state.competition==='all'?all:all.filter(x=>String(x.id)===state.competition);
    if(rows.length)return tournamentSum(rows);
    if(state.competition!=='all')return null;
    return statsBySeason[season]?.[p.id]||null;
  }""")
    html=patch(html,"const urls=[];\n    const custom=storedPhoto(code);",
               "const urls=[];\n    if(p.apiPhoto)urls.push({url:p.apiPhoto,source:'API-Football / ID'});\n    const custom=storedPhoto(code);")
    controls=r"""  function renderTournamentSelector(p){
    const ru=state.language==='ru';
    const select=$('competitionSelect');
    const rows=tournamentRows[state.season]?.[p.id]||[];
    const allNames=new Map(tournamentCatalogue.map(x=>[String(x.id),x.name]));
    for(const x of rows)if(!allNames.has(String(x.id)))allNames.set(String(x.id),x.name);
    const previously=select.value;
    select.innerHTML='<option value="all">'+(ru?'Все загруженные турниры':'All available competitions')+'</option>'+
      [...allNames].map(([id,name])=>'<option value="'+esc(id)+'">'+esc(name)+'</option>').join('');
    select.value=state.competition;
    if(select.value!==state.competition){state.competition='all';select.value='all';}
    select.onchange=()=>{state.competition=select.value;renderProfile()};
    const items=state.competition==='all'?rows:rows.filter(x=>String(x.id)===state.competition);
    const title=state.competition==='all'?(ru?'Все турниры':'All competitions'):(allNames.get(state.competition)||state.competition);
    const date=ROOT.liveUpdatedAt?new Date(ROOT.liveUpdatedAt).toLocaleDateString(ru?'ru-RU':'en-GB'):'';
    let message='';
    if(items.length){
      const onlyArchive=items.every(x=>x.source==='historical_appearances');
      if(onlyArchive){
        $('competitionStatus').textContent=title+' · '+(ru?'Архив до ':'Archive through ')+(ROOT.historicalThrough||'2026-06-28')+
          ' · '+(ru?'матчи из источника Transfermarkt, не текущий сезон':'Transfermarkt match data, not live');
        return;
      }
      message=(ru?'Загружено: ':'Available: ')+items.length+' '+(ru?'турн.':'comp.')+
        (date?' · '+(ru?'обновлено ':'updated ')+date:'')+' · '+(ru?'покрытие неполное':'partial coverage');
    }else if(ROOT.liveStatus==='awaiting_api_key'||!ROOT.liveUpdatedAt){
      message=ru?'API ещё не подключён · доступны только архивные данные':'API not connected · archive only';
    }else{
      message=(ru?'Нет подтверждённой статистики по выбору':'No verified data for this selection')+
        (date?' · '+date:'');
    }
    $('competitionStatus').textContent=title+' · '+message;
  }
"""
    # Accurate role display: never assert that all broad defenders are centre-backs.
    html=patch(html,
      "function roleFor(p){const override=roleOverrides[p.id]||rolesByName[normalize(p.name)];",
      "function roleFor(p){const override=p.scoutRole||roleOverrides[p.id]||rolesByName[normalize(p.name)];")
    html=patch(html,"$('pPosition').textContent=roleFor(p).role;",
      "$('pPosition').textContent=p.displayPosition||(roleFor(p).exact?roleFor(p).role:({'Defender':'DEF','Midfielder':'MID','Forward':'FWD','Goalkeeper':'GK'}[p.pos]||'—'));")
    html=patch(html,
      "$('pFoot').textContent=meta.foot?(ru?(meta.foot==='left'?'Левая':'Правая'):(meta.foot==='left'?'Left':'Right')):'—';",
      "const playerFoot=meta.foot||p.foot;$('pFoot').textContent=playerFoot?(ru?(playerFoot==='left'?'Левая':playerFoot==='both'?'Обе':'Правая'):(playerFoot==='left'?'Left':playerFoot==='both'?'Both':'Right')):'—';")
    html=patch(html,"function derivedAge(player){if(player?.age!=null",
      "function derivedAge(player){if(player?.birth){const born=new Date(player.birth),today=new Date();if(!Number.isNaN(born.getTime()))return today.getUTCFullYear()-born.getUTCFullYear()-(today.getUTCMonth()<born.getUTCMonth()||(today.getUTCMonth()===born.getUTCMonth()&&today.getUTCDate()<born.getUTCDate())?1:0);}if(player?.age!=null")
    # No automatic Wikipedia thumbnails: name search often returns the wrong person.
    html=patch(html,"if(profile||firstCards){lookupWikipedia(p).then(found=>",
      "if(false && (profile||firstCards)){lookupWikipedia(p).then(found=>")
    html=patch(html,"${esc(position[state.language][p.pos]||p.pos)}</div>${sub}","${esc(p.displayPosition?(p.displayPosition+' · '+(position[state.language][p.pos]||p.pos)):(position[state.language][p.pos]||p.pos))}</div>${sub}")
    html=patch(html,"function cardMarkup(p){const c=contract(p),s=stat(p);const sub=","function cardMarkup(p){const c=contract(p),s=stat(p),idx=projectedIndex(p);const indexTag=idx.proxy?'<small class=\"player-index unavailable\">'+(state.language==='ru'?'Индекс: нет данных':'Index: no data')+'</small>':'<small class=\"player-index\">'+(state.language==='ru'?'Индекс ':'Index ')+idx.score+'/100'+(idx.exact?'':' ≈')+'</small>';const sub=")
    html=patch(html,"${esc(p.season||'2026/27')}</span></span></button>","${esc(p.season||'2026/27')}</span>${indexTag}</span></button>")
    html=patch(html,"  function renderProfile(){",controls+"  function renderProfile(){")
    html=patch(html,"renderChart(p,s);renderStrengths(s,p);renderAdvanced(s);",
               """renderChart(p,s);renderStrengths(s,p);renderAdvanced(s);renderTournamentSelector(p);
    if(s?.source==='api_football_partial'){
      $('statsSourceCaption').textContent='API-Football · '+(state.language==='ru'?'по загруженным турнирам (неполное покрытие)':'loaded competitions only (partial)');
    }else if(s){
      $('statsSourceCaption').textContent=s.source==='transfermarkt_historical'
        ?(state.language==='ru'?'Архив матчей до июня 2026 · все доступные турниры':'Match archive through June 2026 · available competitions')
        :(state.language==='ru'?'Архивные данные · не обновлялись сегодня':'Archived statistics · not a current update');
    }""")
    html=patch(html,"const meta=PLAYER_META[p.id]||{},a=derivedAge(p),ru=state.language==='ru';",
               "const meta=PLAYER_META[p.id]||{},a=derivedAge(p)??(p.birth?(()=>{const d=new Date(p.birth),now=new Date();return Number.isNaN(d.getTime())?null:now.getUTCFullYear()-d.getUTCFullYear()-(now.getUTCMonth()<d.getUTCMonth()||(now.getUTCMonth()===d.getUTCMonth()&&now.getUTCDate()<d.getUTCDate())?1:0)})():null),ru=state.language==='ru';")
    html=patch(html,"$('pHeight').textContent=meta.height?meta.height+' '+(ru?'см':'cm'):'—';",
               "$('pHeight').textContent=(meta.height||p.height)?String(meta.height||p.height).replace(/[^0-9]/g,'')+' '+(ru?'см':'cm'):'—';")
    return html

if __name__=='__main__':
    import sys
    path=pathlib.Path(sys.argv[1])
    path.write_text(embed(path.read_text(encoding='utf-8')),encoding='utf-8')
    print('Embedded provider snapshot into',path)
