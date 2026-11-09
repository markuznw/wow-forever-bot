#!/usr/bin/env python3
"""Tracker dello stato dei server di WoW: Forever (EU) con avvisi su Telegram.

Legge i dati della pagina pubblica "Server Status" di Blizzard con la stessa richiesta che fa la pagina
(veloce, senza browser). Se Blizzard la cambia, ripiega su Chrome: apre la pagina, indirizza la sua
richiesta sui server di Forever della regione scelta e impara il nuovo formato per i controlli successivi.
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

import requests

import bot

REGION = os.environ.get("STATUS_REGION", "eu").strip().lower() or "eu"
SLUG = f"forever-{REGION}"
PAGE = f"https://worldofwarcraft.blizzard.com/en-gb/game/status/{REGION}"
STATE_FILE = Path(__file__).with_name("status.json")
NOTIFY = os.environ.get("STATUS_NOTIFY", "on").lower() not in ("0", "off", "no", "false")
GRAPHQL = "https://worldofwarcraft.blizzard.com/en-gb/graphql"
DEFAULT_DOC_HASH = "e890f42a5375f136b9f9165408fb2bc372cc5f88be0b21e7dc681a70d9999c67"  # GetRealmStatusData
UA = "wow-forever-telegram-bot/1.0 (+https://github.com/markuznw/wow-forever-bot)"
CONFIRM_DELAY = 60  # secondi: prima di avvisare ricontrolla, per evitare falsi allarmi
REGION_NAME = {"eu": "EU", "us": "US", "kr": "KR", "tw": "TW"}.get(REGION, REGION.upper())


LEARNED = {}  # codice della richiesta imparato dalla pagina (se Blizzard lo cambia)


def fetch_direct(doc_hash):
    """Richiesta diretta, nel formato usato dalla pagina: veloce, senza browser."""
    body = {"operationName": "GetRealmStatusData",
            "variables": {"input": {"compoundRegionGameVersionSlug": SLUG}},
            "extensions": {"clientLibrary": {"name": "@apollo/client", "version": "4.1.7"},
                           "persistedQuery": {"version": 1, "sha256Hash": doc_hash}}}
    headers = {"accept": "application/graphql-response+json,application/json;q=0.9",
               "content-type": "application/json", "user-agent": UA}
    try:
        r = requests.post(GRAPHQL, json=body, headers=headers, timeout=20)
        realms = (r.json().get("data") or {}).get("Realms") if r.ok else None
        if realms:
            return {x["name"]: bool(x.get("online")) for x in realms}
        print(f"[warn] richiesta diretta non accettata ({r.status_code}): {r.text[:120]}", file=sys.stderr)
    except Exception as ex:
        print(f"[warn] richiesta diretta non riuscita: {ex}", file=sys.stderr)
    return None


def fetch_status(doc_hash=DEFAULT_DOC_HASH):
    """Restituisce {nome server: online?} oppure None se Blizzard non risponde."""
    realms = fetch_direct(doc_hash)
    if realms:
        return realms
    print("[info] uso la pagina con Chrome", file=sys.stderr)
    return fetch_with_browser()


def fetch_with_browser():
    """Ripiego: apre la pagina pubblica con Chrome e ne legge i dati."""
    from playwright.sync_api import sync_playwright

    realms = {}

    def reroute(route):
        # la pagina chiede i server della versione predefinita: la indirizziamo su Forever
        try:
            body = json.loads(route.request.post_data or "{}")
            inp = body.get("variables", {}).get("input", {})
            if body.get("operationName") == "GetRealmStatusData":
                h = body.get("extensions", {}).get("persistedQuery", {}).get("sha256Hash")
                if h:
                    LEARNED["doc_hash"] = h
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


def save_state(data):
    if LEARNED.get("doc_hash"):
        data["doc_hash"] = LEARNED["doc_hash"]
    STATE_FILE.write_text(json.dumps(data, indent=1))


def main():
    state = load_state()
    doc_hash = state.get("doc_hash") or DEFAULT_DOC_HASH
    realms = fetch_status(doc_hash)
    if realms is None:
        print("[warn] stato dei server non letto, riprovo al prossimo controllo", file=sys.stderr)
        return
    if LEARNED.get("doc_hash") and LEARNED["doc_hash"] != state.get("doc_hash"):
        state["doc_hash"] = LEARNED["doc_hash"]
        save_state(dict(state))
    prev = state.get("realms")
    print(f"[info] server Forever {REGION_NAME}: " + ", ".join(f"{n}={'up' if u else 'down'}" for n, u in sorted(realms.items())))

    if prev is None:  # primo avvio: salva lo stato senza avvisare
        save_state({"realms": realms, "down_since": None if all(realms.values()) else time.time(), "doc_hash": doc_hash})
        return
    if realms == prev:
        return

    # cambiamento: ricontrolla dopo un minuto prima di avvisare
    time.sleep(CONFIRM_DELAY)
    again = fetch_status(LEARNED.get("doc_hash") or doc_hash)
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
    save_state({"realms": realms, "down_since": down_since, "doc_hash": LEARNED.get("doc_hash") or doc_hash})


if __name__ == "__main__":
    main()
