"""Blue post (post dello staff Blizzard) dal forum ufficiale, resi come immagine."""
import base64
import html
import os
import re
import sys
import time
from datetime import datetime
from pathlib import Path

import requests
from html.parser import HTMLParser

FORUM = "https://us.forums.blizzard.com/en/wow"
TRACKER = f"{FORUM}/groups/blizzard-tracker/posts.json"
FOREVER_CATEGORIES = {346, 347, 348, 352}  # WoW: Forever e sottocategorie
UA = "Mozilla/5.0 (compatible; wow-forever-telegram-bot/1.0)"
HERE = Path(__file__).parent
LOGO_URL = os.environ.get("LOGO_URL") or (
    "https://blz-contentstack-images.akamaized.net/v3/assets/blt9c12f249ac15c7ec/"
    "blt527dd61848a757c7/6aa3316cad92093ee45628fd/camelot-logo-gamepage.png"
)
LOGO_MIME = {".png": "image/png", ".webp": "image/webp", ".avif": "image/avif", ".jpg": "image/jpeg", ".jpeg": "image/jpeg"}
PAGE_PX = 1150      # altezza massima (px CSS) di ogni immagine; i post lunghi diventano più immagini
MAX_PAGES = 10      # limite di Telegram per un album

CSS = """
* { box-sizing: border-box; }
body { margin: 0; padding: 24px; background: #0e1014; width: 860px;
       font-family: 'Open Sans', 'DejaVu Sans', sans-serif; }
.card { background: #1c1f26; border: 1px solid #2c3442; border-radius: 10px; overflow: hidden;
        box-shadow: 0 6px 24px rgba(0,0,0,.45); }
.head { display: flex; align-items: center; gap: 14px; padding: 16px 22px;
        background: linear-gradient(90deg, #0b2747 0%, #123d6c 60%, #0f3157 100%);
        border-bottom: 1px solid #1f4f86; }
.av { position: relative; width: 56px; height: 56px; flex: none; }
.logo + .badge { margin-left: 14px; }
.av .ini { position: absolute; inset: 0; border-radius: 50%; border: 2px solid #4fb3ff;
           background: radial-gradient(circle at 30% 30%, #2a7fd4, #0b2747); color: #fff;
           display: flex; align-items: center; justify-content: center; font-weight: 700; font-size: 26px; }
.av img { position: absolute; inset: 0; width: 56px; height: 56px; border-radius: 50%; border: 2px solid #4fb3ff; object-fit: cover; }
.who { display: flex; flex-direction: column; }
.name { color: #fff; font-weight: 700; font-size: 20px; }
.role { color: #8fd0ff; font-size: 14px; }
.logo { margin-left: auto; height: 78px; width: auto; filter: drop-shadow(0 2px 6px rgba(0,0,0,.5)); }
.badge { margin-left: auto; color: #0b2747; background: #4fb3ff; font-weight: 700; font-size: 12px;
         letter-spacing: .08em; padding: 5px 10px; border-radius: 999px; text-transform: uppercase; }
.title { color: #fff; font-size: 22px; font-weight: 700; padding: 18px 26px 0; line-height: 1.3; }
.body { color: #3fb2ff; font-size: 17px; line-height: 1.55; padding: 8px 26px 22px; position: relative; }
.body strong, .body b, .body h1, .body h2, .body h3, .body h4 { color: #fff; }
.body h1, .body h2, .body h3, .body h4 { font-size: 18px; margin: 18px 0 6px; }
.body p { margin: 10px 0; }
.body ul, .body ol { margin: 6px 0; padding-left: 24px; }
.body li { margin: 6px 0; }
.body li::marker { color: #6b7a90; }
.body a { color: #7fd0ff; text-decoration: none; }
.body hr { border: 0; border-top: 1px solid #2c3442; margin: 12px 0; }
.body img { max-width: 100%; height: auto; border-radius: 6px; }
.body img.emoji { width: 20px; height: 20px; vertical-align: -3px; }
.body blockquote, .body aside.quote { border-left: 3px solid #4a5568; margin: 10px 0; padding: 4px 14px; color: #c7ced9; }
.body .anchor, .body .lightbox-wrapper .meta { display: none; }
"""


def is_forever(p) -> bool:
    if p.get("category_id") in FOREVER_CATEGORIES:
        return True
    # post fuori categoria ma su Forever (es. note di sviluppo), esclusi gli articoli del blog
    return bool(re.search(r"\bforever\b", p.get("topic_title", ""), re.I)) and p.get("username") != "BlizzardEntertainment"


def fetch_blue_posts():
    """Restituisce i blue post su Forever, dal più vecchio al più nuovo."""
    try:
        r = requests.get(TRACKER, headers={"User-Agent": UA}, timeout=20)
        r.raise_for_status()
        posts = r.json().get("posts", [])
    except Exception as ex:
        print(f"[warn] forum Blizzard: {ex}", file=sys.stderr)
        return []
    print(f"[info] Forum Blizzard: {len(posts)} blue post letti")
    items = []
    for p in posts:
        if not is_forever(p):
            continue
        ts = datetime.strptime(p["created_at"][:19], "%Y-%m-%dT%H:%M:%S")
        items.append({
            "kind": "blue",
            "id": p["id"],
            "topic_id": p["topic_id"],
            "title": html.unescape(p.get("topic_title", "")),
            "author": p.get("name") or p.get("username"),
            "role": p.get("user_title") or "Blizzard",
            "avatar": FORUM.split("/en/")[0] + p["avatar_template"].replace("{size}", "120") if p.get("avatar_template", "").startswith("/") else p.get("avatar_template", "").replace("{size}", "120"),
            "link": f"{FORUM}/t/{p['topic_slug']}/{p['topic_id']}/{p['post_number']}",
            "wowhead": f"https://www.wowhead.com/forever/blue-tracker/topic/us/{p['topic_id']}",
            "ts": ts.timestamp(),
            "dt": ts,
            "excerpt": p.get("excerpt", ""),
        })
    items.sort(key=lambda i: i["ts"])
    return items


def fetch_cooked(item) -> str:
    try:
        r = requests.get(f"{FORUM}/posts/{item['id']}.json", headers={"User-Agent": UA}, timeout=20)
        r.raise_for_status()
        return r.json().get("cooked", "")
    except Exception as ex:
        print(f"[warn] testo completo del post {item['id']} non disponibile: {ex}", file=sys.stderr)
        return item.get("excerpt", "")


def sanitize(cooked: str) -> str:
    c = re.sub(r"(?is)<(script|iframe|style)[^>]*>.*?</\1>", "", cooked)
    c = re.sub(r"(?is)<a[^>]*class=\"anchor\"[^>]*>.*?</a>", "", c)
    c = re.sub(r"^\s*<hr\s*/?>", "", c)
    return c


def find_logo():
    """Cerca un file logo (logo.png/.webp/.avif/.jpg, o qualsiasi *logo*.*) nella radice o in assets/."""
    for folder in (HERE / "assets", HERE):
        if not folder.is_dir():
            continue
        for f in sorted(folder.iterdir()):
            if f.suffix.lower() in LOGO_MIME and "logo" in f.name.lower():
                return f
    return None


def logo_tag() -> str:
    f = find_logo()
    if not f:
        # nessun file locale: usa il logo online (se non carica, l'immagine viene nascosta)
        return f'<img class="logo" src="{html.escape(LOGO_URL, quote=True)}" onerror="this.remove()">' if LOGO_URL else ""
    data = base64.b64encode(f.read_bytes()).decode()
    return f'<img class="logo" src="data:{LOGO_MIME[f.suffix.lower()]};base64,{data}">'


def build_html(item, cooked: str, months) -> str:
    d = item["dt"]
    date = f"{d.day} {months[d.month - 1]} {d.year}"
    return f"""<!doctype html><html><head><meta charset="utf-8">
<base href="{FORUM.split('/en/')[0]}/">
<link href="https://fonts.googleapis.com/css2?family=Open+Sans:wght@400;600;700&display=swap" rel="stylesheet">
<style>{CSS}</style></head><body><div class="card">
<div class="head"><div class="av"><div class="ini">{html.escape((item['author'] or 'B')[:1].upper())}</div><img src="{html.escape(item['avatar'], quote=True)}" onerror="this.remove()"></div>
<div class="who"><span class="name">{html.escape(item['author'])}</span><span class="role">{html.escape(item['role'])}</span></div>
{logo_tag()}<span class="badge">Blue post</span></div>
<div class="title">{html.escape(item['title'])}</div>
<div class="body" id="body">{sanitize(cooked)}</div>
<div class="foot">WoW: Forever · Blue post · {date}</div>
</div></body></html>"""


def render_pages(page_html: str) -> list[bytes]:
    """Renderizza la card e la divide in più immagini senza spezzare le righe di testo."""
    from playwright.sync_api import sync_playwright
    with sync_playwright() as pw:
        exe = os.environ.get("BROWSER_PATH")
        try:
            browser = pw.chromium.launch(executable_path=exe) if exe else pw.chromium.launch(channel="chrome")
        except Exception:
            browser = pw.chromium.launch()
        page = browser.new_page(viewport={"width": 908, "height": 800}, device_scale_factor=2)
        page.set_content(page_html, wait_until="networkidle", timeout=30000)
        info = page.evaluate("""() => {
            const card = document.querySelector('.card').getBoundingClientRect();
            const rects = [];
            const walker = document.createTreeWalker(document.getElementById('body'), NodeFilter.SHOW_TEXT);
            while (walker.nextNode()) {
                const n = walker.currentNode;
                if (!n.textContent.trim()) continue;
                const r = document.createRange(); r.selectNodeContents(n);
                for (const c of r.getClientRects()) if (c.height > 0) rects.push([c.top + scrollY, c.bottom + scrollY]);
            }
            document.querySelectorAll('#body img').forEach(i => {
                const c = i.getBoundingClientRect(); if (c.height > 0) rects.push([c.top + scrollY, c.bottom + scrollY]);
            });
            return {top: card.top + scrollY, bottom: card.bottom + scrollY, left: card.left, width: card.width, rects};
        }""")
        top, bottom = info["top"], info["bottom"]
        rects = sorted(info["rects"])
        # punti di taglio sicuri: spazi tra righe che nessun elemento attraversa
        safe, reach = [], None
        for t, b in rects:
            if reach is not None and t > reach:
                safe.append((reach + t) / 2)
            reach = b if reach is None else max(reach, b)
        cuts, start = [top], top
        while bottom - start > PAGE_PX:
            options = [y for y in safe if start + PAGE_PX * 0.5 < y <= start + PAGE_PX]
            y = max(options) if options else start + PAGE_PX
            cuts.append(y)
            start = y
            if len(cuts) > MAX_PAGES:  # troppo lungo per un album: il resto si legge dai link
                print(f"[info] post molto lungo: mostrate solo le prime {MAX_PAGES} immagini", file=sys.stderr)
                break
        else:
            cuts.append(bottom)
        pngs = []
        for a, b in zip(cuts, cuts[1:]):
            pngs.append(page.screenshot(type="png", full_page=True,
                                        clip={"x": info["left"], "y": a, "width": info["width"], "height": b - a}))
        browser.close()
        return pngs


def render(item, months) -> list[bytes]:
    try:
        return render_pages(build_html(item, item_cooked(item), months))
    except Exception as ex:
        print(f"[warn] immagine del blue post {item['id']} non generata: {ex}", file=sys.stderr)
        return []


def item_cooked(item) -> str:
    if "cooked" not in item:
        item["cooked"] = fetch_cooked(item)
    return item["cooked"]


class _Summary(HTMLParser):
    """Converte l'HTML del post in testo per Telegram con punti e sottopunti."""

    def __init__(self):
        super().__init__()
        self.lines, self.cur, self.depth, self.bold, self.skip = [], "", 0, 0, 0

    def flush(self, prefix=""):
        t = re.sub(r"\s+", " ", self.cur).strip()
        if t and t not in ("<b></b>",):
            self.lines.append(prefix + t)
        self.cur = ""

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style", "aside", "figure"):
            self.skip += 1
        elif tag in ("ul", "ol"):
            self.flush(self._prefix()); self.depth += 1
        elif tag == "li":
            self.flush(self._prefix())
        elif tag in ("p", "div", "h1", "h2", "h3", "h4", "br", "hr"):
            self.flush(self._prefix())
        if tag in ("strong", "b", "h1", "h2", "h3", "h4") and not self.skip:
            self.cur += "<b>"; self.bold += 1

    def handle_endtag(self, tag):
        if tag in ("script", "style", "aside", "figure"):
            self.skip = max(0, self.skip - 1)
            return
        if tag in ("strong", "b", "h1", "h2", "h3", "h4") and self.bold:
            self.cur += "</b>"; self.bold -= 1
        if tag in ("ul", "ol"):
            self.flush(self._prefix()); self.depth = max(0, self.depth - 1)
        elif tag in ("li", "p", "div", "h1", "h2", "h3", "h4"):
            self.flush(self._prefix())

    def handle_data(self, data):
        if not self.skip:
            self.cur += html.escape(data, quote=False)

    def _prefix(self):
        return "" if self.depth == 0 else ("• " if self.depth == 1 else "    ◦ ")


def summary(item, limit=650) -> str:
    """Riassunto del post (HTML Telegram) che sta in `limit` caratteri visibili."""
    p = _Summary()
    p.feed(sanitize(item_cooked(item)))
    p.flush()
    lines = [re.sub(r"<b>\s*</b>", "", l) for l in p.lines]
    lines = [l for l in lines if re.sub(r"<[^>]+>|[•◦\s]", "", l)]
    out, used = [], 0
    for l in lines:
        n = len(html.unescape(re.sub(r"<[^>]+>", "", l))) + 1
        if used + n > limit:
            room = limit - used - 2
            if room > 60 and not out[-1:] == [""]:
                plain = re.sub(r"<[^>]+>", "", l)
                out.append(plain[:room].rsplit(" ", 1)[0] + "…")
            else:
                out.append("…")
            break
        out.append(l)
        used += n
    return "\n".join(out)
