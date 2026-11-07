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

FORUM = "https://us.forums.blizzard.com/en/wow"
TRACKER = f"{FORUM}/groups/blizzard-tracker/posts.json"
FOREVER_CATEGORIES = {346, 347, 348, 352}  # WoW: Forever e sottocategorie
UA = "Mozilla/5.0 (compatible; wow-forever-telegram-bot/1.0)"
HERE = Path(__file__).parent
LOGO_MIME = {".png": "image/png", ".webp": "image/webp", ".avif": "image/avif", ".jpg": "image/jpeg", ".jpeg": "image/jpeg"}
MAX_BODY_PX = 1200  # oltre questa altezza il testo sfuma e si rimanda al forum

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
.logo { margin-left: auto; height: 64px; width: auto; filter: drop-shadow(0 2px 6px rgba(0,0,0,.5)); }
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
.body.cut { max-height: __MAX__px; overflow: hidden; }
.fade { position: absolute; left: 0; right: 0; bottom: 0; height: 160px;
        background: linear-gradient(rgba(28,31,38,0), #1c1f26 85%); }
.more { color: #8fd0ff; font-size: 15px; font-weight: 600; text-align: center; padding: 0 0 18px; }
.foot { color: #6b7a90; font-size: 13px; padding: 10px 26px; border-top: 1px solid #2c3442; }
""".replace("__MAX__", str(MAX_BODY_PX))


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
        return ""
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


def render_png(page_html: str) -> bytes:
    from playwright.sync_api import sync_playwright
    with sync_playwright() as pw:
        exe = os.environ.get("BROWSER_PATH")
        try:
            browser = pw.chromium.launch(executable_path=exe) if exe else pw.chromium.launch(channel="chrome")
        except Exception:
            browser = pw.chromium.launch()
        page = browser.new_page(viewport={"width": 908, "height": 800}, device_scale_factor=2)
        page.set_content(page_html, wait_until="networkidle", timeout=30000)
        page.evaluate(f"""() => {{
            const b = document.getElementById('body');
            if (b.scrollHeight > {MAX_BODY_PX}) {{
                b.classList.add('cut');
                const f = document.createElement('div'); f.className = 'fade'; b.appendChild(f);
                const m = document.createElement('div'); m.className = 'more';
                m.textContent = 'Continua a leggere ↓'; b.after(m);
            }}
        }}""")
        png = page.locator(".card").screenshot(type="png")
        browser.close()
        return png


def render(item, months) -> bytes | None:
    try:
        return render_png(build_html(item, fetch_cooked(item), months))
    except Exception as ex:
        print(f"[warn] immagine del blue post {item['id']} non generata: {ex}", file=sys.stderr)
        return None
