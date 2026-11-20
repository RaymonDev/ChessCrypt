"""Tests for the ChessCrypt CLI (`chesscrypt.cli`)."""

from chesscrypt.cli import main


def test_cli_demo_runs_hello_world(capsys):
    rc = main(["demo"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "Hello World" in out
    assert "RookCipherBot" in out
    assert "PawnVaultBot" in out
    assert "SUCCESS (100% lossless match)" in out


def test_cli_encode_and_decode_roundtrip(tmp_path, capsys):
    pgn_file = tmp_path / "hello.pgn"
    rc_enc = main(["encode", "Hello World", "-o", str(pgn_file)])
    assert rc_enc == 0
    assert pgn_file.exists()

    rc_dec = main(["decode", "-f", str(pgn_file)])
    assert rc_dec == 0
    out = capsys.readouterr().out.strip()
    assert out == "Hello World"


def test_cli_dictionary_command(capsys):
    rc = main(["dictionary"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "Radix ($N$): 20 legal moves" in out or "**Radix ($N$):** 20 legal moves" in out
    assert "`d2d3`" in out


def test_cli_store_lichess_simulated(capsys):
    rc = main(["store-lichess", "Hello World", "--simulate"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "Stored in Unrated Game: https://lichess.org/" in out
    assert "1. d3 b6 2. f3 f5" in out


def test_cli_binary_file_roundtrip(tmp_path, capsys):
    blob = b"\x00\x00" + bytes(range(0, 256, 9)) + b"\xff\x00"
    src = tmp_path / "blob.bin"
    src.write_bytes(blob)
    pgn_file = tmp_path / "blob.pgn"
    out_file = tmp_path / "restored.bin"

    assert main(["encode", "-i", str(src), "--passphrase", "pw", "-o", str(pgn_file)]) == 0
    assert main(["decode", "-f", str(pgn_file), "--passphrase", "pw", "-o", str(out_file)]) == 0
    assert out_file.read_bytes() == blob


def test_cli_binary_payload_to_stdout_is_a_clean_error(tmp_path, capsys):
    pgn_file = tmp_path / "bin.pgn"
    src = tmp_path / "bin.dat"
    src.write_bytes(b"\xff\xfe\x00")
    assert main(["encode", "-i", str(src), "-o", str(pgn_file)]) == 0
    capsys.readouterr()

    assert main(["decode", "-f", str(pgn_file)]) == 1
    err = capsys.readouterr().err
    assert "binary" in err and "--output" in err


def test_cli_wrong_passphrase_reports_error_without_traceback(tmp_path, capsys):
    pgn_file = tmp_path / "secret.pgn"
    assert main(["encode", "top secret", "--passphrase", "right", "-o", str(pgn_file)]) == 0
    assert main(["decode", "-f", str(pgn_file), "--passphrase", "wrong"]) == 1
    assert "chesscrypt: error: Decryption failed" in capsys.readouterr().err


def test_cli_passphrase_from_environment(tmp_path, capsys, monkeypatch):
    monkeypatch.setenv("CHESSCRYPT_PASSPHRASE", "from-env")
    pgn_file = tmp_path / "env.pgn"
    assert main(["encode", "env secret", "-o", str(pgn_file)]) == 0
    capsys.readouterr()

    from chesscrypt.encoder import decode_pgn

    assert decode_pgn(pgn_file.read_text(), passphrase="from-env").text == "env secret"


def test_cli_encode_requires_input(capsys):
    assert main(["encode"]) == 1
    assert "Nothing to encode" in capsys.readouterr().err


def test_cli_fetch_lichess_decodes_exported_games(monkeypatch, capsys):
    from chesscrypt.encoder import encode_text
    from chesscrypt.lichess import LichessBotClient

    game = encode_text("Fetched from Lichess")[0]
    requested = []

    def fake_export(self, game_id):
        requested.append(game_id)
        return game.to_pgn(game_id)

    monkeypatch.setattr(LichessBotClient, "export_game_pgn", fake_export)
    assert main(["fetch-lichess", "https://lichess.org/AbCd1234/black"]) == 0
    assert requested == ["AbCd1234"]
    assert capsys.readouterr().out.strip() == "Fetched from Lichess"


def test_parse_game_id_accepts_ids_and_urls():
    import pytest

    from chesscrypt.cli import _parse_game_id

    assert _parse_game_id("AbCd1234") == "AbCd1234"
    assert _parse_game_id("AbCd1234wxyz") == "AbCd1234"
    assert _parse_game_id("lichess.org/AbCd1234") == "AbCd1234"
    assert _parse_game_id("https://lichess.org/game/export/AbCd1234") == "AbCd1234"
    with pytest.raises(ValueError):
        _parse_game_id("https://lichess.org/@/someone")
