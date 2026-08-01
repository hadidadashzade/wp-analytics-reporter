#!/usr/bin/env python3
"""
wp_report.py — WordPress Site Analytics Reporter

Point this at any public WordPress site and get a content/engagement
report: posting frequency over time, most active categories, most
prolific authors, and (optionally) average comments per post by category.

Usage:
    python wp_report.py --site https://example.com
    python wp_report.py --site https://wordpress.org/news --pages 3 --include-comments
    python wp_report.py --demo   # run against the bundled sample dataset, no network needed

Output:
    output/<site>/report.html   — a single portable HTML report
    output/<site>/*.png         — the individual charts
    output/<site>/posts.csv     — the processed post data
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys

import pandas as pd

import analysis
import visualize
import report as report_module


def slugify(site_url: str) -> str:
    return re.sub(r"\W+", "_", site_url.replace("https://", "").replace("http://", "")).strip("_")


def run_live(site_url: str, max_pages: int, per_page: int, include_comments: bool) -> pd.DataFrame:
    import wp_client  # imported lazily so --demo works without `requests` installed

    print(f"Fetching posts from {site_url} ...")
    try:
        posts = wp_client.fetch_posts(site_url, max_pages=max_pages, per_page=per_page)
    except wp_client.WordPressClientError as exc:
        print(f"\nCouldn't fetch posts: {exc}")
        print("\nTips:")
        print("  - Use the site's homepage URL, not a category/post/page URL")
        print("    e.g. https://example.com, not https://example.com/category/blog")
        print(f"  - Try opening {site_url.rstrip('/')}/wp-json/wp/v2/posts in a browser")
        print("    to check the REST API responds with JSON")
        sys.exit(1)

    if not posts:
        print("No posts found. Is the REST API enabled on this site?")
        sys.exit(1)
    print(f"  {len(posts)} posts fetched.")

    # Posts are fetched with _embed, so author/category names usually come
    # back attached already (see wp_client.extract_embedded). Only fall back
    # to the separate /users and /categories endpoints -- which many larger
    # sites block or rate-limit -- for posts missing that embedded data.
    needs_author_fallback = any(not wp_client.extract_embedded(p)[0] for p in posts)
    needs_category_fallback = any(not wp_client.extract_embedded(p)[1] for p in posts)

    category_map = {}
    if needs_category_fallback:
        print("Some posts are missing embedded category data, fetching categories ...")
        try:
            category_map = wp_client.fetch_taxonomy_map(site_url, "categories")
        except wp_client.WordPressClientError as exc:
            print(f"  Warning: couldn't fetch categories ({exc}). "
                  f"Those posts will show a category ID instead of a name.")

    author_map = {}
    if needs_author_fallback:
        print("Some posts are missing embedded author data, resolving authors ...")
        author_ids = [p["author"] for p in posts if "author" in p]
        try:
            author_map = wp_client.fetch_author_map(site_url, author_ids)
        except wp_client.WordPressClientError as exc:
            print(f"  Warning: couldn't fetch authors ({exc}). "
                  f"Those posts will show 'Author <id>' instead of a name.")

    comment_counts = {}
    if include_comments:
        print("Fetching comment counts (this makes one request per post)...")
        for i, post in enumerate(posts, 1):
            comment_counts[post["id"]] = wp_client.fetch_comment_count(site_url, post["id"])
            if i % 20 == 0:
                print(f"  {i}/{len(posts)} done")

    return analysis.posts_to_dataframe(posts, category_map, author_map, comment_counts)


def run_demo() -> tuple[pd.DataFrame, str]:
    demo_path = os.path.join(os.path.dirname(__file__), "sample_data", "demo_posts.json")
    with open(demo_path, encoding="utf-8") as f:
        bundle = json.load(f)
    df = analysis.posts_to_dataframe(
        bundle["posts"],
        {int(k): v for k, v in bundle["categories"].items()},
        {int(k): v for k, v in bundle["authors"].items()},
        {int(k): v for k, v in bundle.get("comment_counts", {}).items()},
    )
    return df, bundle["site_url"]


def main():
    parser = argparse.ArgumentParser(description="WordPress site analytics reporter")
    parser.add_argument("--site", help="Site URL, e.g. https://example.com")
    parser.add_argument("--pages", type=int, default=5, help="Max pages of posts to fetch (100/page by default)")
    parser.add_argument("--per-page", type=int, default=40,
                         help="Posts per page (lower this, e.g. 15-20, if a site times out)")
    parser.add_argument("--include-comments", action="store_true",
                         help="Also fetch comment counts (one extra request per post)")
    parser.add_argument("--demo", action="store_true",
                         help="Run against the bundled sample dataset (no network needed)")
    parser.add_argument("--output", default="output", help="Output directory")
    args = parser.parse_args()

    if not args.demo and not args.site:
        parser.error("Provide --site <url> or use --demo")

    if args.demo:
        df, site_url = run_demo()
    else:
        site_url = args.site
        df = run_live(site_url, args.pages, args.per_page, args.include_comments)

    if df.empty:
        print("No data to report on.")
        sys.exit(1)

    out_dir = os.path.join(args.output, slugify(site_url))
    os.makedirs(out_dir, exist_ok=True)

    df.drop(columns=["categories"]).to_csv(os.path.join(out_dir, "posts.csv"), index=False)

    stats = analysis.summary_stats(df)
    monthly = analysis.posts_per_month(df)
    categories = analysis.top_categories(df)
    authors = analysis.top_authors(df)
    avg_comments = analysis.average_comments_by_category(df)

    chart_paths = {
        "posts_per_month": visualize.plot_posts_per_month(monthly, out_dir),
        "top_categories": visualize.plot_top_categories(categories, out_dir),
        "top_authors": visualize.plot_top_authors(authors, out_dir),
        "avg_comments_by_category": visualize.plot_avg_comments_by_category(avg_comments, out_dir),
    }

    report_path = report_module.build_html_report(
        site_url, stats, chart_paths, os.path.join(out_dir, "report.html")
    )

    print("\n--- Summary ---")
    for k, v in stats.items():
        print(f"{k}: {v}")
    print(f"\nReport written to: {report_path}")


if __name__ == "__main__":
    main()
