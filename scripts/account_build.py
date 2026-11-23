#!/usr/bin/env python3
"""Add TransferLab personal history, opt-in account UI and visitor analytics.

No analytics beacon is sent unless its site token is configured. Supabase
requires a public publishable/anon key only; service_role keys are rejected.
This is a static GitHub Pages site, so registration is inactive until a real
Supabase project and RLS tables have been configured by the site owner.
"""
from __future__ import annotations

import base64
import html as html_lib
import json
import os
import pathlib
import re
import sys
from urllib.parse import urlparse

NAV = ('<button type="button" id="navAccount" aria-current="false" '
       'aria-label="История и аккаунт">'
       '<span class="sym" aria-hidden="true">◷</span>'
       '<span class="nav-label">История</span></button>')

SECTION = """<section id="viewAccount" class="hidden tl-account" aria-labelledby="tlAccountTitle">
  <div class="tl-account-header">
    <span class="tl-eyebrow">TRANSFERLAB ACCOUNT</span>
    <h1 id="tlAccountTitle">История игроков</h1>
    <p>Последние просмотренные футболисты. На этом устройстве история доступна без регистрации.</p>
  </div>
  <div class="tl-account-columns">
    <div class="tl-account-panel">
      <h2>Мой аккаунт</h2>
      <p id="tlAccountStatus" role="status" aria-live="polite">История хранится в этом браузере.</p>
      <form id="tlAccountForm" hidden>
        <label for="tlAccountEmail">Email для регистрации или входа</label>
        <input id="tlAccountEmail" type="email" required autocomplete="email"
               maxlength="254" placeholder="name@example.com">
        <button id="tlAccountSend" type="submit">Получить ссылку для входа</button>
      </form>
      <button id="tlAccountLogout" type="button" hidden>Выйти из аккаунта</button>
      <p class="tl-account-caption">Вход без пароля: ссылка придёт на email. История в аккаунте видна только вам.
        Регистрация не требуется для поиска игроков.</p>
    </div>
    <div class="tl-account-panel">
      <div class="tl-account-row">
        <h2>Недавно просмотренные</h2>
        <button id="tlHistoryClear" type="button" class="tl-account-quiet">Очистить</button>
      </div>
      <p id="tlHistoryInfo" class="tl-account-caption">История ещё пуста.</p>
      <div id="tlHistoryItems" class="tl-history-items" aria-live="polite"></div>
    </div>
  </div>
</section>"""

BRIDGE = r"""  // A lightweight event bridge into the existing player navigation.
  // History never influences model predictions or public transfer rankings.
  const transferLabHistoryChoose = choosePlayer;
  choosePlayer = function(id){
    const result = transferLabHistoryChoose(id);
    document.dispatchEvent(new CustomEvent('transferlab:player-opened',{
      detail:{playerId:String(id)}}));
    return result;
  };
  window.TransferLabAccountBridge={
    getPlayer(id){return players.find(p=>String(p.id)===String(id))||null;},
    openPlayer(id){choosePlayer(id);},
    showCatalog(){showView('catalog');}
  };
  const transferLabHistoryShowView=showView;
  showView=function(view){
    const history=document.getElementById('viewAccount');
    if(history)history.classList.add('hidden');
    const tab=document.getElementById('navAccount');
    if(tab){tab.classList.remove('active');tab.setAttribute('aria-current','false');}
    return transferLabHistoryShowView(view);
  };
"""

def validate_publishable_key(key: str) -> str:
    if not key:
        return ""
    key = key.strip()
    if re.fullmatch(r'sb_publishable_[A-Za-z0-9_-]{8,500}', key):
        return key
    if key.startswith("sb_secret_"):
        raise RuntimeError("Never use a Supabase secret key in a public website")
    # Legacy JWT anon keys are accepted if and only if their signed payload
    # advertises the anon role (never service_role).
    try:
        pieces = key.split(".")
        if len(pieces) != 3:
            raise ValueError("unexpected key format")
        raw = pieces[1] + "=" * (-len(pieces[1]) % 4)
        payload = json.loads(base64.urlsafe_b64decode(raw.encode()).decode())
        if payload.get("role") != "anon":
            raise ValueError("not an anon key")
        return key
    except Exception as exc:
        raise RuntimeError("Only Supabase publishable/anon keys can be published") from exc

def public_config():
    url = os.getenv("TRANSFERLAB_SUPABASE_URL", "").strip()
    key = validate_publishable_key(
        os.getenv("TRANSFERLAB_SUPABASE_PUBLISHABLE_KEY", ""))
    if bool(url) != bool(key):
        raise RuntimeError("Set both the Supabase URL and publishable key")
    if url:
        parsed = urlparse(url)
        if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment or parsed.path not in ("", "/"):
            raise RuntimeError("Supabase URL must be an HTTPS project origin")
        url = url.rstrip("/")
    token = os.getenv("TRANSFERLAB_CLOUDFLARE_WEB_ANALYTICS_TOKEN", "").strip()
    if token and not re.fullmatch(r"[a-fA-F0-9]{32}", token):
        raise RuntimeError("Cloudflare Web Analytics token must be 32 hexadecimal characters")
    return {"supabaseUrl": url, "supabasePublishableKey": key,
            "analyticsEnabled": bool(token)}, token

def inject(source: str, config: dict | None = None, token: str = "") -> str:
    if 'id="viewAccount"' in source or 'id="navAccount"' in source:
        raise RuntimeError("Account UI must be added exactly once")
    marker = '  function renderProfile(){'
    section_anchor = '<section id="viewCatalog" class="hidden">'
    if source.count(marker) != 1 or source.count(section_anchor) != 1:
        raise RuntimeError("Account injection markers are absent or ambiguous")
    favorites = re.search(
        r'<button(?=[^>]*id="navFavorites")[^>]*>.*?</button>',
        source, re.I | re.S)
    if not favorites:
        raise RuntimeError("Navigation is missing navFavorites")
    source = source[:favorites.end()] + NAV + source[favorites.end():]
    source = source.replace(section_anchor, SECTION + section_anchor, 1)
    source = source.replace(marker, BRIDGE + marker, 1)
    if source.count("</head>") != 1 or source.count("</body>") != 1:
        raise RuntimeError("Cannot insert account scripts into HTML")
    cfg = config or {"supabaseUrl":"","supabasePublishableKey":"","analyticsEnabled":False}
    config_js = json.dumps(cfg, separators=(",", ":"), ensure_ascii=False)
    # Prevent script tag break-outs, even though owners configure values.
    config_js = config_js.replace("<", "\\u003c").replace(">", "\\u003e")
    analytics = ""
    if token:
        beacon_data = html_lib.escape(
            json.dumps({"token": token}, separators=(",", ":")), quote=True)
        analytics = ('<script defer src="https://static.cloudflareinsights.com/beacon.min.js" '
                     f'data-cf-beacon="{beacon_data}"></script>\n')
    source = source.replace(
        "</head>",
        '<link rel="stylesheet" href="assets/account.css">\n'
        f'<script>window.TransferLabAccountConfig={config_js};</script>\n'
        + analytics + "</head>", 1)
    source = source.replace(
        "</body>", '<script src="assets/account.js" defer></script>\n</body>', 1)
    return source

def main():
    path = pathlib.Path(sys.argv[1]) if len(sys.argv) > 1 else pathlib.Path("_site/index.html")
    config, token = public_config()
    before = path.read_text(encoding="utf-8")
    html = inject(before, config, token)
    path.write_text(html, encoding="utf-8")
    print("Account/history interface embedded. Supabase configured:",bool(config["supabaseUrl"]),
          "; Cloudflare analytics configured:",bool(token))
    print("No visitor measurements or registrations occur until provider setup.")

if __name__ == "__main__":
    main()
