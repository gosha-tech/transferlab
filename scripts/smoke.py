#!/usr/bin/env python3
"""End-to-end browser checks for the published TransferLab build."""
import functools
import http.server
import os
import re
import pathlib
import shutil
import threading
import json
import time
from playwright.sync_api import sync_playwright

class QuietHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, format, *args):
        pass

def main():
    root=pathlib.Path('_site')
    assert (root/'index.html').exists(), 'No built site'
    handler=functools.partial(QuietHandler,directory=str(root))
    server=http.server.ThreadingHTTPServer(('127.0.0.1',0),handler)
    threading.Thread(target=server.serve_forever,daemon=True).start()
    url='http://127.0.0.1:'+str(server.server_port)
    screenshot=pathlib.Path('smoke_screenshots');screenshot.mkdir(exist_ok=True)
    errors=[]
    chrome=shutil.which('google-chrome') or shutil.which('chromium') or shutil.which('chromium-browser')
    with sync_playwright() as playwright:
        options={'headless':True,'args':['--no-sandbox','--disable-dev-shm-usage']}
        if chrome:options['executable_path']=chrome
        browser=playwright.chromium.launch(**options)
        # First-paint regression: sidebar entry must exist and be visible even
        # when the deferred Hidden Gems JS is disabled or never downloads.
        static_context=browser.new_context(java_script_enabled=False,
                                           viewport={'width':1440,'height':900})
        static_page=static_context.new_page()
        static_page.goto(url,wait_until='domcontentloaded',timeout=25000)
        assert static_page.locator('#navGems').is_visible(), (
            'Hidden Gems nav must be in server-rendered HTML, not created by JS')
        assert static_page.locator('#navGems .nav-label').inner_text()=='Hidden Gems'
        assert static_page.locator('#navCatalog').is_visible()
        static_context.close()
        print('Hidden Gems first paint without JavaScript PASS')
        page=browser.new_page(viewport={'width':1440,'height':900})
        started=time.perf_counter()
        page.on('pageerror',lambda error:errors.append(str(error)))
        page.route('**/*',lambda route: route.abort() if route.request.url.startswith(('https://','http://')) and '127.0.0.1' not in route.request.url else route.continue_())
        page.goto(url,wait_until='domcontentloaded',timeout=25000)
        page.locator('#pName').wait_for(timeout=15000)
        page.locator('#navCatalog').click()
        page.locator('.player-card').first.wait_for(timeout=15000)
        catalog_ready_ms=round((time.perf_counter()-started)*1000)
        count=int(page.locator('#kpiPlayers').inner_text().replace(' ',''))
        assert count>=10000, ('Requested 10000-player catalogue has not been built',count)
        # Full roster regression: explicit role AM/CM/DM must never render as
        # Defender. Wirtz is a sentinel, but reconciliation covers everyone.
        positions=page.evaluate("""() => {
          const root=JSON.parse(document.getElementById('embeddedData').textContent);
          const expected={GK:'Goalkeeper',CB:'Defender',RB:'Defender',
            LB:'Defender',AM:'Midfielder',CM:'Midfielder',DM:'Midfielder',
            LW:'Forward',RW:'Forward',ST:'Forward'};
          const contradictions=root.players.filter(p=>
            expected[String(p.displayPosition||'').toUpperCase()]&&
            expected[String(p.displayPosition||'').toUpperCase()]!==p.pos);
          const w=root.players.find(p=>p.name==='Florian Wirtz');
          const rows=root.liveTournamentStats?.['2026/27']?.[w?.id]||[];
          return {contradictions:contradictions.slice(0,12).map(p=>p.name),
            total:contradictions.length,wirtz:w&&
              {id:w.id,pos:w.pos,role:w.displayPosition,team:w.team,league:w.league},
            wirtzTournamentRows:rows.map(r=>({name:r.name,id:r.id,
              source:r.source,is_complete:r.is_complete,
              stats:{matches:r.stats?.matches,matches_min:r.stats?.matches_min,
                starts:r.stats?.starts,minutes:r.stats?.minutes,
                goals:r.stats?.goals,assists:r.stats?.assists}}))};
        }""")
        print('POSITION/MATCH-SOURCE AUDIT:',positions)
        assert positions['total']==0,positions
        assert positions['wirtz'] and positions['wirtz']['pos']=='Midfielder',positions
        assert positions['wirtz']['role']=='AM',positions
        page.locator('#search').fill('Florian Wirtz')
        page.locator('#suggestions [data-suggest]').first.wait_for(timeout=5000)
        page.locator('#suggestions [data-suggest]').first.click()
        assert page.locator('#pPosition').inner_text()=='AM'
        matches_display=page.locator('#statStarts').inner_text().strip()
        minutes_text=page.locator('#statMinutes').inner_text()
        displayed_minutes=int(re.sub(r'[^0-9]','',minutes_text) or '0')
        # 4 matches and 1,040 minutes must not masquerade as a complete total.
        if matches_display.isdigit():
            assert displayed_minutes<=int(matches_display)*130,(
                'Full-season minutes exceed feasible minutes per reported match',
                matches_display,minutes_text,positions)
        else:
            assert matches_display.startswith('≥') or matches_display=='—',matches_display
        assert page.locator('#profileEvidenceLabel').is_visible()
        assert page.locator('#profileEvidence').evaluate('(e)=>!e.open')
        page.locator('#profileEvidenceLabel').click()
        assert page.locator('#verifiedProfileMeta p').count()>0
        assert 'T10:' not in page.locator('#currentSeasonBanner').inner_text()
        assert len(page.locator('#currentSeasonBanner').inner_text())<170
        assert len(page.locator('#advancedCoverageNote').inner_text())<170
        print('WIRTZ PROFILE PASS:',matches_display,'matches,',
              minutes_text,'minutes; correctly categorized as AM/Midfielder')

        current_archive=page.evaluate("""() => {
          const root=JSON.parse(document.getElementById('embeddedData').textContent);
          const live=root.liveIndexStats?.['2026/27']||{};
          const archived=root.players.filter(p=>p.origin==='transfermarkt_archived_2026');
          const stale=archived.find(p=>!p.clubSourceAsOf);
          const current=archived.find(p=>{
            const row=live[String(p.id)];
            return row&&Number(row.minutes)>0 &&
              !['transfermarkt_historical','historical_appearances',
                'club_fixture_unverified_player'].includes(String(row.source||''));
          });
          return {staleName:stale?.name||null,currentName:current?.name||null,
                  currentEvidence:current?live[String(current.id)]:null};
        }""")
        assert current_archive['staleName'],current_archive
        page.locator('#search').fill(current_archive['staleName'])
        page.locator('#suggestions [data-suggest]').first.wait_for(timeout=5000)
        page.locator('#suggestions [data-suggest]').first.click()
        club_note=page.locator('#verifiedProfileMeta').inner_text()
        assert 'не подтверждён' in club_note or 'не подтвержден' in club_note,club_note
        page.locator('#navCatalog').click()
        if current_archive['currentName']:
            page.locator('#search').fill(current_archive['currentName'])
            page.locator('#suggestions [data-suggest]').first.wait_for(timeout=5000)
            page.locator('#suggestions [data-suggest]').first.click()
            assert '2026/27' in page.locator('#currentSeasonBanner').inner_text(),current_archive
            page.locator('#navCatalog').click()
        print('Current vs archive club and season labelling PASS')
        # Expansion entries are archive-only, have a source identity and real
        # 2025/26 stats. Their previous-season totals must open in the profile.
        expanded = page.evaluate("""() => {
          const root=JSON.parse(document.getElementById('embeddedData').textContent);
          const row=root.players.find(p=>p.origin==='transfermarkt_archived_2026' &&
            Number(root.liveIndexStats?.['2025/26']?.[String(p.id)]?.minutes||0)>=450);
          return {total:root.players.length, expanded:root.catalogueExpansion?.added||0,
                  player:row?.name||null};
        }""")
        assert expanded['total']==count
        assert expanded['expanded']>=8600, expanded
        assert expanded['player'], 'No expanded profile with sourced 2025/26 minutes'
        # A short-match archival profile retains true stats, never a made-up index.
        audit=page.evaluate('''() => {
          const root=JSON.parse(document.getElementById('embeddedData').textContent);
          const young=root.players.filter(p=>p.origin==='transfermarkt_archived_2026');
          return {added:young.length,zeroMinutes:young.filter(p=>
            !Number.isFinite(Number(p.archiveLastSeasonMinutes))||
            Number(p.archiveLastSeasonMinutes)<=0).length,
            noEvidence:young.filter(p=>!p.archiveStatEvidence).length,
            noSource:young.filter(p=>!p.originSource).length,
            withContract:young.filter(p=>!!p.contractUntilArchive).length};
        }''')
        assert audit['added']>=8600,audit
        assert audit['zeroMinutes']==0,audit
        assert audit['noEvidence']==0,audit
        assert audit['noSource']==0,audit
        rpl=page.evaluate("""() => {
          const root=JSON.parse(document.getElementById('embeddedData').textContent);
          const russian=root.players.filter(p=>p.league==='Russian Premier League');
          const withMatches=russian.filter(p=>
            ['2023/24','2024/25','2025/26'].some(s=>
              (root.liveTournamentStats?.[s]?.[String(p.id)]||[])
              .some(x=>x.source==='historical_appearances' && Number(x.stats?.minutes)>0)));
          return {players:russian.length,withMatches:withMatches.length};
        }""")
        assert rpl['players']>=350 and rpl['withMatches']>=300,(
            'Russian Premier League match-backed coverage too low',rpl)
        print('RPL coverage:',rpl)

        print('10000+ verified profiles audit:',audit)

        samples=page.evaluate("""() => {
          const root=JSON.parse(document.getElementById('embeddedData').textContent);
          const rows=root.players.filter(p=>p.origin==='transfermarkt_archived_2026');
          const older=rows.find(p=>p.archiveStatEvidence==='older_archival' &&
            p.archiveReferenceSeason==='2024/25');
          const short=rows.find(p=>p.archiveStatEvidence==='very_limited' &&
            p.archiveReferenceSeason==='2025/26');
          return [{kind:'older',id:older?.id,name:older?.name,
                   season:older?.archiveReferenceSeason},
                  {kind:'short',id:short?.id,name:short?.name,
                   season:short?.archiveReferenceSeason}];
        }""")
        for item in samples:
            assert item['id'] and item['name'] and item['season'],item
            page.locator('#search').fill(item['name'])
            page.locator('#suggestions [data-suggest]').first.wait_for(timeout=5000)
            page.locator('#suggestions [data-suggest]').first.click()
            assert item['name'] in page.locator('#pName').inner_text(),item
            banner=page.locator('#currentSeasonBanner').inner_text()
            assert item['season'] in banner,(
                'Archived player opened with the wrong season',item,banner)
            shown=page.locator('#statMinutes').inner_text()
            assert int(''.join(c for c in shown if c.isdigit()) or '0')>0,(
                'Verified historical stat disappeared for a low-minute player',
                item,shown)
            page.locator('#navCatalog').click()
        print('Historical short-sample and older-season player profile tests PASS')

        page.locator('#search').fill(expanded['player'])
        page.locator('#suggestions [data-suggest]').first.wait_for(timeout=5000)
        page.locator('#suggestions [data-suggest]').first.click()
        assert expanded['player'] in page.locator('#pName').inner_text()
        assert page.locator('#statMinutes').inner_text().replace(' ','').strip() not in ('0','—',''), (
            'Expanded player historical performance missing',expanded['player'])
        page.locator('#navCatalog').click()


        # Hidden Gems is a separate page, backed by current player model and verified valuations.
        # All sidebar tabs must have the same horizontal start, width,
        # height and icon gutter (regression from a plain-text Gems button).
        nav_geometry=page.evaluate("""() => {
          const buttons=[...document.querySelectorAll('.sidebar .nav button')];
          const gems=document.getElementById('navGems');
          return {total:buttons.length,gemsIcon:!!gems?.querySelector('.sym'),
            rows:buttons.map(el=>({id:el.id,left:el.getBoundingClientRect().left,
              width:el.getBoundingClientRect().width,
              height:el.getBoundingClientRect().height})),
            horizontalOverflow:document.documentElement.scrollWidth>innerWidth};
        }""")
        assert nav_geometry['total']>=4 and nav_geometry['gemsIcon'],nav_geometry
        measured=nav_geometry['rows']
        assert max(x['left'] for x in measured)-min(x['left'] for x in measured)<=2,nav_geometry
        assert max(x['width'] for x in measured)-min(x['width'] for x in measured)<=2,nav_geometry
        assert max(x['height'] for x in measured)-min(x['height'] for x in measured)<=2,nav_geometry
        assert not nav_geometry['horizontalOverflow'],nav_geometry
        print('Sidebar navigation alignment PASS',nav_geometry)
        gems_started=time.perf_counter()
        page.locator('#navGems').click()
        assert page.locator('#viewGems').is_visible(), 'Hidden Gems page did not open'
        assert page.locator('#gemsAge').input_value()=='23'
        assert page.locator('#gemsPrice').input_value()=='15'
        assert page.locator('#gemsPosition').input_value()=='all'
        page.wait_for_function("""() => {
          const text=document.getElementById('gemsInfo')?.textContent||'';
          return text.length>0 && !/Рассчитываем|Готовим/.test(text);
        }""",timeout=35000)
        gems_ready_ms=round((time.perf_counter()-gems_started)*1000)
        assert page.locator('#viewGems .gems-beta-link a[href="beta.html"]').count()==1
        # An empty confirmed list is legitimate when no current licensed prices exist.
        page.locator('#gemsPreviewTab').click()
        assert page.locator('#gemsPreviewCount').inner_text().strip().isdigit()
        preview_count=int(page.locator('#gemsPreviewCount').inner_text().replace(' ',''))
        assert preview_count>=40,('Archive-backed Hidden Gems did not expand',preview_count)
        assert page.locator('.gems-card').count()>0
        layout=page.evaluate("""() => {
          const card=document.querySelector('.gems-card-open');
          const details=card?.querySelector('.gems-card-main');
          const metrics=card?.querySelector('.gems-card-stats');
          if(!card||!details||!metrics)return null;
          return {display:getComputedStyle(card).display,
                  metricsBelow:metrics.getBoundingClientRect().top >= details.getBoundingClientRect().top,
                  metricsWidth:metrics.getBoundingClientRect().width,
                  detailsWidth:details.getBoundingClientRect().width,
                  overflow:document.documentElement.scrollWidth>innerWidth};
        }""")
        assert layout and layout['display']=='grid' and layout['metricsBelow'],layout
        assert layout['metricsWidth']>=layout['detailsWidth'],layout
        assert not layout['overflow'],('Hidden Gems desktop overflow',layout)

        assert 'Архивный сезон' in page.locator('.gems-card').first.inner_text() or (
            'Подтверждённый текущий сезон' in page.locator('.gems-card').first.inner_text())
        assert 'Контракт' in page.locator('.gems-card').first.inner_text()
        scored=page.locator('.gems-archival-score').count()
        print('Hidden Gems preview:',preview_count,'players; archive comparison visible:',scored)
        measured=page.evaluate('() => window.TransferLabGemsCoverage')
        assert measured and measured['youthWithSeasonMinutes']>=preview_count
        assert measured['youthWithMeasuredIndex']>=50, measured
        # Historical scoring is a narrowly defined 2025/26 attacking-output
        # screening signal, NOT a 36-month index backdated to archived fees.
        assert measured['archiveIsNotCurrent'] is True, measured
        assert measured['youthWithArchivedValueGap']>=0, measured
        if scored:
            assert 'Г+А/90' in page.locator('.gems-archival-score').first.inner_text()
        assert measured['youthWithVerifiedCurrentValueGap']==0 or (
            measured['youthWithVerifiedCurrentValueGap']>0)
        print('HIDDEN GEMS COVERAGE:',measured)
        # Diagnose a concrete outlier using sourced rows, not a manual score override.
        zonneveld=page.evaluate("""() => {
          const root=JSON.parse(document.getElementById('embeddedData').textContent);
          const p=root.players.find(p=>String(p.name).toLowerCase()==='milan zonneveld');
          if(!p)return null;
          const id=String(p.id);
          const stats=Object.fromEntries(['2024/25','2025/26','2026/27'].map(
             season=>[season,{aggregate:root.liveIndexStats?.[season]?.[id]||null,
                              tournaments:root.liveTournamentStats?.[season]?.[id]||[]}]));
          const r=window.TransferLabGemsBridge.list().find(x=>x.id===id);
          return {id,name:p.name,role:p.scoutRole,club:p.team,league:p.league,
                  marketValueArchiveEUR:p.marketValueArchiveEUR,
                  rating:r?.rating,stats,archive:r?.archive};
        }""")
        print('MILAN ZONNEVELD INDEX DIAGNOSIS:',str(zonneveld)[:14000])
        targets=page.evaluate("""() => {
          const root=JSON.parse(document.getElementById('embeddedData').textContent);
          const targets=['marc guiu','mika biereth','jhon dur','mohamed-ali cho'];
          const raw=window.TransferLabGemsBridge.list();
          return targets.map(needle=>{
            const p=root.players.find(x=>String(x.name).toLowerCase().includes(needle));
            if(!p)return {name:needle,missing:true};
            const x=raw.find(y=>String(y.id)===String(p.id));
            return {name:p.name,id:p.id,position:p.scoutRole,league:p.league,
              contract:p.contractUntilArchive,model:x?.rating,
              seasons:Object.fromEntries(['2023/24','2024/25','2025/26','2026/27']
                .map(season=>[season,{stats:root.liveIndexStats?.[season]?.[String(p.id)]||null,
                  tournaments:root.liveTournamentStats?.[season]?.[String(p.id)]||[]}]))};
          });
        }""")
        for target in targets:
            print('HIGH SCORE GEM DIAGNOSIS:',str(target)[:8000])
            assert not target.get('missing'),('Missing gem regression player',target)
            assert target.get('model'),('Missing rating evidence',target)
            actual=target['model']
            current=target['seasons']['2026/27']['stats'] or {}
            previous=target['seasons']['2025/26']['stats'] or {}
            if float(current.get('minutes') or 0)<450 and float(previous.get('minutes') or 0)<2000:
                assert actual['score']<80,(
                    'Insufficient recent evidence cannot justify elite rating',
                    target['name'],actual)
                assert actual['provisional'] is True
                assert float(actual['evidenceFactor'])<1


        assert zonneveld and zonneveld['rating'], 'Zonneveld archival index absent'
        assert zonneveld['rating']['provisional'] is True
        assert zonneveld['rating']['exact'] is False
        assert zonneveld['rating']['score']<80,(
            'One-season archival-only score cannot be presented as elite',
            zonneveld['rating'])
        assert zonneveld['rating']['evidenceFactor']<1



        for card in page.locator('.gems-card').all()[:5]:
            assert card.locator('.gems-player').inner_text().strip()
            assert 'Hidden Gem Score' in card.inner_text()
            assert '—' not in card.locator('.gems-player').inner_text()
        page.screenshot(path=str(screenshot/'hidden-gems-desktop.png'))
        if page.locator('.gems-card').count()>0:
            page.locator('.gems-card [data-gem-open]').first.click()
            assert page.locator('#pName').is_visible()
            assert not page.locator('#viewGems').is_visible()
        page.locator('#navCatalog').click()

        assert page.locator('.player-index').count()>0,'Catalog indices must be shown'
        # Every card (not just cards with goals or contracts) has the same
        # ordered content: current season G/A, contract, tournament and index.
        for el in page.locator('#catalogGrid .player-card').all():
            assert el.locator('.card-body-uniform').count()==1
            assert el.locator('.card-fixed-stats').count()==1
            assert el.locator('.card-fixed-contract').count()==1
            assert el.locator('.card-fixed-bottom .league-tag').count()==1
            assert el.locator('.card-fixed-bottom .player-index').count()==1
            assert el.locator('.card-fixed-stats').inner_text().startswith(('Матчи:', 'Matches:'))
            assert el.locator('.card-fixed-contract').inner_text().startswith(('Контракт', 'Contract', 'Архив: договор', 'Archived contract'))
            assert el.locator('.card-fixed-stats').bounding_box()['y'] < el.locator('.card-fixed-contract').bounding_box()['y']
            assert el.locator('.card-fixed-contract').bounding_box()['y'] < el.locator('.card-fixed-bottom').bounding_box()['y']
        # An absent statistic is not a zero, and contract never replaces G/A.
        unknown=page.locator('#catalogGrid .card-fixed-stats')
        assert unknown.count()==page.locator('#catalogGrid .card-fixed-contract').count()
        cards=page.locator('.card-name').all_text_contents()
        assert cards,'Catalog has no cards'
        assert page.evaluate("""() => {
          const names=[...document.querySelectorAll('#catalogGrid .card-name')].map(n=>n.textContent.trim());
          const cmp=new Intl.Collator('ru',{sensitivity:'base',numeric:true});
          return names.every((n,i)=>i===0 || cmp.compare(names[i-1],n)<=0);
        }"""),('Alphabetical sort not applied',cards[:5])
        board=page.locator('#freeMatchesPanel')
        assert board.count()==1,'Missing free match-results panel'
        board.locator('summary').click()
        if page.locator('#freeMatchLeague option').count()>0:
            assert page.locator('.free-match-row').count()>0,'Match results missing in visible scoreboard'
        page.screenshot(path=str(screenshot/'catalog-desktop.png'))
        page.locator('#filterLeague').select_option('Primeira Liga')
        assert page.locator('.player-card').count()>0,'Portugal filter returned no cards'
        page.locator('#filterLeague').select_option('')
        page.locator('#search').fill('Messi')
        page.locator('#suggestions [data-suggest]').first.wait_for(timeout=5000)
        page.locator('#suggestions [data-suggest]').first.click()
        assert 'Messi' in page.locator('#pName').inner_text(),'Search did not navigate to Messi'
        assert '2026' in page.locator('#currentSeasonBanner').inner_text(), 'MLS defaults to current 2026 season'
        # A Miami player must not show England's EPL / French Ligue 1.
        picker=page.locator('#competitionSelect')
        assert picker.count()==1
        assert picker.locator('option[value="39"]').count()==0,'MLS player shows English league'
        assert picker.locator('option[value="61"]').count()==0,'MLS player shows Ligue 1'
        page.locator('#search').fill('Phil Foden')
        page.locator('#suggestions [data-suggest]').first.wait_for(timeout=5000)
        page.locator('#suggestions [data-suggest]').first.click()
        available=picker.locator('option').evaluate_all('(nodes)=>nodes.map(x=>x.value)')
        assert available==['all','39','45','48','2','eng-community-shield'],('Foden competition list is incorrect',available)
        picker.select_option('eng-community-shield')
        assert page.locator('#statStarts').inner_text().strip()=='1', 'Foden played Community Shield'
        assert page.locator('#statGoals').inner_text().strip()=='0'
        assert page.locator('#statAssists').inner_text().strip()=='0'
        banner=page.locator('#currentSeasonBanner').inner_text()
        assert '2026/27' in banner,('Foden must open current season, not archive',banner)
        assert re.search(r'2026-\d{2}-\d{2}',banner),(
            'Player evidence date must be shown without a technical timestamp',banner)
        assert 'PitchAPI checked' not in banner,('Banner should not show provider debugging text',banner)
        assert 'Статистика этого игрока ещё не получена' not in banner, ('Foden current data must display',banner)
        assert not any(x in available for x in ['61','66','3','140','135'])
        picker.select_option('45')
        assert 'нет' in page.locator('#competitionStatus').inner_text().lower() or 'получена' in page.locator('#competitionStatus').inner_text().lower()
        picker.select_option('2')
        assert 'Фоден' not in page.locator('#competitionStatus').inner_text() # does not claim unverified match scores
        picker.select_option('all')
        # Verify real PitchAPI UCL records remain attached to competition 2.
        page.locator('#search').fill('Mbapp')
        page.locator('#suggestions [data-suggest]').first.wait_for(timeout=5000)
        page.locator('#suggestions [data-suggest]').first.click()
        assert 'Mbapp' in page.locator('#pName').inner_text()
        picker.select_option('2')
        cl_minutes=page.locator('#statMinutes').inner_text().replace(' ','').replace('\\u00a0','')
        cl_goals=page.locator('#statGoals').inner_text().strip()
        assert cl_minutes not in ('—','0',''), ('Mbappe UCL minutes absent despite provider records',cl_minutes)
        assert cl_goals not in ('—','0',''), ('Mbappe UCL goals absent despite provider records',cl_goals)
        print('Mbappe UCL 2026/27:',cl_minutes,'minutes,',cl_goals,'goals;',
              'model value:',page.locator('#valueMain').inner_text(),
              'index:',page.locator('#playerIndexBadge').inner_text())
        picker.select_option('all')
        # Verify exact right-back classification from PSG, not generic CB.
        page.locator('#search').fill('Achraf Hakimi')
        page.locator('#suggestions [data-suggest]').first.wait_for(timeout=5000)
        page.locator('#suggestions [data-suggest]').first.click()
        assert 'Hakimi' in page.locator('#pName').inner_text()
        assert page.locator('#pPosition').inner_text()=='RB','Achraf Hakimi must be right-back'
        hakimi_badge=page.locator('#playerIndexBadge').inner_text()
        hakimi_match=re.search(r'(\d+)\s*/\s*100',hakimi_badge)
        assert hakimi_match and int(hakimi_match.group(1))>=85,(
            'Reliability adjustment over-penalized consistently documented elite fullback',
            hakimi_badge)

        # Official-source reconciliation as of 2026-11-22. Substitute
        # appearances count as a match, not only a starting XI.
        assert picker.locator('option[value="uefa-super-cup"]').count()==1
        assert picker.locator('option[value="fr-super-cup"]').count()==1
        for comp,expected in [('all','15'),('61','9'),('2','4'),
                              ('uefa-super-cup','1'),('fr-super-cup','1')]:
            picker.select_option(comp)
            shown=page.locator('#statStarts').inner_text().strip()
            assert shown==expected,('Hakimi appearances by competition incorrect',comp,shown,expected)
        picker.select_option('all')
        total_mins=''.join(c for c in page.locator('#statMinutes').inner_text() if c.isdigit())
        assert total_mins=='1157',('Hakimi total verified minutes',total_mins)
        assert page.locator('#statGoals').inner_text().strip()=='3'
        assert page.locator('#statAssists').inner_text().strip()=='4'
        assert 'Матчи' in page.locator('#viewProfile').inner_text(), 'Starts heading must be Match appearances'
        print('HAKIMI MATCHES VERIFIED: 9 Ligue 1 + 4 UCL + 1 UEFA Super Cup + 1 France Super Cup = 15')

        # Regressive role-only price underestimate (28m before the dated
        # market-prior calibration) is no longer acceptable for this
        # well-documented elite RB. This checks the model, not a hard-coded
        # player-specific price override.
        assert page.locator('[data-value-kind="market"]').count()>=10, 'Five-year historic value points missing for Hakimi'
        hakimi_eur=int(''.join(ch for ch in page.locator('#valueMain').inner_text().split('млн')[0] if ch.isdigit()))
        assert hakimi_eur>=50,('Elite RB valuation is still implausibly depressed',hakimi_eur)
        print('INDEX CONTRIBUTIONS HAKIMI:',
              page.locator('#formulaBreakdown').inner_text().replace('\\n',' / ')[:2800])
        rank_caption=page.locator('#verifiedProfileMeta').inner_text()
        assert 'Ранг в базе' in rank_caption or 'Rank among' in rank_caption, (
            'Hakimi should have evidence-based comparison with other fullbacks',rank_caption)
        print('HAKIMI POSITION RANK:',rank_caption[:300])
        print('HAKIMI DIAGNOSTIC:',page.locator('#valueMain').inner_text(),
              page.locator('#playerIndexBadge').inner_text(),
              'quality:',page.locator('#modelQuality').inner_text(),
              'market dots:',page.locator('[data-value-kind=market]').count(),
              'chart:',page.locator('#chartSubtitle').inner_text())

        # Cross-player model diagnostics: both PSG wing-backs share the same
        # role and dated archive, so any large discrepancy needs attribution.
        page.locator('#search').fill('Nuno Mendes')
        page.locator('#suggestions [data-suggest]').first.wait_for(timeout=5000)
        page.locator('#suggestions [data-suggest]').first.click()
        print('NUNO DIAGNOSTIC:',page.locator('#pPosition').inner_text(),
              'index',page.locator('#playerIndexBadge').inner_text(),
              'value',page.locator('#valueMain').inner_text(),
              'quality',page.locator('#modelQuality').inner_text())
        print('NUNO BREAKDOWN:',page.locator('#formulaBreakdown').inner_text().replace('\\n',' / ')[:2100])
        print('NUNO PROFILE:',page.locator('#verifiedProfileMeta').inner_text()[:1200])
        print('NUNO EVIDENCE:',page.evaluate("""() => {
            const root=JSON.parse(document.querySelector('#embeddedData').textContent);
            const p=root.players.find(x=>x.name==='Nuno Mendes');
            if(!p)return 'missing player';
            return JSON.stringify({id:p.id,role:p.scoutRole,archiveEUR:p.marketValueArchiveEUR,
              source:p.position_source,contract:p.contractUntilCurrent||p.contractThroughYear||p.contractUntilArchive,
              index2026:root.liveIndexStats?.['2026/27']?.[p.id],
              index2025:root.liveIndexStats?.['2025/26']?.[p.id],
              tournaments2026:root.liveTournamentStats?.['2026/27']?.[p.id],
              market:root.marketHistory5Y?.[p.id]});
          }""")[:2900])
        # Verify evidence, not a fixed numerical rating: team data may change.
        assert page.locator('#pPosition').inner_text()=='LB'
        meta=page.locator('#verifiedProfileMeta').inner_text()
        assert '2029-06-30' in meta and '2026-11-22' in meta
        assert '€80' in meta
        for comp,minutes in [('uefa-super-cup','74'),('fr-super-cup','26')]:
            assert picker.locator('option[value="'+comp+'"]').count()==1
            picker.select_option(comp)
            assert page.locator('#statStarts').inner_text().strip()=='1'
            assert page.locator('#statMinutes').inner_text().strip()==minutes
            assert page.locator('#statGoals').inner_text().strip()=='0'
            assert page.locator('#statAssists').inner_text().strip()=='0'
        picker.select_option('all')
        assert int(page.locator('#statStarts').inner_text().strip())>=8, 'New live matches may increase current season total'
        # Club corrections must restore Lookman's current La Liga metrics,
        # instead of attaching his 2026/27 appearances to Atalanta.
        page.locator('#search').fill('Ademola Lookman')
        page.locator('#suggestions [data-suggest]').first.wait_for(timeout=5000)
        page.locator('#suggestions [data-suggest]').first.click()
        assert 'Atlético' in page.locator('#pClub').inner_text(), 'Lookman club must be Atlético Madrid'
        assert picker.locator('option[value="140"]').count()==1, 'Lookman must have La Liga eligibility'
        assert page.locator('#statMinutes').inner_text().strip() not in ('—','0',''), 'Lookman current minutes missing'
        print('INDEX CONTRIBUTIONS LOOKMAN:',
              page.locator('#formulaBreakdown').inner_text().replace('\\n',' / ')[:2800])
        print('LOOKMAN DIAGNOSTIC:',page.locator('#pClub').inner_text(),
              page.locator('#valueMain').inner_text(),page.locator('#playerIndexBadge').inner_text(),
              'current mins:',page.locator('#statMinutes').inner_text(),
              'goals:',page.locator('#statGoals').inner_text())
        page.locator('#search').fill('Mohamed Salah')
        page.locator('#suggestions [data-suggest]').first.wait_for(timeout=5000)
        page.locator('#suggestions [data-suggest]').first.click()
        assert 'Trabzonspor' in page.locator('#pClub').inner_text(), 'Salah moved to Turkish Süper Lig'
        label=picker.locator('option[value="cup-turkey"]').inner_text()
        assert label=='Кубок Турции',('Turkish Cup must be Russian in RU mode',label)
        print('SALAH DIAGNOSTIC:',page.locator('#pClub').inner_text(),
              page.locator('#valueMain').inner_text(),page.locator('#playerIndexBadge').inner_text(),
              'season minutes:',page.locator('#statMinutes').inner_text())
        page.locator('#seasonSelect').select_option('2024/25')
        assert page.locator('#statGoals').inner_text().strip() not in ('—','0',''), 'Salah 2024/25 history lost'
        page.locator('#search').fill('Abdülkadir Ömür')
        page.locator('#suggestions [data-suggest]').first.wait_for(timeout=5000)
        page.locator('#suggestions [data-suggest]').first.click()
        assert page.locator('#pPosition').inner_text()=='AM', 'Ömür must be attacking midfielder'
        print('ÖMÜR role corrected to AM')
        # Never present a current Al-Hilal estimate as a July 2026
        # pre-transfer quote. A verified reported fee is separate evidence.
        page.locator('#search').fill('Crysencio Summerville')
        page.locator('#suggestions [data-suggest]').first.wait_for(timeout=5000)
        page.locator('#suggestions [data-suggest]').first.click()
        assert 'Al-Hilal' in page.locator('#pClub').inner_text()
        compare=page.locator('#transferComparison')
        print('SUMMERVILLE_UI_DIAGNOSTIC',page.evaluate("""() => {
            const root=JSON.parse(document.querySelector('#embeddedData').textContent);
            const p=root.players.find(x=>x.name==='Crysencio Summerville');
            return {player:p?.id,coverage:root.transferEvidenceCoverage,
              transfer:root.verifiedTransfersByPlayer?.[p?.id],
              panel:document.querySelector('#transferComparison')?.outerHTML?.slice(0,800)};
        }"""),'JS errors:',errors)
        assert compare.is_visible(), 'Missing sourced Summerville transfer card'
        transfer_text=compare.inner_text()
        assert '70' in transfer_text and 'West Ham United' in transfer_text
        assert 'Нет сохранённого прогноза' in transfer_text, (
            'Must not re-label a present-day forecast as historical',transfer_text)
        assert 'Текущая оценка модели' in transfer_text
        print('SUMMERVILLE TRANSFER vs MODEL:',
              transfer_text.replace('\\n',' / ')[:1000],
              'current model:',page.locator('#valueMain').inner_text())
        page.locator('#search').fill('Messi')
        page.locator('#suggestions [data-suggest]').first.wait_for(timeout=5000)
        page.locator('#suggestions [data-suggest]').first.click()
        page.locator('#detailsButton').click()
        page.locator('#advancedWrap').wait_for(state='visible',timeout=5000)
        assert page.locator('.advanced-group').count()==4,'Advanced stats grouping missing'
        page.screenshot(path=str(screenshot/'profile-desktop.png'))
        page.set_viewport_size({'width':390,'height':844})
        page.locator('#navCatalog').click()
        assert page.locator('.player-card').count()>0,'Mobile catalog empty'
        page.screenshot(path=str(screenshot/'catalog-mobile.png'))
        browser.close()
    server.shutdown()
    metric_path=root/'data'/'performance.json'
    metric_path.parent.mkdir(parents=True,exist_ok=True)
    metric_path.write_text(json.dumps({'schema_version':1,'catalog_ready_ms':catalog_ready_ms,
          'hidden_gems_ready_ms':gems_ready_ms,'player_count':count,
          'environment':'GitHub Actions local Chromium; third-party photos blocked',
          'photo_latency_ms':None,'browser_errors':len(errors)},indent=2)+'\n',encoding='utf-8')
    print('Beta benchmark: catalog',catalog_ready_ms,'ms; Hidden Gems',gems_ready_ms,
          'ms (CI, NOT end-user network latency)')
    assert not errors,'Browser runtime errors: '+str(errors[:4])
    print('Browser smoke PASS: profiles, sorting, Portugal, search, Champions League & EPL selections, four advanced panels, mobile; players='+str(count))

if __name__=='__main__':main()
