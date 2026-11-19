"""Unit tests for the 2D Terminal UI visualizer (`chesscrypt.viewer`)."""

import chess
from chesscrypt.dictionary import get_position_dictionary
from chesscrypt.encoder import encode_text
from chesscrypt.viewer import (
    format_dictionary_grid,
    format_frame_2d,
    play_2d_terminal_match,
    render_board_2d_lines,
    render_progress_bar,
    visible_len,
)


def test_render_board_2d_lines_ascii_and_color():
    board = chess.Board()
    move = chess.Move.from_uci("d2d3")
    board.push(move)

    ascii_lines = render_board_2d_lines(board, last_move=move, use_color=False)
    assert len(ascii_lines) == 11
    joined_ascii = "\n".join(ascii_lines)
    assert "[P]" in joined_ascii  # Highlighted d3 pawn

    color_lines = render_board_2d_lines(board, last_move=move, use_color=True)
    assert len(color_lines) == 11
    joined_color = "\n".join(color_lines)
    assert "♙" in joined_color
    assert visible_len(color_lines[1]) > 20


def test_render_progress_bar():
    p_plain = render_progress_bar(10, 20, width=10, use_color=False)
    assert "[#####.....]  50% (10/20)" in p_plain

    p_color = render_progress_bar(20, 20, width=10, use_color=True)
    assert "100%" in p_color
    assert "█" in p_color


def test_format_dictionary_grid_highlights_chosen_move():
    board = chess.Board()
    entries = get_position_dictionary(board)
    rows_plain = format_dictionary_grid(entries, chosen_index=8, columns=4, use_color=False)
    joined_plain = "\n".join(rows_plain)
    assert ">>[ 8] d3   (d2d3)<<" in joined_plain

    rows_color = format_dictionary_grid(entries, chosen_index=8, columns=4, use_color=True)
    joined_color = "\n".join(rows_color)
    assert "▶[ 8] d3   (d2d3)◀" in joined_color


def test_format_frame_2d_includes_hud_and_dictionary():
    game = encode_text("Hello World")[0]
    board = chess.Board()
    dict_entries = get_position_dictionary(board)
    move = chess.Move.from_uci(game.traces[0].uci)
    board.push(move)

    frame = format_frame_2d(
        board,
        game.traces[0],
        total_plies=len(game.traces),
        white_bot="RookCipherBot",
        black_bot="PawnVaultBot",
        last_move=move,
        dictionary_entries=dict_entries,
        all_traces=game.traces,
        use_color=False,
    )
    assert "RookCipherBot" in frame
    assert "PawnVaultBot" in frame
    assert "1. d3 (d2d3)" in frame
    assert "Position Move Dictionary at Ply 1" in frame
    assert ">>[ 8] d3   (d2d3)<<" in frame


def test_play_2d_terminal_match_all_plies_mode(capsys):
    game = encode_text("Hi")[0]
    play_2d_terminal_match(
        game,
        delay=0.0,
        show_all_plies=True,
        use_color=False,
        animate_in_place=False,
    )
    out = capsys.readouterr().out
    assert "[2D Board — Ply 1/" in out
    assert "Position Move Dictionary at Ply 1" in out
