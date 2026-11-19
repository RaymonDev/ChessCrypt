"""ChessCrypt: Encode and store arbitrary data inside legal chess games on Lichess."""

from chesscrypt.crypto import CryptoError, decrypt_payload, encrypt_payload
from chesscrypt.dictionary import MoveEntry, get_position_dictionary
from chesscrypt.encoder import (
    DecodedResult,
    EncodedGame,
    PlyTrace,
    bytes_to_bigint,
    bigint_to_bytes,
    decode_games,
    decode_moves,
    decode_pgn,
    encode_bytes,
    encode_text,
)
from chesscrypt.lichess import (
    BOT_BLACK_NAME,
    BOT_WHITE_NAME,
    LichessBotClient,
    LichessMatchOrchestrator,
    SimulatedLichessServer,
)

__all__ = [
    "BOT_BLACK_NAME",
    "BOT_WHITE_NAME",
    "CryptoError",
    "DecodedResult",
    "EncodedGame",
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
    "get_position_dictionary",
]
