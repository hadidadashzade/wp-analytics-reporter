# WordPress Site Analytics Reporter

A command-line tool that connects to any public WordPress site through its REST API and generates a content and engagement analytics report — no plugin or login required.

Point it at a site and get, in one command, a portable HTML report covering:

- **Posting frequency over time** — is the site actively maintained?
- **Most active categories** — where is content concentrated?
- **Most prolific authors** — who's actually publishing?
- **Average comments per post, by category** *(optional)* — what content drives engagement?

Built for freelance and agency use: run it against a prospective client's site before a pitch, or hand a client a snapshot of their content health.

## Why this exists

It combines three practical skills — Python, data analysis (pandas/matplotlib), and WordPress — into one tool. Most WordPress freelancers can build sites; fewer can also show a client, in a single report, how their content has actually performed over time.

## Quick start

```bash
pip install -r requirements.txt

# Try it instantly with the bundled sample dataset — no network needed
python wp_report.py --demo

# Run against a real site
python wp_report.py --site https://example.com

# Fetch more history and include comment-engagement data
python wp_report.py --site https://example.com --pages 10 --include-comments

# Lower the page size for very large sites
python wp_report.py --site https://example.com --per-page 20
```

Output lands in `output/<site-name>/`:
- `report.html` — a single self-contained file (charts embedded inline) — open it in any browser or send it straight to a client
- `posts.csv` — the underlying processed data, for further analysis in Excel or pandas
- individual `.png` charts

## How it works

| File | Responsibility |
|---|---|
| `wp_client.py` | Talks to the WordPress REST API (`/wp-json/wp/v2/`) — fetches posts, categories, authors, and optionally comment counts. Read-only, so no authentication is required. |
| `analysis.py` | Converts raw API responses into a tidy pandas DataFrame and computes the report metrics. |
| `visualize.py` | Builds the matplotlib charts. |
| `report.py` | Assembles everything into one portable HTML file. |
| `wp_report.py` | CLI entry point that wires it all together. |

## Design notes

- **Resilient fetching.** Each page of posts is requested with WordPress's `_embed` parameter so author and category names come back attached directly, avoiding extra round-trips. Since `_embed` is more expensive for the server to compute, any page that's slow to respond automatically falls back to a lighter request and resolves names separately instead — so the tool adapts to the site rather than requiring per-site tuning.
- **Respectful of the target server.** Requests are paginated with a small delay between calls rather than fired in a burst, and page size is tunable via `--per-page` for larger sites.
- **Portable output.** The HTML report has its charts embedded as inline images, so it's a single file that opens correctly with no external dependencies — easy to email or archive.

## Known limitations

- A minority of sites restrict their `/wp-json/wp/v2/users` endpoint for privacy, which is a deliberate choice on the site's part. On those sites, the report shows an author ID instead of a display name; every other metric is unaffected.
- Sites with unusually strong bot protection (CAPTCHA/JS challenges) may block automated requests entirely. If `https://<site>/wp-json/wp/v2/posts` doesn't load JSON directly in a browser, the REST API is likely disabled or gated on that site.

## Demo dataset

`sample_data/demo_posts.json` is a small, realistic dataset modeled on real WordPress REST API responses, so the tool can be tried and demoed without network access. Run `python wp_report.py --demo` to see it in action.

## Possible extensions

- Compare two time periods (e.g. this quarter vs. last) to show growth or decline
- A `--schedule` mode to run weekly and track trends over time
- Export a PDF version of the report for client deliverables
