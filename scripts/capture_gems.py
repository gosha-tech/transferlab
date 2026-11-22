#!/usr/bin/env python3
"""Archive real dated Hidden Gems decisions, not hindsight reclassifications.

The export is computed by the same browser algorithm visitors see. Only
source-complete and genuinely underpriced candidates enter this archive.
"""
from __future__ import annotations
import datetime as dt
import functools
import http.server
import json
import math
import pathlib
import re
import shutil
import threading

from capture_forecasts import SITE, QuietHandler
from gem_history import HISTORY

def record(value, archive):
    today = dt.datetime.now(dt.timezone.utc).date().isoformat()
    day = str(value.get("as_of") or "")
    if day != today:
        raise RuntimeError("Cannot backdate or forward-date gem discoveries")
    discoveries = value.get("discoveries")
    if not isinstance(discoveries, dict):
        raise RuntimeError("Gem export must provide a player-ID map")
    if len(discoveries) > 1000:
        raise RuntimeError("Unreasonable gem discovery count")
    clean = {}
    for pid, row in discoveries.items():
        if not isinstance(row, dict) or not str(pid) or len(str(pid)) > 80:
            continue
        market = row.get("market_value_eur")
        gap = row.get("gap")
        performance = row.get("performance_percentile")
        as_of = str(row.get("market_as_of") or "")
        if (not isinstance(market, int) or isinstance(market, bool) or
                market <= 0 or market > 500_000_000 or
                not isinstance(gap, (int, float)) or not math.isfinite(gap) or gap < .2 or
                not isinstance(performance, (int, float)) or
                not math.isfinite(performance) or performance < .65 or
                not re.fullmatch(r"20\d{2}-\d{2}-\d{2}", as_of) or as_of > day or
                (dt.date.fromisoformat(day) - dt.date.fromisoformat(as_of)).days > 120 or
                not str(row.get("source_url") or "").startswith("https://") or
                not str(row.get("club") or "").strip()):
            continue
        clean[str(pid)] = {
            "name": str(row.get("name") or ""),
            "club": str(row["club"]),
            "league": str(row.get("league") or ""),
            "age": row.get("age"),
            "position": str(row.get("position") or ""),
            "minutes": row.get("minutes"),
            "market_value_eur": market,
            "market_as_of": as_of,
            "market_source": str(row.get("market_source") or ""),
            "source_url": str(row["source_url"]),
            "gap": round(float(gap), 5),
            "performance_percentile": round(float(performance), 5),
            "score": row.get("score")
        }
    snapshots = [v for v in (archive.get("snapshots") or [])
                 if isinstance(v, dict) and v.get("as_of") != day]
    snapshots.append({"as_of": day, "model_version": str(value.get("model_version") or "unknown"),
                      "discoveries": clean})
    snapshots.sort(key=lambda x: x["as_of"])
    return {"schema_version": 1, "snapshots": snapshots[-730:]}

def capture():
    from playwright.sync_api import sync_playwright
    if not (SITE / "index.html").exists():
        raise RuntimeError("Missing site; cannot capture discoveries")
    handler = functools.partial(QuietHandler, directory=str(SITE))
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        with sync_playwright() as playwright:
            chrome = shutil.which("google-chrome") or shutil.which("chromium") or shutil.which("chromium-browser")
            args = {"headless": True, "args": ["--no-sandbox", "--disable-dev-shm-usage"]}
            if chrome:
                args["executable_path"] = chrome
            browser = playwright.chromium.launch(**args)
            try:
                page = browser.new_page()
                page.set_default_timeout(90000)
                page.route("**/*", lambda route: route.abort()
                           if route.request.url.startswith(("http://", "https://"))
                           and "127.0.0.1" not in route.request.url else route.continue_())
                page.goto("http://127.0.0.1:" + str(server.server_port),
                          wait_until="domcontentloaded", timeout=30000)
                page.wait_for_function('typeof window.transferLabGemsSnapshotExport==="function"')
                result = page.evaluate("window.transferLabGemsSnapshotExport()")
            finally:
                browser.close()
    finally:
        server.shutdown()
    try:
        prior = json.loads(HISTORY.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        prior = {}
    updated = record(result, prior)
    HISTORY.parent.mkdir(parents=True, exist_ok=True)
    temporary = HISTORY.with_suffix(".tmp")
    temporary.write_text(json.dumps(updated, ensure_ascii=False,
                                    separators=(",", ":")) + "\n", encoding="utf-8")
    temporary.replace(HISTORY)
    print("Archived dated source-complete Hidden Gems:", len(updated["snapshots"][-1]["discoveries"]))

def selftest():
    today = dt.datetime.now(dt.timezone.utc).date().isoformat()
    sample = {"name": "Example", "club": "Old FC", "market_value_eur": 5_000_000,
              "market_as_of": today, "source_url": "https://example.org/source",
              "gap": .31, "performance_percentile": .83, "score": 75}
    result = record({"as_of": today, "model_version": "test",
                     "discoveries": {"p1": sample, "p2": dict(sample, gap=.05)}},
                    {"snapshots": []})
    assert len(result["snapshots"][-1]["discoveries"]) == 1
    assert len(record({"as_of": today, "discoveries": {"p1": sample}}, result)["snapshots"]) == 1
    try:
        record({"as_of": "2026-01-01", "discoveries": {}}, {})
    except RuntimeError:
        pass
    else:
        raise AssertionError("Accepted backdated gem discovery")
    print("Dated Hidden Gems snapshot capture PASS")

if __name__ == "__main__":
    import sys
    if "--self-test" in sys.argv:
        selftest()
    else:
        capture()
