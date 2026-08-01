"""
visualize.py
------------
Matplotlib chart builders for the WordPress analytics report.
Each function saves a PNG to `output_dir` and returns the file path.
"""

from __future__ import annotations

import os

import matplotlib
matplotlib.use("Agg")  # headless-safe backend
import matplotlib.pyplot as plt
import pandas as pd


def _save(fig, output_dir: str, filename: str) -> str:
    os.makedirs(output_dir, exist_ok=True)
    path = os.path.join(output_dir, filename)
    fig.savefig(path, bbox_inches="tight", dpi=140)
    plt.close(fig)
    return path


def plot_posts_per_month(series: pd.Series, output_dir: str) -> str:
    fig, ax = plt.subplots(figsize=(9, 4))
    ax.plot(series.index, series.values, marker="o", color="#2271b1")
    ax.set_title("Posting Frequency Over Time")
    ax.set_xlabel("Month")
    ax.set_ylabel("Posts published")
    ax.grid(alpha=0.3)
    fig.autofmt_xdate()
    return _save(fig, output_dir, "posts_per_month.png")


def plot_top_categories(series: pd.Series, output_dir: str) -> str:
    fig, ax = plt.subplots(figsize=(8, 4.5))
    series.sort_values().plot(kind="barh", ax=ax, color="#2271b1")
    ax.set_title("Most Active Categories")
    ax.set_xlabel("Number of posts")
    return _save(fig, output_dir, "top_categories.png")


def plot_top_authors(series: pd.Series, output_dir: str) -> str:
    fig, ax = plt.subplots(figsize=(8, 4.5))
    series.sort_values().plot(kind="barh", ax=ax, color="#d63638")
    ax.set_title("Most Prolific Authors")
    ax.set_xlabel("Number of posts")
    return _save(fig, output_dir, "top_authors.png")


def plot_avg_comments_by_category(series: pd.Series, output_dir: str) -> str | None:
    if series.empty:
        return None
    fig, ax = plt.subplots(figsize=(8, 4.5))
    series.sort_values().plot(kind="barh", ax=ax, color="#00a32a")
    ax.set_title("Average Comments per Post, by Category")
    ax.set_xlabel("Average comments")
    return _save(fig, output_dir, "avg_comments_by_category.png")
