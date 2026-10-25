#!/usr/bin/env python3
"""Helpers for the posts-like-this skill: fetch candidate posts with live
numbers, search Reddit and Hacker News, and remember what a profile has
already judged so no post is shown twice.

Usage:
  posts.py x <url>... [--profile DIR] [--max-age DAYS] [--chars N]
      Fetch X posts through fxtwitter: author, followers, age, metrics, text.
      With --profile, posts already in DIR/seen.jsonl are skipped, and posts
      older than --max-age (or deleted) are recorded so they aren't refetched.
  posts.py reddit <sub>[,<sub>...] <query> [--days N] [--profile DIR] [--chars N]
      Search subreddits (newest first) through Reddit's RSS, with post text.
  posts.py hn <query> [--days N] [--profile DIR] [--chars N]
      Search Hacker News stories through Algolia.
  posts.py read <url>...
      Read X, Reddit or HN posts in full: the author's whole X thread, X
      Articles with their links, and every outbound link in a Reddit post.
  posts.py mark DIR match|maybe|no <url>... [--note TEXT]
      Record verdicts. The latest verdict for a post wins.
  posts.py seen DIR
      Count verdicts and show the date of the last mark.

Run with python3 -I. Uses curl, not urllib: python.org builds on macOS often
lack CA certs, while curl uses the system keychain.
"""
import datetime as dt
import html
import json
import re
import subprocess
import sys
import time
import urllib.parse
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

UA_API = "Mozilla/5.0 (posts-like-this skill for Claude Code)"
# Reddit's RSS answers 403 to unknown agents; a browser UA gets 200.
UA_BROWSER = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 14_0) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/126 Safari/537.36")
STATUS_RE = re.compile(
    r"(?:twitter|x|fxtwitter|fixupx|vxtwitter|fixvx)\.com/"
    r"(?:i/web/|i/|[A-Za-z0-9_]{1,15}/)status(?:es)?/(\d+)")
ARTICLE_RE = re.compile(r"x\.com/(?:i|[A-Za-z0-9_]{1,15})/articles?/(\d+)")
REDDIT_RE = re.compile(r"reddit\.com/r/[^/]+/comments/(\w+)")
HN_RE = re.compile(r"news\.ycombinator\.com/item\?id=(\d+)")
ATOM = {"a": "http://www.w3.org/2005/Atom"}
NOW = dt.datetime.now(dt.timezone.utc)


def curl(url, ua=UA_API):
    """Return (http_code, body). Code 0 means curl itself failed."""
    try:
        p = subprocess.run(["curl", "-sS", "-m", "25", "-A", ua, "-w", "\n%{http_code}", url],
                           capture_output=True, text=True, timeout=30)
    except Exception as e:
        return 0, str(e)
    if p.returncode != 0:
        return 0, p.stderr.strip() or f"curl exit {p.returncode}"
    body, _, code = p.stdout.rpartition("\n")
    return int(code or 0), body


def key(url):
    """A stable id per post, so the same post found twice is one post."""
    for prefix, rx in (("x", STATUS_RE), ("reddit", REDDIT_RE), ("hn", HN_RE)):
        m = rx.search(url)
        if m:
            return f"{prefix}:{m.group(1)}"
    u = urllib.parse.urlsplit(url.strip())
    return f"url:{u.netloc.lower().removeprefix('www.')}{u.path.rstrip('/')}"


# --- seen.jsonl -------------------------------------------------------------

def load_seen(profile):
    seen = {}
    if not profile:
        return seen
    path = Path(profile) / "seen.jsonl"
    if path.exists():
        for line in path.read_text().splitlines():
            if line.strip():
                rec = json.loads(line)
                seen[rec["key"]] = rec
    return seen


def append_seen(profile, records):
    if not profile or not records:
        return
    path = Path(profile) / "seen.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a") as f:
        for r in records:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


def seen_record(url, verdict, note=""):
    rec = {"key": key(url), "url": url, "verdict": verdict, "date": NOW.date().isoformat()}
    if note:
        rec["note"] = note
    return rec


# --- formatting -------------------------------------------------------------

def num(n):
    if n is None:
        return "?"
    n = int(n)
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f}M"
    if n >= 10_000:
        return f"{n / 1000:.0f}k"
    if n >= 1000:
        return f"{n / 1000:.1f}k"
    return str(n)


def age(when):
    days = (NOW - when).total_seconds() / 86400
    if days < 1:
        return f"{max(1, round(days * 24))}h ago"
    return f"{days:.0f}d ago"


def clip(text, chars):
    text = re.sub(r"\s+", " ", text or "").strip()
    return text if len(text) <= chars else text[:chars].rstrip() + "…"


# --- X ----------------------------------------------------------------------

class MirrorDown(Exception):
    """fxtwitter itself failed, so the post may be fine; don't record it as gone."""


def fetch_status(sid):
    code, body = curl(f"https://api.fxtwitter.com/2/status/{sid}")
    try:
        data = json.loads(body)
    except ValueError:
        return None, MirrorDown(f"HTTP {code}: {body[:120]}")
    s = data.get("status")
    if data.get("code") != 200 or not s or s.get("type") == "tombstone":
        if data.get("code", 0) >= 500:
            return None, MirrorDown(f"code {data.get('code')}")
        return None, (s or {}).get("reason") or data.get("message") or f"code {data.get('code')}"
    return s, None


def status_links(s):
    links = []
    for f in (s.get("raw_text") or {}).get("facets") or []:
        if f.get("type") == "url":
            u = f.get("replacement") or f.get("original")
            if u and u not in links:
                links.append(u)
    return links


def render_status(i, s, chars):
    a = s.get("author") or {}
    when = dt.datetime.fromtimestamp(s.get("created_timestamp", 0), dt.timezone.utc)
    kind = ("Article" if s.get("article") else "reply" if s.get("replying_to")
            else "quote" if s.get("quote") else "post")
    views, saves = s.get("views"), s.get("bookmarks")
    per_k = f" ({saves / views * 1000:.1f} per 1k views)" if views and saves is not None else ""
    lines = [
        f"[{i}] {s.get('url')}",
        f"    @{a.get('screen_name')} ({a.get('name')}) · {num(a.get('followers'))} followers"
        f" · {age(when)} ({when.date()}) · {kind}",
        f"    views {num(views)} · likes {num(s.get('likes'))} · reposts {num(s.get('reposts'))}"
        f" · replies {num(s.get('replies'))} · saves {num(saves)}{per_k}",
    ]
    art = s.get("article")
    if art:
        lines.append(f"    title: {art.get('title')}")
        lines.append(f"    article: {clip(art.get('preview_text'), chars)}")
    text = re.sub(r"https://x\.com/i/article/\d+", "", s.get("text") or "").strip()
    if text:
        lines.append(f"    text: {clip(text, chars)}")
    links = [u for u in status_links(s) if "x.com/i/article/" not in u]
    if links:
        lines.append("    links: " + "  ".join(links[:4]))
    q = s.get("quote")
    if q and q.get("type") != "tombstone":
        qa = (q.get("author") or {}).get("screen_name")
        qtitle = (q.get("article") or {}).get("title")
        qtext = f"Article \"{qtitle}\"" if qtitle else clip(q.get("text"), 160)
        lines.append(f"    quoting @{qa}: {qtext}")
    return "\n".join(lines), when


def cmd_x(urls, profile, max_age, chars):
    seen = load_seen(profile)
    todo, notes, dupes = {}, [], 0
    for u in urls:
        if ARTICLE_RE.search(u) and not STATUS_RE.search(u):
            notes.append(f"{u}: an Article page link, which can't be fetched. "
                         "Search its title in quotes to find the post that shares it.")
            continue
        k = key(u)
        if not k.startswith("x:"):
            notes.append(f"{u}: not an X post link")
        elif k in seen:
            dupes += 1
        elif k not in todo:
            todo[k] = u
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(lambda k: (k, *fetch_status(k[2:])), todo))
    out, skipped = [], []
    i = 0
    for k, s, err in results:
        if isinstance(err, MirrorDown):
            notes.append(f"{todo[k]}: the fxtwitter mirror failed ({err}); try again later")
            continue
        if err:
            skipped.append(seen_record(todo[k], "gone", err))
            notes.append(f"{todo[k]}: unreadable ({err})")
            continue
        block, when = render_status(i + 1, s, chars)
        if max_age and (NOW - when).days > max_age:
            skipped.append(seen_record(s.get("url") or todo[k], "old", str(when.date())))
            continue
        i += 1
        out.append(block)
    append_seen(profile, skipped)
    old = sum(1 for r in skipped if r["verdict"] == "old")
    too_old = f" · {old} older than {max_age} days" if max_age else ""
    print(f"{len(out)} new posts to judge · {dupes} already seen{too_old} · {len(notes)} notes\n")
    print("\n\n".join(out))
    if notes:
        print("\nNotes:\n" + "\n".join("- " + n for n in notes))


# --- Reddit -----------------------------------------------------------------

def reddit_t(days):
    return "day" if days <= 1 else "week" if days <= 7 else "month" if days <= 31 else "year"


def html_text(fragment):
    text = re.sub(r"<[^>]+>", " ", html.unescape(fragment or ""))
    text = html.unescape(text)
    # Reddit appends "submitted by /u/x [link] [comments]" to every entry.
    return re.sub(r"\s*submitted by\s+/u/\S+.*$", "", text, flags=re.S).strip()


def reddit_get(url):
    """Fetch politely: the unauthenticated limit is about one request per 5-8s."""
    for wait in (0, 20, 45):
        time.sleep(wait or 6)
        code, body = curl(url, UA_BROWSER)
        if code != 429:
            return code, body
    return code, body


def cmd_reddit(subs, query, days, profile, chars, pages=4):
    seen = load_seen(profile)
    cutoff = NOW - dt.timedelta(days=days)
    out, dupes, problems = [], 0, []
    for sub in (s for s in subs.split(",") if s):
        after = None
        # Each page holds the newest 25 matches; page back until the window is covered.
        for _ in range(pages):
            url = (f"https://www.reddit.com/r/{sub}/search.rss?q={urllib.parse.quote(query)}"
                   f"&restrict_sr=1&sort=new&t={reddit_t(days)}&limit=25"
                   + (f"&after={after}" if after else ""))
            code, body = reddit_get(url)
            if code != 200:
                problems.append(f"r/{sub}: HTTP {code}, stopped")
                break
            try:
                entries = ET.fromstring(body).findall("a:entry", ATOM)
            except ET.ParseError as e:
                problems.append(f"r/{sub}: unreadable feed ({e})")
                break
            reached_cutoff = False
            for e in entries:
                link = e.find("a:link", ATOM).get("href")
                stamp = (e.findtext("a:published", namespaces=ATOM)
                         or e.findtext("a:updated", namespaces=ATOM))
                when = dt.datetime.fromisoformat(stamp)
                if when < cutoff:
                    reached_cutoff = True
                    continue
                if key(link) in seen:
                    dupes += 1
                    continue
                author = (e.findtext("a:author/a:name", namespaces=ATOM) or "?").removeprefix("/u/")
                out.append(f"[{len(out) + 1}] {link}\n    u/{author} · r/{sub} · {age(when)} ({when.date()})\n"
                           f"    title: {e.findtext('a:title', namespaces=ATOM)}\n"
                           f"    text: {clip(html_text(e.findtext('a:content', namespaces=ATOM)), chars)}")
            if reached_cutoff or len(entries) < 25:
                break
            after = entries[-1].findtext("a:id", namespaces=ATOM)
        else:
            problems.append(f"r/{sub}: stopped after {pages} pages before reaching {cutoff.date()}; "
                            "narrow the query")
    print(f"{len(out)} new Reddit posts · {dupes} already seen (no scores in RSS)\n")
    for p in problems:
        print(p)
    print("\n\n".join(out))


# --- Hacker News ------------------------------------------------------------

def cmd_hn(query, days, profile, chars):
    seen = load_seen(profile)
    since = int((NOW - dt.timedelta(days=days)).timestamp())
    url = ("https://hn.algolia.com/api/v1/search_by_date?tags=story&hitsPerPage=40"
           f"&query={urllib.parse.quote(query)}&numericFilters=created_at_i%3E{since}")
    code, body = curl(url)
    if code != 200:
        print(f"HN: HTTP {code}: {body[:200]}")
        return
    out, dupes = [], 0
    for h in json.loads(body).get("hits", []):
        link = f"https://news.ycombinator.com/item?id={h['objectID']}"
        if key(link) in seen:
            dupes += 1
            continue
        when = dt.datetime.fromtimestamp(h["created_at_i"], dt.timezone.utc)
        lines = [f"[{len(out) + 1}] {link}",
                 f"    {h.get('author')} · {h.get('points')} points · {h.get('num_comments') or 0} comments"
                 f" · {age(when)} ({when.date()})",
                 f"    title: {h.get('title')}"]
        if h.get("url"):
            lines.append(f"    links: {h['url']}")
        if h.get("story_text"):
            lines.append(f"    text: {clip(html_text(h['story_text']), chars)}")
        out.append("\n".join(lines))
    print(f"{len(out)} new HN stories · {dupes} already seen\n")
    print("\n\n".join(out))


# --- reading one post in full ----------------------------------------------

ARTICLE_PREFIX = {"header-one": "# ", "header-two": "## ", "header-three": "### ",
                  "unordered-list-item": "- ", "ordered-list-item": "1. ", "blockquote": "> "}


def article_text(article):
    """X Articles arrive as Draft.js blocks; flatten them to Markdown-ish text."""
    content = article.get("content") or {}
    entities = {str(e["key"]): e["value"] for e in content.get("entityMap", [])}
    lines = [f"## Article: {article.get('title', '(untitled)')}", ""]
    for b in content.get("blocks", []):
        if b.get("type") == "atomic":
            for r in b.get("entityRanges", []):
                ent = entities.get(str(r["key"])) or {}
                if ent.get("type") == "TWEET":
                    lines.append(f"[embedded post: https://x.com/i/status/{ent['data'].get('tweetId')}]")
            continue
        lines.append(ARTICLE_PREFIX.get(b.get("type"), "") + b.get("text", ""))
    # Links inside an Article live in its entity map, not in the text.
    urls = []
    for e in entities.values():
        u = (e.get("data") or {}).get("url") if e.get("type") == "LINK" else None
        if u and u not in urls:
            urls.append(u)
    if urls:
        lines += ["", "Article links: " + "  ".join(urls)]
    return "\n".join(lines)


def read_x(url):
    sid = STATUS_RE.search(url).group(1)
    # The thread endpoint adds the author's own replies, where giveaway links often sit.
    code, body = curl(f"https://api.fxtwitter.com/2/thread/{sid}")
    try:
        data = json.loads(body)
    except ValueError:
        data = {}
    posts = [t for t in data.get("thread") or [] if t and t.get("type") != "tombstone"]
    if not posts:
        s, err = fetch_status(sid)
        if err:
            return f"{url}: unreadable ({err})"
        posts = [s]
    out = []
    for n, s in enumerate(posts, 1):
        block, _ = render_status(f"{n}/{len(posts)}", s, 100_000)
        out.append(block)
        if s.get("article"):
            out.append(article_text(s["article"]))
    return "\n\n".join(out)


def read_reddit(url):
    base = url.split("?")[0].rstrip("/")
    code, body = reddit_get(f"{base}/.rss?limit=1")
    if code != 200:
        return f"{url}: HTTP {code}"
    entry = ET.fromstring(body).find("a:entry", ATOM)
    content = html.unescape(entry.findtext("a:content", namespaces=ATOM) or "")
    links = []
    for u in re.findall(r'href="([^"]+)"', content):
        if "reddit.com" not in u and "redd.it" not in u and u not in links:
            links.append(u)
    author = (entry.findtext("a:author/a:name", namespaces=ATOM) or "?").removeprefix("/u/")
    lines = [url, f"    u/{author} · {entry.findtext('a:updated', namespaces=ATOM)}",
             f"    title: {entry.findtext('a:title', namespaces=ATOM)}",
             f"    text: {html_text(content) or '(no text: a link or media post)'}"]
    if links:
        lines.append("    links: " + "  ".join(links))
    return "\n".join(lines)


def read_hn(url):
    code, body = curl(f"https://hn.algolia.com/api/v1/items/{HN_RE.search(url).group(1)}")
    if code != 200:
        return f"{url}: HTTP {code}"
    h = json.loads(body)
    lines = [url, f"    {h.get('author')} · {h.get('points')} points · {h.get('created_at')}",
             f"    title: {h.get('title')}"]
    if h.get("url"):
        lines.append(f"    links: {h['url']}")
    if h.get("text"):
        lines.append(f"    text: {html_text(h['text'])}")
    return "\n".join(lines)


def cmd_read(urls):
    out = []
    for u in urls:
        if STATUS_RE.search(u):
            out.append(read_x(u))
        elif REDDIT_RE.search(u):
            out.append(read_reddit(u))
        elif HN_RE.search(u):
            out.append(read_hn(u))
        else:
            out.append(f"{u}: not an X, Reddit or HN post. Read it with a web fetch tool.")
    print("\n\n---\n\n".join(out))


# --- verdicts ---------------------------------------------------------------

def cmd_mark(profile, verdict, urls, note):
    if verdict not in ("match", "maybe", "no"):
        sys.exit("verdict must be match, maybe or no")
    append_seen(profile, [seen_record(u, verdict, note) for u in urls])
    print(f"marked {len(urls)} as {verdict} in {Path(profile) / 'seen.jsonl'}")


def cmd_seen(profile):
    seen = load_seen(profile)
    counts = {}
    for r in seen.values():
        counts[r["verdict"]] = counts.get(r["verdict"], 0) + 1
    last = max((r["date"] for r in seen.values()), default="never")
    print(f"{len(seen)} posts seen · " + " · ".join(f"{v} {n}" for v, n in sorted(counts.items()))
          + f" · last marked {last}")


# --- CLI --------------------------------------------------------------------

def pop_opt(args, name, default=None, cast=str):
    if name in args:
        i = args.index(name)
        val = args[i + 1]
        del args[i:i + 2]
        return cast(val)
    return default


def main(argv):
    args = list(argv)
    if not args or args[0] in ("-h", "--help"):
        print(__doc__.strip())
        return 2
    cmd = args.pop(0)
    profile = pop_opt(args, "--profile")
    chars = pop_opt(args, "--chars", 500, int)
    days = pop_opt(args, "--days", 7, int)
    max_age = pop_opt(args, "--max-age", None, int)
    if cmd == "x":
        cmd_x(args, profile, max_age, chars)
    elif cmd == "reddit" and len(args) >= 2:
        cmd_reddit(args[0], " ".join(args[1:]), days, profile, chars)
    elif cmd == "hn" and args:
        cmd_hn(" ".join(args), days, profile, chars)
    elif cmd == "read" and args:
        cmd_read(args)
    elif cmd == "mark" and len(args) >= 3:
        note = pop_opt(args, "--note", "")
        cmd_mark(args[0], args[1], args[2:], note)
    elif cmd == "seen" and args:
        cmd_seen(args[0])
    else:
        print(__doc__.strip())
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
