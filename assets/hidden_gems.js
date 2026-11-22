/* Hidden Gems 1.0 — no external API requests, no fabricated valuations. */
(() => {
  'use strict';
  const byId = id => document.getElementById(id);
  const esc = value => String(value ?? '').replace(/[&<>"']/g, char =>
    ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[char]));
  const money = n => '€' + (Number(n) / 1000000).toLocaleString('ru-RU', {maximumFractionDigits:2}) + ' млн';
  const fmt = n => n===null || n===undefined || !Number.isFinite(Number(n)) ? '—' : Number(n).toLocaleString('ru-RU');
  const YYYYMMDD = /^\d{4}-\d{2}-\d{2}$/;
  const marketMaxAgeDays = 120;
  let bridge, data = null, activeTab = 'confirmed', shown = 30, observer = null, firstRender = true;

  function asDate(s) {
    if (typeof s !== 'string' || !YYYYMMDD.test(s)) return null;
    const d = new Date(s + 'T00:00:00Z');
    return Number.isFinite(d.getTime()) && d.toISOString().slice(0,10) === s ? d : null;
  }
  function asOf() {
    const raw = byId('embeddedData')?.textContent;
    try {
      const v = JSON.parse(raw || '{}').siteBuiltAtUTC;
      return new Date(v).toISOString().slice(0,10);
    } catch (_) {
      return new Date().toISOString().slice(0,10);
    }
  }
  function ageAt(birth, stamp) {
    const a = asDate(birth), b = asDate(stamp);
    if (!a || !b || a > b) return null;
    let age = b.getUTCFullYear() - a.getUTCFullYear();
    if (b.getUTCMonth() < a.getUTCMonth() ||
        (b.getUTCMonth() === a.getUTCMonth() && b.getUTCDate() < a.getUTCDate())) age--;
    return age;
  }
  function percentile(values, value) {
    let lower = 0, ties = 0;
    for (const n of values) {
      if (n < value) lower++;
      else if (n === value) ties++;
    }
    return (lower + ties / 2) / values.length;
  }
  function prepare() {
    const stamp = asOf();
    const verification = new Map((bridge.verification()?.players||[]).map(row=>[row.player_id,row]));
    data = bridge.list().map(p => {
      const age = ageAt(p.birth, stamp);
      const r = p.rating;
      const eligible = !!p.positionEvidence && p.minutes !== null &&
        Number.isFinite(p.minutes) && p.minutes >= 450 &&
        ['Goalkeeper','Defender','Midfielder','Forward'].includes(p.position);
      // A limited archive supports exploration, not a current verified rating.
      const rated = !!r && !r.proxy && Number.isFinite(r.score) &&
        r.weightedMinutes >= 450 && r.coverage >= 30;
      const reliable = eligible && rated && p.currentEvidence &&
        r.coverage >= 60;
      const marketDate = p.market && asDate(p.market.as_of);
      const ageDays = marketDate ? (asDate(stamp) - marketDate) / 86400000 : NaN;
      const fresh = !!marketDate && ageDays >= 0 && ageDays <= marketMaxAgeDays;
      return {...p, age, eligible, rated, reliable, market:fresh?p.market:null,
        verification:verification.get(String(p.id))||null,
        marketStale:!fresh && !!p.market,
        score:null, archiveScore:null, scoutPercentile:null, scoutPeers:0, peers:0, archivePeers:0,
        gap:null, archiveGap:null, performancePercentile:null,
        pricePercentile:null, archivePerformancePercentile:null,
        archivePricePercentile:null, quality:'C'};
    }).filter(p => p.age !== null && p.age >= 0 && p.age <= 35);

    // Current market comparisons use only contemporaneously verified data.
    const known = data.filter(p => p.reliable && p.market && p.market.value_eur > 0);
    for (const candidate of known) {
      const peers = known.filter(p => p.rating.role === candidate.rating.role &&
        Math.abs(p.age-candidate.age) <= 3);
      candidate.peers = peers.length;
      if (peers.length < 25) continue;
      const performance = percentile(peers.map(p=>p.rating.score),candidate.rating.score);
      const price = percentile(peers.map(p=>p.market.value_eur),candidate.market.value_eur);
      candidate.performancePercentile = performance;
      candidate.pricePercentile = price;
      candidate.gap = performance-price;
      candidate.score = Math.round(100*Math.max(0,Math.min(1,.5+.5*candidate.gap)));
      candidate.quality = candidate.rating.coverage >= 80 &&
        !candidate.statsPartial && candidate.rating.exact ? 'A':'B';
    }

    // Current sporting scout percentile, independent of market prices. Never
    // call this "undervalued": source-backed play does not establish a deal fee.
    const scoutPool=data.filter(p=>p.reliable&&p.age<=25);
    const currentByRole=new Map();
    for(const p of scoutPool){
      if(!currentByRole.has(p.rating.role))currentByRole.set(p.rating.role,[]);
      currentByRole.get(p.rating.role).push(p);
    }
    for(const p of scoutPool){
      const peers=(currentByRole.get(p.rating.role)||[]).filter(other=>
        Math.abs(other.age-p.age)<=4);
      p.scoutPeers=peers.length;
      if(peers.length<12)continue;
      p.scoutPercentile=Math.round(100*percentile(
        peers.map(other=>other.rating.score),p.rating.score));
    }

    // Dated archival screening. A CURRENT rolling index cannot be used as
    // 2025/26 performance against a 2026 archival price: that leaks later data.
    // Restrict this narrower signal to verified 2025/26 G+A per 90 for
    // attacking roles and recorded archive prices after the season.
    const attackingRoles=new Set(['ST','LW/RW','AM','CM']);
    const archiveKnown=data.filter(p=>{
      const row=p.archiveStats,stamp=String(p.archive?.as_of||'');
      const dated=stamp.startsWith('2026-07') ||
        (asDate(stamp) && asDate(stamp)>=asDate('2026-06-28'));
      if (!p.eligible || !attackingRoles.has(p.role) ||
          p.archiveSeason!=='2025/26' || !dated || !p.archive ||
          !Number.isFinite(p.archive.eur) || p.archive.eur<=0 ||
          !row || !Number.isFinite(Number(row.minutes)) ||
          Number(row.minutes)<450 || row.goals==null || row.assists==null) return false;
      p.archiveProduction=90*(Number(row.goals)+Number(row.assists))/Number(row.minutes);
      return Number.isFinite(p.archiveProduction) && p.archiveProduction>=0;
    });
    const byRole=new Map();
    for(const p of archiveKnown){
      if(!byRole.has(p.role))byRole.set(p.role,[]);
      byRole.get(p.role).push(p);
    }
    for(const candidate of archiveKnown){
      const peers=(byRole.get(candidate.role)||[]).filter(p=>
        Math.abs(p.age-candidate.age)<=3);
      candidate.archivePeers=peers.length;
      if(peers.length<25)continue;
      const sport=percentile(peers.map(p=>p.archiveProduction),candidate.archiveProduction);
      const price=percentile(peers.map(p=>p.archive.eur),candidate.archive.eur);
      candidate.archivePerformancePercentile=sport;
      candidate.archivePricePercentile=price;
      candidate.archiveGap=sport-price;
      candidate.archiveScore=Math.round(100*Math.max(0,Math.min(1,.5+.5*candidate.archiveGap)));
    }
    window.TransferLabGemsCoverage={
      youthWithSeasonMinutes:data.filter(p=>p.age>=16&&p.age<=23&&p.eligible).length,
      youthWithMeasuredIndex:data.filter(p=>p.age>=16&&p.age<=23&&p.eligible&&p.rated).length,
      youthWithArchivedValueGap:data.filter(p=>p.age>=16&&p.age<=23&&p.archiveScore!==null).length,
      youthWithContemporaneousScoutingScore:data.filter(p=>p.age>=16&&p.age<=23&&p.scoutPercentile!==null).length,
      youthWithVerifiedCurrentValueGap:data.filter(p=>p.age>=16&&p.age<=23&&p.score!==null).length,
      archiveIsNotCurrent:true
    };
    const leagues=[...new Set(data.map(p=>p.league).filter(Boolean))].sort((a,b)=>a.localeCompare(b,'ru'));
    const host=byId('gemsLeague');
    for (const league of leagues) {
      const option=document.createElement('option');
      option.value=league; option.textContent=league; host.append(option);
    }
  }
  function filtered() {
    const maxAge=Number(byId('gemsAge').value);
    const maxPrice=Number(byId('gemsPrice').value)*1000000;
    const minMinutes=Number(byId('gemsMinutes').value);
    const position=byId('gemsPosition').value;
    const league=byId('gemsLeague').value;
    const valid=data.filter(p => p.age <= maxAge && p.eligible &&
      p.minutes >= minMinutes && (position==='all'||p.position===position) &&
      (league==='all'||p.league===league));
    const confirmed=valid.filter(p=>p.score!==null && p.market?.value_eur<=maxPrice &&
      p.verification?.data_ready_for_market_comparison===true &&
      p.performancePercentile>=.65 && p.gap>=.20);
    const preliminary=valid.filter(p=>{
      if (p.score!==null && p.market?.value_eur<=maxPrice &&
        p.verification?.data_ready_for_market_comparison===true &&
        p.performancePercentile>=.65 && p.gap>=.20) return false;
      // A dated archive valuation is a FILTER ON THE ARCHIVE, not today's price.
      // Players with unknown price stay visible as clearly labelled candidates.
      if (p.archive && Number.isFinite(p.archive.eur) && p.archive.eur>maxPrice) return false;
      if (p.market && p.market.value_eur>maxPrice) return false;
      return true;
    });
    const sort=byId('gemsSort').value;
    function sortFn(a,b) {
      const aindex=a.rated?a.rating.score:-1, bindex=b.rated?b.rating.score:-1;
      const avalue=a.market?.value_eur??a.archive?.eur??Infinity;
      const bvalue=b.market?.value_eur??b.archive?.eur??Infinity;
      if (sort==='index') return bindex-aindex || a.name.localeCompare(b.name,'ru');
      if (sort==='age') return a.age-b.age || bindex-aindex;
      if (sort==='price') return avalue-bvalue || bindex-aindex;
      if (sort==='minutes') return b.minutes-a.minutes || bindex-aindex;
      // First compare current validated rank, then separately the historical score.
      return (b.score??b.scoutPercentile??b.archiveScore??-1)-(a.score??a.scoutPercentile??a.archiveScore??-1) ||
        bindex-aindex || a.name.localeCompare(b.name,'ru');
    }
    const scouted=valid.filter(p=>p.scoutPercentile!==null)
      // This category deliberately DOES NOT use archived "budget" as though
      // it were a confirmed current market price.
      .sort((a,b)=>b.scoutPercentile-a.scoutPercentile ||
        b.rating.score-a.rating.score || a.age-b.age);
    confirmed.sort(sortFn); preliminary.sort(sortFn);
    const successes=(bridge.outcomeReport()?.successes||[]).filter(p=>
      Number(p.age_at_discovery)<=maxAge &&
      Number(p.market_value_eur)<=maxPrice &&
      Number(p.minutes_at_discovery)>=minMinutes &&
      (position==='all'||p.position===position) &&
      (league==='all'||p.league===league));
    return {confirmed,preliminary,scouted,successes};
  }
  function renderCard(p) {
    const price=p.market ?
      money(p.market.value_eur)+' <small>от '+esc(p.market.as_of)+' · '+esc(p.market.source)+'</small>' :
      p.archive && Number.isFinite(p.archive.eur) ?
      money(p.archive.eur)+' <small>архив · '+esc(p.archive.as_of)+' · не текущая стоимость</small>' :
      'Актуальная стоимость неизвестна';
    const ratio=p.score!==null ?
      '<strong class="gems-score">'+p.score+'/100</strong>' :
      '<span class="gems-unrated" title="Свежая рыночная оценка отсутствует">—</span>';
    const archiveRatio=p.archiveScore!==null ?
      '<span class="gems-archival-score">Архивный атакующий сигнал (Г+А/90): '+p.archiveScore+'/100 · '+
        p.archivePeers+' аналогов</span>' : '';
    const scouting=p.scoutPercentile!==null?
      '<span class="gems-scout-score">Уровень среди сверстников: '+p.scoutPercentile+
      '-й процентиль · '+p.scoutPeers+
      ' аналогов. Не рыночная недооценка.</span>' : '';
    const explanation=p.score!==null ?
      'По эффективности '+Math.round(p.performancePercentile*100)+'-й процентиль, по цене '+
      Math.round(p.pricePercentile*100)+'-й · '+p.peers+' аналогов' :
      p.scoutPercentile!==null ?
      'Сверено с игроками той же позиции и близкого возраста при наличии текущих матчей. Для доказательства рыночной недооценённости нужна внешняя цена.' :
      p.archiveScore!==null ?
      'Сезон 2025/26: Г+А/90 '+p.archiveProduction.toFixed(2)+
        ', атакующий вклад '+Math.round(p.archivePerformancePercentile*100)+
        '-й процентиль, цена архива '+Math.round(p.archivePricePercentile*100)+
        '-й · это не общий индекс и не текущая недооценка' :
      p.rated ? 'Нет актуальных оценок или 25 сопоставимых игроков; число недооценённости не рассчитывается' :
      'Спортивный индекс пока не подтверждён по полноте показателей';
    const tag=p.score!==null && p.performancePercentile>=.65 && p.gap>=.20 ?
      '<span class="gems-find">Выраженная недооценённость</span>' : '';
    const contract=p.contractCurrent ?
      'Контракт до '+esc(String(p.contractCurrent).slice(0,4))+' · опубликованные данные' :
      p.contractArchived ?
      'Контракт до '+esc(String(p.contractArchived).slice(0,4))+
      ' · архив '+esc(p.contractArchivedAt||'2026-07') :
      'Контракт: нет подтверждения';
    const index=p.rated?(p.rating.exact?'':'≈')+p.rating.score+'/100':'—';
    // Source audit says what can actually be verified. An archived valuation
    // or a proprietary model estimate never passes as a licensed current quote.
    const status=p.verification;
    const checks=status?[
      status.current_stats_verified,status.current_club_verified,
      status.fresh_value_verified].filter(Boolean).length:null;
    const missingLabels={
      current_matches:'свежие матчи',
      current_club:'актуальный клуб',
      licensed_fresh_market_value:'актуальная подтверждённая цена'};
    const auditLine=status?
      '<span class="gems-evidence">'+
      'Проверка источников: '+checks+'/3 · '+
      (status.missing.length?
        'Нужно подтвердить: '+status.missing.map(k=>missingLabels[k]||k).join(', '):
        'все данные для рыночного сравнения собраны')+
      '</span>':'';
    const period=p.currentEvidence?'Подтверждённый текущий сезон '+p.statPeriod:
      'Архивный сезон '+p.statPeriod;
    const club=esc(p.club)+(p.clubArchived?' · клуб по историческим данным, сейчас не подтверждён':'')+' · '+esc(p.league);
    const quality=p.score!==null?'Data Confidence: '+p.quality+' · актуальная оценка':
      p.rated&&p.rating.provisional?'Data Confidence: C · предварительный индекс':
      p.rated?'Data Confidence: B · частичная статистика':
      'Data Confidence: C · индекс недоступен';
    return '<article class="gems-card"><button class="gems-card-open" type="button" data-gem-open="'+esc(p.id)+'">'+
      '<span class="gems-avatar"><span class="gems-avatar-fallback" data-gem-fallback="'+esc(p.id)+'">'+
      esc(p.name.split(/\s+/).slice(0,2).map(s=>s[0]||'').join(''))+'</span>'+
      '<img data-gem-photo="'+esc(p.id)+'" alt="" loading="lazy" decoding="async" hidden></span>'+
      '<span class="gems-card-main"><span class="gems-player">'+esc(p.name)+'</span>'+
      '<span class="gems-meta">'+club+'</span><span class="gems-meta">'+p.age+' лет · '+
      esc(p.precisePosition||p.position)+' · '+fmt(p.minutes)+' минут · '+fmt(p.matches)+' матчей</span>'+
      '<span class="gems-meta">'+esc(period)+' · '+esc(p.statsSource||'источник не указан')+
      ' · срез '+esc(p.statsAsOf||'не указан')+'</span>'+
      '<span class="gems-price">'+price+'</span>'+
      '<span class="gems-contract">'+contract+'</span>'+auditLine+scouting+
      '<span class="gems-explain">'+esc(explanation)+'</span>'+tag+'</span>'+
      '<span class="gems-card-stats"><span class="gems-stat-label">TransferLab Index</span>'+
      '<strong>'+index+'</strong><span class="gems-stat-label">Hidden Gem Score</span>'+
      ratio+archiveRatio+'<span class="gems-quality">'+esc(quality)+'</span></span>'+
      '</button></article>';
  }
  function renderSuccessCard(p) {
    const fee=money(Number(p.reported_fee_eur_m)*1000000);
    const predicted=money(Number(p.model_forecast_eur_m)*1000000);
    return '<article class="gems-card gems-success-card">'+
      '<button class="gems-card-open" type="button" data-gem-open="'+esc(p.player_id)+'">'+
      '<span class="gems-card-main"><span class="gems-player">'+esc(p.name||p.player_id)+'</span>'+
      '<span class="gems-meta">Найден '+esc(p.discovered_at)+' · '+esc(p.from_club)+
      ' → '+esc(p.to_club)+' · трансфер '+esc(p.deal_date)+'</span>'+
      '<span class="gems-meta">Рыночная оценка при обнаружении: '+money(p.market_value_eur)+
      ' ('+esc(p.market_as_of)+')</span>'+
      '<span class="gems-meta">Прогноз TransferLab от '+esc(p.forecast_at)+
      ': '+predicted+' · сообщённая сумма: '+fee+'</span>'+
      '<span class="gems-meta">Ошибка прогноза: '+fmt(p.forecast_error_pct)+'% · Hidden Gem Score: '+
      fmt(p.hidden_gem_score)+'/100</span>'+
      '<span class="gems-explain">Ретроспективная проверка; цена перехода не равна объективной стоимости.</span>'+
      '</span></button><p class="gems-success-sources">Источники: <a href="'+esc(p.market_source_url)+
      '" target="_blank" rel="noopener noreferrer">оценка</a> · <a href="'+esc(p.official_source)+
      '" target="_blank" rel="noopener noreferrer">клуб</a> · <a href="'+esc(p.fee_source)+
      '" target="_blank" rel="noopener noreferrer">сумма перехода</a></p></article>';
  }
  function connectPhotos(host) {
    if (observer) observer.disconnect();
    const avatars=[...host.querySelectorAll('.gems-avatar')];
    const load=el=>{
      const img=el.querySelector('[data-gem-photo]');
      const fallback=el.querySelector('[data-gem-fallback]');
      if(img && fallback) bridge.attachPortrait(img,fallback,img.dataset.gemPhoto);
    };
    // Load the first visible portraits immediately; never block on observer events.
    if (!('IntersectionObserver' in window)) { avatars.forEach(load); return; }
    observer=new IntersectionObserver(entries=>{
      for(const e of entries){
        if(!e.isIntersecting)continue;
        observer.unobserve(e.target);
        load(e.target);
      }
    },{rootMargin:'250px'});
    avatars.forEach((el,i)=>i<8?load(el):observer.observe(el));
  }
  function render(reset=true) {
    if (!data) return;
    if (reset) shown=30;
    const choices=filtered();
    byId('gemsConfirmedCount').textContent=fmt(choices.confirmed.length);
    byId('gemsScoutCount').textContent=fmt(choices.scouted.length);
    byId('gemsPreviewCount').textContent=fmt(choices.preliminary.length);
    byId('gemsSuccessCount').textContent=fmt(choices.successes.length);
    if (firstRender && !choices.confirmed.length && activeTab==='confirmed') {
      activeTab=choices.scouted.length?'scouted':'preview';
    }
    firstRender=false;
    for (const [tab,id] of [['confirmed','gemsConfirmedTab'],
      ['scouted','gemsScoutTab'],['preview','gemsPreviewTab'],['success','gemsSuccessTab']]) {
      byId(id).classList.toggle('active',activeTab===tab);
      byId(id).setAttribute('aria-pressed',String(activeTab===tab));
    }
    byId('gemsAgeLabel').textContent=byId('gemsAge').value;
    byId('gemsPriceLabel').textContent='€'+byId('gemsPrice').value+' млн';
    const rows=activeTab==='preview'?choices.preliminary:
      activeTab==='scouted'?choices.scouted:
      activeTab==='success'?choices.successes:choices.confirmed;
    const host=byId('gemsGrid');
    host.innerHTML=rows.slice(0,shown).map(activeTab==='success'?renderSuccessCard:renderCard).join('');
    for (const button of host.querySelectorAll('[data-gem-open]')) {
      button.addEventListener('click',()=>{
        const id=button.dataset.gemOpen;
        bridge.openPlayer(id);
      });
    }
    connectPhotos(host);
    const more=byId('gemsMore');
    more.hidden=rows.length<=shown;
    const note=activeTab==='success' ?
      (rows.length ? 'Эти находки сохранены ДО трансферов. Сравниваем исходную цену, датированный прогноз и сообщённую сумму сделки. Это не доказательство причинной связи.' :
      'Нет успешных прогнозов с подтверждённым обнаружением ДО перехода. Находки задним числом не создаём.') :
      activeTab==='scouted' ?
      (rows.length?
       'Спортивный срез: индекс за 36 месяцев, минимум 450 минут текущего сезона, ровесники той же роли. Фильтр €15 млн здесь НЕ применяется: свежая цена неизвестна. Это не доказанная недооценка.' :
       'Для выбранных параметров нет 12 сопоставимых футболистов с подтверждёнными текущими матчами.') :
      activeTab==='confirmed' ?
      (rows.length ? 'Все три проверки источников пройдены; выявлен выраженный разрыв между эффективностью и ценой. Будущий дорогой трансфер не гарантирован.' :
      'Нет проверенных недооценённых игроков: нужны свежие матчи, клуб, разрешённые цены, 25 аналогов и заметный разрыв эффективности и цены.') :
      (rows.length ? 'Исследовательская подборка: текущая спортивная сила сверяется по ровесникам и позиции; архивный атакующий сигнал — отдельно по Г+А/90. Ни один показатель сам по себе не доказывает рыночную недооценку.' :
      'Нет кандидатов с достаточным количеством подтверждённых минут. Попробуйте изменить фильтры.');
    const check=bridge.verification()?.coverage||{};
    const reviewCount=Number(check.review_candidates||0);
    const auditSummary=reviewCount?
      ' · Аудит базы: '+Number(check.verified_current_matches||0)+' со свежими матчами, '+
      Number(check.verified_current_club||0)+' с подтверждённым клубом, '+
      Number(check.licensed_current_values||0)+' с разрешённой актуальной ценой '+
      'из '+reviewCount+' кандидатов.':'';
    byId('gemsInfo').textContent=note+auditSummary;
  }
  // Store real source-complete observations as-of the build date. Never backdate.
  window.transferLabGemsSnapshotExport=()=>{
    bridge=bridge||window.TransferLabGemsBridge;
    if(!bridge)throw Error('Hidden Gems model is unavailable');
    if(!data)prepare();
    const eligible=data.filter(p=>p.age<=23 && p.eligible && p.minutes>=450 &&
      p.score!==null && p.market?.value_eur<=15000000 &&
      p.verification?.data_ready_for_market_comparison===true &&
      p.performancePercentile>=.65 && p.gap>=.20);
    const discoveries={};
    for(const p of eligible){
      discoveries[String(p.id)]={
        name:p.name,club:p.club,league:p.league,position:p.position,age:p.age,
        minutes:p.minutes,market_value_eur:p.market.value_eur,
        market_as_of:p.market.as_of,market_source:p.market.source,
        source_url:p.market.source_url,gap:p.gap,
        performance_percentile:p.performancePercentile,score:p.score
      };
    }
    return {as_of:asOf(),model_version:'hidden-gems-1.1-beta',discoveries};
  };
  function show() {
    if (!bridge) return;
    bridge.showCatalog();
    byId('viewCatalog')?.classList.add('hidden');
    byId('viewGems').classList.remove('hidden');
    const nav=byId('navGems');
    const catalogue=byId('navCatalog');
    catalogue?.classList.remove('active');
    catalogue?.setAttribute('aria-current','false');
    nav?.classList.add('active');
    nav?.setAttribute('aria-current','page');
    if (!data) {
      byId('gemsInfo').textContent='Рассчитываем индексы на подтверждённых матчах…';
      // Defer the heavier cached score preparation to allow loading UI to paint.
      setTimeout(()=>{
        try { prepare(); render(); }
        catch (error) {
          byId('gemsInfo').textContent='Не удалось сформировать подборку. Остальные разделы TransferLab доступны.';
          console.error('Hidden Gems:',error);
        }
      },30);
    } else render();
  }
  function init() {
    bridge=window.TransferLabGemsBridge;
    const catalogue=byId('navCatalog');
    // The nav is rendered as static HTML by the build pipeline. Only attach
    // behaviour here; never wait for this deferred script to create the tab.
    const nav=byId('navGems');
    if (!bridge || !catalogue || !nav || !byId('viewGems')) return;
    nav.addEventListener('click',show);
    for (const id of ['gemsAge','gemsPrice','gemsPosition','gemsLeague','gemsMinutes','gemsSort']) {
      byId(id).addEventListener('input',()=>render());
      byId(id).addEventListener('change',()=>render());
    }
    byId('gemsConfirmedTab').addEventListener('click',()=>{activeTab='confirmed';render();});
    byId('gemsPreviewTab').addEventListener('click',()=>{activeTab='preview';render();});
    byId('gemsScoutTab').addEventListener('click',()=>{activeTab='scouted';render();});
    byId('gemsSuccessTab').addEventListener('click',()=>{activeTab='success';render();});
    byId('gemsMore').addEventListener('click',()=>{shown+=30;render(false);});
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded',init);
  else init();
})();
