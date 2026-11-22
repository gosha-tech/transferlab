#!/usr/bin/env python3
"""TransferLab Beta release gate measured from the exact deployed build.

Never infer product-readiness from a hand-picked player's rating or from the
size of an archival catalogue. False confidence is a release blocker.
A failing product gate is reported but must NOT stop publication of a working
research beta: publication and readiness are different states.
"""
from __future__ import annotations
from collections import Counter
from datetime import date,datetime,timezone,timedelta
from html import escape
from pathlib import Path
import json,os,sys
from audit_coverage import load_site
from forecast_backtest import evaluate as backtest

ROOT=Path(__file__).resolve().parents[1]
SITE=ROOT/'_site'
HISTORY=ROOT/'data'/'beta_health_history.json'
CALENDAR={'MLS','Brasileirão','Argentine Primera División','Eliteserien',
          'Allsvenskan','J1 League','K League 1'}
ARCHIVAL={'transfermarkt_historical','historical_appearances',
          'club_fixture_unverified_player'}
THRESHOLDS={
  'unique_players':10000,
  'priority_players':1000,
  'current_stats_pct':90,
  'predeal_transfers':100,
  'max_median_transfer_error_pct':40,
  'verified_hidden_gems_inputs':30,
  'consecutive_test_days':7,
}

def fresh_current_row(p,stats):
    if not isinstance(stats,dict):return False
    if str(stats.get('source') or '').lower() in ARCHIVAL:return False
    if not str(stats.get('source') or '').strip():return False
    if not all(stats.get(k) is not None for k in ('matches','minutes','goals','assists')):return False
    try:return int(stats['matches'])>0 and float(stats['minutes'])>0
    except (ValueError,TypeError):return False

def priority_coverage(root,target=1000):
    pool=root.get('liveIndexStats') or {}
    ranked=[]
    for p in root.get('players') or []:
        pid=str(p.get('id'))
        calendar=p.get('league') in CALENDAR
        old='2025' if calendar else '2025/26'
        current='2026' if calendar else '2026/27'
        prior=(pool.get(old) or {}).get(pid) or {}
        present=(pool.get(current) or {}).get(pid) or {}
        # Make the priority cohort reproducible: most minutes in the last
        # completed season, then source identity, then immutable player ID.
        # No name, headline price or current formula score enters selection.
        minutes=prior.get('minutes')
        try:mins=max(0,float(minutes or 0))
        except (ValueError,TypeError):mins=0
        ranked.append((mins,pid,p,present))
    ranked.sort(key=lambda x:(-x[0],x[1]))
    cohort=ranked[:target]
    verified=[r for r in cohort if fresh_current_row(r[2],r[3])]
    missing=[{'id':r[1],'name':r[2].get('name'),'league':r[2].get('league'),
              'previous_season_minutes':round(r[0]),
              'reason':'no verified current-season match, minutes and G+A together'}
              for r in cohort if not fresh_current_row(r[2],r[3])]
    pct=round(100*len(verified)/len(cohort),1) if cohort else 0
    missing_by_league=dict(sorted(Counter(x['league'] or 'Unknown'
        for x in missing).items(),key=lambda x:(-x[1],x[0])))
    return {'priority_count':len(cohort),'current_verified':len(verified),
        'current_verified_pct':pct,'missing_count':len(missing),
        'missing_by_league':missing_by_league,
        'missing_player_ids':[x['id'] for x in missing],
        'method':'Top 1000 by observed minutes of most recently completed season, all leagues',
        'missing_examples':missing[:25]}

def count_consecutive_days(history,today):
    days={str(r.get('date')) for r in history if isinstance(r,dict) and r.get('qa_passed') is True}
    days.add(today.isoformat())
    n=0
    while (today-timedelta(days=n)).isoformat() in days:
        n+=1
        if n>=365:break
    return n

def assess(root,market_report,history,as_of):
    players=root.get('players') or []
    ids=[str(p.get('id')) for p in players]
    priority=priority_coverage(root)
    back=backtest(root.get('verifiedTransfersByPlayer') or {})
    verification=(root.get('gemsVerification') or {}).get('coverage') or {}
    ready_gems=int(verification.get('all_three_data_checks') or 0)
    quality_days=count_consecutive_days(history,as_of)
    known_contracts=sum(bool(p.get('contractUntilCurrent') or p.get('contractThroughYear')) for p in players)
    archival_contracts=sum(bool(p.get('contractUntilArchive')) and
                           not bool(p.get('contractUntilCurrent') or p.get('contractThroughYear')) for p in players)
    unique=len(ids)==len(set(ids))
    catalog_ok=unique and len(ids)>=THRESHOLDS['unique_players']
    stats_ok=priority['priority_count']==THRESHOLDS['priority_players'] and priority['current_verified_pct']>=90
    model_ok=back['eligible_pre_deal_predictions']>=100 and (
       back['median_absolute_percentage_error'] is not None and
       back['median_absolute_percentage_error']<=THRESHOLDS['max_median_transfer_error_pct'])
    gems_ok=ready_gems>=30 and int(market_report.get('fresh_rights_reviewed_market_values') or 0)>=30
    qa_ok=quality_days>=7
    gates=[
      {'key':'catalog','label':'10 000+ unique real player profiles',
       'value':len(ids),'target':10000,'passed':catalog_ok,
       'notes':'Archive-only profiles are explicitly separate from current-season records'},
      {'key':'current_stats','label':'At least 90% current basic stats for priority 1000',
       'value':priority['current_verified_pct'],'target':90,'unit':'%',
       'passed':stats_ok,'notes':'Verified matches, minutes, goals and assists; missing advanced events remain unknown'},
      {'key':'valuation_backtest','label':'100 genuinely pre-transfer forecast evaluations, median absolute percentage error ≤40%',
       'value':back['eligible_pre_deal_predictions'],'target':100,
       'passed':model_ok,'notes':'No hindsight from prices computed after deals; actual transfer fees are not fair values'},
      {'key':'hidden_gems','label':'30 source-complete Hidden Gems candidates',
       'value':ready_gems,'target':30,'passed':gems_ok,
       'notes':'Requires authorized fresh market prices, verified clubs and current matches; candidate is not automatically a bargain'},
      {'key':'seven_day_qa','label':'Seven consecutive days of successful automated builds',
       'value':quality_days,'target':7,'passed':qa_ok,
       'notes':'Daily QA checks only; external availability monitoring is not yet measured'}]
    return {'schema_version':1,'as_of':as_of.isoformat(),
       'release_recommendation':'public_beta_ready' if all(g['passed'] for g in gates) else 'not_ready',
       'passed_gates':sum(g['passed'] for g in gates),'total_gates':len(gates),
       'gates':gates,'thresholds':THRESHOLDS,
       'catalog':{'unique_profiles':len(ids),'ids_unique':unique,
                  'russian_premier_league':sum(p.get('league')=='Russian Premier League' for p in players),
                  'current_contracts_verified_or_source_year':known_contracts,
                  'only_historical_contract':archival_contracts,
                  'contract_missing':len(players)-known_contracts-archival_contracts},
       'priority_statistics':priority,'transfer_backtest':back,
       'hidden_gems':{'candidate_checks':verification,
           'market_provider_approved_values':market_report.get('fresh_rights_reviewed_market_values') or 0,
           'note':'No past market price is relabeled as fresh; no current market values are invented'},
       'stability':{'consecutive_qa_days':quality_days,
                    'external_uptime_monitor':'not_configured',
                    'note':'CI passing does not prove a 7-day public uptime SLA'},
       'user_explanation':'Beta readiness is evidence-based, not a subjective percentage. Failing gates indicate specific missing evidence.'}

def html_report(info):
    cards=''.join(
      '<article class="gate '+('passed' if g['passed'] else 'blocked')+'"><div class="status">'+
      ('ПРОЙДЕНО' if g['passed'] else 'ЕЩЁ НЕ ПРОЙДЕНО')+'</div><h2>'+escape(g['label'])+
      '</h2><p class="value">'+escape(str(g['value']))+
      (escape(g.get('unit') or ''))+' / '+escape(str(g['target']))+
      (escape(g.get('unit') or ''))+'</p><p>'+escape(g['notes'])+'</p></article>'
      for g in info['gates'])
    return """<!doctype html><html lang="ru"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="robots" content="noindex">
<title>TransferLab — готовность к Beta</title>
<style>
:root{color-scheme:dark;font-family:Inter,system-ui,Arial,sans-serif}
body{margin:0;background:#081725;color:#e9f5f6;line-height:1.55}
main{max-width:1000px;padding:36px 18px 64px;margin:auto}
a{color:#59ebce}h1{font-size:clamp(29px,5vw,44px);line-height:1.1}
.summary{color:#a6c3cb;font-size:16px;margin:0 0 27px}
.overview{font-size:20px;color:#54ebd0;font-weight:750}
.grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:14px}
.gate{border:1px solid #29485d;background:#0e293e;padding:20px;border-radius:14px}
.status{font-size:11px;font-weight:800;letter-spacing:.08em;color:#f7cb75}
.gate.passed .status{color:#55edd0}
.gate h2{font-size:17px;margin:8px 0}
.gate p{color:#b5cbd4;font-size:13px}
.gate .value{font-size:22px;font-weight:750;color:#fff;margin:12px 0}
footer{margin-top:24px;color:#9fb8c5;font-size:13px}
@media(max-width:680px){.grid{grid-template-columns:1fr}}
</style></head><body><main>
<a href="./">← На TransferLab</a><h1>Готовность к публичной Beta</h1>
<p class="summary">Автоматическая проверка реальных источников, полноты статистики,
исторических прогнозов и качества сборок. Процент готовности не назначается вручную.</p>
<div class="overview">""" +str(info['passed_gates'])+'/'+str(info['total_gates'])+""" контрольных критериев выполнено</div>
<p>Дата проверки: """+escape(info['as_of'])+"""</p>
<div class="grid">"""+cards+"""</div>
<footer>Архивные контракты и клубы не считаются актуально подтверждёнными.
Неполная статистика — не нулевые действия.
Точные проверки доступны в <a href="data/beta_readiness.json">JSON-отчёте</a>,
<a href="data/coverage.json">отчёте покрытия</a>,
<a href="data/player_data_gaps.json">пробелах статистики для всей базы</a>,
<a href="data/priority_refresh_queue.json">очереди обновления игроков</a>,
<a href="data/source_health.json">состоянии источников</a>,
<a href="data/hidden_gems_verification.json">очереди Hidden Gems</a> и
<a href="data/forecast_backtest.json">оценке прошлых прогнозов</a>.</footer>
</main></body></html>"""

def selftest():
    sample={'players':[{'id':'a','name':'A','league':'Premier League'}],
       'liveIndexStats':{},'verifiedTransfersByPlayer':{},'gemsVerification':{'coverage':{}}}
    d=date(2026,11,22)
    a=assess(sample,{},[],d)
    assert a['release_recommendation']=='not_ready' and len(a['gates'])==5
    assert a['gates'][2]['passed'] is False
    h=html_report(a)
    assert '0/5' in h and 'Beta' in h
    hst=[{'date':(d-timedelta(days=i)).isoformat(),'qa_passed':True} for i in range(1,7)]
    assert count_consecutive_days(hst,d)==7
    assert count_consecutive_days(hst[:-1],d)==6
    rows={'players':[{'id':str(i),'league':'Premier League'} for i in range(1000)],
          'liveIndexStats':{'2025/26':{str(i):{'minutes':1000+i} for i in range(1000)},
          '2026/27':{str(i):{'matches':1,'minutes':85,'goals':0,'assists':0,
                               'source':'official'} for i in range(900)}}}
    assert priority_coverage(rows)['current_verified_pct']==90
    assert priority_coverage(rows)['missing_by_league']['Premier League']==100
    assert len(priority_coverage(rows)['missing_player_ids'])==100
    print('Beta readiness gates and priority coverage tests PASS')

def main():
    root=load_site(SITE/'index.html')
    today=datetime.now(timezone.utc).date()
    market_path=SITE/'data'/'hidden_gems_coverage.json'
    market=json.loads(market_path.read_text(encoding='utf-8')) if market_path.exists() else {}
    try:history=json.loads(HISTORY.read_text(encoding='utf-8')).get('days') or []
    except (OSError,ValueError,AttributeError):history=[]
    report=assess(root,market,history,today)
    player_report_path=SITE/'data'/'player_data_gaps.json'
    if player_report_path.exists():
        try:
            gaps=json.loads(player_report_path.read_text(encoding='utf-8'))
            report['all_player_stats']={key:gaps.get(key) for key in
              ('players','current_season_basics_verified','current_season_partial',
               'historical_only','no_measured_minutes')}
        except (OSError,ValueError):pass
    # Save the *source gap* list for the NEXT scheduled PitchAPI import.
    # The queue only sets request order. It never claims missing matches exist.
    priority=report['priority_statistics']
    # Every competition should eventually be refreshed, even if its archived
    # players were absent from the last-season top-1000 minute sample.
    all_missing=Counter()
    for p in root.get('players') or []:
        season='2026' if p.get('league') in CALENDAR else '2026/27'
        cur=(root.get('liveIndexStats') or {}).get(season,{})
        if not fresh_current_row(p,cur.get(str(p['id']))):
            all_missing[p.get('league') or 'Unknown']+=1
    priority_queue={'schema_version':1,'as_of':today.isoformat(),
      'cohort_count':priority['priority_count'],
      'current_verified':priority['current_verified'],
      'missing_by_league':priority['missing_by_league'],
      'all_missing_by_league':dict(sorted(all_missing.items(),
        key=lambda x:(-x[1],x[0]))),
      'missing_player_ids':priority['missing_player_ids']}
    queue_data=json.dumps(priority_queue,ensure_ascii=False,indent=2)+'\n'
    (ROOT/'data'/'priority_refresh_queue.json').write_text(
      queue_data,encoding='utf-8')
    (SITE/'data'/'priority_refresh_queue.json').write_text(
      queue_data,encoding='utf-8')

    source_path=SITE/'data'/'source_health.json'
    if source_path.exists():
        try:report['source_health']=json.loads(source_path.read_text(encoding='utf-8'))
        except (OSError,ValueError):pass
    performance_path=SITE/'data'/'performance.json'
    if performance_path.exists():
        try:report['performance']=json.loads(performance_path.read_text(encoding='utf-8'))
        except (OSError,ValueError):pass
    outfile=SITE/'data'/'beta_readiness.json'
    outfile.parent.mkdir(parents=True,exist_ok=True)
    outfile.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    (SITE/'beta.html').write_text(html_report(report),encoding='utf-8')
    # Record a day only after the browser smoke & unit suite completed.
    # If the later Pages deployment fails, the uptime conclusion remains unknown.
    history=[r for r in history if r.get('date')!=today.isoformat()]
    history.append({'date':today.isoformat(),'qa_passed':True,
                    'model_verified':report['gates'][2]['passed'],
                    'priority_coverage_pct':report['priority_statistics']['current_verified_pct'],
                    'commit':os.getenv('GITHUB_SHA','')[:12]})
    history=sorted(history,key=lambda r:r['date'])[-60:]
    HISTORY.parent.mkdir(parents=True,exist_ok=True)
    HISTORY.write_text(json.dumps({'schema_version':1,'days':history},
                         ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print('TRANSFERLAB BETA QUALITY GATES:',report['passed_gates'],'/',report['total_gates'])
    print('TOP 1000 VERIFIED CURRENT BASIC STATS:',report['priority_statistics']['current_verified'],
          '/',report['priority_statistics']['priority_count'])
    print('SAFE PREDEAL TRANSFERS:',report['transfer_backtest']['eligible_pre_deal_predictions'])
    print('SOURCE COMPLETE HIDDEN GEMS:',report['hidden_gems']['candidate_checks'].get('all_three_data_checks',0))
    print('RELEASE STATUS:',report['release_recommendation'])

if __name__=='__main__':
    if '--self-test' in sys.argv:selftest()
    else:main()
