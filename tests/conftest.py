"""Shared pytest fixtures."""

import pytest


@pytest.fixture(autouse=True)
def _isolate_from_local_env(monkeypatch):
    """Keep a developer's local .env from leaking a passphrase or tokens into tests.

    `load_dotenv()` never overrides variables that are already set, so pinning
    them to empty strings makes the CLI behave as if nothing were configured.
    """
    for var in (
        "CHESSCRYPT_PASSPHRASE",
        "LICHESS_WHITE_BOT_TOKEN",
        "LICHESS_BLACK_BOT_TOKEN",
        "LICHESS_WHITE_BOT_NAME",
        "LICHESS_BLACK_BOT_NAME",
    ):
        monkeypatch.setenv(var, "")
