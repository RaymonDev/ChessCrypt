"""Lichess Bot API client, two-bot unrated match orchestrator, and local Lichess simulator."""

from __future__ import annotations

from dataclasses import dataclass, field
import json
import secrets
import time
from typing import Iterator, Protocol
import chess
import chess.pgn
import requests

from chesscrypt.encoder import (
    DecodedResult,
    EncodedGame,
    decode_pgn,
    encode_bytes,
    encode_text,
)

LICHESS_BASE_URL = "https://lichess.org"
BOT_WHITE_NAME = "RookCipherBot"
BOT_BLACK_NAME = "PawnVaultBot"


class LichessAPIError(RuntimeError):
    """Raised when a Lichess API call fails."""


class BotClientProtocol(Protocol):
    """Protocol shared by real LichessBotClient and SimulatedLichessBotClient."""

    username: str

    def get_account(self) -> dict: ...
    def upgrade_to_bot(self) -> bool: ...
    def create_challenge(
        self,
        opponent_username: str,
        *,
        rated: bool = False,
        clock_limit: int = 300,
        clock_increment: int = 3,
        color: str = "white",
    ) -> dict: ...
    def accept_challenge(self, challenge_id: str) -> bool: ...
    def make_move(self, game_id: str, uci_move: str) -> bool: ...
    def resign_game(self, game_id: str) -> bool: ...
    def export_game_pgn(self, game_id: str) -> str: ...


class LichessBotClient:
    """Official Lichess Bot API client using Personal Access Tokens (OAuth2)."""

    def __init__(
        self,
        token: str,
        username: str = BOT_WHITE_NAME,
        *,
        base_url: str = LICHESS_BASE_URL,
        session: requests.Session | None = None,
        timeout: float = 15.0,
    ) -> None:
        self.token = token
        self.username = username
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.session = session or requests.Session()
        self.session.headers.update(
            {
                "Authorization": f"Bearer {self.token}",
                "Accept": "application/json",
            }
        )

    def get_account(self) -> dict:
        """Fetch the authenticated Lichess user profile (`GET /api/account`)."""
        resp = self.session.get(f"{self.base_url}/api/account", timeout=self.timeout)
        if resp.status_code != 200:
            raise LichessAPIError(
                f"Failed to fetch Lichess account ({resp.status_code}): {resp.text}"
            )
        data = resp.json()
        if "username" in data:
            self.username = data["username"]
        return data

    def upgrade_to_bot(self) -> bool:
        """Upgrade a fresh Lichess account (0 games played) to a BOT account.

        Calls `POST /api/bot/account/upgrade`. If the account is already a BOT,
        returns True.
        """
        account = self.get_account()
        if account.get("title") == "BOT":
            return True

        resp = self.session.post(
            f"{self.base_url}/api/bot/account/upgrade",
            timeout=self.timeout,
        )
        if resp.status_code != 200:
            raise LichessAPIError(
                f"Failed to upgrade {self.username} to BOT ({resp.status_code}): {resp.text}"
            )
        return True

    def create_challenge(
        self,
        opponent_username: str,
        *,
        rated: bool = False,
        clock_limit: int = 300,
        clock_increment: int = 3,
        color: str = "white",
    ) -> dict:
        """Create an unrated challenge against `opponent_username` (`POST /api/challenge/{user}`)."""
        if rated:
            raise ValueError("ChessCrypt only uses unrated bot games (rated must be False).")

        payload = {
            "rated": "false",
            "clock.limit": str(clock_limit),
            "clock.increment": str(clock_increment),
            "color": color,
            "variant": "standard",
        }
        resp = self.session.post(
            f"{self.base_url}/api/challenge/{opponent_username}",
            data=payload,
            timeout=self.timeout,
        )
        if resp.status_code not in (200, 201):
            raise LichessAPIError(
                f"Failed to create challenge vs {opponent_username} ({resp.status_code}): {resp.text}"
            )
        data = resp.json()
        return data.get("challenge", data)

    def accept_challenge(self, challenge_id: str) -> bool:
        """Accept an incoming challenge (`POST /api/challenge/{challengeId}/accept`)."""
        resp = self.session.post(
            f"{self.base_url}/api/challenge/{challenge_id}/accept",
            timeout=self.timeout,
        )
        if resp.status_code != 200:
            raise LichessAPIError(
                f"Failed to accept challenge {challenge_id} ({resp.status_code}): {resp.text}"
            )
        return True

    def make_move(self, game_id: str, uci_move: str) -> bool:
        """Play a UCI move in an active bot game (`POST /api/bot/game/{gameId}/move/{move}`)."""
        resp = self.session.post(
            f"{self.base_url}/api/bot/game/{game_id}/move/{uci_move}",
            timeout=self.timeout,
        )
        if resp.status_code != 200:
            raise LichessAPIError(
                f"Failed to play move {uci_move} in game {game_id} ({resp.status_code}): {resp.text}"
            )
        return True

    def resign_game(self, game_id: str) -> bool:
        """Resign an active bot game (`POST /api/bot/game/{gameId}/resign`)."""
        resp = self.session.post(
            f"{self.base_url}/api/bot/game/{game_id}/resign",
            timeout=self.timeout,
        )
        if resp.status_code != 200:
            raise LichessAPIError(
                f"Failed to resign game {game_id} ({resp.status_code}): {resp.text}"
            )
        return True

    def stream_game_events(self, game_id: str) -> Iterator[dict]:
        """Stream NDJSON game events (`GET /api/bot/game/stream/{gameId}`)."""
        with self.session.get(
            f"{self.base_url}/api/bot/game/stream/{game_id}",
            headers={"Accept": "application/x-ndjson"},
            stream=True,
            timeout=self.timeout,
        ) as resp:
            if resp.status_code != 200:
                raise LichessAPIError(
                    f"Failed to stream game {game_id} ({resp.status_code}): {resp.text}"
                )
            for line in resp.iter_lines():
                if line:
                    yield json.loads(line.decode("utf-8"))

    def export_game_pgn(self, game_id: str) -> str:
        """Download the archived PGN of a game (`GET /game/export/{gameId}`)."""
        resp = self.session.get(
            f"{self.base_url}/game/export/{game_id}",
            params={"clocks": "false", "evals": "false", "opening": "false"},
            headers={"Accept": "application/x-chess-pgn"},
            timeout=self.timeout,
        )
        if resp.status_code != 200:
            raise LichessAPIError(
                f"Failed to export PGN for game {game_id} ({resp.status_code}): {resp.text}"
            )
        return resp.text.strip()

    def export_user_games_pgn(
        self,
        username: str | None = None,
        *,
        vs: str | None = None,
        max_games: int = 10,
    ) -> str:
        """Download recent unrated games of a bot user in PGN format."""
        target = username or self.username
        params: dict[str, str | int] = {
            "max": max_games,
            "rated": "false",
            "clocks": "false",
            "evals": "false",
        }
        if vs:
            params["vs"] = vs
        resp = self.session.get(
            f"{self.base_url}/api/games/user/{target}",
            params=params,
            headers={"Accept": "application/x-chess-pgn"},
            timeout=self.timeout,
        )
        if resp.status_code != 200:
            raise LichessAPIError(
                f"Failed to export games for user {target} ({resp.status_code}): {resp.text}"
            )
        return resp.text.strip()


@dataclass
class _SimGame:
    game_id: str
    white: str
    black: str
    rated: bool
    board: chess.Board = field(default_factory=chess.Board)
    uci_moves: list[str] = field(default_factory=list)
    status: str = "created"
    result: str = "*"


class SimulatedLichessServer:
    """In-memory Lichess Bot API simulator for offline execution and automated testing."""

    def __init__(self) -> None:
        self.accounts: dict[str, dict] = {
            BOT_WHITE_NAME: {"id": BOT_WHITE_NAME.lower(), "username": BOT_WHITE_NAME, "title": "BOT"},
            BOT_BLACK_NAME: {"id": BOT_BLACK_NAME.lower(), "username": BOT_BLACK_NAME, "title": "BOT"},
        }
        self.challenges: dict[str, dict] = {}
        self.games: dict[str, _SimGame] = {}

    def create_client(self, username: str) -> "SimulatedLichessBotClient":
        if username not in self.accounts:
            self.accounts[username] = {
                "id": username.lower(),
                "username": username,
                "title": None,
            }
        return SimulatedLichessBotClient(self, username)


class SimulatedLichessBotClient:
    """Simulated LichessBotClient backed by SimulatedLichessServer."""

    def __init__(self, server: SimulatedLichessServer, username: str) -> None:
        self.server = server
        self.username = username

    def get_account(self) -> dict:
        return dict(self.server.accounts[self.username])

    def upgrade_to_bot(self) -> bool:
        self.server.accounts[self.username]["title"] = "BOT"
        return True

    def create_challenge(
        self,
        opponent_username: str,
        *,
        rated: bool = False,
        clock_limit: int = 300,
        clock_increment: int = 3,
        color: str = "white",
    ) -> dict:
        if rated:
            raise ValueError("ChessCrypt only uses unrated bot games (rated must be False).")
        challenge_id = secrets.token_urlsafe(6)[:8].replace("-", "x").replace("_", "z")
        white = self.username if color == "white" else opponent_username
        black = opponent_username if color == "white" else self.username
        challenge = {
            "id": challenge_id,
            "status": "created",
            "rated": False,
            "challenger": {"id": self.username.lower(), "name": self.username, "title": "BOT"},
            "destUser": {"id": opponent_username.lower(), "name": opponent_username, "title": "BOT"},
            "color": color,
            "white": white,
            "black": black,
            "clock": {"limit": clock_limit, "increment": clock_increment},
        }
        self.server.challenges[challenge_id] = challenge
        return challenge

    def accept_challenge(self, challenge_id: str) -> bool:
        if challenge_id not in self.server.challenges:
            raise LichessAPIError(f"Challenge {challenge_id} not found.")
        ch = self.server.challenges[challenge_id]
        ch["status"] = "accepted"
        self.server.games[challenge_id] = _SimGame(
            game_id=challenge_id,
            white=ch["white"],
            black=ch["black"],
            rated=ch["rated"],
            status="started",
        )
        return True

    def make_move(self, game_id: str, uci_move: str) -> bool:
        if game_id not in self.server.games:
            raise LichessAPIError(f"Game {game_id} not found.")
        sim_game = self.server.games[game_id]
        if sim_game.status != "started":
            raise LichessAPIError(f"Game {game_id} is not active (status={sim_game.status}).")

        expected_player = (
            sim_game.white if sim_game.board.turn == chess.WHITE else sim_game.black
        )
        if self.username != expected_player:
            raise LichessAPIError(
                f"It is {expected_player}'s turn in game {game_id}, not {self.username}'s."
            )

        move = chess.Move.from_uci(uci_move)
        if move not in sim_game.board.legal_moves:
            raise LichessAPIError(
                f"Illegal move {uci_move} in game {game_id} at FEN {sim_game.board.fen()}."
            )

        sim_game.board.push(move)
        sim_game.uci_moves.append(uci_move)
        return True

    def resign_game(self, game_id: str) -> bool:
        if game_id not in self.server.games:
            raise LichessAPIError(f"Game {game_id} not found.")
        sim_game = self.server.games[game_id]
        sim_game.status = "resign"
        sim_game.result = "0-1" if self.username == sim_game.white else "1-0"
        return True

    def export_game_pgn(self, game_id: str) -> str:
        if game_id not in self.server.games:
            raise LichessAPIError(f"Game {game_id} not found.")
        sim_game = self.server.games[game_id]
        game = chess.pgn.Game()
        game.headers["Event"] = "Casual Bot Game"
        game.headers["Site"] = f"https://lichess.org/{sim_game.game_id}"
        game.headers["Date"] = "2026.11.19"
        game.headers["White"] = sim_game.white
        game.headers["Black"] = sim_game.black
        game.headers["Result"] = sim_game.result
        game.headers["WhiteTitle"] = "BOT"
        game.headers["BlackTitle"] = "BOT"

        node: chess.pgn.GameNode = game
        for uci in sim_game.uci_moves:
            node = node.add_variation(chess.Move.from_uci(uci))

        exporter = chess.pgn.StringExporter(headers=True, variations=False, comments=False)
        return game.accept(exporter).strip()


@dataclass
class PlayedMatchRecord:
    """Metadata and archived PGN for a single unrated bot match played on Lichess."""

    game_id: str
    url: str
    white_bot: str
    black_bot: str
    rated: bool
    plies_played: int
    uci_moves: list[str]
    pgn: str


class LichessMatchOrchestrator:
    """Orchestrates two unrated Lichess bots (`RookCipherBot` & `PawnVaultBot`) to store and fetch data."""

    def __init__(
        self,
        white_client: BotClientProtocol,
        black_client: BotClientProtocol,
        *,
        move_delay_seconds: float = 0.0,
    ) -> None:
        self.white_client = white_client
        self.black_client = black_client
        self.move_delay_seconds = move_delay_seconds

    def ensure_bots_ready(self) -> tuple[dict, dict]:
        """Verify both accounts and upgrade them to Lichess BOT accounts if needed."""
        self.white_client.upgrade_to_bot()
        self.black_client.upgrade_to_bot()
        return self.white_client.get_account(), self.black_client.get_account()

    def play_encoded_game(self, encoded_game: EncodedGame) -> PlayedMatchRecord:
        """Have White challenge Black to an unrated match and play out `encoded_game`."""
        challenge = self.white_client.create_challenge(
            self.black_client.username,
            rated=False,
            clock_limit=300,
            clock_increment=3,
            color="white",
        )
        game_id = challenge["id"]
        self.black_client.accept_challenge(game_id)

        for trace in encoded_game.traces:
            active_client = (
                self.white_client if trace.turn == "White" else self.black_client
            )
            active_client.make_move(game_id, trace.uci)
            if self.move_delay_seconds > 0:
                time.sleep(self.move_delay_seconds)

        # Conclude the game cleanly by having the next-to-move bot resign
        next_to_move_is_white = len(encoded_game.traces) % 2 == 0
        resigning_client = (
            self.white_client if next_to_move_is_white else self.black_client
        )
        resigning_client.resign_game(game_id)

        pgn = self.white_client.export_game_pgn(game_id)
        return PlayedMatchRecord(
            game_id=game_id,
            url=f"https://lichess.org/{game_id}",
            white_bot=self.white_client.username,
            black_bot=self.black_client.username,
            rated=False,
            plies_played=len(encoded_game.traces),
            uci_moves=encoded_game.uci_moves,
            pgn=pgn,
        )

    def store_text(
        self,
        text: str,
        *,
        passphrase: str | None = None,
        max_chunk_bytes: int = 32,
    ) -> list[PlayedMatchRecord]:
        """Encode `text` into chess game(s) and play them out between the two unrated bots."""
        games = encode_text(
            text,
            passphrase=passphrase,
            max_chunk_bytes=max_chunk_bytes,
            white_name=self.white_client.username,
            black_name=self.black_client.username,
        )
        return [self.play_encoded_game(g) for g in games]

    def store_bytes(
        self,
        data: bytes,
        *,
        passphrase: str | None = None,
        max_chunk_bytes: int = 32,
    ) -> list[PlayedMatchRecord]:
        """Encode `data` into chess game(s) and play them out between the two unrated bots."""
        games = encode_bytes(
            data,
            passphrase=passphrase,
            max_chunk_bytes=max_chunk_bytes,
            white_name=self.white_client.username,
            black_name=self.black_client.username,
        )
        return [self.play_encoded_game(g) for g in games]

    def fetch_and_decode(
        self,
        game_ids: list[str],
        *,
        passphrase: str | None = None,
    ) -> DecodedResult:
        """Fetch PGNs for `game_ids` from Lichess and decode the original secret payload."""
        pgns = [self.white_client.export_game_pgn(gid) for gid in game_ids]
        combined_pgn = "\n\n".join(pgns)
        return decode_pgn(combined_pgn, passphrase=passphrase)
