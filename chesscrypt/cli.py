"""Command-line interface for ChessCrypt."""

from __future__ import annotations

import argparse
import os
import sys
import chess
from dotenv import load_dotenv

from chesscrypt.dictionary import format_dictionary_markdown
from chesscrypt.encoder import decode_pgn, encode_text
from chesscrypt.lichess import (
    BOT_BLACK_NAME,
    BOT_WHITE_NAME,
    LichessBotClient,
    LichessMatchOrchestrator,
    SimulatedLichessServer,
)
from chesscrypt.viewer import enable_terminal_ansi, play_2d_terminal_match


def _print_banner(message: str) -> None:
    enable_terminal_ansi()
    print("╭──────────────────────────────────────────────────────────────────────────────────╮")
    print("│ ♟  CHESSCRYPT TERMINAL ARENA  •  UNRATED LICHESS BOT STORAGE                     │")
    print(f"│    Bots   : {BOT_WHITE_NAME} (White) vs {BOT_BLACK_NAME} (Black)                         │")
    print(f"│    Secret : {message!r:<68s} │")
    print("╰──────────────────────────────────────────────────────────────────────────────────╯")


def _cmd_demo(args: argparse.Namespace) -> int:
    message = getattr(args, "message", None) or "Hello World"
    passphrase = getattr(args, "passphrase", None) or None
    delay = getattr(args, "delay", 0.20)
    step_mode = getattr(args, "step", False)
    all_plies = getattr(args, "all_plies", False)
    color_flag = getattr(args, "color", None)

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
            delay=delay,
            step_mode=step_mode,
            show_all_plies=all_plies,
            use_color=color_flag,
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
    print("\n╭── Lichess Unrated Bot Match Completed ───────────────────────────────────────────╮")
    for r in records:
        print(
            f"│  Game ID : {r.game_id:<12s} | Rated: {str(r.rated):<5s} | "
            f"{r.white_bot} vs {r.black_bot} ({r.plies_played} plies)"
        )
    print("╰──────────────────────────────────────────────────────────────────────────────────╯")

    decoded = orchestrator.fetch_and_decode(game_ids, passphrase=passphrase)
    print("\n╭── Decryption Verification ───────────────────────────────────────────────────────╮")
    print(f"│  Recovered BigInt(s) : {decoded.recovered_bigints}")
    print(f"│  Recovered Hex Bytes : {decoded.decrypted_bytes.hex(' ')}")
    print(f"│  Decrypted Message   : {decoded.text!r}")

    if decoded.text != message:
        print("│  Status              : ERROR (Decrypted text did not match original!)", file=sys.stderr)
        print("╰──────────────────────────────────────────────────────────────────────────────────╯")
        return 1
    print("│  Status              : SUCCESS (100% lossless match)")
    print("╰──────────────────────────────────────────────────────────────────────────────────╯")
    return 0


def _cmd_dictionary(args: argparse.Namespace) -> int:
    board = chess.Board(args.fen) if args.fen else chess.Board()
    print(format_dictionary_markdown(board))
    return 0


def _cmd_encode(args: argparse.Namespace) -> int:
    games = encode_text(
        args.text,
        passphrase=args.passphrase,
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
    else:
        print(pgns)
    return 0


def _cmd_decode(args: argparse.Namespace) -> int:
    if args.pgn_file:
        with open(args.pgn_file, "r", encoding="utf-8") as f:
            pgn_text = f.read()
    elif args.pgn:
        pgn_text = args.pgn
    else:
        pgn_text = sys.stdin.read()

    result = decode_pgn(pgn_text, passphrase=args.passphrase)
    print(result.text)
    return 0


def _cmd_setup_bots(args: argparse.Namespace) -> int:
    load_dotenv()
    white_token = args.white_token or os.getenv("LICHESS_WHITE_BOT_TOKEN")
    black_token = args.black_token or os.getenv("LICHESS_BLACK_BOT_TOKEN")
    white_name = args.white_name or os.getenv("LICHESS_WHITE_BOT_NAME", BOT_WHITE_NAME)
    black_name = args.black_name or os.getenv("LICHESS_BLACK_BOT_NAME", BOT_BLACK_NAME)

    if not white_token or not black_token:
        print(
            "Missing LICHESS_WHITE_BOT_TOKEN or LICHESS_BLACK_BOT_TOKEN.\n"
            f"1. Register '{white_name}' and '{black_name}' at https://lichess.org/signup\n"
            "2. Create API tokens with 'bot:play' & 'challenge:write' at https://lichess.org/account/oauth/token/create\n"
            "3. Save them in .env and re-run `python -m chesscrypt setup-bots`.",
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
    load_dotenv()
    if args.simulate:
        server = SimulatedLichessServer()
        w_client = server.create_client(BOT_WHITE_NAME)
        b_client = server.create_client(BOT_BLACK_NAME)
        orchestrator = LichessMatchOrchestrator(w_client, b_client)
    else:
        white_token = args.white_token or os.getenv("LICHESS_WHITE_BOT_TOKEN")
        black_token = args.black_token or os.getenv("LICHESS_BLACK_BOT_TOKEN")
        white_name = os.getenv("LICHESS_WHITE_BOT_NAME", BOT_WHITE_NAME)
        black_name = os.getenv("LICHESS_BLACK_BOT_NAME", BOT_BLACK_NAME)
        if not white_token or not black_token:
            print(
                "Error: Live Lichess tokens not configured in .env (use --simulate for local simulation).",
                file=sys.stderr,
            )
            return 1
        w_client = LichessBotClient(white_token, username=white_name)
        b_client = LichessBotClient(black_token, username=black_name)
        orchestrator = LichessMatchOrchestrator(
            w_client, b_client, move_delay_seconds=0.35
        )

    records = orchestrator.store_text(args.text, passphrase=args.passphrase)
    for r in records:
        print(f"Stored in Unrated Game: {r.url} ({r.plies_played} plies)")
        print(r.pgn)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="chesscrypt",
        description="Encode and store data as legal chess games between two unrated Lichess bots.",
    )
    sub = parser.add_subparsers(dest="command")

    p_demo = sub.add_parser("demo", help="Run full 'Hello World' 2D console chess encrypt & decrypt demo")
    p_demo.add_argument("--message", default="Hello World", help="Message to encrypt")
    p_demo.add_argument("--passphrase", default=None, help="Optional encryption passphrase")
    p_demo.add_argument(
        "--delay",
        type=float,
        default=0.20,
        help="Delay in seconds between plies for terminal 2D board animation",
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
        help="Force ANSI truecolor Lichess board rendering",
    )
    p_demo.add_argument(
        "--no-color",
        dest="color",
        action="store_false",
        help="Disable ANSI colors (plain ASCII 2D board)",
    )
    p_demo.set_defaults(func=_cmd_demo)

    p_dict = sub.add_parser("dictionary", help="Display the Move Dictionary for a FEN position")
    p_dict.add_argument("--fen", default=None, help="Custom FEN (defaults to starting position)")
    p_dict.set_defaults(func=_cmd_dictionary)

    p_enc = sub.add_parser("encode", help="Encode text into chess PGN(s)")
    p_enc.add_argument("text", help="Text string to encode")
    p_enc.add_argument("--passphrase", default=None, help="Optional passphrase")
    p_enc.add_argument("--white", default=BOT_WHITE_NAME, help="White bot username")
    p_enc.add_argument("--black", default=BOT_BLACK_NAME, help="Black bot username")
    p_enc.add_argument("--trace", action="store_true", help="Print ply-by-ply dictionary trace")
    p_enc.add_argument("-o", "--output", default=None, help="Output PGN file path")
    p_enc.set_defaults(func=_cmd_encode)

    p_dec = sub.add_parser("decode", help="Decode chess PGN(s) back into text")
    p_dec.add_argument("--pgn", default=None, help="Inline PGN string")
    p_dec.add_argument("-f", "--pgn-file", default=None, help="Path to PGN file")
    p_dec.add_argument("--passphrase", default=None, help="Optional passphrase")
    p_dec.set_defaults(func=_cmd_decode)

    p_setup = sub.add_parser("setup-bots", help="Upgrade both Lichess accounts to BOT status")
    p_setup.add_argument("--white-token", default=None)
    p_setup.add_argument("--black-token", default=None)
    p_setup.add_argument("--white-name", default=None)
    p_setup.add_argument("--black-name", default=None)
    p_setup.set_defaults(func=_cmd_setup_bots)

    p_store = sub.add_parser(
        "store-lichess",
        help="Store text by playing an unrated bot match on Lichess",
    )
    p_store.add_argument("text", help="Text payload to store")
    p_store.add_argument("--passphrase", default=None)
    p_store.add_argument("--simulate", action="store_true", help="Use local Lichess simulator")
    p_store.add_argument("--white-token", default=None)
    p_store.add_argument("--black-token", default=None)
    p_store.set_defaults(func=_cmd_store_lichess)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not hasattr(args, "func"):
        return _cmd_demo(argparse.Namespace(message="Hello World", passphrase=None))
    return args.func(args)
