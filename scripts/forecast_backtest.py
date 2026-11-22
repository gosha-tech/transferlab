#!/usr/bin/env python3
"""Leakage-safe evaluation of real pre-transfer price forecasts.

Only already-archived, dated forecasts made before reported deals qualify.
An August or November evaluation of a July deal does NOT qualify.
Transfer fees differ from market valuations; this is a diagnostic, not a
statistical claim that exact transaction price is predictable.
"""
from __future__ import annotations
from datetime import date
from statistics import median
from math import isfinite
import json

def date_or_none(value):
    try: return date.fromisoformat(str(value)[:10])
    except (ValueError,TypeError): return None

def evaluate(moves):
    scored=[]
    seen=set()
    total=0
    excluded={'without_historical_snapshot':0,'invalid_amount_or_date':0,
              'snapshot_not_before_transfer':0,'duplicate_deal':0}
    for player_id,events in (moves or {}).items():
        if not isinstance(events,list):continue
        for event in events:
            total+=1
            if not isinstance(event,dict):
                excluded['invalid_amount_or_date']+=1;continue
            key=(player_id,str(event.get('event_id') or event.get('date') or ''))
            if key in seen:
                excluded['duplicate_deal']+=1;continue
            seen.add(key)
            day=date_or_none(event.get('date'))
            fee=event.get('reported_fee_eur_m')
            if not day or isinstance(fee,bool) or not isinstance(fee,(int,float)) or not isfinite(fee) or fee<=0:
                excluded['invalid_amount_or_date']+=1;continue
            previous=event.get('pre_transfer_prediction')
            if not previous:
                excluded['without_historical_snapshot']+=1;continue
            historical_day=date_or_none(previous.get('as_of'))
            forecast=previous.get('eur_m')
            if not historical_day or historical_day>=day:
                excluded['snapshot_not_before_transfer']+=1;continue
            if (day-historical_day).days>45:
                excluded['without_historical_snapshot']+=1;continue
            if isinstance(forecast,bool) or not isinstance(forecast,(float,int)) or not isfinite(forecast) or forecast<=0:
                excluded['invalid_amount_or_date']+=1;continue
            error=abs(float(forecast)-float(fee))
            scored.append({'player_id':str(player_id),'event_id':key[1],
               'deal_date':day.isoformat(),'forecast_date':historical_day.isoformat(),
               'forecast_eur_m':round(float(forecast),2),'reported_fee_eur_m':round(float(fee),2),
               'absolute_error_eur_m':round(error,2),
               'absolute_percentage_error':round(error/float(fee)*100,2),
               'snapshot_commit':previous.get('model_commit') or None,
               'source':event.get('fee_source')})
    errors=[r['absolute_error_eur_m'] for r in scored]
    percentages=[r['absolute_percentage_error'] for r in scored]
    return {'schema_version':1,'deals_reviewed':total,
       'eligible_pre_deal_predictions':len(scored),
       'median_absolute_error_eur_m':round(median(errors),2) if errors else None,
       'median_absolute_percentage_error':round(median(percentages),2) if percentages else None,
       'exclusions':excluded,'evaluated_deals':scored,
       'disclaimer':'Transfer fee is not the same as fair market valuation. Only earlier dated forecasts are included.'}

def selftest():
    move={'event_id':'a','date':'2026-07-24','reported_fee_eur_m':70,
          'pre_transfer_prediction':{'as_of':'2026-07-20','eur_m':55}}
    wrong={'event_id':'b','date':'2026-07-24','reported_fee_eur_m':70,
          'pre_transfer_prediction':{'as_of':'2026-11-22','eur_m':65}}
    missing={'event_id':'c','date':'2026-07-24','reported_fee_eur_m':70,
             'pre_transfer_prediction':None}
    result=evaluate({'p1':[move,wrong,missing]})
    assert result['eligible_pre_deal_predictions']==1
    assert result['median_absolute_error_eur_m']==15
    assert result['median_absolute_percentage_error']==21.43
    assert result['exclusions']['snapshot_not_before_transfer']==1
    assert result['exclusions']['without_historical_snapshot']==1
    assert evaluate({'x':[wrong,missing]})['median_absolute_percentage_error'] is None
    print('Leakage-safe transfer valuation backtest PASS')

if __name__=='__main__':
    import sys
    if '--self-test' in sys.argv:selftest()
    else:
        import re,pathlib
        path=pathlib.Path(sys.argv[1] if len(sys.argv)>1 else '_site/index.html')
        match=re.search(r'<script id="embeddedData" type="application/json">(.*?)</script>',path.read_text(encoding='utf-8'),re.S)
        if not match:raise RuntimeError('No embedded player data')
        root=json.loads(match.group(1))
        report=evaluate(root.get('verifiedTransfersByPlayer') or {})
        outfile=path.parent/'data'/'forecast_backtest.json'
        outfile.parent.mkdir(parents=True,exist_ok=True)
        outfile.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
        print('Historical price backtest:',report['eligible_pre_deal_predictions'],'eligible deals of',report['deals_reviewed'])
