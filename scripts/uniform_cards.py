"""Consistent player cards: real season totals, contract evidence and index."""
def inject_uniform_cards(html):
    begin='  function cardMarkup(p){'
    end='  function setupCards(host){'
    if html.count(begin)!=1 or html.count(end)!=1:
        raise RuntimeError('Cannot locate unique player-card code')
    a=html.index(begin)
    b=html.index(end,a)
    renderer=r"""  function cardCurrentSeason(p){
    return ['MLS','Brasileirão'].includes(p.league)?'2026':'2026/27';
  }
  function cardStatEvidence(p){
    const year=cardCurrentSeason(p),id=String(p.id);
    const source=ROOT.liveIndexStats?.[year]?.[id]||statsBySeason[year]?.[id]||null;
    if(!source||![source.minutes,source.matches,source.goals,source.assists]
       .some(v=>v!==null&&v!==undefined))return null;
    return source;
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
    const legacy=contract(p);
    if(legacy&&Number(legacy.year)>=Number(today.slice(0,4))&&(!transfer||transfer<=archiveAsOf))
      return {text:(ru?'Контракт до ':'Contract until ')+legacy.year,
              status:'archived',hint:ru?'справочный срез':'reference snapshot'};
    return {text:ru?'Контракт: не подтверждён':'Contract: unverified',
            status:'missing',hint:ru?'Данные уточняются':'Awaiting source'};
  }
  function cardMarkup(p){
    const ru=state.language==='ru';
    const year=cardCurrentSeason(p);
    const stats=cardStatEvidence(p);
    const c=cardContractEvidence(p);
    const idx=projectedIndex(p);
    const goal=stats?.goals==null?'—':nf(stats.goals);
    const assist=stats?.assists==null?'—':nf(stats.assists);
    const gs=(ru?'Голы: ':'Goals: ')+goal+
      (ru?' · Ассисты: ':' · Assists: ')+assist;
    const label=stats
      ?(ru?'Статистика '+year:'Stats '+year)
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
          '<span class="card-meta">'+esc(p.team||'—')+'<br>'+esc(role)+'</span>'+
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
