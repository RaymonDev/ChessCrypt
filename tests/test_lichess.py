"""Unit and integration tests for Lichess Bot API client and two-bot match orchestrator."""

from unittest.mock import MagicMock
import pytest

from chesscrypt.lichess import (
    BOT_BLACK_NAME,
    BOT_WHITE_NAME,
    LichessAPIError,
    LichessBotClient,
    LichessMatchOrchestrator,
    SimulatedLichessServer,
)


def test_simulated_unrated_bot_match_stores_and_fetches_hello_world():
    server = SimulatedLichessServer()
    white = server.create_client(BOT_WHITE_NAME)
    black = server.create_client(BOT_BLACK_NAME)

    orchestrator = LichessMatchOrchestrator(white, black)
    w_acc, b_acc = orchestrator.ensure_bots_ready()
    assert w_acc["username"] == "RookCipherBot"
    assert w_acc["title"] == "BOT"
    assert b_acc["username"] == "PawnVaultBot"
    assert b_acc["title"] == "BOT"

    records = orchestrator.store_text("Hello World")
    assert len(records) == 1
    rec = records[0]
    assert rec.rated is False
    assert rec.white_bot == "RookCipherBot"
    assert rec.black_bot == "PawnVaultBot"
    assert rec.plies_played == 20
    assert "1. d3 b6 2. f3 f5" in rec.pgn

    decoded = orchestrator.fetch_and_decode([rec.game_id])
    assert decoded.text == "Hello World"


def test_rated_challenge_is_rejected():
    server = SimulatedLichessServer()
    white = server.create_client(BOT_WHITE_NAME)
    with pytest.raises(ValueError, match="unrated"):
        white.create_challenge(BOT_BLACK_NAME, rated=True)


def test_wrong_turn_or_illegal_move_rejected_in_simulator():
    server = SimulatedLichessServer()
    white = server.create_client(BOT_WHITE_NAME)
    black = server.create_client(BOT_BLACK_NAME)
    ch = white.create_challenge(BOT_BLACK_NAME, rated=False)
    gid = ch["id"]
    black.accept_challenge(gid)

    # Black trying to move on White's turn
    with pytest.raises(LichessAPIError, match="turn"):
        black.make_move(gid, "e7e5")

    # White trying an illegal move
    with pytest.raises(LichessAPIError, match="Illegal move"):
        white.make_move(gid, "e2e5")


def test_http_lichess_bot_client_endpoints():
    session = MagicMock()
    client = LichessBotClient("lip_test_token", username=BOT_WHITE_NAME, session=session)

    # 1. get_account (not yet BOT) -> upgrade_to_bot
    resp_acc = MagicMock(status_code=200)
    resp_acc.json.return_value = {"id": "rookcipherbot", "username": BOT_WHITE_NAME, "title": None}
    resp_upg = MagicMock(status_code=200)
    session.get.return_value = resp_acc
    session.post.return_value = resp_upg

    assert client.upgrade_to_bot() is True
    session.post.assert_called_with(
        "https://lichess.org/api/bot/account/upgrade",
        timeout=15.0,
    )

    # 2. create_challenge (enforces rated="false")
    resp_ch = MagicMock(status_code=200)
    resp_ch.json.return_value = {"challenge": {"id": "g1234567", "rated": False}}
    session.post.return_value = resp_ch
    ch = client.create_challenge(BOT_BLACK_NAME, rated=False)
    assert ch["id"] == "g1234567"
    _, kwargs = session.post.call_args
    assert kwargs["data"]["rated"] == "false"

    # 3. make_move
    resp_mv = MagicMock(status_code=200)
    session.post.return_value = resp_mv
    assert client.make_move("g1234567", "d2d3") is True
    session.post.assert_called_with(
        "https://lichess.org/api/bot/game/g1234567/move/d2d3",
        timeout=15.0,
    )
