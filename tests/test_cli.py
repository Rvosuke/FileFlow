from pathlib import Path

from typer.testing import CliRunner

from fileflow.cli import app
from fileflow.db.operations import Database


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


def test_config_edit_uses_editor(monkeypatch, tmp_path: Path) -> None:
    app_home = tmp_path / "app"
    monkeypatch.setenv("FILEFLOW_HOME", str(app_home))
    monkeypatch.setenv("EDITOR", "fake-editor")

    calls: list[list[str]] = []

    def fake_run(command: list[str], check: bool = False):
        calls.append(command)
        return None

    monkeypatch.setattr("fileflow.cli.subprocess.run", fake_run)

    assert runner.invoke(app, ["init"]).exit_code == 0
    edit_result = runner.invoke(app, ["config", "edit"])

    assert edit_result.exit_code == 0
    assert calls
    assert calls[0][0] == "fake-editor"


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

    preview_result = runner.invoke(app, ["preview"])
    assert preview_result.exit_code == 0
    assert "Preview mode" in preview_result.stdout


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


def test_feedback_apply_and_list(monkeypatch, tmp_path: Path) -> None:
    app_home = tmp_path / "app"
    source_dir = tmp_path / "Downloads"
    target_dir = tmp_path / "Organized"
    source_dir.mkdir()
    target_dir.mkdir()
    original_file = source_dir / "invoice_202403.txt"
    original_file.write_text("hello fileflow\n" * 128, encoding="utf-8")

    monkeypatch.setenv("FILEFLOW_HOME", str(app_home))

    assert runner.invoke(app, ["init"]).exit_code == 0
    assert runner.invoke(app, ["source", "add", str(source_dir)]).exit_code == 0
    assert runner.invoke(app, ["config", "set", "general.target_root", str(target_dir)]).exit_code == 0
    assert runner.invoke(app, ["scan", "--execute"]).exit_code == 0

    correction_result = runner.invoke(app, ["feedback", "apply", "1", "文档/归档"])
    assert correction_result.exit_code == 0
    assert "Correction applied" in correction_result.stdout

    corrected_file = target_dir / "文档" / "归档" / "invoice_202403.txt"
    assert corrected_file.exists()

    list_result = runner.invoke(app, ["feedback", "list"])
    assert list_result.exit_code == 0
    assert "文档/归档" in list_result.stdout

    rules_result = runner.invoke(app, ["rules"])
    assert rules_result.exit_code == 0
    assert "文档/归档" in rules_result.stdout

    pattern_rules_result = runner.invoke(app, ["rules", "--type", "pattern"])
    assert pattern_rules_result.exit_code == 0
    pattern_rules = Database(app_home / "fileflow.db").get_rule_cache_entries(match_type="pattern")
    assert any(
        row["target_path"] == "文档/归档" and r"\d+" in row["match_key"]
        for row in pattern_rules
    )

    status_result = runner.invoke(app, ["status"])
    assert status_result.exit_code == 0
    assert "Corrections" in status_result.stdout
    assert "1" in status_result.stdout


def test_feedback_learning_affects_future_ai_scan(monkeypatch, tmp_path: Path) -> None:
    app_home = tmp_path / "app"
    source_dir = tmp_path / "Downloads"
    target_dir = tmp_path / "Organized"
    source_dir.mkdir()
    target_dir.mkdir()

    first_file = source_dir / "invoice_202403.txt"
    first_file.write_text("hello fileflow\n" * 128, encoding="utf-8")

    monkeypatch.setenv("FILEFLOW_HOME", str(app_home))

    assert runner.invoke(app, ["init"]).exit_code == 0
    assert runner.invoke(app, ["source", "add", str(source_dir)]).exit_code == 0
    assert runner.invoke(app, ["config", "set", "general.target_root", str(target_dir)]).exit_code == 0
    assert runner.invoke(app, ["scan", "--execute"]).exit_code == 0
    assert runner.invoke(app, ["feedback", "apply", "1", "文档/归档"]).exit_code == 0

    second_file = source_dir / "invoice_202404.txt"
    second_file.write_text("hello fileflow\n" * 128, encoding="utf-8")

    ai_scan_result = runner.invoke(app, ["scan", "--ai"])

    assert ai_scan_result.exit_code == 0
    assert "1 cache hits" in ai_scan_result.stdout
    assert "文档/归档" in ai_scan_result.stdout


def test_rules_add_pattern_and_exact(monkeypatch, tmp_path: Path) -> None:
    app_home = tmp_path / "app"
    monkeypatch.setenv("FILEFLOW_HOME", str(app_home))

    assert runner.invoke(app, ["init"]).exit_code == 0

    add_pattern_result = runner.invoke(
        app,
        ["rules", "add-pattern", r"invoice_\d+\.txt", "文档/归档"],
    )
    assert add_pattern_result.exit_code == 0
    assert "Added pattern rule" in add_pattern_result.stdout

    add_exact_result = runner.invoke(
        app,
        ["rules", "add-exact", "salary_slip.pdf", "文档/财务"],
    )
    assert add_exact_result.exit_code == 0
    assert "Added exact rule" in add_exact_result.stdout

    add_type_dir_result = runner.invoke(
        app,
        ["rules", "add-type-dir", ".exe", "Downloads", "安装包/开发工具"],
    )
    assert add_type_dir_result.exit_code == 0
    assert "Added type_dir rule" in add_type_dir_result.stdout

    database = Database(app_home / "fileflow.db")
    pattern_rules = database.get_rule_cache_entries(match_type="pattern")
    exact_rules = database.get_rule_cache_entries(match_type="exact")
    type_dir_rules = database.get_rule_cache_entries(match_type="type_dir")

    assert any(rule["match_key"] == r"invoice_\d+\.txt" for rule in pattern_rules)
    assert any(rule["match_key"] == "salary_slip.pdf" for rule in exact_rules)
    assert any(rule["match_key"] == ".exe:Downloads" for rule in type_dir_rules)
