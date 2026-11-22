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
    data = bridge.list().map(p => {
      const age = ageAt(p.birth, stamp);
      const r = p.rating;
      const reliable = !!p.positionEvidence && !!r && !r.proxy && r.coverage >= 60 &&
        r.weightedMinutes >= 450 && Number.isFinite(r.score) &&
        p.minutes >= 450 && ['Goalkeeper','Defender','Midfielder','Forward'].includes(p.position);
      const fresh = p.market && asDate(p.market.as_of) &&
        (asDate(stamp) - asDate(p.market.as_of)) / 86400000 >= 0 &&
        (asDate(stamp) - asDate(p.market.as_of)) / 86400000 <= marketMaxAgeDays;
      return {...p, age, reliable, market: fresh ? p.market : null,
        marketStale: !fresh && !!p.market, score: null, peers: 0, gap: null,
        performancePercentile: null, pricePercentile: null, quality: 'C'};
    }).filter(p => p.age !== null && p.age >= 0 && p.age <= 35);
    const known = data.filter(p => p.reliable && p.market && p.market.value_eur > 0);
    for (const candidate of known) {
      const peers = known.filter(p => p.rating.role === candidate.rating.role &&
        Math.abs(p.age - candidate.age) <= 3);
      candidate.peers = peers.length;
      if (peers.length < 25) continue;
      const performance = percentile(peers.map(p => p.rating.score), candidate.rating.score);
      const price = percentile(peers.map(p => p.market.value_eur), candidate.market.value_eur);
      candidate.performancePercentile = performance;
      candidate.pricePercentile = price;
      candidate.gap = performance - price;
      candidate.score = Math.round(100 * Math.max(0,Math.min(1,0.5 + 0.5*candidate.gap)));
      candidate.quality = candidate.rating.coverage >= 80 &&
        !candidate.statsPartial && candidate.rating.exact ? 'A' : 'B';
    }
    const leagues = [...new Set(data.map(p => p.league).filter(Boolean))]
      .sort((a,b) => a.localeCompare(b,'ru'));
    const host = byId('gemsLeague');
    for (const league of leagues) {
      const opt = document.createElement('option');
      opt.value = league; opt.textContent = league; host.append(opt);
    }
  }
  function filtered() {
    const maxAge=Number(byId('gemsAge').value);
    const maxPrice=Number(byId('gemsPrice').value)*1000000;
    const minMinutes=Number(byId('gemsMinutes').value);
    const position=byId('gemsPosition').value;
    const league=byId('gemsLeague').value;
    const valid=data.filter(p => p.age <= maxAge && p.reliable && p.minutes >= minMinutes &&
      (position==='all'||p.position===position) && (league==='all'||p.league===league));
    const confirmed=valid.filter(p => p.score !== null && p.market.value_eur<=maxPrice);
    const preliminary=valid.filter(p => {
      if (p.score !== null) return false;
      if (p.market) return p.market.value_eur <= maxPrice;
      // Historical values do not prove today's price, but can narrow previews.
      if (p.archive && Number.isFinite(p.archive.eur) && p.archive.eur > maxPrice) return false;
      return true;
    });
    const sortBy=byId('gemsSort').value;
    const sortFn=(a,b) => {
      if (sortBy==='index') return b.rating.score-a.rating.score || a.name.localeCompare(b.name);
      if (sortBy==='age') return a.age-b.age || b.rating.score-a.rating.score;
      if (sortBy==='price') return (a.market?.value_eur??a.archive?.eur??Infinity)-
          (b.market?.value_eur??b.archive?.eur??Infinity) || b.rating.score-a.rating.score;
      if (sortBy==='minutes') return b.minutes-a.minutes || b.rating.score-a.rating.score;
      return (b.score??-1)-(a.score??-1) || b.rating.score-a.rating.score ||
        a.name.localeCompare(b.name);
    };
    confirmed.sort(sortFn); preliminary.sort(sortFn);
    return {confirmed,preliminary};
  }
  function renderCard(p) {
    const price=p.market ? money(p.market.value_eur)+' <small>· '+esc(p.market.as_of)+' · '+esc(p.market.source)+'</small>' :
      p.archive && Number.isFinite(p.archive.eur) ?
        money(p.archive.eur) + ' <small>архив · '+esc(p.archive.as_of)+' · Transfermarkt</small>' :
        'Нет проверенной стоимости';
    const rating=p.score!==null ?
      '<strong class="gems-score">'+p.score+'/100</strong>' :
      '<span class="gems-unrated">Недостаточно данных для оценки цены</span>';
    const tag=p.score!==null && p.performancePercentile>=.65 && p.gap>=.20 ?
      '<span class="gems-find">Выраженная недооценённость</span>' : '';
    const explanation=p.score!==null ?
      'Эффективность: '+Math.round(p.performancePercentile*100)+'-й процентиль · '+
      'стоимость: '+Math.round(p.pricePercentile*100)+'-й · аналогов: '+p.peers :
      (p.market ? 'Недостаточно сопоставимых игроков с актуальной стоимостью' :
      'Актуальная стоимость не подтверждена; рейтинг недооценённости не рассчитывается');
    const meta=esc(p.club)+' · '+esc(p.league);
    return '<article class="gems-card"><button class="gems-card-open" type="button" data-gem-open="'+esc(p.id)+'">'+
      '<span class="gems-avatar"><span class="gems-avatar-fallback" data-gem-fallback="'+esc(p.id)+'">'+
      esc(p.name.split(/\s+/).slice(0,2).map(s=>s[0]||'').join(''))+'</span>'+
      '<img data-gem-photo="'+esc(p.id)+'" alt="" loading="lazy" decoding="async" hidden></span>'+
      '<span class="gems-card-main"><span class="gems-player">'+esc(p.name)+'</span>'+
      '<span class="gems-meta">'+meta+'</span><span class="gems-meta">'+p.age+' лет · '+
      esc(p.precisePosition||p.position)+' · '+fmt(p.minutes)+' минут · '+fmt(p.matches??'—')+' матчей</span>'+
      '<span class="gems-meta">Статистика: '+esc(p.statsAsOf||'дата не подтверждена')+' · '+esc(p.statsSource||'источник не указан')+'</span>'+ 
      '<span class="gems-price">'+price+'</span>'+
      '<span class="gems-explain">'+esc(explanation)+'</span>'+tag+'</span>'+
      '<span class="gems-card-stats"><span class="gems-stat-label">TransferLab Index</span>'+
      '<strong>'+p.rating.score+'/100</strong><span class="gems-stat-label">Hidden Gem Score</span>'+
      rating+'<span class="gems-quality">Данные: '+p.quality+'</span></span>'+
      '</button></article>';
  }
  function connectPhotos(host) {
    if (!('IntersectionObserver' in window)) return;
    if (observer) observer.disconnect();
    observer=new IntersectionObserver(entries=>{
      for (const e of entries) {
        if (!e.isIntersecting) continue;
        observer.unobserve(e.target);
        const img=e.target.querySelector('[data-gem-photo]');
        const fallback=e.target.querySelector('[data-gem-fallback]');
        if (img && fallback) bridge.attachPortrait(img,fallback,img.dataset.gemPhoto);
      }
    },{rootMargin:'100px'});
    host.querySelectorAll('.gems-avatar').forEach(el=>observer.observe(el));
  }
  function render(reset=true) {
    if (!data) return;
    if (reset) shown=30;
    const choices=filtered();
    byId('gemsConfirmedCount').textContent=fmt(choices.confirmed.length);
    byId('gemsPreviewCount').textContent=fmt(choices.preliminary.length);
    if (firstRender && !choices.confirmed.length && activeTab==='confirmed' && choices.preliminary.length) {
      activeTab='preview';
    }
    firstRender=false;
    for (const [tab,id] of [['confirmed','gemsConfirmedTab'],['preview','gemsPreviewTab']]) {
      byId(id).classList.toggle('active',activeTab===tab);
      byId(id).setAttribute('aria-pressed',String(activeTab===tab));
    }
    byId('gemsAgeLabel').textContent=byId('gemsAge').value;
    byId('gemsPriceLabel').textContent='€'+byId('gemsPrice').value+' млн';
    const rows=activeTab==='preview'?choices.preliminary:choices.confirmed;
    const host=byId('gemsGrid');
    host.innerHTML=rows.slice(0,shown).map(renderCard).join('');
    for (const button of host.querySelectorAll('[data-gem-open]')) {
      button.addEventListener('click',()=>{
        const id=button.dataset.gemOpen;
        bridge.openPlayer(id);
      });
    }
    connectPhotos(host);
    const more=byId('gemsMore');
    more.hidden=rows.length<=shown;
    const note=activeTab==='confirmed' ?
      (rows.length ? 'Актуальные цены подтверждены. Индекс экспериментальный; дата цены указана в карточке.' :
      'Нет подтверждённых находок по выбранным фильтрам. Для расчёта нужны свежие оценки (не старше 120 дней) и минимум 25 аналогов по роли и возрасту.') :
      (rows.length ? 'Предварительная подборка: спортивные показатели подтверждены, но актуальная стоимость или достаточная группа сравнения отсутствует. Архивные цены не означают соответствие бюджету сегодня.' :
      'Нет кандидатов с достаточным количеством подтверждённых минут. Попробуйте изменить фильтры.');
    byId('gemsInfo').textContent=note;
  }
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
    if (!bridge || !catalogue || !byId('viewGems')) return;
    const nav=catalogue.cloneNode(false);
    nav.id='navGems';
    nav.removeAttribute('data-view');
    nav.removeAttribute('onclick');
    nav.classList.remove('active');
    nav.textContent='✦ Hidden Gems';
    nav.setAttribute('aria-current','false');
    nav.setAttribute('aria-label','Hidden Gems — недооценённые игроки');
    catalogue.insertAdjacentElement('afterend',nav);
    nav.addEventListener('click',show);
    for (const id of ['gemsAge','gemsPrice','gemsPosition','gemsLeague','gemsMinutes','gemsSort']) {
      byId(id).addEventListener('input',()=>render());
      byId(id).addEventListener('change',()=>render());
    }
    byId('gemsConfirmedTab').addEventListener('click',()=>{activeTab='confirmed';render();});
    byId('gemsPreviewTab').addEventListener('click',()=>{activeTab='preview';render();});
    byId('gemsMore').addEventListener('click',()=>{shown+=30;render(false);});
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded',init);
  else init();
})();
