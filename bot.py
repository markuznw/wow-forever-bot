#!/usr/bin/env python3
"""Bot che pubblica su un canale Telegram le news su World of Warcraft: Forever.

Legge una lista di feed RSS/Atom, tiene solo le notizie su "Forever",
scarta quelle già pubblicate (seen.json) e le invia al canale.

Variabili d'ambiente:
  TELEGRAM_BOT_TOKEN  token del bot (da @BotFather)
  TELEGRAM_CHANNEL    @nomecanale, id numerico (-100...) oppure un link
                      t.me/c/<id>/<topic> o t.me/<nome>/<topic> (gruppo con argomenti)
  TELEGRAM_TOPIC_ID   (opzionale) id dell'argomento, se non è nel link
  DRY_RUN=1           stampa i messaggi invece di inviarli
"""
import html
import json
import os
import re
import sys
import time
import urllib.parse
from pathlib import Path

import feedparser
import requests

FEEDS = [
    # (nome mostrato, url, serve il filtro parola chiave?)
    ("Wowhead", "https://www.wowhead.com/news/rss/all", True),
]

KEYWORD = re.compile(r"\bforever\b", re.I)
STATE_FILE = Path(__file__).with_name("seen.json")
MAX_SEEN = 2000          # quante chiavi ricordare
MAX_POSTS_PER_RUN = 10   # evita di inondare il canale
SUMMARY_CHARS = 900      # lunghezza massima del testo sotto il titolo
FIRST_RUN_POSTS = 10     # news pubblicate al primo avvio
TARGET_LANG = os.environ.get("TRANSLATE_TO", "off").strip()  # es. "it" per tradurre
if TARGET_LANG.lower() in ("", "off", "no", "none"):
    TARGET_LANG = ""  # traduzione disattivata
UA = "Mozilla/5.0 (compatible; wow-forever-telegram-bot/1.0)"


def norm_title(t: str) -> str:
    t = re.sub(r"\s+-\s+[^-]+$", "", t)  # Google News aggiunge " - Fonte"
    return re.sub(r"[^a-z0-9]+", " ", t.lower()).strip()


def norm_url(u: str) -> str:
    p = urllib.parse.urlsplit(u)
    return urllib.parse.urlunsplit((p.scheme, p.netloc.lower(), p.path.rstrip("/"), "", ""))


def clean(text: str, limit: int = 300) -> str:
    text = re.sub(r"<[^>]+>", " ", text or "")
    text = html.unescape(re.sub(r"\s+", " ", text)).strip()
    return text if len(text) <= limit else text[: limit - 1].rsplit(" ", 1)[0] + "…"


def clean_structured(raw: str, limit: int) -> str:
    """Come clean() ma mantiene paragrafi ed elenchi puntati."""
    t = raw or ""
    t = re.sub(r"(?is)<(script|style|figure|figcaption)[^>]*>.*?</\1>", " ", t)
    t = re.sub(r"(?i)<li[^>]*>", "\n• ", t)
    t = re.sub(r"(?i)<br\s*/?>|</(p|div|li|ul|ol|h[1-6]|tr)>", "\n", t)
    t = re.sub(r"<[^>]+>", " ", t)
    t = html.unescape(t)
    t = re.sub(r"(?im)^.*(continue reading|read more|leggi tutto).*$", "", t)
    lines = [re.sub(r"[ \t\xa0]+", " ", l).strip() for l in t.split("\n")]
    lines = [l for l in lines if l and l != "•"]
    out = []
    for l in lines:
        if not l.startswith("•") and out and out[-1].startswith("•"):
            out.append("")  # riga vuota tra elenco e paragrafo
        elif not l.startswith("•") and out:
            out.append("")
        out.append(l)
    t = "\n".join(out).strip()
    if len(t) <= limit:
        return t
    cut = t[:limit]
    cut = cut.rsplit("\n", 1)[0] if cut.count("\n") and len(cut.rsplit("\n", 1)[0]) > limit * 0.6 else cut.rsplit(" ", 1)[0]
    return cut.rstrip() + " …"


MONTHS = ["gennaio", "febbraio", "marzo", "aprile", "maggio", "giugno", "luglio",
          "agosto", "settembre", "ottobre", "novembre", "dicembre"]
TAGS = [
    (r"hotfix", "#Hotfix"), (r"patch notes?|patch\b", "#Patch"), (r"\bguide|\bguida", "#Guida"),
    (r"\bpvp\b|battleground|arena", "#PvP"), (r"\braid", "#Raid"), (r"dungeon", "#Dungeon"),
    (r"\bevent|\bevento", "#Evento"), (r"blue post|developer|devs?\b|interview", "#Blizzard"),
    (r"class|warrior|paladin|hunter|rogue|priest|shaman|mage|warlock|druid", "#Classi"),
    (r"legendary|leggendari", "#Leggendari"), (r"maintenance|server|outage|queue", "#Server"),
]


def tags_for(title: str):
    found = ["#WoWForever"]
    for pat, tag in TAGS:
        if re.search(pat, title, re.I) and tag not in found:
            found.append(tag)
    return " ".join(found[:4])


def translate(text: str) -> str:
    """Traduce in TARGET_LANG con Google Translate (gratuito). In caso di errore restituisce l'originale."""
    if not text or not TARGET_LANG:
        return text
    for attempt in range(3):
        try:
            r = requests.get(
                "https://translate.googleapis.com/translate_a/single",
                params={"client": "gtx", "sl": "auto", "tl": TARGET_LANG, "dt": "t", "q": text},
                headers={"User-Agent": UA}, timeout=15,
            )
            r.raise_for_status()
            data = r.json()
            if data[2] == TARGET_LANG:
                return text
            return "".join(part[0] for part in data[0] if part and part[0]) or text
        except Exception as ex:
            if attempt == 2:
                print(f"[warn] traduzione non riuscita, uso il testo originale: {ex}", file=sys.stderr)
                return text
            time.sleep(3 * (attempt + 1))


def find_image(e, body: str):
    """Cerca l'immagine dell'articolo: media RSS, enclosure o primo <img> nel testo."""
    for key in ("media_content", "media_thumbnail"):
        for m in e.get(key) or []:
            if m.get("url"):
                return m["url"]
    for enc in e.get("enclosures") or []:
        if enc.get("type", "").startswith("image") and enc.get("href"):
            return enc["href"]
    m = re.search(r'<img[^>]+src=["\']([^"\']+)', body or "")
    if m:
        u = html.unescape(m.group(1))
        return "https:" + u if u.startswith("//") else u
    return None


def is_forever(e) -> bool:
    hay = " ".join([e.get("title", ""), e.get("summary", ""), e.get("link", "")])
    return bool(KEYWORD.search(hay)) or "/forever/" in e.get("link", "")


def load_state():
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text())
    return {"initialized": False, "seen": []}


def collect():
    items = []
    for name, url, need_kw in FEEDS:
        try:
            r = requests.get(url, headers={"User-Agent": UA}, timeout=20)
            r.raise_for_status()
            feed = feedparser.parse(r.content)
        except Exception as ex:  # una fonte giù non blocca le altre
            print(f"[warn] {name}: {ex}", file=sys.stderr)
            continue
        for e in feed.entries:
            if not e.get("link") or not e.get("title"):
                continue
            if need_kw and not is_forever(e):
                continue
            ts = e.get("published_parsed") or e.get("updated_parsed")
            body = e.get("summary", "")
            if e.get("content"):
                body = max((c.get("value", "") for c in e.content), key=len, default=body)
            items.append({
                "source": name,
                "title": clean(e.title, 200),
                "link": e.link,
                "summary": clean_structured(body, SUMMARY_CHARS),
                "date": f"{ts.tm_mday} {MONTHS[ts.tm_mon - 1]} {ts.tm_year}" if ts else "",
                "tags": tags_for(e.title),
                "image": find_image(e, body),
                "ts": time.mktime(ts) if ts else 0,
            })
        print(f"[info] {name}: {len(feed.entries)} voci lette")
    items.sort(key=lambda i: i["ts"])  # dalla più vecchia alla più nuova
    return items


def parse_target(raw: str):
    """Restituisce (chat_id, topic_id) da @nome, -100..., o link t.me."""
    raw = raw.strip()
    topic = os.environ.get("TELEGRAM_TOPIC_ID", "").strip() or None
    m = re.match(r"(?:https?://)?t\.me/c/(\d+)(?:/(\d+))?(?:/\d+)?/?$", raw)
    if m:
        return "-100" + m.group(1), topic or m.group(2)
    m = re.match(r"(?:https?://)?t\.me/([A-Za-z0-9_]+)(?:/(\d+))?(?:/\d+)?/?$", raw)
    if m:
        return "@" + m.group(1), topic or m.group(2)
    return raw, topic


def build_text(item, limit):
    title = html.escape(translate(item["title"]), quote=False)
    meta = " · ".join(x for x in [f"🗓 {item['date']}" if item.get("date") else "", item.get("tags", "")] if x)
    summary = translate(item["summary"]) if item["summary"] else ""
    while True:
        text = f"<b>{title}</b>"
        if meta:
            text += f"\n<i>{html.escape(meta, quote=False)}</i>"
        if summary:
            text += f"\n\n<blockquote expandable>{html.escape(summary, quote=False)}</blockquote>"
        if len(re.sub(r"<[^>]+>", "", html.unescape(text))) <= limit or not summary:
            return text
        summary = summary[: max(0, len(summary) - 60)].rsplit(" ", 1)[0].rstrip() + " …"


def send(token, chat, item, topic=None):
    photo = item.get("image")
    text = build_text(item, 1000 if photo else 4000)
    if os.environ.get("DRY_RUN"):
        print("---" + (f"\n[foto] {photo}" if photo else "") + "\n" + text + f"\n[pulsante] {item['link']}")
        return True
    method = "sendPhoto" if photo else "sendMessage"
    payload = {
        "chat_id": chat,
        "parse_mode": "HTML",
        "reply_markup": {"inline_keyboard": [[{"text": f"📖 Leggi su {item['source']}", "url": item["link"]}]]},
    }
    if photo:
        payload.update(photo=photo, caption=text)
    else:
        payload.update(text=text, link_preview_options={"url": item["link"], "prefer_large_media": True,
                                                        "show_above_text": True})
    if topic:
        payload["message_thread_id"] = int(topic)
    for _ in range(4):
        r = requests.post(
            f"https://api.telegram.org/bot{token}/{method}", json=payload, timeout=20
        )
        if r.status_code == 400 and method == "sendPhoto" and "thread" not in r.text.lower():
            # immagine non valida per Telegram: invia solo il testo
            print(f"[warn] foto non accettata ({r.text}), invio senza immagine", file=sys.stderr)
            method = "sendMessage"
            payload.pop("photo"); payload["text"] = payload.pop("caption")
            continue
        if r.status_code == 400 and "thread not found" in r.text.lower() and topic:
            print(f"[warn] argomento {topic} non trovato, invio nel gruppo principale", file=sys.stderr)
            payload.pop("message_thread_id")
            topic = None
            continue
        if r.status_code == 429:
            time.sleep(r.json().get("parameters", {}).get("retry_after", 5) + 1)
            continue
        if not r.ok:
            print(f"[error] Telegram {r.status_code}: {r.text}", file=sys.stderr)
        return r.ok
    return False


def main():
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    chat, topic = parse_target(os.environ.get("TELEGRAM_CHANNEL", ""))
    if not os.environ.get("DRY_RUN") and not (token and chat):
        sys.exit("Mancano TELEGRAM_BOT_TOKEN e/o TELEGRAM_CHANNEL")
    print(f"[info] destinazione: chat {chat}" + (f", argomento {topic}" if topic else ""))
    if not os.environ.get("DRY_RUN"):
        r = requests.post(f"https://api.telegram.org/bot{token}/getChat", json={"chat_id": chat}, timeout=20)
        if not r.ok:
            sys.exit(
                f"[error] Il bot non riesce ad accedere alla chat {chat}: {r.text}\n"
                "Controlla che il bot sia stato aggiunto al gruppo/canale (meglio come amministratore) "
                "e che TELEGRAM_CHANNEL sia corretto."
            )
        print(f"[info] chat trovata: {r.json()['result'].get('title')}")

    state = load_state()
    seen = set(state["seen"])
    first_run = not state.get("initialized")
    new = []
    for it in collect():
        keys = {"u:" + norm_url(it["link"]), "t:" + norm_title(it["title"])}
        if keys & seen:
            continue
        seen |= keys
        new.append((it, keys))

    if first_run:
        # Primo avvio: pubblica solo le ultime FIRST_RUN_POSTS per non inondare il canale.
        to_post = new[-FIRST_RUN_POSTS:]
    else:
        to_post = new[-MAX_POSTS_PER_RUN:]

    posted, failed = 0, []
    for it, keys in to_post:
        if send(token, chat, it, topic):
            posted += 1
            time.sleep(3)
        else:
            failed.append(keys)
    print(f"[info] nuove: {len(new)}, pubblicate: {posted}, fallite: {len(failed)}")

    # Le news non inviate non vengono segnate come viste: riproverà al prossimo giro.
    skip = set().union(*failed) if failed else set()
    old = set(state["seen"])
    order = state["seen"] + [k for _, ks in new for k in sorted(ks) if k not in old and k not in skip]
    STATE_FILE.write_text(json.dumps({"initialized": state.get("initialized") or posted > 0 or not to_post,
                                      "seen": order[-MAX_SEEN:]}, indent=0))
    if failed:
        sys.exit(f"[error] {len(failed)} news non inviate, vedi gli errori sopra")


if __name__ == "__main__":
    main()
