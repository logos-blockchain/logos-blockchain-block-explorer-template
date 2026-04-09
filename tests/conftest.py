"""Pytest configuration and fixtures."""

import sys
from pathlib import Path

import pytest

# Add src directory to path for imports
src_path = Path(__file__).parent.parent / "src"
if str(src_path) not in sys.path:
    sys.path.insert(0, str(src_path))


@pytest.fixture(scope="session")
def event_loop_policy():
    """Use default event loop policy."""
    import asyncio

    return asyncio.DefaultEventLoopPolicy()
