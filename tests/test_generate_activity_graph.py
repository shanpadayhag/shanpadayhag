"""Accuracy tests for the GitHub contribution graph data and SVG summary."""

from __future__ import annotations

import importlib.util
import io
import json
import sys
import unittest
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import patch


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
RENDERER_PATH = REPOSITORY_ROOT / ".github" / "scripts" / "generate_activity_graph.py"


def load_renderer():
    spec = importlib.util.spec_from_file_location(
        "tested_activity_graph_renderer", RENDERER_PATH
    )
    if spec is None or spec.loader is None:
        raise RuntimeError("Unable to load the activity graph renderer")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


renderer = load_renderer()


def calendar_payload(
    start: date,
    counts: list[int],
    *,
    reported_total: int | None = None,
) -> dict[str, object]:
    days = [
        {
            "date": (start + timedelta(days=offset)).isoformat(),
            "contributionCount": count,
        }
        for offset, count in enumerate(counts)
    ]
    return {
        "totalContributions": sum(counts) if reported_total is None else reported_total,
        "weeks": [{"contributionDays": days}],
    }


class FetchContributionsTests(unittest.TestCase):
    def test_fetch_preserves_every_github_day_and_uses_exact_utc_window(self) -> None:
        today = date(2026, 9, 1)
        start = today - timedelta(days=renderer.WINDOW_DAYS - 1)
        counts = [0] * renderer.WINDOW_DAYS
        counts[0], counts[42], counts[82], counts[-1] = 7, 2, 37, 2
        response_body = {
            "data": {
                "user": {
                    "contributionsCollection": {
                        "contributionCalendar": calendar_payload(start, counts)
                    }
                }
            }
        }

        response = io.BytesIO(json.dumps(response_body).encode("utf-8"))
        with patch.object(renderer, "urlopen", return_value=response) as mocked_urlopen:
            contributions = renderer.fetch_contributions(
                "shanpadayhag", "test-token", today=today
            )

        request = mocked_urlopen.call_args.args[0]
        request_payload = json.loads(request.data)
        self.assertEqual(
            request_payload["variables"],
            {
                "username": "shanpadayhag",
                "from": "2026-06-04T00:00:00Z",
                "to": "2026-09-01T23:59:59Z",
            },
        )
        self.assertIn("totalContributions", request_payload["query"])
        self.assertEqual(
            contributions,
            [
                renderer.Contribution(start + timedelta(days=offset), count)
                for offset, count in enumerate(counts)
            ],
        )

    def test_missing_day_is_rejected_instead_of_becoming_false_zero(self) -> None:
        start = date(2026, 6, 4)
        calendar = calendar_payload(start, [3, 0, 4])
        calendar["weeks"][0]["contributionDays"].pop(1)

        with self.assertRaisesRegex(
            RuntimeError, "omitted contribution data for 2026-06-05"
        ):
            renderer.parse_contribution_calendar(
                calendar, start, start + timedelta(days=2)
            )

    def test_duplicate_day_is_rejected(self) -> None:
        start = date(2026, 6, 4)
        calendar = calendar_payload(start, [3, 4])
        calendar["weeks"][0]["contributionDays"].append(
            {"date": start.isoformat(), "contributionCount": 3}
        )

        with self.assertRaisesRegex(RuntimeError, "duplicate contribution data"):
            renderer.parse_contribution_calendar(
                calendar, start, start + timedelta(days=1)
            )

    def test_reported_total_must_equal_sum_of_daily_counts(self) -> None:
        start = date(2026, 6, 4)
        calendar = calendar_payload(start, [3, 0, 4], reported_total=8)

        with self.assertRaisesRegex(RuntimeError, "8 reported, 7 calculated"):
            renderer.parse_contribution_calendar(
                calendar, start, start + timedelta(days=2)
            )


class RenderSvgAccuracyTests(unittest.TestCase):
    def test_svg_summary_is_calculated_from_the_same_daily_counts(self) -> None:
        start = date(2026, 6, 4)
        counts = [0] * renderer.WINDOW_DAYS
        counts[0], counts[42], counts[82], counts[-1] = 7, 2, 37, 2
        contributions = [
            renderer.Contribution(start + timedelta(days=offset), count)
            for offset, count in enumerate(counts)
        ]

        svg = renderer.render_svg("shanpadayhag", contributions)

        self.assertIn(
            "A 90-day line graph showing 48 contributions across 4 active days. "
            "The busiest day had 37 contributions.",
            svg,
        )
        self.assertIn("THROUGH SEP 01, 2026", svg)

    def test_renderer_rejects_out_of_order_or_gapped_dates(self) -> None:
        start = date(2026, 6, 4)
        contributions = [
            renderer.Contribution(start + timedelta(days=offset), 0)
            for offset in range(renderer.WINDOW_DAYS)
        ]
        contributions[20] = renderer.Contribution(start + timedelta(days=21), 0)

        with self.assertRaisesRegex(ValueError, "chronological and contiguous"):
            renderer.render_svg("shanpadayhag", contributions)


if __name__ == "__main__":
    unittest.main()
