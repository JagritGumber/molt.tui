"""Shared fixtures and config for X agent evals."""

import pytest


def pytest_addoption(parser):
    parser.addoption(
        "--destructive",
        action="store_true",
        default=False,
        help="Run destructive evals (will post/delete real tweets)",
    )
    parser.addoption(
        "--cdp-port",
        default="9222",
        help="CDP port for Chrome connection (default: 9222)",
    )


def pytest_configure(config):
    config.addinivalue_line("markers", "destructive: marks tests that post/delete real tweets")
    config.addinivalue_line("markers", "browser: marks tests that need a CDP browser connection")
    config.addinivalue_line("markers", "llm: marks tests that need Z.ai LLM access")
    config.addinivalue_line("markers", "network: marks tests that need internet (HN/RSS)")


def pytest_collection_modifyitems(config, items):
    if not config.getoption("--destructive"):
        skip_destructive = pytest.mark.skip(reason="need --destructive flag to run")
        for item in items:
            if "destructive" in item.keywords:
                item.add_marker(skip_destructive)


@pytest.fixture
def cdp_port(request):
    return int(request.config.getoption("--cdp-port"))
