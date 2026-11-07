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
    ("Warcraft Tavern", "https://www.warcrafttavern.com/feed/", True),
    ("Blizzard", "https://news.blizzard.com/en-us/rss/world-of-warcraft", True),
    ("Google News", "https://news.google.com/rss/search?q=%22World+of+Warcraft:+Forever%22+OR+%22WoW+Forever%22&hl=en-US&gl=US&ceid=US:en", True),
    ("Google News IT", "https://news.google.com/rss/search?q=%22WoW+Forever%22+OR+%22World+of+Warcraft:+Forever%22&hl=it&gl=IT&ceid=IT:it", True),
]

KEYWORD = re.compile(r"\bforever\b", re.I)
STATE_FILE = Path(__file__).with_name("seen.json")
MAX_SEEN = 2000          # quante chiavi ricordare
MAX_POSTS_PER_RUN = 10   # evita di inondare il canale
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
            items.append({
                "source": name,
                "title": clean(e.title, 200),
                "link": e.link,
                "summary": "" if name.startswith("Google") else clean(e.get("summary", "")),
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


def send(token, chat, item, topic=None):
    text = f"<b>{html.escape(item['title'])}</b>"
    if item["summary"]:
        text += f"\n\n{html.escape(item['summary'])}"
    text += f"\n\n🔗 <a href=\"{html.escape(item['link'], quote=True)}\">{html.escape(item['source'])}</a>"
    if os.environ.get("DRY_RUN"):
        print("---\n" + text)
        return True
    payload = {"chat_id": chat, "text": text, "parse_mode": "HTML"}
    if topic:
        payload["message_thread_id"] = int(topic)
    for _ in range(3):
        r = requests.post(
            f"https://api.telegram.org/bot{token}/sendMessage", json=payload, timeout=20
        )
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
        # Primo avvio: pubblica solo le ultime 3 per non inondare il canale.
        to_post = new[-3:]
    else:
        to_post = new[-MAX_POSTS_PER_RUN:]

    posted = 0
    for it, _ in to_post:
        if send(token, chat, it, topic):
            posted += 1
            time.sleep(3)
    print(f"[info] nuove: {len(new)}, pubblicate: {posted}")

    order = state["seen"] + [k for _, ks in new for k in sorted(ks) if k not in state["seen"]]
    STATE_FILE.write_text(json.dumps({"initialized": True, "seen": order[-MAX_SEEN:]}, indent=0))


if __name__ == "__main__":
    main()
