"""Consistent player cards: real season totals, contract evidence and index."""
def inject_uniform_cards(html):
    begin='  function cardMarkup(p){'
    end='  function setupCards(host){'
    if html.count(begin)!=1 or html.count(end)!=1:
        raise RuntimeError('Cannot locate unique player-card code')
    a=html.index(begin)
    b=html.index(end,a)
    renderer=r"""  const cardObserver=window.IntersectionObserver?new IntersectionObserver(entries=>{
    for(const x of entries){
      if(!x.isIntersecting)continue;
      const avatar=x.target;cardObserver.unobserve(avatar);
      const img=avatar.querySelector('[data-photo]');
      const fb=avatar.querySelector('[data-pfallback]');
      if(img&&fb)attachPhoto(img,fb,img.dataset.photo);
    }
  },{rootMargin:'140px'}):null;
  function cardCurrentSeason(p){
    return ['MLS','Brasileirão','Argentine Primera División','Eliteserien','Allsvenskan','J1 League','K League 1'].includes(p.league)?'2026':'2026/27';
  }
  function cardStatEvidence(p){
    const year=cardCurrentSeason(p),id=String(p.id);
    const valid=source=>source&&[source.minutes,source.matches,source.goals,source.assists]
      .some(v=>v!==null&&v!==undefined);
    if(p.origin==='transfermarkt_archived_2026'){
      // The index aggregation requires >=180 minutes, but a factual card
      // remains available for a single verified appearance. Never zero-fill
      // missing advanced stats or label a 2024/25 match as 2025/26.
      const candidates=[p.archiveReferenceSeason,p.season,year==='2026'?'2025':'2025/26',
        year==='2026'?'2024':'2024/25'];
      for(const season of [...new Set(candidates.filter(Boolean))]){
        const rows=(ROOT.liveTournamentStats?.[season]?.[id]||[])
          .filter(r=>r.source==='historical_appearances'&&
            Number(r.stats?.minutes)>0);
        if(rows.length){
          const sum=key=>rows.reduce((n,r)=>n+(Number(r.stats?.[key])||0),0);
          return {stats:{matches:sum('matches'),minutes:sum('minutes'),
            goals:sum('goals'),assists:sum('assists')},season,archived:true,
            source:'transfermarkt_historical',lowSample:sum('minutes')<180};
        }
      }
      return null;
    }
    const current=ROOT.liveIndexStats?.[year]?.[id]||statsBySeason[year]?.[id]||null;
    if(valid(current))return {stats:current,season:year,archived:false};
    const prior=year==='2026'?'2025':'2025/26';
    const history=ROOT.liveIndexStats?.[prior]?.[id]||statsBySeason[prior]?.[id]||null;
    if(valid(history))return {stats:history,season:prior,archived:true};
    return null;
  }
  function cardContractEvidence(p){
    const ru=state.language==='ru';
    const today=dayAsOf();
    const transfer=String(p.clubSourceAsOf||'').slice(0,10);
    const archiveAsOf=String(p.contractArchiveAsOf||'2026-07').slice(0,10);
    const future=v=>/^20\d{2}-\d{2}-\d{2}$/.test(String(v||''))&&String(v)>=today;
    if(future(p.contractUntilCurrent))
      return {text:(ru?'Контракт до ':'Contract until ')+String(p.contractUntilCurrent).slice(0,4),
              status:'verified',hint:ru?'Опубликованный срез':'Published snapshot'};
    if(p.contractThroughYear && Number(p.contractThroughYear)>=Number(today.slice(0,4)))
      return {text:(ru?'Контракт до ':'Contract through ')+p.contractThroughYear,
              status:'verified',hint:ru?'Год подтверждён':'Year confirmed'};
    // Do not carry an archived contract into a new club after a transfer.
    if(future(p.contractUntilArchive)&&(!transfer||transfer<=archiveAsOf))
      return {text:(ru?'Контракт до ':'Contract until ')+String(p.contractUntilArchive).slice(0,4),
              status:'archived',hint:ru?'архив · июль 2026':'archived · July 2026'};
    if(p.contractUntilArchive)
      return {text:(ru?'Архив: договор до ':'Archived contract until ')+
                String(p.contractUntilArchive).slice(0,4),
              status:'archived',hint:ru?'истёк или клуб изменился; текущий не подтверждён':
                                     'expired or moved; current unverified'};
    const legacy=contract(p);
    if(legacy&&Number(legacy.year)>=Number(today.slice(0,4))&&(!transfer||transfer<=archiveAsOf))
      return {text:(ru?'Контракт до ':'Contract until ')+legacy.year,
              status:'archived',hint:ru?'справочный срез':'reference snapshot'};
    return {text:ru?'Контракт: не подтверждён':'Contract: unverified',
            status:'missing',hint:ru?'Данные уточняются':'Awaiting source'};
  }
  let roleRankCache=null;
  function relativeRoleRank(p){
    const rated=projectedIndex(p);
    if(rated.proxy||rated.coverage<60||(rated.rolling?.weightedMinutes||0)<450)
      return null;
    if(roleRankCache===null){
      roleRankCache={};
      for(const athlete of players){
        const r=projectedIndex(athlete);
        if(r.proxy||r.coverage<60||(r.rolling?.weightedMinutes||0)<450)
          continue;
        (roleRankCache[r.role]??=[]).push({id:String(athlete.id),score:r.score});
      }
      for(const values of Object.values(roleRankCache))
        values.sort((a,b)=>b.score-a.score||a.id.localeCompare(b.id));
    }
    const group=roleRankCache[rated.role]||[];
    const rank=group.findIndex(x=>x.id===String(p.id))+1;
    return rank>0?{rank,total:group.length,role:rated.role}:null;
  }
  function cardMarkup(p){
    const ru=state.language==='ru';
    const year=p.origin==='transfermarkt_archived_2026'
      ? (p.archiveReferenceSeason||p.season||'2025/26') : cardCurrentSeason(p);
    const stats=cardStatEvidence(p);
    const c=cardContractEvidence(p);
    const idx=projectedIndex(p);
    const goal=stats?.stats?.goals==null?'—':nf(stats.stats.goals);
    const assist=stats?.stats?.assists==null?'—':nf(stats.stats.assists);
    const seasonLabel=stats?.archived
      ?(ru?' · Архив '+stats.season:' · Archive '+stats.season):'';
    const matchCount=stats?.stats?.matches==null?'—':nf(stats.stats.matches);
    const gs=(ru?'Матчи: ':'Matches: ')+matchCount+
      (ru?' · Голы: ':' · Goals: ')+goal+
      (ru?' · Ассисты: ':' · Assists: ')+assist+seasonLabel;
    const label=stats
      ?(ru?'Подтверждённая статистика '+stats.season:
            'Verified statistics '+stats.season)
      :(ru?'Нет подтверждённой статистики '+year:'Unverified stats '+year);
    const index=idx.proxy?(ru?'Индекс: нет данных':'Index: no data'):
      (ru?'Индекс ':'Index ')+(idx.exact?'':'≈')+idx.score+'/100';
    const role=p.displayPosition?
      p.displayPosition+' · '+(position[state.language][p.pos]||p.pos):
      (position[state.language][p.pos]||p.pos||'—');
    const cls=idx.proxy?'unavailable':'';
    return '<article class="player-card card-uniform">'+
      '<button class="player-card-open" data-open="'+esc(p.id)+'">'+
        '<span class="avatar"><span class="fallback" data-pfallback="'+esc(p.id)+'">'+
          esc(initials(p))+'</span><img data-photo="'+esc(p.id)+
          '" alt="" loading="lazy" decoding="async" hidden></span>'+
        '<span class="card-body-uniform">'+
          '<span class="card-name">'+esc(p.name)+'</span>'+
          '<span class="card-meta">'+esc(p.team||'—')+
            (p.origin==='transfermarkt_archived_2026'?' · архив клуба 2026':'')+'<br>'+esc(role)+'</span>'+
          '<span class="card-fixed-stats" title="'+esc(label)+'">'+esc(gs)+'</span>'+
          '<span class="card-fixed-contract '+c.status+'" title="'+esc(c.hint)+'">'+
            esc(c.text)+' <small>'+esc(c.hint)+'</small></span>'+
          '<span class="card-fixed-bottom">'+
            '<span class="league-tag">'+esc(p.league||'—')+' · '+year+'</span>'+
            '<span class="player-index '+cls+'">'+esc(index)+'</span>'+
          '</span>'+
        '</span>'+
      '</button>'+
      '<button class="card-fav '+(state.favorites.includes(p.id)?'active':'')+
      '" title="Favorite" data-favorite="'+esc(p.id)+'">'+
      (state.favorites.includes(p.id)?'★':'☆')+'</button></article>';
  }
"""
    return html[:a]+renderer+html[b:]
