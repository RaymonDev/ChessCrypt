"""Rich 2D Terminal UI for watching ChessCrypt games and live Move Dictionary lookups."""

from __future__ import annotations

import os
import re
import sys
import time
import chess

from chesscrypt.dictionary import MoveEntry, get_position_dictionary
from chesscrypt.encoder import EncodedGame, PlyTrace

ANSI_ESCAPE_RE = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")

UNICODE_PIECES = {
    "P": "♙",
    "N": "♘",
    "B": "♗",
    "R": "♖",
    "Q": "♕",
    "K": "♔",
    "p": "♟",
    "n": "♞",
    "b": "♝",
    "r": "♜",
    "q": "♛",
    "k": "♚",
}

# ANSI truecolor helpers matching Lichess theme
RESET = "\033[0m"
BOLD = "\033[1m"
DIM = "\033[2m"
FG_BRIGHT = "\033[38;2;255;255;255m"
FG_MUTED = "\033[38;2;175;175;175m"
FG_BORDER = "\033[38;2;120;116;110m"
FG_GREEN = "\033[38;2;150;209;86m"
FG_CYAN = "\033[38;2;86;182;194m"
FG_GOLD = "\033[38;2;229;192;123m"
BG_BOT_BADGE = "\033[48;2;163;87;208m\033[1;38;2;255;255;255m"
BG_CHOSEN = "\033[48;2;98;153;36m\033[1;38;2;255;255;255m"


def enable_terminal_ansi() -> None:
    """Configure UTF-8 output and enable ANSI virtual terminal processing on Windows."""
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except Exception:
            pass
    if os.name == "nt":
        os.system("")


def visible_len(text: str) -> int:
    """Return the printable character width of a string (stripping ANSI codes)."""
    return len(ANSI_ESCAPE_RE.sub("", text))


def pad_ansi(text: str, width: int) -> str:
    """Pad an ANSI-styled string on the right to `width` visible characters."""
    vlen = visible_len(text)
    if vlen >= width:
        return text
    return text + (" " * (width - vlen))


def render_progress_bar(current: int, total: int, width: int = 20, *, use_color: bool = True) -> str:
    """Render a smooth progress bar for ply progress."""
    if total <= 0:
        return "[" + ("-" * width) + "] 0%"
    ratio = min(1.0, max(0.0, current / total))
    filled = int(round(ratio * width))
    empty = width - filled
    pct = int(round(ratio * 100))
    if not use_color:
        return f"[{'#' * filled}{'.' * empty}] {pct:3d}% ({current}/{total})"
    bar = f"{FG_GREEN}{'█' * filled}{FG_BORDER}{'░' * empty}{RESET}"
    return f"[{bar}] {BOLD}{pct:3d}%{RESET} ({current}/{total})"


def render_board_2d_lines(
    board: chess.Board,
    *,
    last_move: chess.Move | None = None,
    use_color: bool = True,
) -> list[str]:
    """Render a 2D 8x8 chessboard as a list of lines (with optional Lichess RGB ANSI colors)."""
    hi_squares = {last_move.from_square, last_move.to_square} if last_move else set()
    lines: list[str] = []

    if not use_color:
        lines.append("    +------------------------+")
        for rank in range(7, -1, -1):
            row_cells = []
            for file in range(8):
                sq = chess.square(file, rank)
                piece = board.piece_at(sq)
                symbol = piece.symbol() if piece else "."
                if sq in hi_squares:
                    row_cells.append(f"[{symbol}]")
                else:
                    row_cells.append(f" {symbol} ")
            lines.append(f"  {rank + 1} |{''.join(row_cells)}|")
        lines.append("    +------------------------+")
        lines.append("      a  b  c  d  e  f  g  h")
        return lines

    lines.append(f"    {FG_BORDER}╭────────────────────────╮{RESET}")
    for rank in range(7, -1, -1):
        row_str = f"  {FG_MUTED}{rank + 1}{RESET} {FG_BORDER}│{RESET}"
        for file in range(8):
            sq = chess.square(file, rank)
            is_light = (rank + file) % 2 == 1
            if sq in hi_squares:
                # Lichess green-yellow last-move highlight (#cdd26a / #aaa23a)
                bg = "\033[48;2;205;210;106m" if is_light else "\033[48;2;170;162;58m"
            else:
                # Lichess classic brown board (#f0d9b5 / #b58863)
                bg = "\033[48;2;240;217;181m" if is_light else "\033[48;2;181;136;99m"

            piece = board.piece_at(sq)
            if piece is None:
                cell = "   "
            else:
                sym = piece.symbol()
                fg = (
                    "\033[1;38;2;255;255;255m"
                    if piece.color == chess.WHITE
                    else "\033[1;38;2;20;20;20m"
                )
                glyph = UNICODE_PIECES.get(sym, sym)
                cell = f"{fg} {glyph} "
            row_str += f"{bg}{cell}{RESET}"
        row_str += f"{FG_BORDER}│{RESET}"
        lines.append(row_str)
    lines.append(f"    {FG_BORDER}╰────────────────────────╯{RESET}")
    lines.append(f"      {FG_MUTED}a  b  c  d  e  f  g  h{RESET}")
    return lines


def format_dictionary_grid(
    entries: list[MoveEntry],
    chosen_index: int | None,
    *,
    columns: int = 5,
    use_color: bool = True,
) -> list[str]:
    """Render the current ply's Position Move Dictionary as a compact multi-column grid."""
    if not entries:
        return ["  (No legal moves)"]

    cells: list[str] = []
    for e in entries:
        is_chosen = chosen_index is not None and e.index == chosen_index
        label = f"[{e.index:2d}] {e.san:<4s} ({e.uci})"
        if not use_color:
            cell = f">>{label}<<" if is_chosen else f"  {label}  "
            cells.append(f"{cell:<20s}")
        else:
            if is_chosen:
                cell = f"{BG_CHOSEN} ▶[{e.index:2d}] {e.san:<4s} ({e.uci})◀ {RESET}"
            else:
                cell = f"  {FG_CYAN}[{e.index:2d}]{RESET} {FG_BRIGHT}{e.san:<4s}{RESET} {FG_MUTED}({e.uci}){RESET}  "
            cells.append(pad_ansi(cell, 21))

    rows: list[str] = []
    for i in range(0, len(cells), columns):
        row = " ".join(cells[i : i + columns])
        rows.append("  " + row)
    return rows


def _format_move_ticker(traces: list[PlyTrace], up_to_ply: int, *, use_color: bool = True) -> str:
    """Format the PGN move ticker up to `up_to_ply`."""
    if up_to_ply <= 0 or not traces:
        return "—"
    tokens: list[str] = []
    subset = traces[:up_to_ply]
    for idx, t in enumerate(subset):
        is_latest = idx == len(subset) - 1
        prefix = f"{t.move_number}." if t.turn == "White" else ""
        move_txt = f"{prefix}{t.san}" if prefix else t.san
        if is_latest and use_color:
            tokens.append(f"{FG_GREEN}{BOLD}{move_txt}{RESET}")
        elif is_latest:
            tokens.append(f"[{move_txt}]")
        else:
            tokens.append(move_txt)

    # Keep the most recent moves visible if ticker gets long
    if len(tokens) > 10:
        tokens = ["..."] + tokens[-10:]
    return " ".join(tokens)


def format_frame_2d(
    board: chess.Board,
    trace: PlyTrace | None,
    *,
    total_plies: int,
    white_bot: str,
    black_bot: str,
    last_move: chess.Move | None = None,
    dictionary_entries: list[MoveEntry] | None = None,
    all_traces: list[PlyTrace] | None = None,
    use_color: bool = True,
) -> str:
    """Render a full 2D terminal dashboard frame (Board + Match Telemetry + Move Dictionary)."""
    board_lines = render_board_2d_lines(board, last_move=last_move, use_color=use_color)

    if use_color:
        bot_badge = f"{BG_BOT_BADGE} BOT {RESET}"
        sep = f"  {FG_BORDER}{'─' * 48}{RESET}"
    else:
        bot_badge = "[BOT]"
        sep = "  " + ("-" * 48)

    if trace is None:
        pbar = render_progress_bar(0, total_plies, use_color=use_color)
        hud = [
            f"  {bot_badge} {BOLD if use_color else ''}{black_bot}{RESET if use_color else ''} (Black)",
            sep,
            f"  Progress   : {pbar}",
            "  Status     : Starting Position (Ply 0)",
            "  Move Played: —",
            "  Dict Radix : N = 20 legal moves (4.32 bits)",
            "  Dict Index : —",
            "  V (before) : Ready to encode",
            "  V (after)  : —",
            "  Moves      : —",
            sep,
            f"  {bot_badge} {BOLD if use_color else ''}{white_bot}{RESET if use_color else ''} (White)",
        ]
    else:
        move_prefix = f"{trace.move_number}." if trace.turn == "White" else f"{trace.move_number}..."
        v_before_str = str(trace.value_before)
        if len(v_before_str) > 28:
            v_before_str = v_before_str[:13] + "..." + v_before_str[-12:]
        v_after_str = str(trace.value_after)
        if len(v_after_str) > 28:
            v_after_str = v_after_str[:13] + "..." + v_after_str[-12:]
        if trace.value_after == 0:
            v_after_str = f"0 ({FG_GREEN}All bits encoded!{RESET})" if use_color else "0 (All bits encoded!)"

        pbar = render_progress_bar(trace.ply, total_plies, use_color=use_color)
        black_active = (
            f" {FG_GREEN}● <-- moved{RESET}"
            if (trace.turn == "Black" and use_color)
            else (" <-- moved" if trace.turn == "Black" else "")
        )
        white_active = (
            f" {FG_GREEN}● <-- moved{RESET}"
            if (trace.turn == "White" and use_color)
            else (" <-- moved" if trace.turn == "White" else "")
        )
        move_str = f"{move_prefix} {trace.san} ({trace.uci}) [{trace.piece_name}]"
        idx_str = f"i = V mod {trace.radix} = [{trace.move_index}]"
        if use_color:
            move_str = f"{FG_GOLD}{BOLD}{move_prefix} {trace.san}{RESET} ({trace.uci}) [{trace.piece_name}]"
            idx_str = f"i = V mod {trace.radix} = {FG_GREEN}{BOLD}[{trace.move_index}]{RESET}"

        ticker = _format_move_ticker(all_traces or [trace], trace.ply, use_color=use_color)

        hud = [
            f"  {bot_badge} {BOLD if use_color else ''}{black_bot}{RESET if use_color else ''} (Black){black_active}",
            sep,
            f"  Progress   : {pbar}",
            f"  Ply        : {trace.ply} / {total_plies} ({trace.turn})",
            f"  Move Played: {move_str}",
            f"  Dict Radix : N = {trace.radix} legal moves ({trace.bits_capacity:.2f} bits)",
            f"  Dict Index : {idx_str}",
            f"  V (before) : {v_before_str}",
            f"  V (after)  : {v_after_str}",
            f"  Moves      : {ticker}",
            sep,
            f"  {bot_badge} {BOLD if use_color else ''}{white_bot}{RESET if use_color else ''} (White){white_active}",
        ]

    combined: list[str] = []
    max_rows = max(len(board_lines), len(hud))
    for i in range(max_rows):
        left = pad_ansi(board_lines[i], 32) if i < len(board_lines) else (" " * 32)
        right = hud[i] if i < len(hud) else ""
        combined.append(f"{left}{right}")

    if dictionary_entries is not None:
        chosen_idx = trace.move_index if trace is not None else None
        if use_color:
            combined.append(
                f"  {FG_BORDER}┄┄ Position Move Dictionary at Ply {trace.ply if trace else 0} "
                f"(Sorted by UCI, N = {len(dictionary_entries)}) ┄┄{RESET}"
            )
        else:
            combined.append(
                f"  -- Position Move Dictionary at Ply {trace.ply if trace else 0} "
                f"(Sorted by UCI, N = {len(dictionary_entries)}) --"
            )
        dict_rows = format_dictionary_grid(
            dictionary_entries, chosen_idx, columns=4, use_color=use_color
        )
        # Pad to fixed height (9 rows) so in-place terminal animation never shifts lines
        while len(dict_rows) < 9:
            dict_rows.append("")
        combined.extend(dict_rows[:9])

    return "\n".join(combined)


def play_2d_terminal_match(
    encoded_game: EncodedGame,
    *,
    delay: float = 0.20,
    step_mode: bool = False,
    show_all_plies: bool = False,
    use_color: bool | None = None,
    animate_in_place: bool | None = None,
) -> None:
    """Display the chess game being played in 2D in the terminal."""
    enable_terminal_ansi()
    is_tty = sys.stdout.isatty()
    if use_color is None:
        use_color = is_tty
    if animate_in_place is None:
        animate_in_place = is_tty and not show_all_plies

    board = chess.Board()
    total_plies = len(encoded_game.traces)

    if animate_in_place:
        prev_line_count = 0
        for idx, trace in enumerate(encoded_game.traces):
            dict_entries = get_position_dictionary(board)
            move = chess.Move.from_uci(trace.uci)
            board.push(move)
            frame = format_frame_2d(
                board,
                trace,
                total_plies=total_plies,
                white_bot=encoded_game.white_name,
                black_bot=encoded_game.black_name,
                last_move=move,
                dictionary_entries=dict_entries,
                all_traces=encoded_game.traces,
                use_color=use_color,
            )
            if idx > 0 and prev_line_count > 0:
                sys.stdout.write(f"\033[{prev_line_count}A")
            # Clear each line to the end so shorter lines never leave artifacts
            cleared_lines = [line + "\033[K" for line in frame.split("\n")]
            output_block = "\n".join(cleared_lines) + "\n"
            sys.stdout.write(output_block)
            sys.stdout.flush()
            prev_line_count = len(cleared_lines)

            if step_mode and idx < total_plies - 1:
                try:
                    input(f"  [Press Enter for Ply {idx + 2}/{total_plies}...] ")
                    prev_line_count += 1
                except EOFError:
                    break
            elif delay > 0 and idx < total_plies - 1:
                time.sleep(delay)
    elif show_all_plies:
        for trace in encoded_game.traces:
            dict_entries = get_position_dictionary(board)
            move = chess.Move.from_uci(trace.uci)
            board.push(move)
            print(f"\n[2D Board — Ply {trace.ply}/{total_plies}]")
            print(
                format_frame_2d(
                    board,
                    trace,
                    total_plies=total_plies,
                    white_bot=encoded_game.white_name,
                    black_bot=encoded_game.black_name,
                    last_move=move,
                    dictionary_entries=dict_entries,
                    all_traces=encoded_game.traces,
                    use_color=use_color,
                )
            )
    else:
        # Clean snapshot output (Opening Move + Final Position with Position Move Dictionary)
        if encoded_game.traces:
            first_trace = encoded_game.traces[0]
            first_dict = get_position_dictionary(board)
            first_move = chess.Move.from_uci(first_trace.uci)
            board.push(first_move)
            print("\n[2D Board — Ply 1 Opening Move]")
            print(
                format_frame_2d(
                    board,
                    first_trace,
                    total_plies=total_plies,
                    white_bot=encoded_game.white_name,
                    black_bot=encoded_game.black_name,
                    last_move=first_move,
                    dictionary_entries=first_dict,
                    all_traces=encoded_game.traces,
                    use_color=use_color,
                )
            )
            last_dict = first_dict
            for trace in encoded_game.traces[1:]:
                last_dict = get_position_dictionary(board)
                board.push(chess.Move.from_uci(trace.uci))
            last_trace = encoded_game.traces[-1]
            last_move = chess.Move.from_uci(last_trace.uci)
            if total_plies > 1:
                print(f"\n[2D Board — Final Position after Ply {total_plies}]")
                print(
                    format_frame_2d(
                        board,
                        last_trace,
                        total_plies=total_plies,
                        white_bot=encoded_game.white_name,
                        black_bot=encoded_game.black_name,
                        last_move=last_move,
                        dictionary_entries=last_dict,
                        all_traces=encoded_game.traces,
                        use_color=use_color,
                    )
                )
