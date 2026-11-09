#!/usr/bin/env python3
"""Tracker dello stato dei server di WoW: Forever (EU) con avvisi su Telegram.

Apre la pagina pubblica "Server Status" di Blizzard con Chrome e ne legge i dati,
indirizzando la richiesta della pagina sui server di Forever della regione scelta.
Avvisa quando un server va offline e quando tornano tutti online.

Variabili d'ambiente (oltre a quelle del bot delle news):
  STATUS_REGION      regione da controllare (default "eu")
  STATUS_CHANNEL     chat/argomento dove inviare gli avvisi (default: TELEGRAM_CHANNEL)
  STATUS_NOTIFY      "off" per inviare anche gli avvisi senza notifica (default "on")
"""
import html
import json
import os
import sys
import time
from pathlib import Path

import bot

REGION = os.environ.get("STATUS_REGION", "eu").strip().lower() or "eu"
SLUG = f"forever-{REGION}"
PAGE = f"https://worldofwarcraft.blizzard.com/en-gb/game/status/{REGION}"
STATE_FILE = Path(__file__).with_name("status.json")
NOTIFY = os.environ.get("STATUS_NOTIFY", "on").lower() not in ("0", "off", "no", "false")
CONFIRM_DELAY = 60  # secondi: prima di avvisare ricontrolla, per evitare falsi allarmi
REGION_NAME = {"eu": "EU", "us": "US", "kr": "KR", "tw": "TW"}.get(REGION, REGION.upper())


def fetch_status():
    """Restituisce {nome server: online?} oppure None se la pagina non risponde."""
    from playwright.sync_api import sync_playwright

    realms = {}

    def reroute(route):
        # la pagina chiede i server della versione predefinita: la indirizziamo su Forever
        try:
            body = json.loads(route.request.post_data or "{}")
            inp = body.get("variables", {}).get("input", {})
            if "compoundRegionGameVersionSlug" in inp:
                inp["compoundRegionGameVersionSlug"] = SLUG
                return route.continue_(post_data=json.dumps(body))
        except Exception:
            pass
        route.continue_()

    def on_response(resp):
        if "graphql" not in resp.url or resp.request.method != "POST":
            return
        try:
            data = resp.json().get("data") or {}
            for r in data.get("Realms") or []:
                realms[r["name"]] = bool(r.get("online"))
        except Exception:
            pass

    with sync_playwright() as pw:
        exe = os.environ.get("BROWSER_PATH")
        try:
            browser = pw.chromium.launch(executable_path=exe) if exe else pw.chromium.launch(channel="chrome")
        except Exception:
            browser = pw.chromium.launch()
        try:
            page = browser.new_page()
            page.route("**/graphql", reroute)
            page.on("response", on_response)
            page.goto(PAGE, wait_until="domcontentloaded", timeout=60000)
            deadline = time.time() + 45
            while not realms and time.time() < deadline:
                page.wait_for_timeout(500)
        except Exception as ex:
            print(f"[warn] pagina di stato non disponibile: {ex}", file=sys.stderr)
        finally:
            browser.close()
    return realms or None


def load_state():
    try:
        return json.loads(STATE_FILE.read_text())
    except Exception:
        return {}


def fmt_duration(seconds: float) -> str:
    m = int(seconds // 60)
    if m < 60:
        return f"{m} min"
    h, m = divmod(m, 60)
    return f"{h} h {m:02d} min"


def realm_lines(realms):
    return "\n".join(f"{'🟢' if up else '🔴'} {html.escape(n, quote=False)}" for n, up in sorted(realms.items()))


def send(text):
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    chat, topic = bot.parse_target(os.environ.get("STATUS_CHANNEL") or os.environ.get("TELEGRAM_CHANNEL", ""))
    if os.environ.get("DRY_RUN"):
        print("---\n" + text)
        return True
    payload = {"chat_id": chat, "text": text, "parse_mode": "HTML", "disable_notification": not NOTIFY,
               "link_preview_options": {"is_disabled": True},
               "reply_markup": {"inline_keyboard": [[{"text": "🌐 Server Status Blizzard", "url": PAGE}]]}}
    if topic:
        payload["message_thread_id"] = int(topic)
    return bot.tg_post(token, "sendMessage", payload).ok


def main():
    realms = fetch_status()
    if realms is None:
        print("[warn] stato dei server non letto, riprovo al prossimo controllo", file=sys.stderr)
        return
    state = load_state()
    prev = state.get("realms")
    print(f"[info] server Forever {REGION_NAME}: " + ", ".join(f"{n}={'up' if u else 'down'}" for n, u in sorted(realms.items())))

    if prev is None:  # primo avvio: salva lo stato senza avvisare
        STATE_FILE.write_text(json.dumps({"realms": realms, "down_since": None if all(realms.values()) else time.time()}, indent=1))
        return
    if realms == prev:
        return

    # cambiamento: ricontrolla dopo un minuto prima di avvisare
    time.sleep(CONFIRM_DELAY)
    again = fetch_status()
    if again is None or again != realms:
        print("[info] cambiamento non confermato, ricontrollo al prossimo giro")
        return

    now = time.time()
    down_since = state.get("down_since")
    was_all_up = all(prev.values())
    all_up = all(realms.values())
    went_down = [n for n, u in realms.items() if not u and prev.get(n, True)]

    text = None
    if all_up and not was_all_up:
        took = f"\n⏱ Down per {fmt_duration(now - down_since)}" if down_since else ""
        text = f"🟢 <b>Server WoW Forever {REGION_NAME} di nuovo online!</b>{took}\n\n{realm_lines(realms)}"
        down_since = None
    elif went_down:
        if was_all_up:
            down_since = now
        title = "offline" if not any(realms.values()) else "parzialmente offline"
        text = f"🔴 <b>Server WoW Forever {REGION_NAME} {title}</b>\n\n{realm_lines(realms)}"
    elif not all_up:
        # qualche server è tornato su ma non tutti: aggiorna senza disturbare
        text = None

    if text and not send(text):
        sys.exit("[error] avviso di stato non inviato")
    STATE_FILE.write_text(json.dumps({"realms": realms, "down_since": down_since}, indent=1))


if __name__ == "__main__":
    main()
