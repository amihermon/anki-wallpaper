#!/usr/bin/env python3
"""Render an Anki habit-tracker wallpaper (PNG) from an Anki collection.

Usage:
  python anki_wallpaper.py --sync --out out            # download from AnkiWeb, then render
  python anki_wallpaper.py --collection path/to/collection.anki2 --out out

AnkiWeb login comes from the ANKI_USERNAME and ANKI_PASSWORD environment variables.
The collection is only ever downloaded, never uploaded, so your AnkiWeb data is not changed.
"""

from __future__ import annotations

import argparse
import base64
import calendar
import html
import json
import mimetypes
import os
import random
import re
import shutil
import subprocess
import sys
import tempfile
from collections import Counter
from datetime import date, datetime, timedelta
from glob import glob
from pathlib import Path
from zoneinfo import ZoneInfo

HERE = Path(__file__).resolve().parent

DEFAULTS = {
    "timezone": "UTC",
    "width": 1080,
    "height": 2392,
    "top_space": 250,
    "tracker": "year",
    "words_label": "Words learned",
    "stats_search": "",
    "quiz_search": "-is:new -is:suspended",
    "background_image": "background.jpg",
    "background_dim": 0.78,
    "colors": {},
}


# ---------------------------------------------------------------- config

def load_config(path: Path) -> dict:
    cfg = json.loads(json.dumps(DEFAULTS))
    if path.exists():
        user = json.loads(path.read_text(encoding="utf-8"))
        cfg.update({k: v for k, v in user.items() if k != "colors"})
        cfg["colors"].update(user.get("colors", {}))
    return cfg


# ---------------------------------------------------------------- AnkiWeb

def download_collection(col_path: Path, username: str, password: str):
    """Create an empty collection and fill it with a full download from AnkiWeb."""
    from anki.collection import Collection
    from anki.sync_pb2 import SyncCollectionResponse as R

    if col_path.exists():
        col_path.unlink()
    col_path.parent.mkdir(parents=True, exist_ok=True)
    col = Collection(str(col_path))
    try:
        auth = col.sync_login(username=username, password=password, endpoint=None)
    except Exception as e:  # noqa: BLE001
        col.close()
        raise SystemExit(
            f"Could not log in to AnkiWeb: {e}\n"
            "If this mentions your username or password, re-check the ANKI_USERNAME and ANKI_PASSWORD secrets."
        )

    # A brand-new local collection never matches the server's schema, so this
    # only exchanges metadata and reports that a full download is needed.
    out = col.sync_collection(auth, sync_media=False)
    if out.server_message:
        print("AnkiWeb says:", out.server_message)
    if out.new_endpoint:
        auth.endpoint = out.new_endpoint

    if out.required in (R.FULL_DOWNLOAD, R.FULL_SYNC):
        col.close_for_full_sync()
        col.full_upload_or_download(auth=auth, server_usn=None, upload=False)
        col.reopen(after_full_sync=True)
    elif out.required == R.FULL_UPLOAD:
        col.close()
        raise SystemExit("Your AnkiWeb account has no collection yet. Sync from AnkiDroid or Anki first.")
    print(f"Downloaded collection: {col.card_count()} cards")
    return col


def open_collection(path: Path):
    from anki.collection import Collection

    # Work on a copy so the original file is never touched.
    tmp = Path(tempfile.mkdtemp()) / "collection.anki2"
    shutil.copy(path, tmp)
    return Collection(str(tmp))


# ---------------------------------------------------------------- text helpers

ANSWER_HR = re.compile(r"<hr[^>]*id\s*=\s*[\"']?answer[\"']?[^>]*>", re.I)


def clean_html(s: str) -> str:
    s = re.sub(r"(?is)<(style|script)[^>]*>.*?</\1>", "", s)
    s = re.sub(r"\[sound:[^\]]*\]", "", s)
    s = re.sub(r"\[anki:play:[^\]]*\]", "", s)
    s = re.sub(r"(?is)\[anki:[^\]]*\].*?\[/anki:[^\]]*\]", "", s)
    s = re.sub(r"(?is)<audio[^>]*>.*?</audio>", "", s)
    s = re.sub(r"(?i)<br\s*/?>|</(div|p|li|tr|h\d)>", "\n", s)
    s = re.sub(r"<[^>]+>", "", s)
    s = html.unescape(s).replace("\xa0", " ")
    lines = [re.sub(r"[ \t]+", " ", ln).strip() for ln in s.split("\n")]
    return "\n".join(ln for ln in lines if ln)


def shorten(s: str, limit: int) -> str:
    s = " / ".join(s.split("\n"))
    return s if len(s) <= limit else s[: limit - 1].rstrip() + "…"


AUDIO = re.compile(r"\[anki:play:q|\[sound:|<audio", re.I)


def card_texts(col, cid: int, use_fields: bool = False) -> tuple[str, str] | None:
    """Front and back text for a card.

    Cards whose front is audio (listening cards) are skipped, because a sound
    can't be shown on a wallpaper. With use_fields=True the note's own text
    fields are used instead of the rendered card.
    """
    card = col.get_card(cid)
    front = back = ""
    if not use_fields:
        try:
            r = card.render_output()
            if AUDIO.search(r.question_text):
                return None
            front = clean_html(r.question_text)
            parts = ANSWER_HR.split(r.answer_text, maxsplit=1)
            back = clean_html(parts[1] if len(parts) > 1 else r.answer_text)
            if len(parts) == 1 and back.startswith(front):
                back = back[len(front):].strip()
        except Exception:  # noqa: BLE001
            pass
    if not front or not back:
        # Ignore fields that hold audio (and the "Listen..." prompt that goes with it).
        fields = [clean_html(f) for f in card.note().fields if not AUDIO.search(f)]
        fields = [f for f in fields if f]
        if len(fields) >= 2:
            front, back = front or fields[0], back or fields[1]
        elif len(fields) == 1 and "\n" in fields[0]:
            first, rest = fields[0].split("\n", 1)
            front, back = front or first, back or rest
    if not front or not back:
        return None
    return shorten(front, 110), shorten(back, 120)


def pick_quiz(col, search: str, rng: random.Random):
    try:
        cids = list(col.find_cards(search or "-is:new -is:suspended"))
    except Exception as e:  # noqa: BLE001
        print(f"Quiz search failed ({e}); using all learned cards.")
        cids = list(col.find_cards("-is:new -is:suspended"))
    rng.shuffle(cids)
    # Prefer cards whose front is text; fall back to note fields for audio-only decks.
    for use_fields in (False, True):
        for cid in cids[:60]:
            t = card_texts(col, cid, use_fields)
            if t:
                return {"front": t[0], "back": t[1], "cid": cid}
    return None


# ---------------------------------------------------------------- stats

def fmt_int(n: int) -> str:
    return f"{n:,}"


def compute(col, cfg: dict, now: datetime, prev_state: dict, rng: random.Random) -> tuple[dict, dict]:
    tz = ZoneInfo(cfg["timezone"])
    now = now.astimezone(tz)
    rollover = int(col.get_config("rollover", 4) or 0)

    def study_day(ms: int) -> date:
        return (datetime.fromtimestamp(ms / 1000, tz) - timedelta(hours=rollover)).date()

    today = (now - timedelta(hours=rollover)).date()

    search = (cfg.get("stats_search") or "").strip()
    allowed = set(col.find_cards(search)) if search else None

    def scoped(sql_cards_where: str) -> str:
        if allowed is None:
            return sql_cards_where
        ids = ",".join(str(i) for i in allowed) or "0"
        return f"({sql_cards_where}) and id in ({ids})"

    per_day: Counter = Counter()
    total_ms = 0
    total_reviews = 0
    recent_rev = recent_pass = 0
    cutoff_30 = (now - timedelta(days=30)).timestamp() * 1000
    for rid, cid, ease, rtype, taken in col.db.execute(
        "select id, cid, ease, type, time from revlog where ease > 0 and type in (0,1,2,3)"
    ):
        if allowed is not None and cid not in allowed:
            continue
        per_day[study_day(rid)] += 1
        total_ms += max(0, min(taken, 600000))
        total_reviews += 1
        if rtype == 1 and rid >= cutoff_30:
            recent_rev += 1
            recent_pass += ease > 1

    studied = set(per_day)
    first_day = min(studied) if studied else today
    studied_today = today in studied
    reviews_today = per_day.get(today, 0)

    # Current streak counts today if done, otherwise runs through yesterday.
    d = today if studied_today else today - timedelta(days=1)
    streak = 0
    while d in studied:
        streak += 1
        d -= timedelta(days=1)

    best = run = 0
    prev = None
    for day in sorted(studied):
        run = run + 1 if prev and (day - prev).days == 1 else 1
        best = max(best, run)
        prev = day

    learned = col.db.scalar(f"select count(distinct nid) from cards where {scoped('type != 0')}") or 0
    mastered = col.db.scalar(f"select count(distinct nid) from cards where {scoped('ivl >= 21')}") or 0
    new_week_q = "introduced:7" + (f" ({search})" if search else "")
    try:
        new_week = len(col.find_notes(new_week_q))
    except Exception:  # noqa: BLE001
        new_week = 0
    due_q = "is:due -is:suspended -is:buried" + (f" ({search})" if search else "")
    due = len(col.find_cards(due_q))

    # ---- tracker months
    if cfg.get("tracker") == "rolling":
        months = []
        y, m = today.year, today.month
        for _ in range(12):
            months.append((y, m))
            y, m = (y - 1, 12) if m == 1 else (y, m - 1)
        months.reverse()
    else:
        months = [(today.year, m) for m in range(1, 13)]

    month_rows = []
    for (y, m) in months:
        ndays = calendar.monthrange(y, m)[1]
        codes = []
        for dd in range(1, 32):
            if dd > ndays:
                codes.append(0)
                continue
            day = date(y, m, dd)
            if day == today:
                codes.append(5 if studied_today else 4)
            elif day > today or day < first_day:
                codes.append(1)
            else:
                codes.append(3 if day in studied else 2)
        name = calendar.month_abbr[m]
        month_rows.append({"name": name, "days": codes, "current": (y, m) == (today.year, today.month)})

    span_start = max(date(months[0][0], months[0][1], 1), first_day)
    span_days = max(0, (today - span_start).days + 1)
    span_done = sum(1 for d in studied if span_start <= d <= today)
    range_label = f"in {today.year}" if cfg.get("tracker") != "rolling" else "in the last 12 months"
    month_start = max(today.replace(day=1), first_day)
    month_days = (today - month_start).days + 1
    month_done = sum(1 for d in studied if month_start <= d <= today)
    plural = "day" if span_done == 1 else "days"
    tracker_foot = (
        f"<b>{month_done}</b> of {month_days} days so far in {today:%B}. "
        f"{span_done} study {plural} {range_label}."
    )

    # ---- motivation lines
    if streak == 0:
        streak_word = "days in a row"
    elif streak == 1:
        streak_word = "day in a row"
    else:
        streak_word = "days in a row"

    if best and streak == best and streak >= 3 and studied_today:
        streak_sub = '<span class="flag">Personal best.</span> Keep it going.'
    elif best:
        streak_sub = f"Longest run: {best} days. {fmt_int(len(studied))} study days total."
    else:
        streak_sub = "Your first study day starts the chain."

    if studied_today and due == 0:
        today_line = f"All done for today. {fmt_int(reviews_today)} reviews in the book."
    elif studied_today:
        today_line = f"{fmt_int(reviews_today)} reviews done today, {fmt_int(due)} still due."
    elif due and streak:
        today_line = f"{fmt_int(due)} cards waiting. Study today to make it {streak + 1} days in a row."
    elif due:
        today_line = f"{fmt_int(due)} cards waiting. Today is a good day to start a streak."
    elif streak:
        today_line = f"Nothing due yet. Learn a few new cards to make it {streak + 1} days."
    else:
        today_line = "Nothing due. Learn a few new cards to start a streak."

    hours = total_ms / 3_600_000
    totals = [
        {"value": fmt_int(learned), "label": cfg.get("words_label") or "Words learned"},
        {"value": fmt_int(mastered), "label": "Mastered"},
        {"value": fmt_int(new_week), "label": "New this week"},
        {"value": fmt_int(total_reviews), "label": "Reviews"},
        {"value": ("0" if hours < 0.05 else f"{hours:.1f}" if hours < 10 else fmt_int(round(hours))), "label": "Hours studied"},
        {"value": (f"{round(100 * recent_pass / recent_rev)}%" if recent_rev else "n/a"), "label": "Recall, 30 days"},
    ]

    # ---- quiz
    quiz = pick_quiz(col, cfg.get("quiz_search", ""), rng)
    last = prev_state.get("quiz") if isinstance(prev_state, dict) else None
    if last and (AUDIO.search(last.get("front", "")) or not last.get("back")):
        last = None
    if last and quiz and last.get("cid") == quiz.get("cid"):
        quiz = pick_quiz(col, cfg.get("quiz_search", ""), rng) or quiz

    data = {
        "w": int(cfg["width"]),
        "h": int(cfg["height"]),
        "top": int(cfg["top_space"]),
        "colors": cfg.get("colors", {}),
        "dateLabel": f"{now:%A} {now.day} {now:%B}",
        "streak": streak,
        "streakWord": streak_word,
        "streakSub": streak_sub,
        "todayLine": today_line,
        "months": month_rows,
        "trackerFoot": tracker_foot,
        "totals": totals,
        "quiz": {"front": quiz["front"]} if quiz else None,
        "last": {"front": last["front"], "back": last["back"]} if last and last.get("front") else None,
        "synced": f"Updated {now.day} {now:%b}, {now:%H:%M}. Refreshes every couple of hours.",
    }
    state = {
        "updated": now.isoformat(),
        "quiz": quiz,
        "streak": streak,
        "best": best,
        "studied_today": studied_today,
        "reviews_today": reviews_today,
        "due": due,
    }
    return data, state


# ---------------------------------------------------------------- rendering

def data_uri(path: Path) -> str:
    mime = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    return f"data:{mime};base64," + base64.b64encode(path.read_bytes()).decode()


def inline_fonts() -> str:
    css_path = HERE / "fonts" / "fonts.css"
    if not css_path.exists():
        return ""
    css = css_path.read_text(encoding="utf-8")

    def repl(m: re.Match) -> str:
        f = HERE / "fonts" / m.group(1)
        return f"url({data_uri(f)})" if f.exists() else m.group(0)

    return re.sub(r"url\(([^)]+\.woff2)\)", repl, css)


def find_chrome() -> str:
    cands = [os.environ.get("CHROME_BIN", "")]
    cands += [shutil.which(n) or "" for n in ("google-chrome", "google-chrome-stable", "chromium", "chromium-browser", "chrome")]
    cands += sorted(glob("/opt/pw-browsers/chromium-*/chrome-linux*/chrome"))
    cands += sorted(glob(os.path.expanduser("~/.cache/ms-playwright/chromium-*/chrome-linux*/chrome")))
    for c in cands:
        if c and os.path.exists(c):
            return c
    raise SystemExit("No Chrome or Chromium found. Set CHROME_BIN to its path.")


def render(data: dict, cfg: dict, out_dir: Path) -> Path:
    bg = HERE / (cfg.get("background_image") or "")
    if cfg.get("background_image") and bg.is_file():
        data["background"] = data_uri(bg)
        data["backgroundDim"] = float(cfg.get("background_dim", 0.78))

    page = (HERE / "template.html").read_text(encoding="utf-8")
    page = page.replace("/*__FONTS__*/", inline_fonts())
    blob = json.dumps(data, ensure_ascii=False).replace("</", "<\\/")
    page = page.replace("__DATA__", blob)

    out_dir.mkdir(parents=True, exist_ok=True)
    html_path = out_dir / "wallpaper.html"
    html_path.write_text(page, encoding="utf-8")
    png = out_dir / "wallpaper.png"
    raw = out_dir / "_raw.png"

    # Headless Chrome's viewport is a little shorter than its window, so render
    # into a taller window and crop to the exact wallpaper size afterwards.
    with tempfile.TemporaryDirectory() as profile:
        cmd = [
            find_chrome(), "--headless=new", "--no-sandbox", "--disable-gpu", "--hide-scrollbars",
            "--force-device-scale-factor=1", f"--window-size={data['w']},{data['h'] + 300}",
            "--virtual-time-budget=4000", f"--user-data-dir={profile}",
            f"--screenshot={raw}", html_path.resolve().as_uri(),
        ]
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    if not raw.exists():
        print(res.stdout, res.stderr, file=sys.stderr)
        raise SystemExit("Chrome did not produce a screenshot.")

    from PIL import Image

    with Image.open(raw) as im:
        im.convert("RGB").crop((0, 0, data["w"], data["h"])).save(png, optimize=True)
    raw.unlink()
    return png


# ---------------------------------------------------------------- main

def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("--sync", action="store_true", help="download the collection from AnkiWeb")
    src.add_argument("--collection", type=Path, help="path to a local collection.anki2")
    ap.add_argument("--out", type=Path, default=HERE / "out")
    ap.add_argument("--config", type=Path, default=HERE / "config.json")
    ap.add_argument("--prev-state", type=Path, help="state.json from the previous run (for the last quiz answer)")
    ap.add_argument("--now", help="pretend the current time is this ISO timestamp (testing)")
    ap.add_argument("--seed", type=int, help="random seed for the quiz card (testing)")
    args = ap.parse_args()

    cfg = load_config(args.config)
    tz = ZoneInfo(cfg["timezone"])
    now = datetime.fromisoformat(args.now).astimezone(tz) if args.now else datetime.now(tz)
    rng = random.Random(args.seed)

    prev_state = {}
    if args.prev_state and args.prev_state.exists():
        try:
            prev_state = json.loads(args.prev_state.read_text(encoding="utf-8") or "{}")
        except json.JSONDecodeError:
            prev_state = {}

    if args.sync:
        user, pw = os.environ.get("ANKI_USERNAME"), os.environ.get("ANKI_PASSWORD")
        if not user or not pw:
            raise SystemExit("Set ANKI_USERNAME and ANKI_PASSWORD (GitHub repository secrets).")
        col = download_collection(Path(tempfile.mkdtemp()) / "collection.anki2", user, pw)
    else:
        col = open_collection(args.collection)

    try:
        data, state = compute(col, cfg, now, prev_state, rng)
    finally:
        col.close()

    png = render(data, cfg, args.out)
    (args.out / "state.json").write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Wrote {png} (streak {state['streak']}, {state['due']} due)")


if __name__ == "__main__":
    main()
