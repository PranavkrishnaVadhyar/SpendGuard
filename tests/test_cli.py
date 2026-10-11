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


def test_insights_and_expected_cli_errors(tmp_path, capsys):
    import json
    path = str(tmp_path / 'insights.db')
    assert main(['--db', path, 'insights']) == 0
    snapshot = json.loads(capsys.readouterr().out)
    assert snapshot['usage_totals']['calls'] == 0 and snapshot['teams'] == []
    assert main(['--db', path, 'kill', '--agent', 'missing']) == 1
    assert 'unknown agent' in capsys.readouterr().err
    assert main(['--db', path, 'feed', '--limit', '-1']) == 1
    assert capsys.readouterr().err


def test_dashboard_env_file_is_loaded_without_launching_server(tmp_path, monkeypatch):
    pytest.importorskip('dotenv')
    import spendguard.cli as cli
    path = tmp_path / '.env'
    path.write_text('SPENDGUARD_SMTP_HOST=smtp.test.invalid\n', encoding='utf-8')
    monkeypatch.delenv('SPENDGUARD_SMTP_HOST', raising=False)
    monkeypatch.setattr(cli, '_run_dashboard', lambda path, port: 0)
    try:
        assert main(['dashboard', '--env-file', str(path)]) == 0
        assert cli.os.environ['SPENDGUARD_SMTP_HOST'] == 'smtp.test.invalid'
    finally:
        cli.os.environ.pop('SPENDGUARD_SMTP_HOST', None)
