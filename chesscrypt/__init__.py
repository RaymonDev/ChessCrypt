"""ChessCrypt: Encode and store arbitrary data inside legal chess games on Lichess."""

from chesscrypt.crypto import CryptoError, decrypt_payload, encrypt_payload
from chesscrypt.dictionary import MoveEntry, get_position_dictionary
from chesscrypt.encoder import (
    DecodedResult,
    EncodedGame,
    PlyTrace,
    bigint_to_bytes,
    bytes_to_bigint,
    decode_games,
    decode_moves,
    decode_pgn,
    encode_bytes,
    encode_text,
)
from chesscrypt.lichess import (
    BOT_BLACK_NAME,
    BOT_WHITE_NAME,
    LichessAPIError,
    LichessBotClient,
    LichessMatchOrchestrator,
    SimulatedLichessServer,
)
from chesscrypt.viewer import (
    format_dictionary_grid,
    format_frame_2d,
    play_2d_terminal_match,
    render_board_2d_lines,
    render_progress_bar,
)

__all__ = [
    "BOT_BLACK_NAME",
    "BOT_WHITE_NAME",
    "CryptoError",
    "DecodedResult",
    "EncodedGame",
    "LichessAPIError",
    "LichessBotClient",
    "LichessMatchOrchestrator",
    "MoveEntry",
    "PlyTrace",
    "SimulatedLichessServer",
    "bigint_to_bytes",
    "bytes_to_bigint",
    "decode_games",
    "decode_moves",
    "decode_pgn",
    "decrypt_payload",
    "encode_bytes",
    "encode_text",
    "encrypt_payload",
    "format_dictionary_grid",
    "format_frame_2d",
    "get_position_dictionary",
    "play_2d_terminal_match",
    "render_board_2d_lines",
    "render_progress_bar",
]
