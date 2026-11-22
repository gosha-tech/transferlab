#!/usr/bin/env python3
"""Budget-aware, source-safe schedule for verified player-match enrichment.

Two improvements:
* Fresh current-season matches from leagues with missing player evidence are
  requested before low-priority historical backfill, without starving history.
* Previously checked match reports are not downloaded every day solely because
  the archived roster grew. Failed/empty reports are retried after a TTL.

The scheduler cannot claim player stats exist: it only decides which authentic
provider match reports to request next.
"""
from __future__ import annotations
from datetime import datetime, timezone, timedelta
import json
import pathlib

ROOT=pathlib.Path(__file__).resolve().parents[1]
QUEUE=ROOT/'data'/'priority_refresh_queue.json'
CALENDAR={'MLS','Brasileirão','Argentine Primera División','Eliteserien',
          'Allsvenskan','J1 League','K League 1'}

def load_queue(path=QUEUE):
    try:
        record=json.loads(pathlib.Path(path).read_text(encoding='utf-8'))
        gaps=record.get('missing_by_league') or {}
        all_gaps=record.get('all_missing_by_league') or {}
        if not isinstance(gaps,dict) or not isinstance(all_gaps,dict):return {}
        leagues=set(gaps)|set(all_gaps)
        def count(x):
            return max(0,min(int(x),10000)) if isinstance(x,(int,float)) and not isinstance(x,bool) else 0
        # Five times priority for the most active 1000 profiles, while
        # retaining nonzero queue weight for unsupported leagues (e.g. RPL).
        return {str(k):5*count(gaps.get(k))+count(all_gaps.get(k))//20
                for k in leagues}
    except (ValueError,OSError,TypeError):return {}

def current_season(canonical,season):
    year='2026' if canonical in CALENDAR else '2026/2027'
    return str(season)==year

def prioritized_tasks(tasks,missing):
    """Fair interleave: 3 current tasks to 1 archived, preserving leagues."""
    current=[t for t in tasks if current_season(t['canonical'],t['season'])]
    archive=[t for t in tasks if not current_season(t['canonical'],t['season'])]
    current.sort(key=lambda x:(-missing.get(x['canonical'],0),x['canonical']))
    # Sort older seasons most recently first, but keep all competitions.
    archive.sort(key=lambda x:(-missing.get(x['canonical'],0),
                                -int(str(x['season'])[:4]),x['canonical']))
    out=[]
    ci=ai=0
    while ci<len(current) or ai<len(archive):
        for _ in range(3):
            if ci<len(current):out.append(current[ci]);ci+=1
        if ai<len(archive):out.append(archive[ai]);ai+=1
    return out

def should_retry(previous,season,roster_size,now=None):
    """True if a match report legitimately needs another source check."""
    if not isinstance(previous,dict) or not previous:return True
    now=now or datetime.now(timezone.utc)
    timestamp=str(previous.get('checked_at') or '')
    try:
        last=datetime.fromisoformat(timestamp.replace('Z','+00:00'))
        if last.tzinfo is None:last=last.replace(tzinfo=timezone.utc)
    except (ValueError,TypeError):
        # A previous report with player records is useful even if an old
        # import did not retain its retrieval timestamp. Don't flood API.
        return not bool(previous.get('players'))
    days=(now-last).total_seconds()/86400
    if days<0:return False
    if previous.get('players'):
        # Profile count may grow sharply when 10k archive players are added;
        # it is not proof that the provider has new player observations.
        # Recheck a current-season match at most once per 30 days and archive
        # only after 90 days when the database identity map expands.
        grew=int(previous.get('roster_profiles') or 0)<roster_size
        is_current=str(season) in ('2026/2027','2026')
        return grew and days >= (30 if is_current else 90)
    # Missing player stats is UNKNOWN, not verified zero. Retry after a
    # shorter window for current fixtures and longer for past games.
    return days >= (5 if str(season) in ('2026/2027','2026') else 21)

def selftest():
    jobs=[{'canonical':'Premier League','season':'2026/2027'},
          {'canonical':'Russian Premier League','season':'2026/2027'},
          {'canonical':'Premier League','season':'2025/2026'},
          {'canonical':'Ligue 1','season':'2026/2027'},
          {'canonical':'Ligue 1','season':'2025/2026'},
          {'canonical':'Premier League','season':'2024/2025'},
          {'canonical':'MLS','season':'2026'}]
    scheduled=prioritized_tasks(jobs,{'Russian Premier League':200,'Premier League':100})
    assert scheduled[0]['canonical']=='Russian Premier League'
    assert scheduled[1]['canonical']=='Premier League'
    assert scheduled[3]['season']=='2025/2026'
    assert len(scheduled)==len(jobs)
    from tempfile import TemporaryDirectory
    with TemporaryDirectory() as folder:
        q=pathlib.Path(folder)/'queue.json'
        q.write_text(json.dumps({'missing_by_league':{'Premier League':40},
            'all_missing_by_league':{'Russian Premier League':652}}))
        weights=load_queue(q)
        assert weights['Premier League']==200
        assert weights['Russian Premier League']==32
    now=datetime(2026,11,22,tzinfo=timezone.utc)
    sample={'players':[{'player_id':'p'}],'roster_profiles':3000,
            'checked_at':'2026-11-15T00:00:00+00:00'}
    assert not should_retry(sample,'2026/2027',10501,now)
    assert should_retry(sample,'2026/2027',10501,now+timedelta(days=40))
    assert not should_retry(sample,'2026/2027',3000,now+timedelta(days=100))
    empty=dict(sample,players=[])
    assert should_retry(empty,'2026/2027',10501,now)
    assert not should_retry(empty,'2025/2026',10501,now)
    print('Source-match fetch priority and cached report TTL PASS')

if __name__=='__main__':selftest()
