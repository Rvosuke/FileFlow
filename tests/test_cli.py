from pathlib import Path

from typer.testing import CliRunner

from fileflow.cli import app


runner = CliRunner()


def test_init_and_status(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("FILEFLOW_HOME", str(tmp_path / "app"))

    init_result = runner.invoke(app, ["init"])
    assert init_result.exit_code == 0
    assert "Initialized" in init_result.stdout

    status_result = runner.invoke(app, ["status"])
    assert status_result.exit_code == 0
    assert "Initialized" in status_result.stdout
    assert "yes" in status_result.stdout


def test_source_add_and_scan(monkeypatch, tmp_path: Path) -> None:
    app_home = tmp_path / "app"
    source_dir = tmp_path / "Downloads"
    source_dir.mkdir()
    (source_dir / "note.txt").write_text("hello fileflow\n" * 128, encoding="utf-8")
    (source_dir / "tiny.tmp").write_text(".", encoding="utf-8")

    monkeypatch.setenv("FILEFLOW_HOME", str(app_home))

    assert runner.invoke(app, ["init"]).exit_code == 0
    add_result = runner.invoke(app, ["source", "add", str(source_dir)])
    assert add_result.exit_code == 0

    scan_result = runner.invoke(app, ["scan"])
    assert scan_result.exit_code == 0
    assert "Scanning... found 1 files" in scan_result.stdout
    assert "1 classified" in scan_result.stdout
    assert "Preview mode" in scan_result.stdout
    assert "No files matched" not in scan_result.stdout


def test_execute_and_undo(monkeypatch, tmp_path: Path) -> None:
    app_home = tmp_path / "app"
    source_dir = tmp_path / "Downloads"
    target_dir = tmp_path / "Organized"
    source_dir.mkdir()
    target_dir.mkdir()
    original_file = source_dir / "note.txt"
    original_file.write_text("hello fileflow\n" * 128, encoding="utf-8")

    monkeypatch.setenv("FILEFLOW_HOME", str(app_home))

    assert runner.invoke(app, ["init"]).exit_code == 0
    assert runner.invoke(app, ["source", "add", str(source_dir)]).exit_code == 0
    assert runner.invoke(app, ["config", "set", "general.target_root", str(target_dir)]).exit_code == 0

    execute_result = runner.invoke(app, ["scan", "--execute"])
    assert execute_result.exit_code == 0
    assert "Moved 1 file(s)" in execute_result.stdout
    assert not original_file.exists()

    moved_file = target_dir / "文档" / "文本" / "note.txt"
    assert moved_file.exists()

    undo_result = runner.invoke(app, ["undo"])
    assert undo_result.exit_code == 0
    assert "Rolled back 1/1 operation(s)." in undo_result.stdout
    assert original_file.exists()
    assert not moved_file.exists()
