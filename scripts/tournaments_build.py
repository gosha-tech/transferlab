#!/usr/bin/env python3
"""Embed provider-backed tournament stats into TransferLab and add competition UI.

This transforms the generated site (not the immutable archived source ZIP).
Only documented API-Football player-season entries become current-season data.
"""
import json, pathlib, re, unicodedata
from collections import defaultdict
from player_competitions import add_choices

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
    free_path=ROOT/'data'/'free_sources.json'
    free=json.loads(free_path.read_text(encoding='utf-8')) if free_path.exists() else {}
    pl_path=ROOT/'data'/'pl_current.json'
    pl=json.loads(pl_path.read_text(encoding='utf-8')) if pl_path.exists() else {}
    commons_path=ROOT/'data'/'commons_photos.json'
    commons=json.loads(commons_path.read_text(encoding='utf-8')) if commons_path.exists() else {}
    pitch_path=ROOT/'data'/'pitchapi.json'
    pitch=json.loads(pitch_path.read_text(encoding='utf-8')) if pitch_path.exists() else {}
    original=root['players']
    for p in original:
        photo=(commons.get('photos') or {}).get(str(p.get('id')))
        if not isinstance(photo,dict) or not photo.get('url'):continue
        p['commonsPhoto']=photo['url']
        p['commonsArtist']=photo.get('artist')
        p['commonsLicense']=photo.get('licence')
        p['commonsLicenseUrl']=photo.get('licence_url')
        p['commonsSourcePage']=photo.get('file_page')
    # Current-season EPL IDs are matched by the upstream fetcher on unique official
    # Premier League code AND player name. Never fuzzy-join across clubs here.
    pl_rows=pl.get('players') or {}
    for p in original:
        live=pl_rows.get(str(p['id']))
        if not live or p.get('league')!='Premier League':continue
        if live.get('team'):p['team']=live['team']
        if live.get('height_cm') and not p.get('height'):p['height']=live['height_cm']
        if live.get('foot') and not p.get('foot'):p['foot']=live['foot']
        if live.get('dob') and not p.get('birth'):p['birth']=live['dob']
        contract=str(live.get('contract_until') or '')
        if re.fullmatch(r'20\d{2}-\d{2}-\d{2}',contract):
            p['contractUntilCurrent']=contract
            p['contractSource']='pl-catalogue'
            p['contractSourceAsOf']=live.get('as_of')
        role=str(live.get('position_detail') or '')
        roles={'Right-Back':'RB','Left-Back':'LB','Centre-Back':'CB',
               'Right Winger':'RW','Left Winger':'LW','Defensive Midfield':'DM',
               'Central Midfield':'CM','Attacking Midfield':'AM',
               'Centre-Forward':'ST','Goalkeeper':'GK'}
        if role in roles:
            precise=roles[role]
            p['displayPosition']=precise
            p['scoutRole']={'RB':'LB/RB','LB':'LB/RB',
                            'RW':'LW/RW','LW':'LW/RW',
                            'GK':'GK'}.get(precise,precise)
            p['pos']=('Goalkeeper' if precise=='GK' else
                      'Defender' if precise in ('RB','LB','CB') else
                      'Forward' if precise in ('RW','LW','ST') else 'Midfielder')
            p['position_source']=live['source']
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
    # Current 2026/27 EPL stats. Never override the same season and competition
    # from an authenticated API. The pl-catalogue export timestamp is visible.
    for pid,entry in pl_rows.items():
        if not isinstance(entry,dict):continue
        if not any(str(p.get('id'))==str(pid) for p in original):continue
        games=entry.get('stats') or {}
        if not games or games.get('minutes') is None:continue
        cur=by_season.setdefault('2026/27',{}).setdefault(str(pid),[])
        if not any(str(x.get('id'))=='39' for x in cur):
            cur.append({'id':39,'name':'Premier League','source':'pl_catalogue',
                        'as_of':entry.get('as_of'),'is_complete':True,
                        'stats':games})
    # Optional free PitchAPI per-match source. An API key is required but free;
    # no new rows are assumed until a real successful provider fetch exists.
    # Full EPL data from pl-catalogue takes priority over partial match imports.
    pitch_groups=defaultdict(list)
    for match in (pitch.get('matches') or {}).values():
        if not isinstance(match,dict):continue
        season=match.get('season')
        mid=str(match.get('id') or '')
        cid=match.get('competition_id')
        if season not in ('2024/25','2025/26','2026/27','2024','2025','2026') or not mid.startswith('m_'):continue
        ident=str(cid) if cid else 'pitch-'+str(match.get('league_id') or '')
        for row in match.get('players') or []:
            pid=str(row.get('player_id') or '')
            if not pid or not isinstance(row.get('stats'),dict):continue
            if cid==39 and pid in pl_rows and season=='2026/27':continue
            if not any(str(p.get('id'))==pid for p in original):continue
            pitch_groups[(season,pid,ident,str(match.get('league') or 'Турнир'))].append((mid,row['stats']))
    for (season,pid,ident,name),data in pitch_groups.items():
        cur=by_season.setdefault(season,{}).setdefault(pid,[])
        if any(str(row.get('id'))==ident and row.get('source') not in ('pitchapi_partial',) for row in cur):
            continue
        totals={}
        valid=set()
        for mid,stats in data:
            if mid in valid:continue
            valid.add(mid)
            for k,v in stats.items():
                if isinstance(v,(float,int)) and not isinstance(v,bool):
                    totals[k]=round(totals.get(k,0)+v,3)
        if not totals:continue
        totals['matches']=sum(1 for mid,stats in data
                               if stats.get('minutes',0)>0 or
                               any(stats.get(k) for k in ('goals','assists','shots','tackles','saves')))
        cur.append({'id':int(cid) if cid and str(cid).isdigit() else ident,'name':name,
                    'source':'pitchapi_partial','is_complete':False,'stats':totals,
                    'matches_loaded':len(valid),'as_of':pitch.get('updated_at'),
                    'source_url':'https://pitchapi.dev/'})
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
                matching=next((q for q in recent if overlaps(q)),None)
                if matching is None:
                    recent.append(record)
                elif matching.get('source')=='pitchapi_partial':
                    # Incomplete PitchAPI coverage must not overwrite full
                    # archived minutes/goals/assists for the same competition.
                    # Merge only the advanced metrics absent from the archive.
                    archive=dict(record)
                    archive['stats']=dict(record.get('stats') or {})
                    for metric,value in (matching.get('stats') or {}).items():
                        if metric not in archive['stats'] and value is not None:
                            archive['stats'][metric]=value
                    archive['advanced_partial_source']='pitchapi_partial'
                    archive['advanced_matches_loaded']=matching.get('matches_loaded',0)
                    recent[recent.index(matching)]=archive
    # TheSportsDB free API only exposes a SMALL SAMPLE of player-stat records.
    # Do not override API-Football current-season rows or older more complete
    # Transfermarkt appearance totals.
    for pid,profile in (free.get('players') or {}).items():
        if not isinstance(profile,dict):continue
        p=next((p for p in original if str(p.get('id'))==str(pid)),None)
        if p is None:continue
        picture=str(profile.get('photo') or '')
        if profile.get('photo_rights_checked') is True and re.fullmatch(r'https://r2\.thesportsdb\.com/images/media/player/(?:cutout|thumb)/[a-zA-Z0-9._-]+\.(?:png|jpg|webp)',picture):
            if not p.get('apiPhoto'):
                p['apiPhoto']=picture
                p['photoAttribution']='TheSportsDB.com'+(': '+str(profile['photo_attribution']) if profile.get('photo_attribution') else '')
                p['photoSource']='TheSportsDB Creative Commons'
        role_name=str(profile.get('position_source') or '').strip()
        known_roles={
            'Goalkeeper':('Goalkeeper','GK','GK'),
            'Centre-Back':('Defender','CB','CB'),
            'Center-Back':('Defender','CB','CB'),
            'Right-Back':('Defender','LB/RB','RB'),
            'Left-Back':('Defender','LB/RB','LB'),
            'Right Winger':('Forward','LW/RW','RW'),
            'Left Winger':('Forward','LW/RW','LW'),
            'Defensive Midfield':('Midfielder','DM','DM'),
            'Central Midfield':('Midfielder','CM','CM'),
            'Attacking Midfield':('Midfielder','AM','AM'),
            'Centre-Forward':('Forward','ST','ST')}
        if role_name in known_roles and not p.get('positionVerified') and not p.get('displayPosition'):
            p['pos'],p['scoutRole'],p['displayPosition']=known_roles[role_name]
            p['position_source']='TheSportsDB · verified profile'
        for record in profile.get('stats') or []:
            if not isinstance(record,dict):continue
            season=str(record.get('season') or '')
            # Historic archive is more complete: use TheSportsDB for current season only.
            if season not in ('2026/27','2026'):continue
            cur=by_season.setdefault(season,{}).setdefault(str(pid),[])
            label=norm(record.get('name'))
            # Only supplement when there is no provider-backed total for the same
            # footballer/competition. Free fragments are ALWAYS partial.
            aliases={'englishpremierleague':'premierleague','uefachampionsleague':'championsleague',
                     'uefaeuropaleague':'europaleague','frenchligue1':'ligue1',
                     'spanishlaliga':'laliga','italianseriea':'seriea'}
            def normalized_comp(row):
                code=norm(row.get('name'))
                return aliases.get(code,code)
            if not any(normalized_comp(q)==aliases.get(label,label) for q in cur):
                cur.append({'id':str(record['id']),'name':str(record.get('name') or 'Турнир'),
                            'source':'thesportsdb_sample','is_complete':False,
                            'stats':record.get('stats') or {}})
    # Feed competition totals into the existing 36-month index only when actual
    # minutes are available; never supply zeroes for unknown metrics.
    index_stats={}
    for season,players_map in by_season.items():
        for pid,events in players_map.items():
            collected={}
            for field in ('matches','starts','minutes','goals','assists','xg','xa','npxg',
                          'shots','shots_on_target','key_passes','passes','tackles',
                          'interceptions','dribbles','recoveries','clearances','blocks',
                          'progressive_passes','progressive_carries','yellow_cards','red_cards'):
                valid=[item['stats'][field] for item in events if item.get('stats',{}).get(field) is not None]
                if valid:collected[field]=sum(valid)
            if collected.get('minutes',0)<180:continue
            archival=all(x.get('source')=='historical_appearances' for x in events)
            community=all(x.get('source')=='thesportsdb_sample' for x in events)
            premier=all(x.get('source')=='pl_catalogue' for x in events)
            pitchonly=all(x.get('source')=='pitchapi_partial' for x in events)
            collected.update({'source':'transfermarkt_historical' if archival else ('thesportsdb_partial' if community else ('pl_catalogue' if premier else ('pitchapi_partial' if pitchonly else 'api_football_partial'))),
                              'partial':True,
                              'as_of':historical.get('as_of') if archival else (free.get('last_success_at') if community else (pl.get('published_at') if premier else (pitch.get('updated_at') if pitchonly else snapshot.get('updated_at')))),
                              'source_url':'https://github.com/dcaribou/transfermarkt-datasets' if archival else ('https://www.thesportsdb.com/' if community else ('https://github.com/oladeeayo/pl-catalogue' if premier else ('https://pitchapi.dev/' if pitchonly else 'https://www.api-football.com/documentation-v3')))})
            index_stats.setdefault(season,{})[pid]=collected
    root['liveIndexStats']=index_stats
    root['profileCoverage']={
        'total':len(original),
        'with_precise_position':sum(bool(p.get('displayPosition')) for p in original),
        'with_foot':sum(p.get('foot') in ('left','right','both') for p in original),
        'with_contract':sum(bool(p.get('contractUntilCurrent') or p.get('contractUntilArchive')) for p in original),
        'with_licensed_commons_photo':sum(bool(p.get('commonsPhoto')) for p in original),
        'with_current_player_stats':len({str(pid) for season in ('2026/27','2026')
                                        for pid,entries in by_season.get(season,{}).items()
                                        if any(r.get('stats') for r in entries)}),
        'with_archive_player_stats':len({str(pid) for season in ('2023/24','2024/25','2025/26')
                                        for pid in (historical.get('by_season') or {}).get(season,{})})}
    root['liveTournamentStats']=by_season
    root['freeMatchResults']=free.get('matches') or {}
    root['freeSourceSyncAt']=free.get('last_success_at')
    root['freeSourceIssues']=len(free.get('issues') or [])
    root['freeSourcePlayerProfiles']=free.get('profiles_verified',0)
    root['freeSourcePlayerStats']=free.get('players_with_current_stats',0)
    root['plCurrentCoverage']=len(pl_rows)
    root['plCurrentAsOf']=pl.get('published_at')
    root['plCurrentSource']=pl.get('source')
    root['commonsPhotoCount']=len(commons.get('photos') or {})
    root['pitchAPIStatsCoverage']=len({row.get('player_id') for m in (pitch.get('matches') or {}).values() for row in m.get('players',[])})
    root['pitchAPILastSync']=pitch.get('updated_at')
    root['pitchAPIKeyConfigured']=pitch.get('key_configured',False)
    root['pitchAPISeasonCoverage']=pitch.get('season_player_coverage') or {}
    root['pitchAPIBackfillIncomplete']=pitch.get('backfill_incomplete',True)
    root['pitchAPIErrors']=pitch.get('errors') or []
    root['liveUpdatedAt']=snapshot.get('updated_at')
    root['liveCoverage']=snapshot.get('coverage',[])
    root['liveStatus']=snapshot.get('status','awaiting_api_key')
    root['historicalThrough']=historical.get('as_of')
    root['historicalCoveragePlayers']=historical.get('covered_players',0)
    root['liveCompetitionCatalog']=[{'id':cid,'name':name} for cid,name in COMPETITIONS]
    add_choices(root)
    root['leagueCatalog']=list(dict.fromkeys(root.get('leagueCatalog',[])+[p.get('league') for p in original if p.get('league')]))
    # Write embedded JSON before modifying the runtime script.
    content=json.dumps(root,ensure_ascii=False,separators=(',',':')).replace('</','<\\/')
    html=html[:m.start(2)]+content+html[m.end(2):]
    # The public UI must never conflate a successful site deployment with
    # a successful current-season statistics sync.
    current_ids=set((root['liveTournamentStats'].get('2026/27') or {}).keys())
    current_ids.update((root['liveTournamentStats'].get('2026') or {}).keys())
    current_count=len(current_ids)
    official_count=len({pid for season in ('2026/27','2026') for pid,entries in (by_season.get(season) or {}).items()
                         if any(x.get('source')!='thesportsdb_sample' and x.get('source')!='historical_appearances'
                                for x in entries)})
    free_count=len({pid for season in ('2026/27','2026') for pid,entries in (by_season.get(season) or {}).items()
                     if any(x.get('source')=='thesportsdb_sample' for x in entries)})
    if current_count:
        timestamp=snapshot.get('updated_at') or 'дата неизвестна'
        msg=('2026/27: '+str(official_count)+' игроков с данными футбольного API, '+str(free_count)+
             ' с частичной статистикой TheSportsDB; результаты матчей обновляются отдельно.'+
             (' · API '+timestamp[:10] if official_count else ''))
    else:
        msg=('Личные показатели 2026/27: пока нет проверенных записей. '
             'Результаты матчей обновляются из бесплатных источников отдельно. '
             'Прошлые сезоны обозначены как архивные.')
    html=html.replace('Архивная база · данные не обновляются в реальном времени · клубы и контракты могут измениться.',
                      msg,1)
    # This panel shows competition match SCORES, never claims individual goals/assists.
    html=patch(html,
      '<div class="quality-note">',
      '<div class="quality-note">',)
    html=patch(html,
      '</div><select id="sortBy" class="filter"',
      '</div><select id="sortBy" class="filter"') if False else html
    html=patch(html,'<div class="quality-note">',
      '<details class="free-scoreboard" id="freeMatchesPanel"><summary>Последние результаты матчей 2026/27 · бесплатные источники</summary>'
      '<div class="free-scoreboard-controls"><label for="freeMatchLeague">Лига</label><select id="freeMatchLeague"></select><span id="freeMatchSource"></span></div>'
      '<div id="freeMatchRows" class="free-match-rows"></div>'
      '<p class="free-scoreboard-note">Это результаты команд, а не статистика конкретного игрока. Источники: OpenFootball / football-data.org.</p></details>'
      '<div class="quality-note">')
    # Required non-commercial attribution of the EPL compilation and source date.
    note=('<div class="pl-source-credit">Статистика АПЛ 2026/27: '
          '<a href="https://github.com/oladeeayo/pl-catalogue" target="_blank" rel="noopener noreferrer">pl-catalogue</a>'
          ' · срез '+str(pl.get('published_at') or 'ещё не загружен')[:10]+
          ' · некоммерческое использование · источник обновляется еженедельно.</div>')
    html=html.replace('<details class="free-scoreboard"',note+'<details class="free-scoreboard"',1)
    anchor='<div class="stat-grid">'
    toolbar='<div class="competition-toolbar"><label for="competitionSelect">Турнир</label><select id="competitionSelect" class="chart-switch" aria-label="Выбор турнира"><option value="all">Все загруженные турниры</option></select><span id="competitionStatus" class="competition-status">Статистика турниров пока не загружена</span></div><div class="verified-profile-meta" id="verifiedProfileMeta" aria-live="polite"></div>'
    html=patch(html,anchor,toolbar+anchor)
    html=patch(html,"const contracts = ROOT.contracts;",r"""const contracts = ROOT.contracts;
  const tournamentRows=ROOT.liveTournamentStats||{};
  // Sourced tournament totals may also improve the rolling index. Existing
  // league-only data are retained when the provider snapshot is less complete.
  for(const [season,map] of Object.entries(ROOT.liveIndexStats||{})){
    const target=statsBySeason[season]??={};
    for(const [id,v] of Object.entries(map)){
      const previous=target[id];
      if(!previous||Number(v.minutes)>=Number(previous.minutes||0)){
        target[id]={...previous,...v};
      }
    }
  }
  const tournamentCatalogue=ROOT.liveCompetitionCatalog||[];
  const tournamentCoverage=ROOT.liveCoverage||[];
  const tournamentMetricKeys=['matches','starts','minutes','goals','assists','shots','shots_on_target',
    'passes','key_passes','tackles','interceptions','dribbles','xg','xa','npxg',
    'recoveries','clearances','blocks','progressive_passes','progressive_carries',
    'yellow_cards','red_cards'];
  function eligibleRows(p,season){
    const pool=tournamentRows[season]?.[p.id]||[];
    const currentSeason=(p.league==='MLS'||p.league==='Brasileirão')?'2026':'2026/27';
    if(season!==currentSeason)return pool;
    const permitted=new Set((ROOT.currentCompetitionByPlayer?.[p.id]||[]).map(c=>String(c.id)));
    // An unverified current competition from a community sample must not
    // add unrelated leagues/cups. Allow authenticated match appearances.
    return pool.filter(x=>permitted.has(String(x.id))||
      (x.source==='pitchapi_partial'&&Number(x.matches_loaded)>0)||
      (x.source==='api_football_authenticated'&&x.team_verified===true));
  }
  function tournamentSum(rows){
    const archived=rows.length>0&&rows.every(r=>r.source==='historical_appearances');
    const community=rows.length>0&&rows.every(r=>r.source==='thesportsdb_sample');
    const premier=rows.length>0&&rows.every(r=>r.source==='pl_catalogue');
    const pitched=rows.length>0&&rows.every(r=>r.source==='pitchapi_partial');
    const result={source:archived?'transfermarkt_historical':community?'thesportsdb_partial':premier?'pl_catalogue':pitched?'pitchapi_partial':'api_football_partial',
      partial:!premier,updated_at:archived?ROOT.historicalThrough:community?ROOT.freeSourceSyncAt:premier?ROOT.plCurrentAsOf:pitched?ROOT.pitchAPILastSync:ROOT.liveUpdatedAt};
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
    const all=eligibleRows(p,season);
    const rows=state.competition==='all'?all:all.filter(x=>String(x.id)===state.competition);
    if(rows.length)return tournamentSum(rows);
    if(state.competition!=='all'){
      const home={'Premier League':'39','La Liga':'140','Bundesliga':'78',
        'Serie A':'135','Ligue 1':'61','Primeira Liga':'94','Belgian Pro League':'144',
        'Süper Lig':'203','Saudi Pro League':'307','MLS':'253','Brasileirão':'br-league'}[p.league];
      if(home===state.competition && season!=='2026/27' && season!=='2026')
        return statsBySeason[season]?.[p.id]||null;
      return null;
    }
    // Do not fall back to an unverified current-season seed.
    if(season==='2026/27'||season==='2026')return null;
    return statsBySeason[season]?.[p.id]||null;
  }""")
    html=patch(html,"const urls=[];\n    const custom=storedPhoto(code);",
               "const urls=[];\n    if(p.apiPhoto)urls.push({url:p.apiPhoto,source:'API-Football / ID'});\n    if(p.commonsPhoto)urls.push({url:p.commonsPhoto,source:'Wikimedia Commons',artist:p.commonsArtist,licence:p.commonsLicense,licence_url:p.commonsLicenseUrl,file_page:p.commonsSourcePage});\n    const custom=storedPhoto(code);")
    controls=r"""  function renderTournamentSelector(p){
    const ru=state.language==='ru';
    const select=$('competitionSelect');
    const rows=eligibleRows(p,state.season);
    const currentSeason=(p.league==='MLS'||p.league==='Brasileirão')?'2026':'2026/27';
    const current=state.season===currentSeason;
    const choices=current?(ROOT.currentCompetitionByPlayer?.[p.id]||[]):[];
    const allNames=new Map(choices.map(x=>[String(x.id),x.name]));
    // Older season: show only recorded competitions. Current season: domestic
    // competitions and verified UEFA clubs, never unrelated countries' cups.
    for(const x of rows){
      const key=String(x.id);
      if(!allNames.has(key) && (!current || x.source!=='historical_appearances'))allNames.set(key,x.name);
    }
    if(!current && !allNames.size && statsBySeason[state.season]?.[p.id]){
      const leagues={'Premier League':'39','La Liga':'140','Bundesliga':'78',
        'Serie A':'135','Ligue 1':'61','Primeira Liga':'94','Belgian Pro League':'144',
        'Süper Lig':'203','Saudi Pro League':'307','MLS':'253','Brasileirão':'br-league'};
      if(leagues[p.league])allNames.set(leagues[p.league],p.league);
    }
    select.innerHTML='<option value="all">'+(ru?'Все загруженные турниры':'All available competitions')+'</option>'+
      [...allNames].map(([id,name])=>'<option value="'+esc(id)+'">'+esc(name)+'</option>').join('');
    select.value=state.competition;
    if(select.value!==state.competition){state.competition='all';select.value='all';return renderProfile();}
    select.onchange=()=>{state.competition=select.value;renderProfile()};
    const items=state.competition==='all'?rows:rows.filter(x=>String(x.id)===state.competition);
    const missingCurrent=state.competition!=='all'&&!items.length&&current &&
      choices.some(x=>String(x.id)===state.competition);
    const title=state.competition==='all'?(ru?'Все турниры':'All competitions'):(allNames.get(state.competition)||state.competition);
    const date=ROOT.liveUpdatedAt?new Date(ROOT.liveUpdatedAt).toLocaleDateString(ru?'ru-RU':'en-GB'):'';
    let message='';
    if(items.length){
      const pitched=items.every(x=>x.source==='pitchapi_partial');
      if(pitched){
        $('competitionStatus').textContent=title+' · '+(ru?'PitchAPI: данные по '+items.reduce((n,x)=>n+(x.matches_loaded||0),0)+' матчам, покрытие ещё неполное':
          'PitchAPI: '+items.reduce((n,x)=>n+(x.matches_loaded||0),0)+' matched games; coverage still partial');
        return;
      }
      const premier=items.every(x=>x.source==='pl_catalogue');
      if(premier){
        $('competitionStatus').textContent=title+' · '+(ru?'АПЛ: актуальный опубликованный срез от ':'PL: published weekly snapshot ')+(ROOT.plCurrentAsOf||'—').slice(0,10);
        return;
      }
      const community=items.every(x=>x.source==='thesportsdb_sample');
      if(community){
        $('competitionStatus').textContent=title+' · '+(ru?'TheSportsDB: неполная выборка (не все матчи/показатели)':'TheSportsDB: partial sample (not all matches/stats)');
        return;
      }
      const onlyArchive=items.every(x=>x.source==='historical_appearances');
      if(onlyArchive){
        $('competitionStatus').textContent=title+' · '+(ru?'Архив до ':'Archive through ')+(ROOT.historicalThrough||'2026-06-28')+
          ' · '+(ru?'матчи из источника Transfermarkt, не текущий сезон':'Transfermarkt match data, not live');
        return;
      }
      message=(ru?'Загружено: ':'Available: ')+items.length+' '+(ru?'турн.':'comp.')+
        (date?' · '+(ru?'обновлено ':'updated ')+date:'')+' · '+(ru?'покрытие неполное':'partial coverage');
    }else if(missingCurrent){
      message=ru?'Клуб участвует в турнире, но статистика игрока ещё не получена; это не означает 0 матчей.':
        'The club enters this competition, but player stats are missing (not 0).';
    }else if(ROOT.liveStatus==='awaiting_api_key'||!ROOT.liveUpdatedAt){
      message=ru?'Статистика игрока ещё не получена':'Verified player statistics not available';
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
      "const playerFoot=p.foot||meta.foot;$('pFoot').textContent=playerFoot?(ru?(playerFoot==='left'?'Левая':playerFoot==='both'?'Обе':'Правая'):(playerFoot==='left'?'Left':playerFoot==='both'?'Both':'Right')):'—';")
    html=patch(html,"function derivedAge(player){if(player?.age!=null",
      "function derivedAge(player){if(player?.birth){const born=new Date(player.birth),today=new Date();if(!Number.isNaN(born.getTime()))return today.getUTCFullYear()-born.getUTCFullYear()-(today.getUTCMonth()<born.getUTCMonth()||(today.getUTCMonth()===born.getUTCMonth()&&today.getUTCDate()<born.getUTCDate())?1:0);}if(player?.age!=null")
    # No automatic Wikipedia thumbnails: name search often returns the wrong person.
    html=patch(html,"if(profile||firstCards){lookupWikipedia(p).then(found=>",
      "if(false && (profile||firstCards)){lookupWikipedia(p).then(found=>")
    html=patch(html,"${esc(position[state.language][p.pos]||p.pos)}</div>${sub}","${esc(p.displayPosition?(p.displayPosition+' · '+(position[state.language][p.pos]||p.pos)):(position[state.language][p.pos]||p.pos))}</div>${sub}")
    html=patch(html,"function cardMarkup(p){const c=contract(p),s=stat(p);const sub=","function cardMarkup(p){const c=contract(p),s=stat(p),idx=projectedIndex(p);const indexTag=idx.proxy?'<small class=\"player-index unavailable\">'+(state.language==='ru'?'Индекс: нет данных':'Index: no data')+'</small>':'<small class=\"player-index\">'+(state.language==='ru'?'Индекс ':'Index ')+idx.score+'/100'+(idx.exact?'':' ≈')+'</small>';const sub=")
    html=patch(html,"${esc(p.season||'2026/27')}</span></span></button>","${esc(p.season||'2026/27')}</span>${indexTag}</span></button>")
    html=patch(html,"function choosePlayer(id){state.player=String(id);",
       "function choosePlayer(id){state.player=String(id);state.competition='all';")
    html=patch(html,"    const apply=o=>{",
      """    const showCredit=o=>{
      if(!label)return;label.textContent='Фото: '+o.source;
      if(o.artist)label.append(document.createTextNode(' · '+o.artist));
      for(const [url,txt] of [[o.file_page,'файл'],[o.licence_url,o.licence||'лицензия']]){
        if(!url||!/^https:\/\//.test(url))continue;
        const a=document.createElement('a');a.href=url;a.target='_blank';a.rel='noopener noreferrer';
        a.textContent=' · '+txt;label.append(a);
      }
    };
    const apply=o=>{""")
    html=html.replace("if(label)label.textContent='Фото: '+o.source","showCredit(o)")
    profile_meta=r"""  function renderVerifiedProfileMeta(p){
    const el=$('verifiedProfileMeta');
    if(!el)return;
    const ru=state.language==='ru';
    const label=(r,e)=>ru?r:e;
    const facts=[];
    if(p.displayPosition)facts.push(label('Амплуа: ','Role: ')+p.displayPosition+
      (p.positionAsOf?' ('+p.positionAsOf+')':''));
    if(p.foot)facts.push(label('Рабочая нога: ','Foot: ')+
      ({left:label('левая','left'),right:label('правая','right'),
        both:label('обе','both')}[p.foot]||p.foot));
    if(p.contractUntilCurrent){
      facts.push(label('Контракт по опубликованному срезу: ','Contract (published snapshot): ')+
        p.contractUntilCurrent+' · '+(p.contractSourceAsOf||''));
    }else if(p.contractUntilArchive){
      facts.push(label('Контракт по архиву: ','Contract (archived): ')+
        p.contractUntilArchive+' · '+(p.contractArchiveAsOf||'2026-07'));
    }
    if(p.marketValueArchiveEUR!=null){
      facts.push(label('Архивная стоимость: €','Archived value: €')+
        Number(p.marketValueArchiveEUR).toLocaleString(ru?'ru-RU':'en-GB'));
    }
    el.textContent=facts.length?facts.join(' · '):
      label('Дополнительные данные профиля пока не подтверждены',
            'Additional profile attributes not yet verified');
  }
"""
    html=patch(html,"  function renderProfile(){",controls+profile_meta+"  function renderProfile(){")
    html=patch(html,"renderChart(p,s);renderStrengths(s,p);renderAdvanced(s);",
               """renderChart(p,s);renderStrengths(s,p);renderAdvanced(s);renderTournamentSelector(p);renderVerifiedProfileMeta(p);
    if(s?.source==='pitchapi_partial'){
      $('statsSourceCaption').textContent=state.language==='ru'?'PitchAPI · проверенные матчи, частичная статистика':'PitchAPI · verified games, partial season';
    }else if(s?.source==='pl_catalogue'){
      $('statsSourceCaption').textContent='pl-catalogue · '+(ROOT.plCurrentAsOf||'').slice(0,10)+' · некоммерческое использование';
    }else if(s?.source==='thesportsdb_partial'){
      $('statsSourceCaption').textContent=state.language==='ru'?'TheSportsDB · неполные показатели, не сезонный итог':'TheSportsDB · incomplete records, not a season total';
    }else if(s?.source==='api_football_partial'){
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
