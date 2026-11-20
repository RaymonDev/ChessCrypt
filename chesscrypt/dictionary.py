"""Deterministic Position Move Dictionary for mapping chess moves <-> integer indices."""

from __future__ import annotations

from dataclasses import dataclass
import math
import chess


PIECE_NAMES = {
    chess.PAWN: "Pawn",
    chess.KNIGHT: "Knight",
    chess.BISHOP: "Bishop",
    chess.ROOK: "Rook",
    chess.QUEEN: "Queen",
    chess.KING: "King",
}


@dataclass(frozen=True)
class MoveEntry:
    """A single entry in a position's deterministic move dictionary."""

    index: int
    total_moves: int
    move: chess.Move
    uci: str
    san: str
    piece_name: str
    from_square: str
    to_square: str

    @property
    def bits_capacity(self) -> float:
        """Information capacity (in bits) of choosing 1 move out of total_moves."""
        return math.log2(self.total_moves) if self.total_moves > 1 else 0.0


# A position can only recur after both sides have made at least two reversible
# moves (e.g. Nf3 Nf6 Ng1 Ng8), so threefold repetition cannot be claimed while
# fewer than 4 plies have passed since the last capture or pawn move.
_MIN_PLIES_FOR_REPETITION = 4


def ends_game(board: chess.Board) -> bool:
    """Return True if the game is over or a draw can be claimed in `board`.

    Exactly equivalent to ``board.is_game_over(claim_draw=True)``, but skips
    python-chess's expensive threefold-repetition scan when no repetition is
    possible yet. That scan dominates encoding time, so this shortcut makes
    dictionary construction several times faster without changing its output.
    """
    if board.is_game_over() or board.can_claim_fifty_moves():
        return True
    return (
        board.halfmove_clock >= _MIN_PLIES_FOR_REPETITION
        and board.can_claim_threefold_repetition()
    )


def _is_safe_continuation(board: chess.Board, move: chess.Move) -> bool:
    """Return True if pushing `move` does not end the game and leaves at least 1 non-terminal reply."""
    board.push(move)
    try:
        if ends_game(board):
            return False
        for reply in board.legal_moves:
            board.push(reply)
            over = ends_game(board)
            board.pop()
            if not over:
                return True
        return False
    finally:
        board.pop()


def get_safe_legal_moves(board: chess.Board) -> list[chess.Move]:
    """Return deterministically sorted (by UCI) safe legal moves for `board`.

    Filters out moves that immediately end the game (checkmate, stalemate, draw)
    or force the next player into an unavoidable game-over on the very next ply.
    Both encoder and decoder call this function identically at every ply.
    """
    all_legal = sorted(board.legal_moves, key=lambda m: m.uci())
    if not all_legal:
        return []

    safe = [m for m in all_legal if _is_safe_continuation(board, m)]
    if safe:
        return safe

    # Fallback 1: any move that does not immediately end the game
    non_terminal = []
    for m in all_legal:
        board.push(m)
        if not ends_game(board):
            non_terminal.append(m)
        board.pop()
    if non_terminal:
        return non_terminal

    # Fallback 2: all legal moves sorted by UCI
    return all_legal


def get_position_dictionary(board: chess.Board) -> list[MoveEntry]:
    """Build the numbered Move Dictionary for the given chess board state."""
    moves = get_safe_legal_moves(board)
    total = len(moves)
    entries: list[MoveEntry] = []
    for idx, move in enumerate(moves):
        piece = board.piece_at(move.from_square)
        piece_name = PIECE_NAMES.get(piece.piece_type, "Unknown") if piece else "Unknown"
        entries.append(
            MoveEntry(
                index=idx,
                total_moves=total,
                move=move,
                uci=move.uci(),
                san=board.san(move),
                piece_name=piece_name,
                from_square=chess.square_name(move.from_square),
                to_square=chess.square_name(move.to_square),
            )
        )
    return entries


def format_dictionary_markdown(board: chess.Board | None = None) -> str:
    """Format the Move Dictionary of a board position as a Markdown table."""
    if board is None:
        board = chess.Board()
    entries = get_position_dictionary(board)
    turn_str = "White" if board.turn == chess.WHITE else "Black"
    cap = entries[0].bits_capacity if entries else 0.0
    lines = [
        f"**FEN:** `{board.fen()}`  ",
        f"**Turn:** {turn_str} | **Radix ($N$):** {len(entries)} legal moves | **Capacity:** {cap:.2f} bits/ply",
        "",
        "| Index (`i`) | UCI Move | SAN Move | Piece | From -> To |",
        "| :---: | :---: | :---: | :--- | :---: |",
    ]
    for e in entries:
        lines.append(
            f"| `{e.index:2d}` | `{e.uci}` | **{e.san}** | {e.piece_name} | `{e.from_square} -> {e.to_square}` |"
        )
    return "\n".join(lines)
