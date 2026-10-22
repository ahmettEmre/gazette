# Sources

Your list lives in `config/sources.json` (created by `/gazette-setup` or `./gazette sources init --packs …`).
Ready-made packs are in `catalog/sources.json`; list them with `./gazette sources packs`.

Every source has `id` (unique), `name`, `type`, `tier` and optionally `topic` (the digest groups candidates by it),
`max` (candidates per edition), `summary_chars`, `exclude` (regex on titles) and `enabled: false`.

`tier` tells the editor how much to trust it:
- `official` — the company, project or institution itself (blog, changelog, release notes, regulator)
- `press` — a news organization
- `community` — Hacker News, Reddit, personal blogs, newsletters

After any change run `./gazette sources test` (one fetch per source, nothing is saved).

## Types

| type | required | optional | what it reads |
|---|---|---|---|
| `feed` | `url` | | any RSS or Atom feed |
| `gnews` | `query` | `lang` (en), `country` (US) | Google News search for any keyword, in any language. Links point to Google News; the editor looks up the original article. |
| `github_releases` | `repo` (`owner/name`) | `prerelease: true` | GitHub releases (keyless API: 60 requests/hour, keep GitHub sources under 40) |
| `hn` | | `query`, `min_points` (100), `tags` (`story`, `show_hn`) | Hacker News stories above a point threshold, optionally matching a keyword |
| `sitemap` | `url`, `include` (list of URL parts) | `exclude_url` (regex), `track_updates` | new pages in a sitemap — for sites without a feed |
| `watch` | `url` | | new lines on a page (changelogs, announcement lists). The first run only takes a snapshot. |
| `github_rising` | | `days` (7), `language` | new GitHub repositories collecting stars fastest |
| `hf_models` / `hf_papers` | | | trending Hugging Face models / daily papers |
| `devpost` | | | open and upcoming hackathons, sorted by prize |

## Examples

```json
{ "id": "rel-django-ninja", "name": "django-ninja releases", "type": "github_releases", "tier": "official",
  "repo": "vitalik/django-ninja", "max": 2, "summary_chars": 400, "topic": "Python" }

{ "id": "gn-fenerbahce", "name": "Google News: Fenerbahçe", "type": "gnews", "tier": "press",
  "query": "Fenerbahçe", "lang": "tr", "country": "TR", "max": 6, "topic": "Sport" }

{ "id": "reddit-selfhosted", "name": "Reddit r/selfhosted + r/homelab", "type": "feed", "tier": "community",
  "url": "https://www.reddit.com/r/selfhosted+homelab/top/.rss?t=day", "max": 8, "summary_chars": 160, "topic": "Self-hosting" }

{ "id": "hn-postgres", "name": "HN: Postgres", "type": "hn", "tier": "community",
  "query": "postgres", "min_points": 40, "max": 5, "topic": "Databases" }
```

## Tips
- Reddit answers a second quick request with 429: combine subreddits in one feed (`r/a+b+c`).
- Sites that block bots or need JavaScript will fail in `sources test`; use a `gnews` query for them instead.
- Paywalled feeds are fine as signals: the editor only uses their headline and summary.
