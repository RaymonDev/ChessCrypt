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
