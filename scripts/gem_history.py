#!/usr/bin/env python3
"""Evidence-based Hidden Gem outcomes: discoveries must precede completed deals.

A reported transfer fee is not a guaranteed measure of sporting quality.
Failures stay in the published review log to limit survivorship bias.
"""
from __future__ import annotations
from datetime import date
from math import isfinite
from pathlib import Path
import json
import re
import unicodedata

ROOT = Path(__file__).resolve().parents[1]
HISTORY = ROOT / "data" / "gem_discovery_snapshots.json"


def valid_day(value):
    if not isinstance(value, str) or not re.fullmatch(r"20\d{2}-\d{2}-\d{2}", value):
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def club_key(value):
    text = unicodedata.normalize("NFKD", str(value or "").casefold())
    return "".join(ch for ch in text if ch.isalnum() and not unicodedata.combining(ch))


def number(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not isfinite(value):
        return None
    return float(value)


def load(path=HISTORY):
    try:
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
        return raw if isinstance(raw, dict) and raw.get("schema_version") == 1 else {}
    except (OSError, ValueError):
        return {}


def assess(history, verified_transfers, today):
    """Return genuine pre-deal discoveries and their outcomes, including misses."""
    snapshots = history.get("snapshots") or []
    results = []
    used = set()
    for player_id, events in (verified_transfers or {}).items():
        if not isinstance(events, list):
            continue
        for deal in events:
            if not isinstance(deal, dict):
                continue
            deal_day = valid_day(deal.get("date"))
            fee = number(deal.get("reported_fee_eur_m"))
            prediction = deal.get("pre_transfer_prediction") or {}
            prediction_day = valid_day(prediction.get("as_of"))
            predicted = number(prediction.get("eur_m"))
            if (not deal_day or deal_day > today or not fee or fee <= 0
                    or not prediction_day or prediction_day >= deal_day
                    or (deal_day - prediction_day).days > 45
                    or not predicted or predicted <= 0
                    or not str(deal.get("official_source") or "").startswith("https://")
                    or not str(deal.get("fee_source") or "").startswith("https://")):
                continue
            key = (str(player_id), str(deal.get("event_id") or deal_day.isoformat()))
            if key in used:
                continue
            used.add(key)
            chosen = None
            for snap in snapshots:
                if not isinstance(snap, dict):
                    continue
                captured = valid_day(snap.get("as_of"))
                if (not captured or captured >= deal_day or
                        (deal_day - captured).days > 365):
                    continue
                discovery = (snap.get("discoveries") or {}).get(str(player_id))
                if not isinstance(discovery, dict):
                    continue
                market_day = valid_day(discovery.get("market_as_of"))
                market = number(discovery.get("market_value_eur"))
                gap = number(discovery.get("gap"))
                performance = number(discovery.get("performance_percentile"))
                if (not market_day or market_day > captured or
                        (captured - market_day).days > 120 or
                        not market or market <= 0 or gap is None or gap < .20 or
                        performance is None or performance < .65 or
                        not str(discovery.get("source_url") or "").startswith("https://")
                        or club_key(discovery.get("club")) != club_key(deal.get("from_club"))):
                    continue
                if chosen is None or captured > chosen[0]:
                    chosen = (captured, discovery, snap)
            if chosen is None:
                continue
            captured, discovery, snap = chosen
            # Fixed, disclosed *research* thresholds. Not evidence of causality.
            underpriced_vs_fee = fee >= (float(discovery["market_value_eur"]) / 1_000_000) * 1.25
            forecast_error_pct = round(abs(predicted - fee) / fee * 100, 2)
            success = underpriced_vs_fee and forecast_error_pct <= 40
            results.append({
                "player_id": str(player_id),
                "name": str(discovery.get("name") or ""),
                "event_id": key[1],
                "discovered_at": captured.isoformat(),
                "deal_date": deal_day.isoformat(),
                "from_club": str(deal.get("from_club") or ""),
                "to_club": str(deal.get("to_club") or ""),
                "league": str(discovery.get("league") or ""),
                "position": str(discovery.get("position") or ""),
                "age_at_discovery": discovery.get("age"),
                "minutes_at_discovery": discovery.get("minutes"),
                "market_value_eur": discovery["market_value_eur"],
                "market_as_of": discovery["market_as_of"],
                "market_source": str(discovery.get("market_source") or ""),
                "market_source_url": discovery["source_url"],
                "hidden_gem_score": discovery.get("score"),
                "model_version": str(snap.get("model_version") or ""),
                "forecast_at": prediction_day.isoformat(),
                "model_forecast_eur_m": round(predicted, 2),
                "reported_fee_eur_m": round(fee, 2),
                "forecast_error_pct": forecast_error_pct,
                "official_source": deal["official_source"],
                "fee_source": deal["fee_source"],
                "successful": success,
                "caveat": "Reported fee is not equal to fair market value; this is retrospective validation, not proof of scouting causality."
            })
    results.sort(key=lambda x: (x["deal_date"], x["player_id"]), reverse=True)
    return {
        "schema_version": 1,
        "discovery_snapshots": len(snapshots),
        "reviewed_after_transfer": len(results),
        "successful_outcomes": sum(bool(row["successful"]) for row in results),
        "outcomes": results,
        "successes": [row for row in results if row["successful"]],
        "methodology": "Only pre-deal, dated, source-backed Hidden Gems with verified completed transfers and independent earlier model forecasts. Success: reported fee >=125% of original dated market quote and forecast error <=40%. Also publish misses."
    }


def selftest():
    today = date(2026, 11, 22)
    base = {"name": "Example", "club": "Old FC", "league": "Serie A",
            "age": 21, "position": "Forward", "minutes": 980,
            "market_value_eur": 5_000_000, "market_as_of": "2026-06-10",
            "source_url": "https://example.org/value", "gap": .3,
            "performance_percentile": .8, "score": 72}
    deals = {"p1": [{"event_id": "one", "date": "2026-07-20", "from_club": "Old FC",
                      "to_club": "New FC", "reported_fee_eur_m": 12,
                      "official_source": "https://club.org/deal",
                      "fee_source": "https://news.org/fee",
                      "pre_transfer_prediction": {"as_of": "2026-07-15", "eur_m": 11}}]}
    history = {"snapshots": [{"as_of": "2026-07-10", "model_version": "test",
                             "discoveries": {"p1": base}}]}
    good = assess(history, deals, today)
    assert good["successful_outcomes"] == 1
    bad = {"snapshots": [{"as_of": "2026-07-21", "discoveries": {"p1": base}}]}
    assert assess(bad, deals, today)["reviewed_after_transfer"] == 0
    wrong_club = {"snapshots": [{"as_of": "2026-07-10",
                                "discoveries": {"p1": dict(base, club="Other FC")}}]}
    assert assess(wrong_club, deals, today)["reviewed_after_transfer"] == 0
    missed = {"p1": [dict(deals["p1"][0], reported_fee_eur_m=6,
                         pre_transfer_prediction={"as_of": "2026-07-15", "eur_m": 11})]}
    outcome = assess(history, missed, today)
    assert outcome["reviewed_after_transfer"] == 1 and outcome["successful_outcomes"] == 0
    print("Leakage-safe Hidden Gems discovery/outcome audit PASS")


if __name__ == "__main__":
    selftest()
