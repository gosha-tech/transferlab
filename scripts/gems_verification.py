#!/usr/bin/env python3
"""Per-player evidence audit and review queue for TransferLab Hidden Gems.

This script DOES NOT supply market prices, assert current club from an archival
dataset, or call any unofficial scraping API. It records which independent
checks remain missing for each default-filter candidate. Full confirmation
requires a fresh, licensed/authorized value, an identifiable current club and
current-season match evidence, all cross-checked by player ID.
"""
from __future__ import annotations
from collections import Counter
from datetime import date
import json
from pathlib import Path

CALENDAR={'MLS','Brasileirão','Argentine Primera División','Eliteserien',
          'Allsvenskan','J1 League','K League 1'}
OLD_SOURCES={'transfermarkt_historical','historical_appearances',
             'pl_catalogue','thesportsdb_sample'}

def valid_date(s):
    try:
        v=date.fromisoformat(str(s)[:10])
        return v if len(str(s))>=10 else None
    except (TypeError,ValueError):return None

def age(born,today):
    d=valid_date(born)
    if not d or d>today:return None
    return today.year-d.year-((today.month,today.day)<(d.month,d.day))

def numeric(value):
    try:return max(0,float(value or 0))
    except (TypeError,ValueError):return 0

def evidence(players,root,as_of,age_max=23,price_limit=15_000_000,min_minutes=450):
    """Audit all default-budget candidates, not just those with a score.

    Unavailable price and current match logs have explicit missing statuses.
    'archive_stats' means source-backed historical appearances, not live stats.
    """
    by_season=root.get('liveIndexStats') or {}
    market=root.get('hiddenGemsMarket') or {}
    rows=[]
    counts=Counter()
    for p in players:
        current_age=age(p.get('birth'),as_of)
        if current_age is None or current_age>age_max:continue
        if p.get('pos') not in ('Goalkeeper','Defender','Midfielder','Forward'):continue
        if not (p.get('displayPosition') or p.get('position_source') or p.get('positionVerified')):continue
        calendar=p.get('league') in CALENDAR
        current_season='2026' if calendar else '2026/27'
        previous_season='2025' if calendar else '2025/26'
        pid=str(p.get('id'))
        live=(by_season.get(current_season) or {}).get(pid) or {}
        old=(by_season.get(previous_season) or {}).get(pid) or {}
        live_minutes=numeric(live.get('minutes'))
        archive_minutes=numeric(old.get('minutes'))
        source=str(live.get('source') or '').lower()
        current_verified=live_minutes>=min_minutes and bool(source) and source not in OLD_SOURCES
        season_minutes=live_minutes if current_verified else archive_minutes
        if season_minutes<min_minutes:continue
        raw_market=market.get(pid) or {}
        current_price=raw_market.get('value_eur')
        has_current_price=isinstance(current_price,int) and not isinstance(current_price,bool) and 0<current_price<=500_000_000
        if has_current_price and current_price>price_limit:continue
        archived_value=p.get('marketValueArchiveEUR')
        if not has_current_price and archived_value is not None and numeric(archived_value)>price_limit:continue
        club_as_of=valid_date(p.get('clubSourceAsOf') or p.get('clubVerifiedAsOf'))
        club_source=p.get('clubSource') or p.get('clubSourceUrl')
        club_verified=bool(club_as_of and club_source and 0<=(as_of-club_as_of).days<=180)
        # Older archive matches already have historical provenance, not a new
        # independent recheck or proof that the player is active now.
        archive_verified=archive_minutes>=min_minutes and bool(old.get('source'))
        missing=[]
        if not current_verified:missing.append('current_matches')
        if not club_verified:missing.append('current_club')
        if not has_current_price:missing.append('licensed_fresh_market_value')
        # A current price and a match record are still insufficient to assert
        # a bargain until there are enough role/age peers for comparisons.
        ready=current_verified and club_verified and has_current_price
        counts['review_candidates']+=1
        counts['verified_archive_matches']+=int(archive_verified)
        counts['verified_current_matches']+=int(current_verified)
        counts['verified_current_club']+=int(club_verified)
        counts['licensed_current_values']+=int(has_current_price)
        counts['all_three_data_checks']+=int(ready)
        if 'current_matches' in missing:counts['missing_current_matches']+=1
        if 'current_club' in missing:counts['missing_current_club']+=1
        if 'licensed_fresh_market_value' in missing:counts['missing_market']+=1
        rows.append({
            'player_id':pid,'name':p.get('name'),'league':p.get('league'),
            'club':p.get('team'),'age':current_age,
            'season':current_season if current_verified else previous_season,
            'minutes':round(season_minutes),
            'historical_stats_verified':archive_verified,
            'current_stats_verified':current_verified,
            'current_club_verified':club_verified,
            'fresh_value_verified':has_current_price,
            'data_ready_for_market_comparison':ready,
            'missing':missing,
            'evidence_as_of':{
                'matches':live.get('as_of') if current_verified else old.get('as_of'),
                'club':club_as_of.isoformat() if club_verified else None,
                'market':raw_market.get('as_of') if has_current_price else None}
        })
    # First review candidates with most data already validated; then those
    # with recent matches and many minutes. No valuation is fabricated.
    rows.sort(key=lambda row:(len(row['missing']),-int(row['current_stats_verified']),
        -row['minutes'],row['name'] or ''))
    return {'schema_version':1,'as_of':as_of.isoformat(),
       'criteria':{'max_age':age_max,'max_market_eur':price_limit,
                   'min_season_minutes':min_minutes},
       'coverage':dict(counts),'players':rows}

def selftest():
    today=date(2026,11,22)
    base={'id':'p1','name':'Example','league':'Premier League',
          'birth':'2004-01-01','pos':'Forward','displayPosition':'LW',
          'team':'Example FC','clubSource':'https://example.com/club',
          'clubSourceAsOf':'2026-11-01'}
    root={'liveIndexStats':{
      '2025/26':{'p1':{'minutes':1200,'source':'transfermarkt_historical'}},
      '2026/27':{'p1':{'minutes':550,'source':'verified_multi_source_partial'}}},
      'hiddenGemsMarket':{}}
    report=evidence([base],root,today)
    assert report['coverage']['review_candidates']==1
    row=report['players'][0]
    assert row['current_stats_verified'] and row['current_club_verified']
    assert not row['data_ready_for_market_comparison']
    assert row['missing']==['licensed_fresh_market_value']
    root['hiddenGemsMarket']={'p1':{'value_eur':12000000,'as_of':'2026-11-20'}}
    row=evidence([base],root,today)['players'][0]
    assert row['data_ready_for_market_comparison'] and row['missing']==[]
    assert evidence([dict(base,birth='1994-01-01')],root,today)['coverage']=={}
    print('Hidden Gems source-evidence audit and honest unverified queue PASS')

if __name__=='__main__':selftest()
