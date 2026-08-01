"""
wp_client.py
------------
A small, dependency-light client for the public WordPress REST API.

Works against ANY WordPress site that exposes the default REST API
(most sites do, unless it's been explicitly disabled). No authentication
is required to read public content: posts, categories, tags, users, comments.

Docs: https://developer.wordpress.org/rest-api/reference/
"""

from __future__ import annotations

import time
from typing import Any, Iterable
from urllib.parse import urlparse

import requests

DEFAULT_TIMEOUT = 30
# Fields to request per post. Restricting this avoids downloading the full
# rendered HTML content/excerpt of every post (which on content-heavy sites
# made responses slow enough to time out) while still keeping _embedded so
# author/category names come through (see extract_embedded below).
POST_FIELDS = "id,date,title,author,categories,tags,link,sticky,comment_status,_links,_embedded"
# A realistic browser User-Agent. Many WordPress sites sit behind a CDN/WAF
# (Cloudflare, ArvanCloud, security plugins, etc.) that blocks requests
# identifying as "python-requests" or similar bot-like strings, even for
# public REST API endpoints. Presenting as an ordinary browser avoids that
# without doing anything the browser itself couldn't do.
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)
DEFAULT_HEADERS = {"User-Agent": USER_AGENT, "Accept": "application/json"}


class WordPressClientError(Exception):
    """Raised when the WordPress REST API can't be reached or parsed."""


def _api_base(site_url: str) -> str:
    """
    Build the REST API base URL from just the site's domain, ignoring any
    path the user included (e.g. a category or post URL). A blog's REST API
    always lives at the site root: https://example.com/wp-json/wp/v2/
    """
    if not site_url.startswith("http"):
        site_url = "https://" + site_url
    parsed = urlparse(site_url)
    root = f"{parsed.scheme}://{parsed.netloc}"
    return f"{root}/wp-json/wp/v2/"


def _get(url: str, params: dict | None = None) -> requests.Response:
    try:
        response = requests.get(
            url, params=params, timeout=DEFAULT_TIMEOUT, headers=DEFAULT_HEADERS,
        )
    except requests.RequestException as exc:
        raise WordPressClientError(f"Could not reach {url}: {exc}") from exc

    if response.status_code == 404:
        raise WordPressClientError(
            f"{url} returned 404 — the REST API may be disabled on this site, "
            f"or this isn't a WordPress site."
        )
    if response.status_code in (401, 403):
        raise WordPressClientError(
            f"{url} returned HTTP {response.status_code} — this site's firewall/CDN "
            f"(e.g. Cloudflare, ArvanCloud, or a security plugin) is likely blocking "
            f"automated requests, even though the REST API itself is enabled."
        )
    if not response.ok:
        raise WordPressClientError(
            f"{url} returned HTTP {response.status_code}: {response.text[:200]}"
        )

    content_type = response.headers.get("Content-Type", "")
    if "json" not in content_type:
        raise WordPressClientError(
            f"{url} did not return JSON (got '{content_type}'). This usually means "
            f"a firewall/CDN (Cloudflare, ArvanCloud, a security plugin, etc.) is "
            f"serving a challenge/error page instead of letting the request through, "
            f"even though the REST API itself may be enabled. "
            f"First 200 chars of response:\n{response.text[:200]}"
        )
    return response


def _fetch_page(base: str, page: int, per_page: int, use_embed: bool) -> requests.Response:
    params = {"per_page": per_page, "page": page, "_fields": POST_FIELDS}
    if use_embed:
        params["_embed"] = "author,wp:term"
    return _get(base, params=params)


def fetch_posts(
    site_url: str,
    max_pages: int = 5,
    per_page: int = 40,
    delay_seconds: float = 0.3,
) -> list[dict[str, Any]]:
    """
    Fetch published posts from a WordPress site, newest first.

    Tries `_embed` first so author/category names come back attached to each
    post (see extract_embedded), avoiding separate /users and /categories
    calls that many larger sites block or rate-limit. However, `_embed` is
    known to be expensive to compute server-side per post (WordPress core
    trac #46249), which can cause timeouts on sites with a lot of posts per
    page. If a page times out, or a first page comes back empty, this
    automatically retries that page without `_embed` -- the plainer request
    that's cheaper for the server and was confirmed to work reliably even
    on sites where the embedded version struggled. Names for posts fetched
    this way fall back to fetch_author_map / fetch_taxonomy_map, handled by
    the caller (see wp_report.run_live).

    Paginates using the collection's X-WP-TotalPages header, stopping at
    max_pages (default 5 * 40 = up to 200 posts) to keep runtime reasonable.
    """
    base = _api_base(site_url) + "posts"
    posts: list[dict[str, Any]] = []

    page = 1
    total_pages = max_pages
    use_embed = True
    while page <= min(max_pages, total_pages):
        try:
            response = _fetch_page(base, page, per_page, use_embed)
            batch = response.json()
        except WordPressClientError:
            if use_embed:
                # _embed can be slow enough to time out on content-heavy
                # sites; fall back to the cheaper plain request for the
                # rest of this run.
                use_embed = False
                response = _fetch_page(base, page, per_page, use_embed)
                batch = response.json()
            else:
                raise

        if not batch and use_embed and page == 1:
            # Some sites return an unexpectedly empty first page only when
            # _embed is requested. Retry that same page without it before
            # concluding there are no posts.
            use_embed = False
            response = _fetch_page(base, page, per_page, use_embed)
            batch = response.json()

        if not batch:
            break
        posts.extend(batch)

        total_pages = int(response.headers.get("X-WP-TotalPages", page))
        page += 1
        time.sleep(delay_seconds)  # be a polite API citizen

    return posts


def extract_embedded(post: dict[str, Any]) -> tuple[str | None, list[str]]:
    """
    Pull the author display name and category names out of a post's
    `_embedded` block (present when posts were fetched with `_embed`).

    Returns (author_name_or_None, list_of_category_names). Falls back to
    (None, []) if the site didn't return embedded data, in which case the
    caller should fall back to fetch_author_map / fetch_taxonomy_map.
    """
    embedded = post.get("_embedded", {})

    author_name = None
    authors = embedded.get("author")
    if authors and isinstance(authors, list) and "name" in authors[0]:
        author_name = authors[0]["name"]

    category_names: list[str] = []
    term_groups = embedded.get("wp:term")
    if term_groups:
        for group in term_groups:
            for term in group:
                if term.get("taxonomy") == "category":
                    category_names.append(term["name"])

    return author_name, category_names


def fetch_taxonomy_map(site_url: str, taxonomy: str = "categories") -> dict[int, str]:
    """
    Fetch the id -> name mapping for 'categories' or 'tags'.
    """
    base = _api_base(site_url) + taxonomy
    mapping: dict[int, str] = {}
    page = 1
    while True:
        response = _get(base, params={"per_page": 100, "page": page, "_fields": "id,name"})
        batch = response.json()
        if not batch:
            break
        for item in batch:
            mapping[item["id"]] = item["name"]
        total_pages = int(response.headers.get("X-WP-TotalPages", page))
        if page >= total_pages:
            break
        page += 1
        time.sleep(0.3)
    return mapping


def fetch_author_map(site_url: str, author_ids: Iterable[int]) -> dict[int, str]:
    """
    Resolve author IDs to display names. Falls back to 'Author {id}' if a
    lookup fails (some sites restrict the /users endpoint).
    """
    base = _api_base(site_url) + "users"
    mapping: dict[int, str] = {}
    for author_id in set(author_ids):
        try:
            response = _get(f"{base}/{author_id}", params={"_fields": "id,name"})
            data = response.json()
            mapping[author_id] = data.get("name", f"Author {author_id}")
        except WordPressClientError:
            mapping[author_id] = f"Author {author_id}"
        time.sleep(0.15)
    return mapping


def fetch_comment_count(site_url: str, post_id: int) -> int:
    """
    Efficiently get the comment count for a single post using the
    X-WP-Total header (per_page=1 keeps the payload tiny).
    """
    base = _api_base(site_url) + "comments"
    response = _get(base, params={"post": post_id, "per_page": 1})
    return int(response.headers.get("X-WP-Total", 0))
