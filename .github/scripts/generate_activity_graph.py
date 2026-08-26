from __future__ import annotations

import argparse
import json
import os
import urllib.request
from datetime import datetime, timedelta, timezone
from html import escape
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
OUTPUT_DIRECTORY = ROOT / "site"
GRAPHQL_URL = "https://api.github.com/graphql"


def fetch_contributions(username: str, token: str) -> list[tuple[str, int]]:
    now = datetime.now(timezone.utc)
    start = now - timedelta(days=90)
    query = """
      query($login: String!, $from: DateTime!, $to: DateTime!) {
        user(login: $login) {
          contributionsCollection(from: $from, to: $to) {
            contributionCalendar {
              weeks {
                contributionDays {
                  date
                  contributionCount
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
                "login": username,
                "from": start.isoformat(),
                "to": now.isoformat(),
            },
        }
    ).encode()
    request = urllib.request.Request(
        GRAPHQL_URL,
        data=payload,
        headers={
            "Authorization": f"bearer {token}",
            "Content-Type": "application/json",
            "User-Agent": "shanpadayhag-activity-graph",
        },
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        result = json.load(response)

    if "errors" in result:
        raise RuntimeError(result["errors"])

    weeks = result["data"]["user"]["contributionsCollection"]["contributionCalendar"]["weeks"]
    contribution_days = [
        (day["date"], day["contributionCount"])
        for week in weeks
        for day in week["contributionDays"]
    ]
    return sorted(dict(contribution_days).items())


def build_graph_svg(username: str, contributions: list[tuple[str, int]]) -> str:
    width, height = 900, 270
    left, right, top, bottom = 62, 34, 52, 50
    graph_width = width - left - right
    graph_height = height - top - bottom
    maximum = max((count for _, count in contributions), default=1)
    maximum = max(maximum, 1)

    points = []
    for index, (_, count) in enumerate(contributions):
        x = left + (graph_width * index / max(len(contributions) - 1, 1))
        y = top + graph_height - (count / maximum * graph_height)
        points.append((x, y))

    line = " ".join(f"{x:.1f},{y:.1f}" for x, y in points)
    area = f"{left},{top + graph_height} {line} {left + graph_width},{top + graph_height}"
    gridlines = "".join(
        f'<line x1="{left}" y1="{top + graph_height * step / 4:.1f}" x2="{left + graph_width}" y2="{top + graph_height * step / 4:.1f}" />'
        for step in range(5)
    )
    labels = []
    previous_month = ""
    for index, (date, _) in enumerate(contributions):
        month = date[:7]
        if month != previous_month:
            previous_month = month
            x = left + (graph_width * index / max(len(contributions) - 1, 1))
            labels.append(f'<text x="{x:.1f}" y="{height - 20}" text-anchor="middle">{date[5:7]}/{date[2:4]}</text>')

    total = sum(count for _, count in contributions)
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}" role="img" aria-labelledby="title description">
  <title id="title">{escape(username)} GitHub activity</title>
  <desc id="description">A line chart of GitHub contributions over the last 90 days.</desc>
  <rect width="100%" height="100%" rx="12" fill="#1a1b27" />
  <text x="{left}" y="28" fill="#c0caf5" font-family="system-ui, sans-serif" font-size="20" font-weight="600">Recent GitHub activity</text>
  <text x="{left}" y="{height - 20}" fill="#7aa2f7" font-family="system-ui, sans-serif" font-size="12">{total} contributions in the last 90 days</text>
  <g stroke="#2f3549" stroke-width="1">{gridlines}</g>
  <polygon points="{area}" fill="#7aa2f7" opacity="0.20" />
  <polyline points="{line}" fill="none" stroke="#7aa2f7" stroke-width="3" stroke-linejoin="round" stroke-linecap="round" />
  <g fill="#565f89" font-family="system-ui, sans-serif" font-size="11">{''.join(labels)}</g>
</svg>'''


def write_site(svg: str) -> None:
    OUTPUT_DIRECTORY.mkdir(exist_ok=True)
    (OUTPUT_DIRECTORY / ".nojekyll").write_text("")
    (OUTPUT_DIRECTORY / "activity.svg").write_text(svg)
    (OUTPUT_DIRECTORY / "index.html").write_text(
        "<main><img src=\"activity.svg\" alt=\"GitHub activity graph\"></main>\n"
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--username", default="shanpadayhag")
    arguments = parser.parse_args()
    token = os.environ.get("GITHUB_TOKEN")
    if not token:
        raise SystemExit("GITHUB_TOKEN is required to generate the activity graph.")
    write_site(build_graph_svg(arguments.username, fetch_contributions(arguments.username, token)))


if __name__ == "__main__":
    main()
