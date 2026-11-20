"""Command-line interface for ChessCrypt."""

from __future__ import annotations

import argparse
import os
import sys
from urllib.parse import urlparse

import chess
from dotenv import load_dotenv

from chesscrypt.dictionary import format_dictionary_markdown
from chesscrypt.encoder import DEFAULT_MAX_CHUNK_BYTES, decode_pgn, encode_bytes, encode_text
from chesscrypt.lichess import (
    BOT_BLACK_NAME,
    BOT_WHITE_NAME,
    LichessAPIError,
    LichessBotClient,
    LichessMatchOrchestrator,
    SimulatedLichessServer,
)
from chesscrypt.viewer import enable_terminal_ansi, play_2d_terminal_match, visible_len

BANNER_INNER_WIDTH = 82
LICHESS_GAME_ID_LEN = 8


def _box_line(text: str = "") -> str:
    """Return `text` framed as one line of the banner box, padded or truncated to fit."""
    if visible_len(text) > BANNER_INNER_WIDTH:
        text = text[: BANNER_INNER_WIDTH - 1] + "…"
    return f"│{text}{' ' * (BANNER_INNER_WIDTH - visible_len(text))}│"


def _box_top(title: str = "") -> str:
    """Return the top border of a banner box, optionally with an inline title."""
    label = f"── {title} " if title else ""
    return "╭" + label + "─" * (BANNER_INNER_WIDTH - len(label)) + "╮"


def _box_bottom() -> str:
    return "╰" + "─" * BANNER_INNER_WIDTH + "╯"


def _print_banner(message: str) -> None:
    enable_terminal_ansi()
    print(_box_top())
    print(_box_line(" ♟  CHESSCRYPT TERMINAL ARENA  •  UNRATED LICHESS BOT STORAGE"))
    print(_box_line(f"    Bots   : {BOT_WHITE_NAME} (White) vs {BOT_BLACK_NAME} (Black)"))
    print(_box_line(f"    Secret : {message!r}"))
    print(_box_bottom())


def _resolve_passphrase(args: argparse.Namespace) -> str | None:
    """Use `--passphrase` if given, else `CHESSCRYPT_PASSPHRASE` from the environment / .env."""
    load_dotenv()
    return args.passphrase or os.getenv("CHESSCRYPT_PASSPHRASE") or None


def _read_payload(args: argparse.Namespace) -> bytes:
    """Return the bytes to encode from either the positional text or `--input-file`."""
    if args.input_file and args.text is not None:
        raise ValueError("Pass either TEXT or --input-file, not both.")
    if args.input_file:
        with open(args.input_file, "rb") as f:
            return f.read()
    if args.text is None:
        raise ValueError("Nothing to encode: pass TEXT or --input-file PATH.")
    return args.text.encode("utf-8")


def _emit_decoded(data: bytes, output: str | None) -> None:
    """Write decoded bytes to `output`, or print them as UTF-8 text."""
    if output:
        with open(output, "wb") as f:
            f.write(data)
        print(f"Wrote {len(data)} bytes to {output}", file=sys.stderr)
        return
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        raise ValueError(
            f"Decoded payload ({len(data)} bytes) is binary, not UTF-8 text. "
            "Use -o/--output PATH to save it to a file."
        ) from None
    print(text)


def _is_game_id(token: str) -> bool:
    # Player-specific IDs append a 4-character suffix to the 8-character game ID.
    return token.isalnum() and len(token) in (LICHESS_GAME_ID_LEN, LICHESS_GAME_ID_LEN + 4)


def _parse_game_id(value: str) -> str:
    """Accept a bare Lichess game ID or a game URL and return the 8-character game ID."""
    raw = value.strip()
    if "/" in raw:
        path = urlparse(raw if "://" in raw else f"https://{raw}").path
        candidates = [s for s in path.split("/") if _is_game_id(s)]
    else:
        candidates = [raw] if _is_game_id(raw) else []
    if not candidates:
        raise ValueError(f"{value!r} is not a Lichess game ID or game URL.")
    return candidates[0][:LICHESS_GAME_ID_LEN]


def _cmd_demo(args: argparse.Namespace) -> int:
    message = args.message or "Hello World"
    passphrase = args.passphrase or None

    _print_banner(message)

    games = encode_text(
        message,
        passphrase=passphrase,
        white_name=BOT_WHITE_NAME,
        black_name=BOT_BLACK_NAME,
    )
    for g in games:
        print()
        play_2d_terminal_match(
            g,
            delay=args.delay,
            step_mode=args.step,
            show_all_plies=args.all_plies,
            use_color=args.color,
        )
        print()
        print(g.format_trace_markdown())
        print("\nGenerated PGN:")
        print("─" * 60)
        print(g.to_pgn())
        print("─" * 60)

    # Play out the unrated match on the Lichess Bot Simulator
    server = SimulatedLichessServer()
    white_client = server.create_client(BOT_WHITE_NAME)
    black_client = server.create_client(BOT_BLACK_NAME)
    orchestrator = LichessMatchOrchestrator(white_client, black_client)
    orchestrator.ensure_bots_ready()

    records = [orchestrator.play_encoded_game(g) for g in games]
    game_ids = [r.game_id for r in records]
    print("\n" + _box_top("Lichess Unrated Bot Match Completed (simulated)"))
    for r in records:
        print(
            f"│  Game ID : {r.game_id:<12s} | Rated: {str(r.rated):<5s} | "
            f"{r.white_bot} vs {r.black_bot} ({r.plies_played} plies)"
        )
    print(_box_bottom())

    decoded = orchestrator.fetch_and_decode(game_ids, passphrase=passphrase)
    print("\n" + _box_top("Decryption Verification"))
    print(f"│  Recovered BigInt(s) : {decoded.recovered_bigints}")
    print(f"│  Recovered Hex Bytes : {decoded.decrypted_bytes.hex(' ')}")
    print(f"│  Decrypted Message   : {decoded.text!r}")

    if decoded.text != message:
        print("│  Status              : ERROR (Decrypted text did not match original!)")
        print(_box_bottom())
        print("chesscrypt: error: round-trip verification failed", file=sys.stderr)
        return 1
    print("│  Status              : SUCCESS (100% lossless match)")
    print(_box_bottom())
    return 0


def _cmd_dictionary(args: argparse.Namespace) -> int:
    board = chess.Board(args.fen) if args.fen else chess.Board()
    print(format_dictionary_markdown(board))
    return 0


def _cmd_encode(args: argparse.Namespace) -> int:
    games = encode_bytes(
        _read_payload(args),
        passphrase=_resolve_passphrase(args),
        max_chunk_bytes=args.chunk_bytes,
        white_name=args.white,
        black_name=args.black,
    )
    if args.trace:
        for g in games:
            print(g.format_trace_markdown())
            print()
    pgns = "\n\n".join(g.to_pgn() for g in games)
    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(pgns + "\n")
        total_plies = sum(len(g.traces) for g in games)
        print(
            f"Wrote {len(games)} game(s), {total_plies} plies, to {args.output}",
            file=sys.stderr,
        )
    else:
        print(pgns)
    return 0


def _cmd_decode(args: argparse.Namespace) -> int:
    if args.pgn_file and args.pgn:
        raise ValueError("Pass either --pgn or --pgn-file, not both.")
    if args.pgn_file:
        with open(args.pgn_file, "r", encoding="utf-8") as f:
            pgn_text = f.read()
    elif args.pgn:
        pgn_text = args.pgn
    else:
        pgn_text = sys.stdin.read()

    result = decode_pgn(pgn_text, passphrase=_resolve_passphrase(args))
    _emit_decoded(result.decrypted_bytes, args.output)
    return 0


def _cmd_setup_bots(args: argparse.Namespace) -> int:
    load_dotenv()
    white_token = args.white_token or os.getenv("LICHESS_WHITE_BOT_TOKEN")
    black_token = args.black_token or os.getenv("LICHESS_BLACK_BOT_TOKEN")
    white_name = args.white_name or os.getenv("LICHESS_WHITE_BOT_NAME") or BOT_WHITE_NAME
    black_name = args.black_name or os.getenv("LICHESS_BLACK_BOT_NAME") or BOT_BLACK_NAME

    if not white_token or not black_token:
        print(
            "Missing LICHESS_WHITE_BOT_TOKEN or LICHESS_BLACK_BOT_TOKEN.\n"
            f"1. Register '{white_name}' and '{black_name}' at https://lichess.org/signup\n"
            "2. Create API tokens with the 'bot:play', 'challenge:read' and 'challenge:write'\n"
            "   scopes at https://lichess.org/account/oauth/token/create\n"
            "3. Save them in .env and re-run `chesscrypt setup-bots`.",
            file=sys.stderr,
        )
        return 1

    w_client = LichessBotClient(white_token, username=white_name)
    b_client = LichessBotClient(black_token, username=black_name)
    orchestrator = LichessMatchOrchestrator(w_client, b_client)
    w_acc, b_acc = orchestrator.ensure_bots_ready()
    print(f"White Bot Ready: {w_acc.get('username')} (title={w_acc.get('title')})")
    print(f"Black Bot Ready: {b_acc.get('username')} (title={b_acc.get('title')})")
    return 0


def _cmd_store_lichess(args: argparse.Namespace) -> int:
    payload = _read_payload(args)
    passphrase = _resolve_passphrase(args)  # also loads .env
    white_name = args.white_name or os.getenv("LICHESS_WHITE_BOT_NAME") or BOT_WHITE_NAME
    black_name = args.black_name or os.getenv("LICHESS_BLACK_BOT_NAME") or BOT_BLACK_NAME

    if args.simulate:
        server = SimulatedLichessServer()
        w_client = server.create_client(white_name)
        b_client = server.create_client(black_name)
        orchestrator = LichessMatchOrchestrator(w_client, b_client)
    else:
        white_token = args.white_token or os.getenv("LICHESS_WHITE_BOT_TOKEN")
        black_token = args.black_token or os.getenv("LICHESS_BLACK_BOT_TOKEN")
        if not white_token or not black_token:
            print(
                "chesscrypt: error: Lichess bot tokens are not configured. Set "
                "LICHESS_WHITE_BOT_TOKEN and LICHESS_BLACK_BOT_TOKEN in .env "
                "(or pass --simulate to use the local simulator).",
                file=sys.stderr,
            )
            return 1
        w_client = LichessBotClient(white_token, username=white_name)
        b_client = LichessBotClient(black_token, username=black_name)
        orchestrator = LichessMatchOrchestrator(
            w_client, b_client, move_delay_seconds=args.move_delay
        )

    records = orchestrator.store_bytes(
        payload, passphrase=passphrase, max_chunk_bytes=args.chunk_bytes
    )
    for r in records:
        print(f"Stored in Unrated Game: {r.url} ({r.plies_played} plies)")
        print(r.pgn)
        print()
    ids = " ".join(r.game_id for r in records)
    print(f"Retrieve with: chesscrypt fetch-lichess {ids}")
    return 0


def _cmd_fetch_lichess(args: argparse.Namespace) -> int:
    game_ids = [_parse_game_id(g) for g in args.game_ids]
    client = LichessBotClient(token=None)
    pgns = [client.export_game_pgn(gid) for gid in game_ids]
    result = decode_pgn("\n\n".join(pgns), passphrase=_resolve_passphrase(args))
    _emit_decoded(result.decrypted_bytes, args.output)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="chesscrypt",
        description="Encode and store data as legal chess games between two unrated Lichess bots.",
        epilog="Run without a command to play the 'Hello World' demo.",
    )
    sub = parser.add_subparsers(dest="command", metavar="COMMAND")

    passphrase_help = "Encryption passphrase (default: $CHESSCRYPT_PASSPHRASE)"
    chunk_help = f"Max payload bytes per game (default: {DEFAULT_MAX_CHUNK_BYTES})"

    p_demo = sub.add_parser("demo", help="Animated 'Hello World' encode -> play -> decode demo")
    p_demo.add_argument("--message", default="Hello World", help="Message to encode")
    p_demo.add_argument("--passphrase", default=None, help="Optional encryption passphrase")
    p_demo.add_argument(
        "--delay",
        type=float,
        default=0.20,
        help="Seconds between plies in the animated board (default: 0.20)",
    )
    p_demo.add_argument(
        "--step",
        action="store_true",
        help="Interactive step-by-step mode (press Enter after each ply)",
    )
    p_demo.add_argument(
        "--all-plies",
        action="store_true",
        help="Print every ply's 2D board and dictionary sequentially",
    )
    p_demo.add_argument(
        "--color",
        dest="color",
        action="store_true",
        default=None,
        help="Force ANSI truecolor board rendering",
    )
    p_demo.add_argument(
        "--no-color",
        dest="color",
        action="store_false",
        help="Disable ANSI colors (plain ASCII board)",
    )
    p_demo.set_defaults(func=_cmd_demo)

    p_dict = sub.add_parser("dictionary", help="Show the Move Dictionary for a position")
    p_dict.add_argument("--fen", default=None, help="Custom FEN (default: starting position)")
    p_dict.set_defaults(func=_cmd_dictionary)

    p_enc = sub.add_parser("encode", help="Encode text or a file into chess PGN")
    p_enc.add_argument("text", nargs="?", default=None, help="Text to encode")
    p_enc.add_argument("-i", "--input-file", default=None, help="Encode this file's bytes instead of TEXT")
    p_enc.add_argument("--passphrase", default=None, help=passphrase_help)
    p_enc.add_argument("--chunk-bytes", type=int, default=DEFAULT_MAX_CHUNK_BYTES, help=chunk_help)
    p_enc.add_argument("--white", default=BOT_WHITE_NAME, help="White player name in the PGN")
    p_enc.add_argument("--black", default=BOT_BLACK_NAME, help="Black player name in the PGN")
    p_enc.add_argument("--trace", action="store_true", help="Print the ply-by-ply encoding trace")
    p_enc.add_argument("-o", "--output", default=None, help="Write PGN to this file")
    p_enc.set_defaults(func=_cmd_encode)

    p_dec = sub.add_parser("decode", help="Decode chess PGN back into the original data")
    p_dec.add_argument("--pgn", default=None, help="Inline PGN string")
    p_dec.add_argument("-f", "--pgn-file", default=None, help="Path to a PGN file (default: stdin)")
    p_dec.add_argument("--passphrase", default=None, help=passphrase_help)
    p_dec.add_argument("-o", "--output", default=None, help="Write decoded bytes to this file")
    p_dec.set_defaults(func=_cmd_decode)

    p_setup = sub.add_parser("setup-bots", help="Upgrade both Lichess accounts to BOT status")
    p_setup.add_argument("--white-token", default=None, help="Default: $LICHESS_WHITE_BOT_TOKEN")
    p_setup.add_argument("--black-token", default=None, help="Default: $LICHESS_BLACK_BOT_TOKEN")
    p_setup.add_argument("--white-name", default=None, help="Default: $LICHESS_WHITE_BOT_NAME")
    p_setup.add_argument("--black-name", default=None, help="Default: $LICHESS_BLACK_BOT_NAME")
    p_setup.set_defaults(func=_cmd_setup_bots)

    p_store = sub.add_parser(
        "store-lichess",
        help="Store text or a file by playing unrated bot games on Lichess",
    )
    p_store.add_argument("text", nargs="?", default=None, help="Text to store")
    p_store.add_argument("-i", "--input-file", default=None, help="Store this file's bytes instead of TEXT")
    p_store.add_argument("--passphrase", default=None, help=passphrase_help)
    p_store.add_argument("--chunk-bytes", type=int, default=DEFAULT_MAX_CHUNK_BYTES, help=chunk_help)
    p_store.add_argument("--simulate", action="store_true", help="Use the local Lichess simulator")
    p_store.add_argument(
        "--move-delay",
        type=float,
        default=0.35,
        help="Seconds to wait between moves on Lichess (default: 0.35)",
    )
    p_store.add_argument("--white-token", default=None, help="Default: $LICHESS_WHITE_BOT_TOKEN")
    p_store.add_argument("--black-token", default=None, help="Default: $LICHESS_BLACK_BOT_TOKEN")
    p_store.add_argument("--white-name", default=None, help="Default: $LICHESS_WHITE_BOT_NAME")
    p_store.add_argument("--black-name", default=None, help="Default: $LICHESS_BLACK_BOT_NAME")
    p_store.set_defaults(func=_cmd_store_lichess)

    p_fetch = sub.add_parser(
        "fetch-lichess",
        help="Download games from Lichess and decode the stored data",
    )
    p_fetch.add_argument(
        "game_ids",
        nargs="+",
        metavar="GAME",
        help="Lichess game IDs or URLs, in storage order",
    )
    p_fetch.add_argument("--passphrase", default=None, help=passphrase_help)
    p_fetch.add_argument("-o", "--output", default=None, help="Write decoded bytes to this file")
    p_fetch.set_defaults(func=_cmd_fetch_lichess)

    return parser


def _use_utf8_stdio() -> None:
    """Emit UTF-8 even when stdout/stderr are redirected on Windows (default: cp1252).

    Without this, board glyphs, box drawing and non-ASCII decoded messages raise
    UnicodeEncodeError as soon as output is piped or redirected to a file.
    """
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(encoding="utf-8")
            except (ValueError, OSError):
                pass


def main(argv: list[str] | None = None) -> int:
    _use_utf8_stdio()
    parser = build_parser()
    args = parser.parse_args(argv)
    if not hasattr(args, "func"):
        args = parser.parse_args(["demo"])
    try:
        return args.func(args)
    except KeyboardInterrupt:
        print(file=sys.stderr)
        return 130
    except (ValueError, LichessAPIError, OSError) as exc:
        # ValueError also covers CryptoError and UnicodeDecodeError.
        print(f"chesscrypt: error: {exc}", file=sys.stderr)
        return 1
