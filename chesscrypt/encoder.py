"""Mixed-Radix BigInt Chess Encoder & Decoder."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import io
import re
import chess
import chess.pgn

from chesscrypt.crypto import decrypt_payload, encrypt_payload
from chesscrypt.dictionary import MoveEntry, get_position_dictionary

DEFAULT_MAX_CHUNK_BYTES = 32
DEFAULT_WHITE_BOT = "RookCipherBot"
DEFAULT_BLACK_BOT = "PawnVaultBot"

_ROUND_RE = re.compile(r"^\s*(\d+)\s*/\s*(\d+)\s*$")
_SAN_ANNOTATIONS = "+#!?"


def pgn_date_today() -> str:
    """Return today's UTC date in PGN `YYYY.MM.DD` format."""
    return datetime.now(timezone.utc).strftime("%Y.%m.%d")


def bytes_to_bigint(chunk: bytes) -> int:
    """Bijectively convert arbitrary bytes into a positive integer >= 1.

    A leading 0x01 sentinel byte is prepended so leading 0x00 bytes in `chunk`
    are preserved and the resulting integer is always >= 1.
    """
    return int.from_bytes(b"\x01" + chunk, "big")


def bigint_to_bytes(value: int) -> bytes:
    """Invert `bytes_to_bigint` to recover the exact original byte string."""
    if value < 1:
        raise ValueError(f"Encoded integer must be >= 1, got {value}")
    byte_len = (value.bit_length() + 7) // 8
    raw = value.to_bytes(byte_len, "big")
    if raw[0] != 1:
        raise ValueError(
            f"Invalid sentinel byte 0x{raw[0]:02x} (expected 0x01). "
            "Move sequence was not encoded by ChessCrypt or is truncated."
        )
    return raw[1:]


@dataclass(frozen=True)
class PlyTrace:
    """Step-by-step trace of a single half-move (ply) during encoding or decoding."""

    ply: int
    move_number: int
    turn: str
    fen_before: str
    radix: int
    move_index: int
    uci: str
    san: str
    piece_name: str
    value_before: int
    value_after: int
    bits_capacity: float


@dataclass
class EncodedGame:
    """A single legal chess game encoding a byte chunk."""

    game_index: int
    total_games: int
    chunk_bytes: bytes
    initial_bigint: int
    traces: list[PlyTrace]
    white_name: str = DEFAULT_WHITE_BOT
    black_name: str = DEFAULT_BLACK_BOT

    @property
    def uci_moves(self) -> list[str]:
        return [t.uci for t in self.traces]

    @property
    def san_moves(self) -> list[str]:
        return [t.san for t in self.traces]

    @property
    def total_bits_capacity(self) -> float:
        return sum(t.bits_capacity for t in self.traces)

    def to_pgn(self, game_id: str | None = None, *, date: str | None = None) -> str:
        """Export this encoded game as a standard PGN string.

        The `Round` header is set to `"<game_index>/<total_games>"` so that
        `decode_pgn` can reassemble multi-game payloads in the right order.
        `date` defaults to today's UTC date (PGN `YYYY.MM.DD` format).
        """
        game = chess.pgn.Game()
        game.headers["Event"] = "ChessCrypt Unrated Bot Storage"
        game.headers["Site"] = (
            f"https://lichess.org/{game_id}" if game_id else "https://lichess.org"
        )
        game.headers["Date"] = date or pgn_date_today()
        game.headers["Round"] = f"{self.game_index}/{self.total_games}"
        game.headers["White"] = self.white_name
        game.headers["Black"] = self.black_name
        game.headers["Result"] = "*"

        node: chess.pgn.GameNode = game
        for trace in self.traces:
            node = node.add_variation(chess.Move.from_uci(trace.uci))

        exporter = chess.pgn.StringExporter(headers=True, variations=False, comments=False)
        return game.accept(exporter).strip()

    def format_trace_markdown(self) -> str:
        """Render a Markdown table showing the ply-by-ply mixed-radix encoding trace."""
        lines = [
            f"### Game {self.game_index}/{self.total_games} — Ply-by-Ply Encoding Trace",
            f"- **Chunk Bytes ({len(self.chunk_bytes)} B):** `{self.chunk_bytes.hex(' ')}`",
            f"- **Sentinel-Prefixed Hex:** `01 {self.chunk_bytes.hex(' ')}`",
            f"- **Initial BigInt ($V_0$):** `{self.initial_bigint}`",
            f"- **Total Plies:** {len(self.traces)} ({(len(self.traces) + 1) // 2} full moves)",
            "",
            "| Ply | Move | Turn | Legal Moves ($N_t$) | Dictionary Index ($i_t = V_t \\bmod N_t$) | UCI | SAN | Piece | Quotient ($V_{t+1} = \\lfloor V_t / N_t \\rfloor$) |",
            "| :-: | :-: | :-: | :-: | :-: | :-: | :-: | :-: | :--- |",
        ]
        for t in self.traces:
            move_label = f"{t.move_number}." if t.turn == "White" else f"{t.move_number}..."
            lines.append(
                f"| {t.ply} | `{move_label}` | {t.turn} | {t.radix} | **`{t.move_index}`** | `{t.uci}` | **{t.san}** | {t.piece_name} | `{t.value_after}` |"
            )
        return "\n".join(lines)


@dataclass
class DecodedResult:
    """Result of decoding one or more ChessCrypt games."""

    raw_payload: bytes
    decrypted_bytes: bytes
    games_traces: list[list[PlyTrace]]
    recovered_bigints: list[int]

    @property
    def text(self) -> str:
        """Decode the decrypted payload as UTF-8 text."""
        return self.decrypted_bytes.decode("utf-8")


def _encode_chunk_to_game(
    chunk: bytes,
    *,
    game_index: int = 1,
    total_games: int = 1,
    white_name: str = DEFAULT_WHITE_BOT,
    black_name: str = DEFAULT_BLACK_BOT,
) -> EncodedGame:
    """Encode a single byte chunk into one legal chess game."""
    initial_v = bytes_to_bigint(chunk)
    v = initial_v
    board = chess.Board()
    traces: list[PlyTrace] = []
    ply = 0

    while v > 0:
        ply += 1
        dictionary = get_position_dictionary(board)
        radix = len(dictionary)
        if radix < 1:
            raise RuntimeError(
                f"Board position at ply {ply} has no legal moves; "
                "reduce max_chunk_bytes."
            )

        move_idx = v % radix
        v_next = v // radix
        entry = dictionary[move_idx]

        traces.append(
            PlyTrace(
                ply=ply,
                move_number=board.fullmove_number,
                turn="White" if board.turn == chess.WHITE else "Black",
                fen_before=board.fen(),
                radix=radix,
                move_index=move_idx,
                uci=entry.uci,
                san=entry.san,
                piece_name=entry.piece_name,
                value_before=v,
                value_after=v_next,
                bits_capacity=entry.bits_capacity,
            )
        )
        board.push(entry.move)
        v = v_next

    return EncodedGame(
        game_index=game_index,
        total_games=total_games,
        chunk_bytes=chunk,
        initial_bigint=initial_v,
        traces=traces,
        white_name=white_name,
        black_name=black_name,
    )


def encode_bytes(
    data: bytes,
    *,
    passphrase: str | None = None,
    salt: bytes | None = None,
    max_chunk_bytes: int = DEFAULT_MAX_CHUNK_BYTES,
    white_name: str = DEFAULT_WHITE_BOT,
    black_name: str = DEFAULT_BLACK_BOT,
) -> list[EncodedGame]:
    """Encrypt (optional) and encode arbitrary bytes into a list of legal chess games."""
    if max_chunk_bytes < 1:
        raise ValueError("max_chunk_bytes must be >= 1")

    payload = encrypt_payload(data, passphrase=passphrase, salt=salt)
    if len(payload) == 0:
        chunks = [b""]
    else:
        chunks = [
            payload[i : i + max_chunk_bytes]
            for i in range(0, len(payload), max_chunk_bytes)
        ]

    total_games = len(chunks)
    return [
        _encode_chunk_to_game(
            chunk,
            game_index=idx + 1,
            total_games=total_games,
            white_name=white_name,
            black_name=black_name,
        )
        for idx, chunk in enumerate(chunks)
    ]


def encode_text(
    text: str,
    *,
    passphrase: str | None = None,
    salt: bytes | None = None,
    max_chunk_bytes: int = DEFAULT_MAX_CHUNK_BYTES,
    white_name: str = DEFAULT_WHITE_BOT,
    black_name: str = DEFAULT_BLACK_BOT,
) -> list[EncodedGame]:
    """Encode a UTF-8 string into one or more legal chess games."""
    return encode_bytes(
        text.encode("utf-8"),
        passphrase=passphrase,
        salt=salt,
        max_chunk_bytes=max_chunk_bytes,
        white_name=white_name,
        black_name=black_name,
    )


def decode_moves(
    moves: list[str],
    *,
    passphrase: str | None = None,
) -> DecodedResult:
    """Decode a single game's list of UCI or SAN move strings back into the original data."""
    return decode_games([moves], passphrase=passphrase)


def _decode_single_game_moves(moves: list[str]) -> tuple[bytes, int, list[PlyTrace]]:
    """Decode one game's move list into (chunk_bytes, recovered_bigint, ply_traces)."""
    if not moves:
        raise ValueError("Cannot decode an empty move list.")

    board = chess.Board()
    multiplier = 1
    accumulated_v = 0
    traces: list[PlyTrace] = []

    for ply_idx, raw_move in enumerate(moves, start=1):
        token = raw_move.strip()
        dictionary = get_position_dictionary(board)
        radix = len(dictionary)

        matched_entry = _match_move(dictionary, token)
        if matched_entry is None:
            raise ValueError(
                f"Move {token!r} at ply {ply_idx} is not in the valid ChessCrypt "
                f"Position Dictionary for FEN {board.fen()!r}."
            )

        v_before = accumulated_v
        accumulated_v += matched_entry.index * multiplier

        traces.append(
            PlyTrace(
                ply=ply_idx,
                move_number=board.fullmove_number,
                turn="White" if board.turn == chess.WHITE else "Black",
                fen_before=board.fen(),
                radix=radix,
                move_index=matched_entry.index,
                uci=matched_entry.uci,
                san=matched_entry.san,
                piece_name=matched_entry.piece_name,
                value_before=v_before,
                value_after=accumulated_v,
                bits_capacity=matched_entry.bits_capacity,
            )
        )
        board.push(matched_entry.move)
        multiplier *= radix

    chunk_bytes = bigint_to_bytes(accumulated_v)
    return chunk_bytes, accumulated_v, traces


def _match_move(dictionary: list[MoveEntry], token: str) -> MoveEntry | None:
    """Find the dictionary entry for a UCI (`e2e4`) or SAN (`e4`, `Qh4+`, `Nf3!?`) token.

    Check/mate markers and annotation glyphs are ignored when matching SAN, so
    `Qh4`, `Qh4+` and `Qh4+!` all resolve to the same move.
    """
    bare = token.rstrip(_SAN_ANNOTATIONS)
    for entry in dictionary:
        if entry.uci == token or entry.san.rstrip(_SAN_ANNOTATIONS) == bare:
            return entry
    return None


def decode_games(
    games_moves: list[list[str]],
    *,
    passphrase: str | None = None,
) -> DecodedResult:
    """Decode a sequence of games (each a list of UCI or SAN moves) into the original payload."""
    if not games_moves:
        raise ValueError("No games provided to decode.")

    chunks: list[bytes] = []
    recovered_bigints: list[int] = []
    games_traces: list[list[PlyTrace]] = []

    for moves in games_moves:
        chunk, v, traces = _decode_single_game_moves(moves)
        chunks.append(chunk)
        recovered_bigints.append(v)
        games_traces.append(traces)

    raw_payload = b"".join(chunks)
    decrypted = decrypt_payload(raw_payload, passphrase=passphrase)
    return DecodedResult(
        raw_payload=raw_payload,
        decrypted_bytes=decrypted,
        games_traces=games_traces,
        recovered_bigints=recovered_bigints,
    )


def decode_pgn(
    pgn_text: str,
    *,
    passphrase: str | None = None,
) -> DecodedResult:
    """Parse one or more games from a PGN string and decode the embedded data.

    If every game carries a ChessCrypt `[Round "g/G"]` header, games are
    reassembled in round order (so the PGN may list them in any order) and a
    missing or duplicated part raises `ValueError`. Otherwise (e.g. PGNs
    exported from Lichess) games are decoded in the order they appear.
    """
    stream = io.StringIO(pgn_text.strip())
    parsed: list[tuple[str, list[str]]] = []

    while True:
        game = chess.pgn.read_game(stream, Visitor=_CollectingGameBuilder)
        if game is None:
            break
        if game.errors:
            raise ValueError(
                f"PGN game #{len(parsed) + 1} contains an illegal or unreadable move: "
                f"{game.errors[0]}"
            )
        moves = [move.uci() for move in game.mainline_moves()]
        if moves:
            parsed.append((game.headers.get("Round", ""), moves))

    if not parsed:
        raise ValueError("No valid chess games with moves found in PGN text.")

    return decode_games(_order_games_by_round(parsed), passphrase=passphrase)


class _CollectingGameBuilder(chess.pgn.GameBuilder):
    """GameBuilder that records parse errors on the game without logging them."""

    def handle_error(self, error: Exception) -> None:
        self.game.errors.append(error)


def _order_games_by_round(parsed: list[tuple[str, list[str]]]) -> list[list[str]]:
    """Sort games by their `[Round "g/G"]` header when all games carry one."""
    rounds = [_ROUND_RE.match(round_tag) for round_tag, _ in parsed]
    if not all(rounds):
        return [moves for _, moves in parsed]

    totals = {int(m.group(2)) for m in rounds}  # type: ignore[union-attr]
    indices = [int(m.group(1)) for m in rounds]  # type: ignore[union-attr]
    if len(totals) != 1:
        raise ValueError(f"PGN games disagree on the total part count: {sorted(totals)}.")
    total = totals.pop()
    if sorted(indices) != list(range(1, total + 1)):
        missing = sorted(set(range(1, total + 1)) - set(indices))
        detail = f"missing part(s) {missing}" if missing else "duplicate parts"
        raise ValueError(
            f"Incomplete ChessCrypt payload: expected rounds 1..{total}, {detail}."
        )

    ordered = sorted(zip(indices, (moves for _, moves in parsed)), key=lambda p: p[0])
    return [moves for _, moves in ordered]
