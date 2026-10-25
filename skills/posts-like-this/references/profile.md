# Post profile: template, fields and digest format

## The fingerprint fields

Two posts are "alike" along some of these and not others. The fingerprint records all of them, and the Must have list picks the ones that matter for this profile's purpose.

| Field | What to write | Example (a free skill pack shared as an X Article) |
| --- | --- | --- |
| **Subject** | What it's about, one level more general than the seed | A Claude Code skill or skill pack that does a creative or professional job |
| **Move** | What the author is *doing* with the post | Giving away something they built, and explaining what it does |
| **Offer / CTA** | What the reader gets and how they get it | A free download link, with no gate and no paid tier |
| **Format** | The post type and its shape | An X Article: pain, then "so I built", how it works, a capability list, a demo, "get it free" |
| **Hook** | The opening pattern, in general terms | "<Job> has just been solved by AI", then the cost of doing it the old way ($20–30 a reel) |
| **Proof** | What makes it believable | A before/after demo in a quote post |
| **Author** | Size band and type | A small builder account (about 5k followers) shipping tools in public |
| **Signal** | How it did, compared with views | 7.4k views, 29 saves, 9 likes: people saved it far more than they liked it |

Moves worth naming: giving away a tool or resource; launching; a teardown or breakdown; a how-to; a case study with numbers; a contrarian take; a curated list; "comment X and I'll send it" (gated giveaway); asking for help; a build-in-public update.

## profile.md template

```markdown
---
name: <slug>
seed: <url>
created: <YYYY-MM-DD>
status: active            # active | paused
purpose: try              # try | model | watch
window_days: 7            # the most a run looks back
platforms: [x, reddit, hn]   # other sites go through site: searches (untested)
subreddits: [ClaudeAI, ClaudeCode]
firecrawl_searches: 3     # per run, 2 credits each
---

# <Short name>: posts like @<handle>'s "<title or first line>"

## The seed
<Two or three sentences: what the post is, who wrote it, how it did.>

## Fingerprint
- **Subject:**
- **Move:**
- **Offer / CTA:**
- **Format:**
- **Hook:**
- **Proof:**
- **Author:**
- **Signal:**

## What counts as "like this"
Purpose: <try | model | watch>, because <why the user wants these posts>.

**Must have** (all of them):
-

**Nice to have** (ranks higher):
-

**Not this** (reject even when it's on topic):
-

## Queries
### X (Firecrawl: `site:x.com` + query, past week)
-
### Reddit (r/…, newest first)
-
### Hacker News
-
### Other sites (optional: `site:linkedin.com/posts` etc. + query)
-
### Watched authors
- @<seed author> (the seed)

## Feedback
<!-- - YYYY-MM-DD: "<the user's words>" → <what changed> -->

## Run log
<!-- - YYYY-MM-DD: window Nd · K new posts judged → M matches, P maybes · Firecrawl C credits · best query: "<q>" -->
```

## Digest format (`runs/<YYYY-MM-DD>.md`)

```markdown
# <Profile name> · <YYYY-MM-DD>

<M> matches and <P> maybes from <K> new posts (the last <N> days). Sources: X via Firecrawl (<n> searches), r/…, HN. Firecrawl: <C> credits.

## Matches

### 1. <What it is, in a few words> · @<handle> (<followers>)
<url> · <post|Article|thread> · <age> · <views> views · <saves> saves (<per 1k> per 1k views)
**Why it fits:** <the must-haves it meets, in one line>
**What's in it:** <for try: the thing offered and its link, plus "not installed, untested". For model: the hook and its structure. For watch: who it is and what they're doing.>

### 2. …

## Maybes
- <url> · @<handle>: <what it is>. Misses: <the must-have it fails>.

## Not shown
<K> judged and dropped: <n> off topic, <n> wrong move (for example courses or news), <n> older than the window.

## For you
- <A proposed profile change, if a pattern showed up. Otherwise leave this out.>
- Verdicts welcome: "more like #2", "#4 isn't it".
```

Rank matches by fit first (more nice-to-haves), then signal: saves per 1k views for `try`; views per follower for `model`. Don't rank by raw likes, because big accounts win on likes whether or not the post is any good.
