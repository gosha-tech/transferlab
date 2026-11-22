#!/usr/bin/env python3
"""Integrate Hidden Gems into the generated TransferLab site.

Only rights-reviewed, dated external valuations may qualify as current.
The existing projectedIndex() remains the only performance rating engine.
"""
from __future__ import annotations
import datetime as dt
import json
import pathlib
import re
import sys
from gems_verification import evidence as audit_candidates

ROOT = pathlib.Path(__file__).resolve().parents[1]
MARKET = ROOT / 'data' / 'current_market_values.json'
MARKER = '  function renderProfile(){'
SECTION_ANCHOR = '<section id="viewCatalog" class="hidden">'
# Navigation is static HTML, not a DOM element injected by a deferred JS file.
# This makes Hidden Gems visible in the same initial paint as the other tabs.
GEMS_NAV = ('<button id="navGems" type="button" aria-current="false" '
            'aria-label="Hidden Gems — недооценённые игроки">'
            '<span class="sym" aria-hidden="true">✦</span>'
            '<span class="nav-label">Hidden Gems</span></button>')

GEMS_SECTION = """<section id="viewGems" class="hidden" aria-labelledby="gemsHeading">
  <div class="gems-head">
    <div><span class="gems-eyebrow">TRANSFERLAB DISCOVERY</span>
      <h1 id="gemsHeading">Hidden Gems <span>✦</span></h1>
      <p>Молодые футболисты с интересными показателями. Сопоставляем эффективность, роль и рыночную оценку — без выдуманных цен.</p>
    </div>
    <div class="gems-head-mark">✦</div>
  </div>
  <div class="gems-controls" aria-label="Фильтры Hidden Gems">
    <label>Возраст до <output id="gemsAgeLabel">23</output> лет
      <input id="gemsAge" type="range" min="16" max="35" value="23"></label>
    <label>Стоимость до <output id="gemsPriceLabel">€15 млн</output>
      <input id="gemsPrice" type="range" min="1" max="100" value="15"></label>
    <label>Позиция<select id="gemsPosition">
      <option value="all">Все позиции</option><option value="Goalkeeper">Вратари</option>
      <option value="Defender">Защитники</option><option value="Midfielder">Полузащитники</option>
      <option value="Forward">Нападающие</option></select></label>
    <label>Чемпионат<select id="gemsLeague"><option value="all">Все лиги</option></select></label>
    <label>Минуты в сезоне данных<select id="gemsMinutes">
      <option value="450">От 450</option><option value="900">От 900</option>
      <option value="1500">От 1500</option></select></label>
    <label>Сортировка<select id="gemsSort">
      <option value="gems">Индекс недооценённости</option>
      <option value="index">TransferLab Index</option>
      <option value="age">Самые молодые</option>
      <option value="price">Самые доступные</option>
      <option value="minutes">Больше минут</option></select></label>
  </div>
  <div class="gems-tabs" role="group" aria-label="Достоверность рыночной оценки">
    <button id="gemsConfirmedTab" type="button" class="gems-tab active" aria-pressed="true">Подтверждённые находки <span id="gemsConfirmedCount">0</span></button>
    <button id="gemsPreviewTab" type="button" class="gems-tab" aria-pressed="false">Кандидаты и архив <span id="gemsPreviewCount">0</span></button>
  </div>
  <p class="gems-info" id="gemsInfo" role="status">Готовим выборку проверенных игроков…</p>
  <div id="gemsGrid" class="gems-grid"></div>
  <div class="gems-more-wrap"><button id="gemsMore" class="gems-more" type="button" hidden>Показать ещё</button></div>
  <p class="gems-method">Hidden Gem Score — экспериментальное процентильное сравнение с футболистами той же роли и похожего возраста. Это не прогноз трансферной цены. Исторические наблюдения относятся к июню–июлю 2026 года; архивные кандидаты не подтверждают сегодняшнюю цену €15 млн.</p>
</section>
"""

BRIDGE = r"""  // Hidden Gems uses the exact same performance model and player objects as profiles.
  // Never infer current market prices from the archival history or the beta model.
  window.TransferLabGemsBridge = {
    verification(){return ROOT.gemsVerification||null;},
    list(){
      const market=ROOT.hiddenGemsMarket||{};
      return players.map(p=>{
        const id=String(p.id);
        const calendar=['MLS','Brasileirão','Argentine Primera División','Eliteserien','Allsvenskan','J1 League','K League 1'].includes(p.league);
        const liveSeason=calendar?'2026':'2026/27';
        const archiveSeason=calendar?'2025':'2025/26';
        const current=ROOT.liveIndexStats?.[liveSeason]?.[id]||null;
        const historic=ROOT.liveIndexStats?.[archiveSeason]?.[id]||null;
        const hasMinutes=row=>row&&Number.isFinite(Number(row.minutes))&&Number(row.minutes)>=450;
        // Calendar 2026 snapshots may themselves be frozen historical reports.
        const liveVerified=hasMinutes(current)&&current.source!=='transfermarkt_historical'&&
          current.source!=='historical_appearances';
        const season=liveVerified?liveSeason:archiveSeason;
        const stats=liveVerified?current:historic;
        const minutes=stats?.minutes==null?null:Number(stats.minutes);
        const archive=ROOT.marketHistory5Y?.[id];
        const last=Array.isArray(archive)&&archive.length?archive[archive.length-1]:null;
        const archiveValue=Number(p.marketValueArchiveEUR);
        const safeArchive=Number.isFinite(archiveValue)&&archiveValue>0&&archiveValue<=500000000?
          {as_of:p.teamArchiveAsOf||p.archive_as_of||'2026-07',eur:archiveValue,
           source:'Transfermarkt · архив'}:
          (last&&last.length>=2&&Number(last[1])>0?
            {as_of:last[0],eur:Math.round(Number(last[1])*1000000),
             source:'Transfermarkt · архив'}:null);
        let rating=null;
        // Use the exact TransferLab 36-month model with archived match evidence.
        // Missing advanced metrics remain missing; never synthesize xG or xA.
        if(p.birth&&hasMinutes(stats)){
          const idx=projectedIndex(p);
          rating={score:idx.score,proxy:!!idx.proxy,role:idx.role||p.scoutRole||p.pos,
            coverage:Number(idx.coverage||0),
            weightedMinutes:Number(idx.rolling?.weightedMinutes||0),
            exact:!!idx.exact,
            provisional:!!idx.indexConfidence?.provisional,
            evidenceFactor:idx.indexConfidence?.provisional?idx.indexConfidence.confidence:null};
        }
        const contractCurrent=p.contractUntilCurrent||p.contractThroughYear||null;
        const contractArchived=p.contractUntilArchive||null;
        return {id,name:p.name,birth:p.birth||null,club:p.team||'—',
          league:p.league||'—',position:p.pos||'Unknown',
          precisePosition:p.displayPosition||null,role:p.scoutRole||p.pos,
          positionEvidence:!!(p.displayPosition||p.position_source||p.positionVerified),
          clubArchived:!!(p.origin==='transfermarkt_archived_2026'&&
            (!p.clubSourceAsOf||!Number.isFinite(Date.parse(p.clubSourceAsOf))||
             (Date.now()-Date.parse(p.clubSourceAsOf)>120*86400000))),
          statPeriod:season,currentEvidence:!!liveVerified,
          minutes, matches:stats?.matches??null,
          statsAsOf:stats?.as_of||(liveVerified?null:'2026-06-28'),
          statsSource:stats?.source||null,
          statsPartial:!!stats?.partial,
          rating,market:market[id]||null,archive:safeArchive,
          contractCurrent,contractArchived,
          contractArchivedAt:p.contractArchiveAsOf||'2026-07'};
      });
    },
    showCatalog(){showView('catalog');},
    openPlayer(id){choosePlayer(id);},
    attachPortrait(img,fallback,id){attachPhoto(img,fallback,id);}
  };
  const hiddenGemsOriginalShowView=showView;
  showView=function(view){
    document.getElementById('viewGems')?.classList.add('hidden');
    const nav=document.getElementById('navGems');
    if(nav){nav.classList.remove('active');nav.setAttribute('aria-current','false');}
    return hiddenGemsOriginalShowView(view);
  };
"""


def parse_date(v):
    if not isinstance(v, str) or not re.fullmatch(r'\d{4}-\d{2}-\d{2}', v):
        return None
    try:
        return dt.date.fromisoformat(v)
    except ValueError:
        return None


def load_market(today: dt.date):
    """Require explicit rights review AND identity confirmation, per player."""
    if not MARKET.exists():
        return {}, 0
    raw = json.loads(MARKET.read_text(encoding='utf-8'))
    if raw.get('schema_version') != 1:
        raise RuntimeError('Unsupported Hidden Gems valuation schema')
    rows = raw.get('players') or {}
    if not isinstance(rows, dict):
        raise RuntimeError('Hidden Gems market entries must be keyed by player ID')
    if raw.get('commercial_rights_checked') is not True:
        return {}, len(rows)
    accepted = {}
    rejected = 0
    for pid, item in rows.items():
        if not isinstance(item, dict) or item.get('identity_verified') is not True:
            rejected += 1
            continue
        source = str(item.get('source') or '').strip()
        source_url = str(item.get('source_url') or '').strip()
        day = parse_date(item.get('as_of'))
        value = item.get('value_eur')
        if (not source or not source_url.startswith('https://') or day is None or
            (today-day).days < 0 or (today-day).days > 120 or
            not isinstance(value, int) or isinstance(value, bool) or
            value <= 0 or value > 500_000_000):
            rejected += 1
            continue
        accepted[str(pid)] = {
            'value_eur': value, 'as_of': day.isoformat(),
            'source': source, 'source_url': source_url
        }
    return accepted, rejected


def patch_embedded(html, today):
    pattern = r'(<script id="embeddedData" type="application/json">)(.*?)(</script>)'
    match = re.search(pattern, html, re.S)
    if not match:
        raise RuntimeError('Hidden Gems requires embeddedData')
    root = json.loads(match.group(2))
    values, rejected = load_market(today)
    player_ids = {str(p.get('id')) for p in root.get('players', [])}
    root['hiddenGemsMarket'] = {pid: item for pid, item in values.items()
                               if pid in player_ids}
    root['hiddenGemsModelVersion'] = '1.0-beta'
    root['hiddenGemsMarketAsOf'] = today.isoformat()
    root['gemsVerification'] = audit_candidates(root.get('players') or [], root, today)
    payload = json.dumps(root, ensure_ascii=False, separators=(',', ':')).replace('</', '<\\/')
    output = html[:match.start(2)] + payload + html[match.end(2):]
    return output, root, rejected + len(values)-len(root['hiddenGemsMarket'])


def age_on(birth, today):
    day = parse_date(birth)
    if day is None or day > today:
        return None
    return today.year - day.year - ((today.month, today.day) < (day.month, day.day))


def summarize(root, today, rejected):
    players = root.get('players') or []
    youths = [p for p in players if (age_on(p.get('birth'), today) is not None and
                                    age_on(p.get('birth'), today) <= 23)]
    current_stats = root.get('liveIndexStats') or {}
    eligible_minutes = []
    historical_minutes = []
    historical_value_under_15m = []
    history = root.get('marketHistory5Y') or {}
    for p in youths:
        is_calendar = p.get('league') in ('MLS','Brasileirão','Argentine Primera División','Eliteserien','Allsvenskan','J1 League','K League 1')
        current = '2026' if is_calendar else '2026/27'
        previous = '2025' if is_calendar else '2025/26'
        pid = str(p.get('id'))
        current_row = (current_stats.get(current) or {}).get(pid) or {}
        old_row = (current_stats.get(previous) or {}).get(pid) or {}
        if (float(current_row.get('minutes') or 0)>=450 and
            current_row.get('source')!='transfermarkt_historical'):
            eligible_minutes.append(p)
        if float(old_row.get('minutes') or 0)>=450:
            historical_minutes.append(p)
            v=p.get('marketValueArchiveEUR')
            if v is None and history.get(pid):
                try:v=float(history[pid][-1][1])*1000000
                except (ValueError,TypeError,IndexError):v=None
            if v is not None:
                try:
                    if 0<float(v)<=15000000:historical_value_under_15m.append(p)
                except (TypeError,ValueError):pass
    values = root.get('hiddenGemsMarket') or {}
    return {
        'generated_at_utc': dt.datetime.now(dt.timezone.utc).isoformat(),
        'model': 'hidden-gems-1.0-beta',
        'default_max_age': 23, 'default_max_market_eur': 15000000,
        'young_players_with_verified_birth': len(youths),
        'young_players_with_450_current_minutes': len(eligible_minutes),
        'young_players_with_450_previous_minutes': len(historical_minutes),
        'young_players_with_archive_under_15m_and_450_previous_minutes':
            len(historical_value_under_15m),
        'archival_candidates_are_not_currently_valued': True,
        'fresh_rights_reviewed_market_values': len(values),
        'with_fresh_value_under_15m_and_450_minutes': sum(
            str(p.get('id')) in values and values[str(p.get('id'))]['value_eur'] <= 15000000
            for p in eligible_minutes),
        'rejected_market_records': rejected,
        'confirmed_score_calculated_in_browser': True,
        'per_player_verification_coverage': (root.get('gemsVerification') or {}).get('coverage',{}),
        'note': 'Market prices are never inferred from archived values or model estimates.'
    }


def inject(html, today=None):
    today = today or dt.datetime.now(dt.timezone.utc).date()
    if 'id="viewGems"' in html:
        raise RuntimeError('Hidden Gems already integrated')
    if html.count(SECTION_ANCHOR) != 1 or html.count(MARKER) != 1:
        raise RuntimeError('Hidden Gems integration anchors missing or ambiguous')
    html, root, rejected = patch_embedded(html, today)
    html = html.replace(SECTION_ANCHOR, GEMS_SECTION + SECTION_ANCHOR, 1)
    # Use the original Catalog nav button as the structural anchor. Inject
    # next to it during BUILD, rather than waiting for HTML parsing and the
    # deferred Hidden Gems script to finish executing in the browser.
    catalog_nav = re.search(
        r'<button\\b(?=[^>]*\\bid=["\\\']navCatalog["\\\'])[^>]*>.*?</button>',
        html, re.S | re.I)
    if not catalog_nav:
        raise RuntimeError('Cannot locate navCatalog for first-paint Hidden Gems tab')
    html = html[:catalog_nav.end()] + GEMS_NAV + html[catalog_nav.end():]
    html = html.replace(MARKER, BRIDGE + MARKER, 1)
    if html.count('</head>') != 1 or html.count('</body>') != 1:
        raise RuntimeError('Cannot link Hidden Gems assets')
    html = html.replace('</head>', '<link rel="stylesheet" href="assets/hidden_gems.css">\n</head>', 1)
    html = html.replace('</body>', '<script src="assets/hidden_gems.js" defer></script>\n</body>', 1)
    return html, summarize(root, today, rejected)


def main():
    path = pathlib.Path(sys.argv[1]) if len(sys.argv)>1 else ROOT/'_site'/'index.html'
    html, report = inject(path.read_text(encoding='utf-8'))
    path.write_text(html, encoding='utf-8')
    out = ROOT/'_site'/'data'/'hidden_gems_coverage.json'
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    # Publish a source-attributed queue covering every default-filter youth.
    # This is a verification checklist, not an assertion of market bargains.
    updated = re.search(r'<script id="embeddedData" type="application/json">(.*?)</script>',html,re.S)
    if updated:
        review = json.loads(updated.group(1)).get('gemsVerification') or {}
        (out.parent/'hidden_gems_verification.json').write_text(
            json.dumps(review,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
        print('Verified-source review queue:',len(review.get('players') or []),
              'candidates; all three checks',
              (review.get('coverage') or {}).get('all_three_data_checks',0))
    print('Hidden Gems integrated:', report['young_players_with_450_current_minutes'],
          'stat-qualified young players;',
          report['fresh_rights_reviewed_market_values'], 'fresh market valuations')


if __name__ == '__main__':
    main()
