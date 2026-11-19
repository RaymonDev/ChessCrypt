"""Unit tests for the Position Move Dictionary (`chesscrypt.dictionary`)."""

import math
import chess
from chesscrypt.dictionary import (
    format_dictionary_markdown,
    get_position_dictionary,
    get_safe_legal_moves,
)


def test_starting_position_dictionary_has_20_sorted_moves():
    board = chess.Board()
    entries = get_position_dictionary(board)
    assert len(entries) == 20

    # Verify strict lexicographical sorting by UCI
    ucis = [e.uci for e in entries]
    assert ucis == sorted(ucis)
    assert entries[0].index == 0
    assert entries[0].uci == "a2a3"
    assert entries[0].san == "a3"
    assert entries[0].piece_name == "Pawn"

    assert entries[8].index == 8
    assert entries[8].uci == "d2d3"
    assert entries[8].san == "d3"

    assert entries[19].index == 19
    assert entries[19].uci == "h2h4"
    assert entries[19].san == "h4"
    assert math.isclose(entries[0].bits_capacity, math.log2(20))


def test_safe_legal_moves_filters_out_immediate_checkmate():
    # Fool's Mate setup: 1. f3 e5 2. g4 — Black has Qh4# (d8h4) as a legal move
    board = chess.Board()
    for san in ["f3", "e5", "g4"]:
        board.push_san(san)

    all_ucis = {m.uci() for m in board.legal_moves}
    assert "d8h4" in all_ucis  # Qh4# is legal

    safe_ucis = {m.uci() for m in get_safe_legal_moves(board)}
    # d8h4 immediately ends the game by checkmate, so it must be excluded
    assert "d8h4" not in safe_ucis
    assert len(safe_ucis) == len(all_ucis) - 1


def test_format_dictionary_markdown_contains_table():
    md = format_dictionary_markdown(chess.Board())
    assert "| Index (`i`) | UCI Move | SAN Move |" in md
    assert "| ` 8` | `d2d3` | **d3** |" in md
    assert "| `19` | `h2h4` | **h4** |" in md
