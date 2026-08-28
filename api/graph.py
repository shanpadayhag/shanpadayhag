"""Serve Shan Padayhag's GitHub activity graph as a Vercel Function."""

from __future__ import annotations

import importlib.util
import os
import sys
from http.server import BaseHTTPRequestHandler
from pathlib import Path
from types import ModuleType


USERNAME = "shanpadayhag"
RENDERER_PATH = (
    Path(__file__).resolve().parents[1]
    / ".github"
    / "scripts"
    / "generate_activity_graph.py"
)


def load_renderer() -> ModuleType:
    """Load the shared renderer used by the GitHub Pages workflow."""
    spec = importlib.util.spec_from_file_location("activity_graph_renderer", RENDERER_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError("Unable to load the activity graph renderer")

    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


renderer = load_renderer()


class handler(BaseHTTPRequestHandler):
    """Return a freshly rendered SVG for the fixed GitHub account."""

    def do_GET(self) -> None:
        token = os.environ.get("GITHUB_TOKEN")
        if not token:
            self.send_error(500, "GITHUB_TOKEN is not configured")
            return

        try:
            contributions = renderer.fetch_contributions(USERNAME, token)
            svg = renderer.render_svg(USERNAME, contributions).encode("utf-8")
        except (RuntimeError, ValueError) as error:
            self.send_error(502, f"Unable to render activity graph: {error}")
            return

        self.send_response(200)
        self.send_header("Content-Type", "image/svg+xml; charset=utf-8")
        self.send_header("Content-Length", str(len(svg)))
        self.send_header("Cache-Control", "no-store, max-age=0")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(svg)
