#!/usr/bin/env python3
"""Publish measured coverage of each season and league; never fill gaps with 0.

This is generated from the exact HTML delivered to visitors, so the report
cannot claim more player coverage than the actual built site.
"""
from __future__ import annotations
from collections import Counter,defaultdict
from profile_consistency import canonical_group
from datetime import datetime,timezone
import json,pathlib,re,sys

ROOT=pathlib.Path(__file__).resolve().parents[1]
SEASONS=('2023/24','2024/25','2025/26','2026/27')
CALENDAR_SEASONS=('2023','2024','2025','2026')

def load_site(path):
    txt=path.read_text(encoding='utf-8')
    m=re.search(r'<script id="embeddedData" type="application/json">(.*?)</script>',txt,re.S)
    if not m:
        raise RuntimeError('Embedded player data missing')
    return json.loads(m.group(1))

def summarize(root):
    players=root.get('players') or []
    ids=[str(p['id']) for p in players]
    if len(ids)!=len(set(ids)) or len(ids)<1300:
        raise RuntimeError('Incomplete or duplicate player registry')
    contradictions=[(str(p.get('id')),p.get('name'),p.get('pos'),
        p.get('displayPosition')) for p in players
        if canonical_group(p) and p.get('pos')!=canonical_group(p)]
    if contradictions:
        raise RuntimeError('Inconsistent broad/detailed positions: '+
                           repr(contradictions[:12]))
    index=root.get('liveIndexStats') or {}
    events=root.get('liveTournamentStats') or {}
    expected=set(ids)
    seasons={}
    for season in (*SEASONS,*CALENDAR_SEASONS):
        pool=events.get(season) or {}
        actual={str(pid) for pid,rows in pool.items()
                if str(pid) in expected and isinstance(rows,list) and
                any(isinstance(r,dict) and isinstance(r.get('stats'),dict) and
                    any(v is not None for v in r['stats'].values()) for r in rows)}
        from_index={str(pid) for pid,v in (index.get(season) or {}).items()
                    if str(pid) in expected and isinstance(v,dict) and
                    v.get('minutes') is not None}
        source_counts=Counter()
        for pid in actual:
            source_counts.update({str(r.get('source') or 'unknown')
                for r in pool.get(pid,[]) if isinstance(r,dict) and r.get('stats')})
        seasons[season]={
            'with_verified_player_stats':len(actual),
            'with_minutes_for_index':len(from_index),
            'without_verified_stats':len(expected-actual),
            'source_profiles':dict(source_counts),
        }
    leagues=defaultdict(lambda:{'players':0,'seasons':defaultdict(int)})
    for p in players:
        pid=str(p['id'])
        league=str(p.get('league') or 'Unknown')
        leagues[league]['players']+=1
        for season in (CALENDAR_SEASONS if league in ('MLS','Brasileirão','Argentine Primera División','Eliteserien','Allsvenskan','J1 League','K League 1') else SEASONS):
            if pid in (events.get(season) or {}) and any(
                 isinstance(r,dict) and r.get('stats') for r in events[season][pid]):
                leagues[league]['seasons'][season]+=1
    competitions={}
    for season in (*SEASONS,*CALENDAR_SEASONS):
        by_comp=defaultdict(lambda:{'players':set(),'with_minutes':set(),'sources':Counter()})
        for pid,rows in (events.get(season) or {}).items():
            if str(pid) not in expected or not isinstance(rows,list):continue
            for record in rows:
                if not isinstance(record,dict) or not isinstance(record.get('stats'),dict):
                    continue
                if not record['stats']:continue
                key=str(record.get('id') or '')+' · '+str(record.get('name') or '?')
                row=by_comp[key]
                row['players'].add(str(pid))
                if float(record['stats'].get('minutes') or 0)>0:
                    row['with_minutes'].add(str(pid))
                row['sources'][str(record.get('source') or 'unknown')]+=1
        competitions[season]={key:{
            'players':len(val['players']),
            'with_minutes':len(val['with_minutes']),
            'source_rows':dict(val['sources'])}
            for key,val in sorted(by_comp.items())}

    current_row_gaps=Counter()
    current_match_missing=set()
    for year in ('2026/27','2026'):
        for pid,rows in (events.get(year) or {}).items():
            for row in rows or []:
                metrics=row.get('stats') or {}
                if float(metrics.get('minutes') or 0)>0 and metrics.get('matches') is None:
                    current_match_missing.add(str(pid))
                    current_row_gaps[str(row.get('source') or 'unknown')]+=1
    market=root.get('marketHistory5Y') or {}
    market_count=len(market)
    profile=root.get('profileCoverage') or {}
    photo_candidates={
      'api_football_id':sum(bool(p.get('apiPhoto')) for p in players),
      'wikimedia_commons_licensed':sum(bool(p.get('commonsPhoto')) for p in players),
      'sofascore_matched_id':sum(bool(p.get('sofaId')) for p in players),
      'premier_league_identity_candidate':sum(bool(str(p.get('id') or '').isdigit()) and
          p.get('league')=='Premier League' for p in players),
    }
    any_photo_candidate=sum(any((
      bool(p.get('apiPhoto')),bool(p.get('commonsPhoto')),
      bool(p.get('sofaId')),
      bool(str(p.get('id') or '').isdigit()) and p.get('league')=='Premier League'
    )) for p in players)
    current_year={'2026/27':set(), '2026':set()}
    previous_year={'2025/26':set(), '2025':set()}
    for group,target in ((current_year,current_year),(previous_year,previous_year)):
      for season in group:
        for pid,rows in (events.get(season) or {}).items():
          if str(pid) in expected and any(isinstance(r,dict) and
             isinstance(r.get('stats'),dict) and
             any(r['stats'].get(k) is not None for k in ('goals','assists','minutes','matches'))
             for r in rows):
            group[season].add(str(pid))
    any_current=len(current_year['2026/27']|current_year['2026'])
    any_last_two=len(current_year['2026/27']|current_year['2026']|
                     previous_year['2025/26']|previous_year['2025'])
    # Explicit role/contract/stat coverage: an archived observation is not
    # proof of a current-season appearance, current team or current contract.
    new=[p for p in players if p.get('origin')=='transfermarkt_archived_2026']
    # Every additional public profile must contain at least one real,
    # positive-minute season row with a dated, named provider.
    def recorded_archival_matches(p):
        pid=str(p['id'])
        years=('2023','2024','2025','2026') if p.get('league') in ('MLS','Brasileirão','Argentine Primera División','Eliteserien','Allsvenskan','J1 League','K League 1') else ('2023/24','2024/25','2025/26')
        return any(isinstance(r,dict) and
            r.get('source')=='historical_appearances' and
            (r.get('stats') or {}).get('matches',0)>0 and
            (r.get('stats') or {}).get('minutes',0)>0 and
            r.get('source_as_of')
            for yr in years for r in (events.get(yr) or {}).get(pid,[]))
    source_backed={str(p['id']) for p in new if recorded_archival_matches(p)}
    if len(source_backed)!=len(new):
        bad=[str(p['id']) for p in new if str(p['id']) not in source_backed]
        raise RuntimeError('Additional profiles missing verified archival match rows: '+str(bad[:10]))
    evidence_counts=Counter(p.get('archiveStatEvidence') or 'unknown' for p in new)
    contract_labels=Counter('current' if p.get('contractUntilCurrent') or p.get('contractThroughYear')
        else 'archival' if p.get('contractUntilArchive') else 'not_confirmed' for p in players)

    def index_minutes(p,seasons):
        pid=str(p['id'])
        return sum(max(0,float((index.get(season) or {}).get(pid,{}).get('minutes') or 0))
                   for season in seasons)
    current_seasons=lambda p: ('2026',) if p.get('league') in ('MLS','Brasileirão','Argentine Primera División','Eliteserien','Allsvenskan','J1 League','K League 1') else ('2026/27',)
    archive_seasons=lambda p: ('2025',) if p.get('league') in ('MLS','Brasileirão','Argentine Primera División','Eliteserien','Allsvenskan','J1 League','K League 1') else ('2025/26',)
    previous_index={str(p['id']) for p in players if
                    index_minutes(p,archive_seasons(p))>=450}
    current_index={str(p['id']) for p in players if
                   index_minutes(p,current_seasons(p))>=450}
    archives={str(p['id']) for p in players if p.get('contractUntilArchive')}
    current_contracts={str(p['id']) for p in players if
        p.get('contractUntilCurrent') or p.get('contractThroughYear')}
    with_market={str(p['id']) for p in players if
                 p.get('marketValueArchiveEUR') is not None or
                 (market.get(str(p['id'])) or [])}
    age_today=datetime.now(timezone.utc).date()
    def valid_youth(p):
        try:
            birth=datetime.strptime(str(p['birth']), '%Y-%m-%d').date()
            age=age_today.year-birth.year-((age_today.month,age_today.day)<
                 (birth.month,birth.day))
            return 16<=age<=23
        except (ValueError,KeyError,TypeError):
            return False
    archive_candidates=[p for p in new if valid_youth(p) and
        str(p['id']) in previous_index and p.get('marketValueArchiveEUR') is not None and
        0<float(p['marketValueArchiveEUR'])<=15_000_000]
    result={
      'built_at_utc':datetime.now(timezone.utc).isoformat(timespec='seconds'),
      'source':'TransferLab built site: embedded, provider-backed player statistics',
      'players_total':len(players),
      'seasons':seasons,
      'leagues':{key:{'players':v['players'],'seasons':dict(v['seasons'])}
                 for key,v in sorted(leagues.items())},
      'profiles':profile,
      'expansion':{
          'archived_profiles_added':len(new),
          'all_added_profiles_have_dated_real_match_stats':len(source_backed)==len(new),
          'added_with_actual_match_stats':len(source_backed),
          'evidence_tiers':dict(evidence_counts),
          'added_with_archival_contract':sum(bool(p.get('contractUntilArchive')) for p in new),
          'added_without_known_contract':sum(not bool(p.get('contractUntilArchive') or
              p.get('contractUntilCurrent') or p.get('contractThroughYear')) for p in new),
          'new_profiles_with_previous_index_minutes_450':
             sum(str(p['id']) in previous_index for p in new),
          'new_profiles_with_current_index_minutes_450':
             sum(str(p['id']) in current_index for p in new),
          'new_profiles_with_archived_contract_date':
             sum(str(p['id']) in archives for p in new),
          'new_profiles_with_current_contract_evidence':
             sum(str(p['id']) in current_contracts for p in new),
          'new_profiles_with_market_archive':
             sum(str(p['id']) in with_market for p in new),
          'young_players_with_archived_market_under_15m_and_450_minutes':
             len(archive_candidates),
          'season_and_contract_note':'Archive 2025/26 does not verify November 2026 price, club, contract or current form'
      },
      'index_inputs':{
         'players_with_450_min_current':len(current_index),
         'players_with_450_min_previous':len(previous_index),
         'players_with_450_min_in_either':len(current_index|previous_index),
         'all_models_require_quality_check':'Minute evidence alone does not guarantee a non-proxy index'
      },
      'contract_evidence':{
         'per_player_status':dict(contract_labels),
         'all_profiles_have_explicit_display_state':True,
         'players_with_current_verified_contract':len(current_contracts),
         'players_with_only_archived_contract':
              len(archives-current_contracts),
         'players_without_record':len(expected-(archives|current_contracts)),
         'archived_expiries_are_not_current_verification':True
      },
      'photo_candidate_coverage':{
        'candidates_by_provider':photo_candidates,
        'players_with_id_backed_candidates':any_photo_candidate,
        'players_without_id_backed_candidates':len(players)-any_photo_candidate,
        'note':'These are portrait URL candidates, NOT confirmed loaded or licensed images. Generic verified photographs may be available for additional players.'
      },
      'catalog_stat_coverage':{
        'players_with_verified_current_season':any_current,
        'players_with_current_or_explicit_previous_season':any_last_two,
        'players_with_neither':len(players)-any_last_two,
        'note':'Previous-season stats are labeled archive; missing current-season values are never replaced with zero.'
      },
      'competition_coverage':competitions,
      'five_year_market_values':{
        'players_with_actual_observations':market_count,
        'players_with_two_or_more':sum(len(v)>=2 for v in market.values()),
        'last_real_market_date':root.get('marketHistoryLastObserved'),
        'source':root.get('marketHistorySource'),
        'observations':sum(len(v) for v in market.values()),
      },
      'pitchapi':{
         'key_configured_on_last_successful_sync':root.get('pitchAPIKeyConfigured',False),
         'source_last_sync':root.get('pitchAPILastSync'),
         'players_by_season':root.get('pitchAPISeasonCoverage') or {},
         'backfill_incomplete':root.get('pitchAPIBackfillIncomplete',True),
         'errors':(root.get('pitchAPIErrors') or [])[:30],
      },
      'position_consistency':root.get('positionConsistency') or {},
      'current_appearance_count_gaps':{
         'players_with_minutes_but_no_exact_match_count':len(current_match_missing),
         'rows_by_source':dict(current_row_gaps),
         'display_policy':'Show verified minimum appearances (≥), never treat UEFA-only counts as a full-season total'
      },
      'interpretation':'Partial coverage is not zero appearances. A value is only supplied when its provider backed data exists.'
    }
    return result

def main():
    site=ROOT/'_site'/'index.html'
    output=ROOT/'_site'/'data'/'coverage.json'
    report=summarize(load_site(site))
    output.parent.mkdir(parents=True,exist_ok=True)
    output.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print('Three-season player coverage:',{s:(v['with_verified_player_stats'],
          v['with_minutes_for_index']) for s,v in report['seasons'].items()})
    print('Coverage report:',output)
    print('ADDED LEAGUES / PLAYER COUNTS:')
    for league,metrics in sorted(report['leagues'].items()):
        print('  '+league+': '+str(metrics['players']))
    print('EXPANSION AUDIT:',json.dumps(report['expansion'],ensure_ascii=False))
    print('CONTRACT AUDIT:',json.dumps(report['contract_evidence'],ensure_ascii=False))
    print('INDEX INPUT AUDIT:',json.dumps(report['index_inputs'],ensure_ascii=False))

if __name__=='__main__':
    main()
