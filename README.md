# posts-like-this

A Claude Code skill: give Claude a post, get a feed of posts like it.

Paste a post you wish you saw more of. Claude works out what makes it *that kind* of post, then searches X, Reddit and Hacker News for new ones that fit. Each run writes a ranked digest, and you'll never see the same post twice. Tell it "more like #3" or "#5 isn't it", and the profile changes to match.

It's the idea behind a lead list's ideal customer profile, applied to posts.

## How it works

1. **Profile.** From your sample post, Claude writes a fingerprint:
   - **subject**: what it's about;
   - **move**: what the author is doing, such as giving away a tool, a teardown, a case study or a launch;
   - **offer**: what the reader gets and how;
   - **format**, **hook** and **proof**;
   - **author**: size and type;
   - **signal**: how the post did.

   It then sets the rules: **Must have**, **Nice to have** and **Not this**, according to what you'll use the posts for:
   - `try`: things you can use;
   - `model`: posts to learn writing from;
   - `watch`: who's doing what in a market.
2. **Search.**
   - X through a date-filtered web search (`site:x.com` over the past week).
   - Reddit through subreddit search.
   - Hacker News through Algolia.
3. **Judge.** Every new post is checked against the profile with live numbers: followers, views, likes, and saves per 1,000 views, the best sign that people kept it for later. Posts that excerpts can't settle are read in full, including the author's whole X thread and any X Article.
4. **Digest.** Matches come ranked, with why each one fits and what's in it. Near misses are listed with the rule they miss. Everything judged is recorded, so the next run only shows new posts.

A digest entry looks like this:

```markdown
### 2. A free skill that writes product demo videos from your codebase · u/someone
https://www.reddit.com/r/ClaudeAI/comments/… · Reddit · 3d ago
**Why it fits:** built and shared by its author, free and open source, does a video-editing job.
**What's in it:** https://github.com/… (not installed, untested)
```

## Install

**As a plugin** (in Claude Code):

```
/plugin marketplace add Temi-pinheiro/posts-like-this
/plugin install posts-like-this@posts-like-this
```

**With the skills CLI:**

```
npx skills add Temi-pinheiro/posts-like-this -g -a claude-code
```

**By hand:** copy `skills/posts-like-this/` into `~/.claude/skills/`.

### Requirements

- Python 3.10+ and `curl`. The helper script uses only the standard library.
- **For X search:** a web search tool that can filter by date. It was built and tested with the [Firecrawl MCP server](https://github.com/firecrawl/firecrawl-mcp-server) (`firecrawl_search` with `tbs`). Without one, Reddit and Hacker News still work.
- X posts are read through [fxtwitter](https://github.com/FixTweet/FxTwitter)'s free public API. No X account or API key is needed.

## Use

In Claude Code:

- `Find posts like this: https://x.com/<user>/status/<id>` builds a profile and does a first run over the past week.
- `Run my post profiles` checks every active profile for posts since its last digest.
- `More like #2`, `#5 isn't it`, `gated giveaways are fine` tune the profile and re-judge the latest digest.
- `Pause the free-skills profile` stops a profile without deleting it.

Profiles live in `$POSTS_LIKE_THIS_DIR` if you set it, otherwise in `post-profiles/` in the folder you run Claude from:

```
post-profiles/<profile>/
  profile.md        # the fingerprint, rules, queries, your feedback and a run log; edit it by hand if you like
  seen.jsonl        # every post already judged
  runs/<date>.md    # one digest per run
```

To run it on a schedule inside an open session, use `/loop 24h /posts-like-this run all`.

## Cost and limits

- **Firecrawl** bills per search (2 credits a search when this was written). A daily run with 3 X searches is about 180 credits a month. Reddit and Hacker News are free.
- **Reddit** is read through public RSS without logging in. That means about one request every 5–8 seconds, and no vote counts.
- **fxtwitter** is a free third-party mirror. When it's down, X posts are retried on the next run rather than dropped.
- **Other sites** (LinkedIn, Threads) should work through the same `site:` search, but haven't been tested.

## Safety

Post text is treated as data, never as instructions. The skill never installs, downloads or runs what a post offers, and never replies to or DMs anyone. It lists the link, and you decide.

## The helper script

`skills/posts-like-this/scripts/posts.py` does the mechanical parts. Run it with no arguments for usage.

```
posts.py x <url>... [--profile DIR] [--max-age DAYS]   # X posts with live numbers, skipping ones already seen
posts.py reddit <sub>[,<sub>] <query> [--days N]        # subreddit search, newest first, paged to cover the window
posts.py hn <query> [--days N]                          # Hacker News stories
posts.py read <url>...                                  # a post in full: X thread and Article, Reddit links, HN text
posts.py mark DIR match|maybe|no <url>... [--note ..]   # record verdicts
posts.py seen DIR                                       # summary
```

## License

MIT. See [LICENSE](LICENSE).
