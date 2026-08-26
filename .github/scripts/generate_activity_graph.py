#!/usr/bin/env python3
"""Generate Shan's self-hosted GitHub contribution graph as an SVG.

Previous graph implementation and visual reference:
https://github.com/ashutosh00710/github-readme-activity-graph
"""

from __future__ import annotations

import argparse
import json
import math
import os
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from html import escape
from pathlib import Path
from typing import Sequence
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


WIDTH = 1200
HEIGHT = 340
WINDOW_DAYS = 90

COLORS = {
    "background": "#0B1120",
    "surface": "#101827",
    "rule": "#25324A",
    "text": "#E6EDF7",
    "muted": "#97A6BA",
    "accent": "#5794F2",
}


@dataclass(frozen=True)
class Contribution:
    day: date
    count: int


def fetch_contributions(username: str, token: str) -> list[Contribution]:
    today = datetime.now(timezone.utc).date()
    start = today - timedelta(days=WINDOW_DAYS - 1)
    query = """
      query($username: String!, $from: DateTime!, $to: DateTime!) {
        user(login: $username) {
          contributionsCollection(from: $from, to: $to) {
            contributionCalendar {
              weeks {
                contributionDays {
                  contributionCount
                  date
                }
              }
            }
          }
        }
      }
    """
    payload = json.dumps(
        {
            "query": query,
            "variables": {
                "username": username,
                "from": f"{start.isoformat()}T00:00:00Z",
                "to": f"{today.isoformat()}T23:59:59Z",
            },
        }
    ).encode("utf-8")
    request = Request(
        "https://api.github.com/graphql",
        data=payload,
        headers={
            "Authorization": f"bearer {token}",
            "Content-Type": "application/json",
            "User-Agent": "shanpadayhag-activity-graph",
        },
        method="POST",
    )

    try:
        with urlopen(request, timeout=30) as response:
            body = json.load(response)
    except (HTTPError, URLError) as error:
        raise RuntimeError(f"GitHub contribution request failed: {error}") from error

    if body.get("errors"):
        raise RuntimeError(f"GitHub GraphQL error: {body['errors']}")

    user = body.get("data", {}).get("user")
    if user is None:
        raise RuntimeError(f"GitHub user @{username} was not found")

    raw_days = user["contributionsCollection"]["contributionCalendar"]["weeks"]
    counts = {
        date.fromisoformat(item["date"]): int(item["contributionCount"])
        for week in raw_days
        for item in week["contributionDays"]
    }
    return [
        Contribution(start + timedelta(days=offset), counts.get(start + timedelta(days=offset), 0))
        for offset in range(WINDOW_DAYS)
    ]


def sample_contributions() -> list[Contribution]:
    """Deterministic data used only for local visual checks."""
    start = date(2026, 5, 29)
    values = [
        max(0, round(3.2 + 2.8 * math.sin(index * 0.31) + 1.7 * math.sin(index * 0.83)))
        for index in range(WINDOW_DAYS)
    ]
    for index, value in {8: 11, 27: 9, 46: 13, 67: 10, 82: 12}.items():
        values[index] = value
    return [Contribution(start + timedelta(days=index), count) for index, count in enumerate(values)]


def nice_ceiling(value: int) -> int:
    if value <= 4:
        return 4
    magnitude = 10 ** math.floor(math.log10(value))
    normalized = value / magnitude
    step = 2 if normalized <= 2 else 5 if normalized <= 5 else 10
    return int(step * magnitude)


def polyline_path(points: Sequence[tuple[float, float]]) -> str:
    if not points:
        return ""
    return "M " + " L ".join(f"{x:.2f} {y:.2f}" for x, y in points)


def text_element(
    x: float,
    y: float,
    value: str,
    *,
    size: int,
    fill: str,
    weight: int = 400,
    anchor: str = "start",
    family: str = "sans",
    tracking: float = 0,
) -> str:
    font = (
        "'SFMono-Regular',Consolas,'Liberation Mono',monospace"
        if family == "mono"
        else "'Segoe UI',system-ui,-apple-system,sans-serif"
    )
    return (
        f'<text x="{x}" y="{y}" fill="{fill}" font-family="{font}" '
        f'font-size="{size}" font-weight="{weight}" text-anchor="{anchor}" '
        f'letter-spacing="{tracking}">{escape(value)}</text>'
    )


def render_svg(username: str, contributions: Sequence[Contribution]) -> str:
    if len(contributions) != WINDOW_DAYS:
        raise ValueError(f"Expected {WINDOW_DAYS} contribution days, received {len(contributions)}")

    total = sum(item.count for item in contributions)
    total_text = f"{total:,}"
    active_days = sum(item.count > 0 for item in contributions)
    peak = max(item.count for item in contributions)
    peak_index = max(range(len(contributions)), key=lambda index: contributions[index].count)
    chart_ceiling = nice_ceiling(peak)

    chart_x = 328
    chart_y = 64
    chart_width = 816
    chart_height = 202
    baseline = chart_y + chart_height
    points = [
        (
            chart_x + index * chart_width / (WINDOW_DAYS - 1),
            baseline - item.count * chart_height / chart_ceiling,
        )
        for index, item in enumerate(contributions)
    ]
    line_path = polyline_path(points)
    area_path = f"{line_path} L {points[-1][0]:.2f} {baseline} L {points[0][0]:.2f} {baseline} Z"

    parts: list[str] = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{WIDTH}" height="{HEIGHT}" viewBox="0 0 {WIDTH} {HEIGHT}" role="img" aria-labelledby="title description">',
        f'<title id="title">@{escape(username)} GitHub contribution signal</title>',
        f'<desc id="description">A 90-day line graph showing {total} contributions across {active_days} active days. The busiest day had {peak} contributions.</desc>',
        f'<rect width="{WIDTH}" height="{HEIGHT}" rx="12" fill="{COLORS["background"]}"/>',
        f'<rect x="16" y="16" width="1168" height="308" rx="8" fill="{COLORS["surface"]}" stroke="{COLORS["rule"]}"/>',
        f'<line x1="292" y1="40" x2="292" y2="300" stroke="{COLORS["rule"]}"/>',
        text_element(42, 70, f"@{username}", size=13, fill=COLORS["accent"], weight=600, family="mono"),
        text_element(42, 113, "Contribution", size=28, fill=COLORS["text"], weight=650),
        text_element(42, 145, "signal", size=28, fill=COLORS["text"], weight=650),
        text_element(42, 179, "Last 90 days", size=14, fill=COLORS["muted"]),
        text_element(42, 228, total_text, size=22, fill=COLORS["text"], weight=600, family="mono"),
        text_element(42 + max(70, len(total_text) * 15 + 10), 228, "contributions", size=13, fill=COLORS["muted"]),
        text_element(42, 260, str(active_days), size=15, fill=COLORS["text"], weight=600, family="mono"),
        text_element(73, 260, "active days", size=13, fill=COLORS["muted"]),
        text_element(42, 290, str(peak), size=15, fill=COLORS["text"], weight=600, family="mono"),
        text_element(73, 290, "peak day", size=13, fill=COLORS["muted"]),
        text_element(chart_x, 46, "DAILY CONTRIBUTIONS", size=11, fill=COLORS["muted"], weight=600, family="mono", tracking=1.4),
        text_element(chart_x + chart_width - 154, 46, f"THROUGH {contributions[-1].day.strftime('%b %d, %Y').upper()}", size=11, fill=COLORS["muted"], weight=500, family="mono", tracking=0.7),
    ]

    for fraction in (0, 0.25, 0.5, 0.75, 1):
        value = round(chart_ceiling * (1 - fraction))
        y = chart_y + chart_height * fraction
        parts.append(
            f'<line x1="{chart_x}" y1="{y:.2f}" x2="{chart_x + chart_width}" y2="{y:.2f}" stroke="{COLORS["rule"]}" stroke-width="1"/>'
        )
        parts.append(
            text_element(chart_x - 14, y + 4, str(value), size=10, fill=COLORS["muted"], anchor="end", family="mono")
        )

    for index in range(0, WINDOW_DAYS, 14):
        x = points[index][0]
        parts.append(
            f'<line x1="{x:.2f}" y1="{chart_y}" x2="{x:.2f}" y2="{baseline}" stroke="{COLORS["rule"]}" stroke-width="1" stroke-dasharray="2 7"/>'
        )
        parts.append(
            text_element(x, 294, contributions[index].day.strftime("%b %d").upper(), size=10, fill=COLORS["muted"], anchor="middle", family="mono", tracking=0.5)
        )

    parts.extend(
        [
            f'<path d="{area_path}" fill="{COLORS["accent"]}" fill-opacity="0.10"/>',
            f'<path d="{line_path}" fill="none" stroke="{COLORS["accent"]}" stroke-width="2.5" stroke-linejoin="round" stroke-linecap="round"/>',
            f'<circle cx="{points[peak_index][0]:.2f}" cy="{points[peak_index][1]:.2f}" r="4" fill="{COLORS["surface"]}" stroke="{COLORS["accent"]}" stroke-width="2"/>',
            f'<circle cx="{points[-1][0]:.2f}" cy="{points[-1][1]:.2f}" r="4" fill="{COLORS["accent"]}"/>',
            text_element(points[-1][0] - 49, max(chart_y + 15, points[-1][1] - 12), "LATEST", size=10, fill=COLORS["accent"], weight=600, family="mono", tracking=0.7),
            "</svg>",
        ]
    )
    return "\n".join(parts) + "\n"


def write_site(output: Path, svg: str) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(svg, encoding="utf-8")
    (output.parent / ".nojekyll").touch()
    (output.parent / "index.html").write_text(
        """<!doctype html>
<html lang="en">
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Shan Padayhag - GitHub activity</title>
<style>
  html { color-scheme: dark; background: #0b1120; }
  body { min-height: 100dvh; margin: 0; display: grid; place-items: center; padding: 24px; box-sizing: border-box; }
  img { display: block; width: min(1200px, 100%); height: auto; }
</style>
<img src="activity.svg" alt="Shan Padayhag GitHub activity graph">
</html>
""",
        encoding="utf-8",
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--username", default="shanpadayhag")
    parser.add_argument("--output", type=Path, default=Path("site/activity.svg"))
    parser.add_argument("--sample", action="store_true", help="Render deterministic local preview data")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.sample:
        contributions = sample_contributions()
    else:
        token = os.environ.get("GITHUB_TOKEN")
        if not token:
            raise RuntimeError("GITHUB_TOKEN is required unless --sample is used")
        contributions = fetch_contributions(args.username, token)
    write_site(args.output, render_svg(args.username, contributions))


if __name__ == "__main__":
    main()
