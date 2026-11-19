"""Unit tests for the Mixed-Radix Chess Encoder & Decoder (`chesscrypt.encoder`)."""

import pytest
from chesscrypt.encoder import (
    bigint_to_bytes,
    bytes_to_bigint,
    decode_games,
    decode_moves,
    decode_pgn,
    encode_bytes,
    encode_text,
)


@pytest.mark.parametrize(
    "payload",
    [
        b"",
        b"\x00",
        b"\x00\x00\x00",
        b"\x00\x01\x00",
        b"Hello World",
        bytes(range(32)),
    ],
)
def test_bytes_bigint_bijection(payload: bytes):
    v = bytes_to_bigint(payload)
    assert v >= 1
    assert bigint_to_bytes(v) == payload


def test_hello_world_encoding_and_decoding():
    games = encode_text("Hello World")
    assert len(games) == 1
    game = games[0]

    # Verify exact deterministic encoding of "Hello World"
    assert game.chunk_bytes == b"Hello World"
    assert game.initial_bigint == 397006627910227602516896868
    assert len(game.traces) == 20
    assert game.san_moves == [
        "d3", "b6", "f3", "f5", "Qd2", "a6", "c3", "c6", "Qc2", "h6",
        "Kf2", "Qc7", "a3", "e6", "g3", "f4", "Qa4", "Ra7", "e4", "Rb7",
    ]

    # Decode from UCI moves
    res_uci = decode_moves(game.uci_moves)
    assert res_uci.text == "Hello World"
    assert res_uci.recovered_bigints == [397006627910227602516896868]

    # Decode from SAN moves
    res_san = decode_moves(game.san_moves)
    assert res_san.text == "Hello World"

    # Decode from exported PGN
    pgn = game.to_pgn()
    res_pgn = decode_pgn(pgn)
    assert res_pgn.text == "Hello World"


def test_hello_world_encrypted_with_passphrase():
    games = encode_text("Hello World", passphrase="my-secret-passphrase")
    assert len(games) == 1
    pgn = games[0].to_pgn()

    decoded = decode_pgn(pgn, passphrase="my-secret-passphrase")
    assert decoded.text == "Hello World"


def test_leading_zero_bytes_preserved_across_chess_moves():
    raw = b"\x00\x00Hello\x00\x00"
    games = encode_bytes(raw)
    decoded = decode_games([g.uci_moves for g in games])
    assert decoded.decrypted_bytes == raw


def test_multi_game_chunking_for_large_payload():
    long_message = (
        "ChessCrypt splits larger payloads across multiple unrated bot games "
        "and reassembles them losslessly in chronological round order!"
    )
    games = encode_text(long_message, max_chunk_bytes=24)
    assert len(games) > 4

    combined_pgn = "\n\n".join(g.to_pgn() for g in games)
    decoded = decode_pgn(combined_pgn)
    assert decoded.text == long_message


def test_invalid_move_raises_value_error():
    with pytest.raises(ValueError, match="not in the valid ChessCrypt"):
        decode_moves(["e2e5"])
