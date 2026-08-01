"""
analysis.py
-----------
Turns raw WordPress REST API post records into a tidy pandas DataFrame
and computes the metrics shown in the report.
"""

from __future__ import annotations

import pandas as pd

import wp_client


def posts_to_dataframe(
    posts: list[dict],
    category_map: dict[int, str],
    author_map: dict[int, str],
    comment_counts: dict[int, int] | None = None,
) -> pd.DataFrame:
    """
    Convert raw WP REST API post dicts into a flat DataFrame.

    Prefers names embedded directly on each post (via `_embed`, see
    wp_client.extract_embedded) since those survive even when a site blocks
    the standalone /users or paginated /categories endpoints. category_map /
    author_map are used only as a fallback for posts without embedded data.
    """
    rows = []
    for post in posts:
        embedded_author, embedded_categories = wp_client.extract_embedded(post)

        if embedded_categories:
            categories = embedded_categories
        else:
            categories = [category_map.get(c, str(c)) for c in post.get("categories", [])]

        author_name = embedded_author or author_map.get(post.get("author"), f"Author {post.get('author')}")

        rows.append({
            "id": post["id"],
            "date": pd.to_datetime(post["date"]),
            "title": post.get("title", {}).get("rendered", ""),
            "author": author_name,
            "categories": categories,
            "primary_category": categories[0] if categories else "Uncategorized",
            "tag_count": len(post.get("tags", [])),
            "sticky": post.get("sticky", False),
            "comments_open": post.get("comment_status") == "open",
            "comment_count": (comment_counts or {}).get(post["id"], None),
            "link": post.get("link", ""),
        })

    df = pd.DataFrame(rows)
    if not df.empty:
        df = df.sort_values("date", ascending=False).reset_index(drop=True)
    return df


def posts_per_month(df: pd.DataFrame) -> pd.Series:
    """Posting frequency, resampled to a monthly count."""
    return df.set_index("date").resample("ME").size()


def top_categories(df: pd.DataFrame, top_n: int = 10) -> pd.Series:
    """Most-used categories by post count (a post can count toward several)."""
    exploded = df.explode("categories")
    return exploded["categories"].value_counts().head(top_n)


def top_authors(df: pd.DataFrame, top_n: int = 10) -> pd.Series:
    """Most prolific authors by post count."""
    return df["author"].value_counts().head(top_n)


def average_comments_by_category(df: pd.DataFrame) -> pd.Series:
    """Average comment count per primary category (requires comment_count filled in)."""
    if df["comment_count"].isna().all():
        return pd.Series(dtype=float)
    return (
        df.dropna(subset=["comment_count"])
        .groupby("primary_category")["comment_count"]
        .mean()
        .sort_values(ascending=False)
    )


def summary_stats(df: pd.DataFrame) -> dict:
    """A handful of headline numbers for the top of the report."""
    if df.empty:
        return {}
    span_days = (df["date"].max() - df["date"].min()).days or 1
    return {
        "total_posts": len(df),
        "date_range": (df["date"].min().date(), df["date"].max().date()),
        "posts_per_week_avg": round(len(df) / (span_days / 7), 2),
        "unique_authors": df["author"].nunique(),
        "unique_categories": df["primary_category"].nunique(),
        "sticky_posts": int(df["sticky"].sum()),
    }
