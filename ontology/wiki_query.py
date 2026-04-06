#!/usr/bin/env python3
"""
Wiki Query — search and retrieve compiled wiki articles.

Usage:
    python3 wiki_query.py search "dscr pipeline"
    python3 wiki_query.py get <slug>
    python3 wiki_query.py related <slug>
    python3 wiki_query.py list
"""

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Optional

WIKI_DIR = Path.home() / ".openclaw" / "wiki"
INDEX_PATH = WIKI_DIR / "index.json"


def _load_index() -> dict:
    if not INDEX_PATH.exists():
        print("No index found. Run 'wiki_compiler.py build' first.", file=sys.stderr)
        return {"articles": []}
    with open(INDEX_PATH) as f:
        return json.load(f)


def _read_article(slug: str) -> Optional[str]:
    path = WIKI_DIR / f"{slug}.md"
    if path.exists():
        return path.read_text()
    return None


def search(query: str, limit: int = 5) -> list[dict]:
    """Search wiki articles by title, tags, content. Returns ranked results."""
    index = _load_index()
    query_lower = query.lower()
    query_words = set(re.findall(r"\w+", query_lower))

    scored: list[tuple[float, dict]] = []

    for article in index.get("articles", []):
        score = 0.0

        # Title match
        title_lower = article.get("topic", "").lower()
        if query_lower in title_lower:
            score += 10.0
        title_words = set(re.findall(r"\w+", title_lower))
        word_overlap = len(query_words & title_words)
        score += word_overlap * 3.0

        # Tag match
        tags = [t.lower() for t in article.get("tags", [])]
        for qw in query_words:
            for tag in tags:
                if qw in tag:
                    score += 2.0

        # Slug match
        slug = article.get("slug", "")
        for qw in query_words:
            if qw in slug:
                score += 1.5

        # Content match (read file if we have partial matches already)
        if score > 0:
            content = _read_article(article.get("slug", ""))
            if content:
                content_lower = content.lower()
                for qw in query_words:
                    count = content_lower.count(qw)
                    score += min(count * 0.1, 3.0)  # cap per-word content boost

        if score > 0:
            result = {
                "topic": article.get("topic"),
                "slug": article.get("slug"),
                "score": round(score, 2),
                "entry_count": article.get("entry_count", 0),
                "tags": article.get("tags", [])[:10],
            }
            scored.append((score, result))

    scored.sort(key=lambda x: x[0], reverse=True)
    return [item for _, item in scored[:limit]]


def get_article(slug: str) -> str:
    """Return full article content."""
    content = _read_article(slug)
    if content is None:
        return f"Article '{slug}' not found."
    return content


def get_related(slug: str) -> list[str]:
    """Return backlinked article slugs."""
    index = _load_index()
    for article in index.get("articles", []):
        if article.get("slug") == slug:
            return article.get("backlinks", [])
    return []


def list_articles() -> list[dict]:
    """List all articles with metadata."""
    index = _load_index()
    results = []
    for article in sorted(index.get("articles", []), key=lambda a: a.get("entry_count", 0), reverse=True):
        results.append({
            "topic": article.get("topic"),
            "slug": article.get("slug"),
            "entry_count": article.get("entry_count", 0),
            "tags": article.get("tags", [])[:10],
            "sources": article.get("sources", []),
            "backlinks": article.get("backlinks", []),
        })
    return results


# ===================================================================
# CLI
# ===================================================================

def main():
    parser = argparse.ArgumentParser(description="Wiki Query — search compiled articles")
    sub = parser.add_subparsers(dest="command")

    search_p = sub.add_parser("search", help="Search articles")
    search_p.add_argument("query", type=str, help="Search query")
    search_p.add_argument("--limit", type=int, default=5, help="Max results")

    get_p = sub.add_parser("get", help="Get article by slug")
    get_p.add_argument("slug", type=str, help="Article slug")

    related_p = sub.add_parser("related", help="Get related articles")
    related_p.add_argument("slug", type=str, help="Article slug")

    sub.add_parser("list", help="List all articles")

    args = parser.parse_args()
    if args.command == "search":
        results = search(args.query, limit=args.limit)
        if not results:
            print("No results found.")
        else:
            for r in results:
                print(f"  {r['score']:6.1f} | {r['slug']:<40s} | {r['topic']} ({r['entry_count']} entries)")
    elif args.command == "get":
        print(get_article(args.slug))
    elif args.command == "related":
        related = get_related(args.slug)
        if related:
            for r in related:
                print(f"  - {r}")
        else:
            print("No related articles found.")
    elif args.command == "list":
        articles = list_articles()
        for a in articles:
            print(f"  {a['entry_count']:3d} entries | {a['slug']:<40s} | {a['topic']}")
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
