"""Opt-in contract test against the heat map rendered on github.com.

Run with:
    RUN_LIVE_GITHUB_TESTS=1 GITHUB_TOKEN=... python -m unittest \
        tests/test_live_github_accuracy.py -v
"""

from __future__ import annotations

import importlib.util
import os
import re
import sys
import unittest
from datetime import date
from html.parser import HTMLParser
from pathlib import Path
from urllib.request import Request, urlopen


USERNAME = "shanpadayhag"
REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
RENDERER_PATH = REPOSITORY_ROOT / ".github" / "scripts" / "generate_activity_graph.py"


def load_renderer():
    spec = importlib.util.spec_from_file_location(
        "live_activity_graph_renderer", RENDERER_PATH
    )
    if spec is None or spec.loader is None:
        raise RuntimeError("Unable to load the activity graph renderer")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


renderer = load_renderer()


class GitHubHeatMapParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.dates_by_cell: dict[str, date] = {}
        self.counts_by_cell: dict[str, int] = {}
        self._tooltip_cell: str | None = None
        self._tooltip_text: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = dict(attrs)
        if tag == "td" and attributes.get("data-date") and attributes.get("id"):
            self.dates_by_cell[attributes["id"]] = date.fromisoformat(
                attributes["data-date"]
            )
        elif tag == "tool-tip" and attributes.get("for"):
            self._tooltip_cell = attributes["for"]
            self._tooltip_text = []

    def handle_data(self, data: str) -> None:
        if self._tooltip_cell is not None:
            self._tooltip_text.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag != "tool-tip" or self._tooltip_cell is None:
            return
        label = "".join(self._tooltip_text).strip()
        match = re.match(r"(No|[\d,]+) contributions?", label)
        if match:
            count = (
                0
                if match.group(1) == "No"
                else int(match.group(1).replace(",", ""))
            )
            self.counts_by_cell[self._tooltip_cell] = count
        self._tooltip_cell = None
        self._tooltip_text = []

    def contributions(self) -> dict[date, int]:
        return {
            contribution_date: self.counts_by_cell[cell]
            for cell, contribution_date in self.dates_by_cell.items()
            if cell in self.counts_by_cell
        }


@unittest.skipUnless(
    os.environ.get("RUN_LIVE_GITHUB_TESTS") == "1" and os.environ.get("GITHUB_TOKEN"),
    "set RUN_LIVE_GITHUB_TESTS=1 and GITHUB_TOKEN to compare with github.com",
)
class LiveGitHubAccuracyTests(unittest.TestCase):
    def test_graphql_daily_counts_match_github_profile_heat_map(self) -> None:
        token = os.environ["GITHUB_TOKEN"]
        graphql_days = renderer.fetch_contributions(USERNAME, token)

        request = Request(
            f"https://github.com/users/{USERNAME}/contributions",
            headers={
                "Accept": "text/html",
                "User-Agent": "shanpadayhag-activity-graph-test",
            },
        )
        with urlopen(request, timeout=30) as response:
            parser = GitHubHeatMapParser()
            parser.feed(response.read().decode("utf-8"))
        heat_map = parser.contributions()

        self.assertGreaterEqual(len(heat_map), renderer.WINDOW_DAYS)
        expected = [(item.day, heat_map[item.day]) for item in graphql_days]
        actual = [(item.day, item.count) for item in graphql_days]
        self.assertEqual(
            actual,
            expected,
            "GraphQL contribution days differ from GitHub's public profile heat map",
        )


if __name__ == "__main__":
    unittest.main()
