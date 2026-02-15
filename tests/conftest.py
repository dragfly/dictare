"""Shared pytest configuration and hooks."""

from __future__ import annotations

import pytest


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption(
        "--openvip-url",
        default=None,
        help="URL of a running OpenVIP server to test against (e.g. http://localhost:8770)",
    )


def pytest_collection_modifyitems(
    config: pytest.Config,
    items: list[pytest.Item],
) -> None:
    """Auto-skip @pytest.mark.internal tests when --openvip-url is set."""
    url = config.getoption("--openvip-url")
    if url is None:
        return
    skip = pytest.mark.skip(reason=f"internal test, skipped with --openvip-url={url}")
    for item in items:
        if "internal" in item.keywords:
            item.add_marker(skip)
