"""CLI integration checks; skipped until Person A's public core is available."""
import pytest


core = pytest.importorskip(
    "spendguard",
    reason="Person A's SpendGuard core is not present in this checkout yet",
)
if not hasattr(core, "SpendGuard"):
    pytest.skip("Person A's SpendGuard core is not present in this checkout yet", allow_module_level=True)

from spendguard.cli import main


def test_status_and_empty_pending(tmp_path, capsys):
    db_path = str(tmp_path / "cli.sqlite")
    assert main(["--db", db_path, "status"]) == 0
    assert "Global kill" in capsys.readouterr().out
    assert main(["--db", db_path, "pending"]) == 0
    assert "No requests" in capsys.readouterr().out
    assert main(["--db", db_path, "kill"]) == 0
    assert "Kill set" in capsys.readouterr().out
    assert main(["--db", db_path, "resume"]) == 0
    assert "Resumed" in capsys.readouterr().out


def test_unknown_request_has_friendly_error(tmp_path, capsys):
    db_path = str(tmp_path / "cli.sqlite")
    for command in ("approve", "reject"):
        result = main(["--db", db_path, command, "missing-id"])
        assert result == 1
        assert capsys.readouterr().err
