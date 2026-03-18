from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

# Fix Windows console encoding for CJK characters
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

from rich.console import Console
from rich.pretty import Pretty
from rich.table import Table
import typer

from fileflow import __version__
from fileflow.config import (
    add_source_path,
    initialize_app,
    is_initialized,
    load_config,
    remove_source_path,
    resolve_app_paths,
    save_config,
    set_config_value,
)
from fileflow.db.operations import Database
from fileflow.scanner import FileScanner
from fileflow.utils.logger import configure_logging


app = typer.Typer(help="FileFlow CLI")
source_app = typer.Typer(help="Manage source folders")
config_app = typer.Typer(help="Inspect and edit config")
feedback_app = typer.Typer(help="Record and inspect user corrections")
rules_app = typer.Typer(help="Inspect and manage learned rules", invoke_without_command=True)
console = Console()


def _require_initialized() -> None:
    if not is_initialized():
        console.print("[red]FileFlow 尚未初始化，请先运行 `fileflow init`。[/red]")
        raise typer.Exit(code=1)


@app.callback()
def main_callback() -> None:
    """FileFlow entrypoint."""


@app.command()
def version() -> None:
    console.print(f"FileFlow {__version__}")


@app.command()
def init(force: bool = typer.Option(False, help="Overwrite the existing config template.")) -> None:
    paths = initialize_app(force=force)
    console.print(f"[green]Initialized[/green] at {paths.home}")
    console.print(f"Config: {paths.config_file}")
    console.print(f"Database: {paths.database_file}")


@source_app.command("add")
def source_add(path: Path) -> None:
    _require_initialized()
    config = load_config()
    if not add_source_path(config, str(path)):
        console.print(f"[yellow]Source already exists:[/yellow] {path}")
        raise typer.Exit(code=0)
    save_config(config)
    console.print(f"[green]Added source[/green] {path}")


@source_app.command("remove")
def source_remove(path: Path) -> None:
    _require_initialized()
    config = load_config()
    if not remove_source_path(config, str(path)):
        console.print(f"[yellow]Source not found:[/yellow] {path}")
        raise typer.Exit(code=1)
    save_config(config)
    console.print(f"[green]Removed source[/green] {path}")


@source_app.command("list")
def source_list() -> None:
    _require_initialized()
    config = load_config()
    if not config.sources.paths:
        console.print("[yellow]No source folders configured.[/yellow]")
        return

    table = Table(title="Source Folders")
    table.add_column("#", justify="right")
    table.add_column("Path")
    for index, source in enumerate(config.sources.paths, start=1):
        table.add_row(str(index), source)
    console.print(table)


@config_app.command("show")
def config_show() -> None:
    _require_initialized()
    config = load_config()
    console.print(Pretty(config.to_dict()))


@config_app.command("set")
def config_set(key: str, value: str) -> None:
    _require_initialized()
    config = load_config()
    try:
        set_config_value(config, key, value)
    except (KeyError, ValueError) as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=1) from exc
    save_config(config)
    console.print(f"[green]Updated[/green] {key} = {value}")


@config_app.command("edit")
def config_edit() -> None:
    """Open the config file in the preferred editor."""
    _require_initialized()
    paths = resolve_app_paths()
    editor = os.getenv("EDITOR")

    if editor:
        subprocess.run([editor, str(paths.config_file)], check=False)
        console.print(f"[green]Opened config in {editor}[/green]")
        return

    if hasattr(os, "startfile"):
        os.startfile(str(paths.config_file))  # type: ignore[attr-defined]
        console.print(f"[green]Opened config[/green] {paths.config_file}")
        return

    console.print(f"[yellow]No editor configured. Config file:[/yellow] {paths.config_file}")


@app.command()
def status() -> None:
    paths = resolve_app_paths()
    initialized = is_initialized()
    table = Table(title="FileFlow Status")
    table.add_column("Item")
    table.add_column("Value")
    table.add_row("Home", str(paths.home))
    table.add_row("Initialized", "yes" if initialized else "no")
    table.add_row("Config", str(paths.config_file))
    table.add_row("Database", str(paths.database_file))

    if initialized:
        config = load_config()
        database = Database(paths.database_file)
        stats = database.get_stats()
        table.add_row("Source folders", str(len(config.sources.paths)))
        table.add_row("Move records", str(stats.move_records))
        table.add_row("Rule cache rows", str(stats.rule_cache_rows))
        table.add_row("Corrections", str(stats.corrections))
        table.add_row("Scans logged", str(stats.scan_logs))
        table.add_row("Last scan", stats.last_scan_at or "never")

    console.print(table)


@app.command()
def scan(
    path: Path | None = typer.Option(None, help="Scan a custom path instead of configured sources."),
    file_type: str | None = typer.Option(None, "--type", help="Filter by broad category."),
    ai: bool = typer.Option(False, "--ai", help="Use AI classification (requires LLM provider)."),
    execute: bool = typer.Option(False, "--execute", "-e", help="Actually move files (default is dry-run preview)."),
) -> None:
    _require_initialized()
    config = load_config()
    scanner = FileScanner(config)
    result = scanner.scan(scan_path=path, category_filter=file_type)

    if not result.files:
        console.print("[yellow]No files matched the current scan settings.[/yellow]")
        return

    console.print(f"\nScanning... found {len(result.files)} files\n")

    # Classify files
    from fileflow.ai.engine import DecisionEngine
    paths = resolve_app_paths()
    database = Database(paths.database_file)

    if ai:
        engine = DecisionEngine(config, database)
        classifications = engine.classify(result.files)
        console.print("[green][AI mode][/green] Using AI + rule cache + heuristic classification.")
    else:
        from fileflow.ai.decision import HeuristicClassifier
        heuristic = HeuristicClassifier()
        classifications = heuristic.classify_batch(result.files)
        console.print("[cyan][heuristic mode][/cyan] Using extension-based rules. Add --ai for AI classification.")

    # Display results table
    table = Table(title="Scan Results" + (" (EXECUTE)" if execute else " (preview)"))
    table.add_column("File", max_width=30)
    table.add_column("Target", max_width=30)
    table.add_column("Confidence", justify="right")
    table.add_column("Source")

    cache_count = 0
    llm_count = 0
    for cr in classifications:
        conf_str = f"{cr.confidence:.2f}"
        if cr.confidence >= 0.8:
            conf_str = f"[green]{conf_str}[/green]"
        elif cr.confidence >= 0.6:
            conf_str = f"[yellow]{conf_str}[/yellow]"
        else:
            conf_str = f"[red]{conf_str}[/red]"

        source_str = {
            "heuristic": "[dim]heuristic[/dim]",
            "rule_cache": "[blue]cache[/blue]",
            "llm": "[green]AI[/green]",
        }.get(cr.source, cr.source)

        if cr.source == "rule_cache":
            cache_count += 1
        elif cr.source == "llm":
            llm_count += 1

        if cr.action == "skip":
            table.add_row(
                cr.original_path.name,
                "[dim](skip)[/dim]",
                "-",
                source_str,
            )
        else:
            table.add_row(
                cr.original_path.name,
                cr.target_path,
                conf_str,
                source_str,
            )
    console.print(table)

    review_count = sum(1 for c in classifications if c.action == "review")
    move_count = sum(1 for c in classifications if c.action == "move")
    console.print(
        f"\nSummary: {len(classifications)} classified | "
        f"{cache_count} cache hits | {llm_count} LLM calls | "
        f"{len(result.skipped)} skipped | {result.duration_ms} ms"
    )
    if review_count:
        console.print(f"[yellow]{review_count} file(s) need manual review (low confidence)[/yellow]")

    # Execute moves if requested
    if execute and move_count > 0:
        from fileflow.executor.mover import FileMover
        mover = FileMover(
            target_root=Path(config.general.target_root),
            db_path=paths.database_file,
            create_shortcut=config.general.create_shortcut,
        )
        meta_lookup = {str(m.path): m for m in result.files}
        moved = 0
        failed = 0
        for cr in classifications:
            if cr.action != "move":
                continue
            meta = meta_lookup.get(str(cr.original_path))
            record = mover.execute(cr, meta=meta, dry_run=False)
            if record.status == "completed":
                moved += 1
                console.print(f"  [green]Moved[/green] {cr.original_path.name} -> {cr.target_path}")
            else:
                failed += 1
                console.print(f"  [red]Failed[/red] {cr.original_path.name}")
        console.print(f"\n[green]Done![/green] Moved {moved} file(s), {failed} failed.")
        console.print("Use [bold]fileflow undo[/bold] to rollback.")
    elif not execute:
        console.print("\n[yellow]Preview mode. Use --execute to actually move files.[/yellow]")

    source_label = str(path) if path else ", ".join(config.sources.paths) or "<none>"
    database.record_scan(
        source_path=source_label,
        files_found=len(result.files),
        files_moved=move_count if execute else 0,
        files_skipped=len(result.skipped),
        files_cached=cache_count,
        llm_calls=llm_count,
        duration_ms=result.duration_ms,
    )


@app.command()
def preview(
    path: Path | None = typer.Option(None, help="Preview a custom path instead of configured sources."),
    file_type: str | None = typer.Option(None, "--type", help="Filter by broad category."),
    ai: bool = typer.Option(False, "--ai", help="Use AI classification (requires LLM provider)."),
) -> None:
    """Explicit preview alias for `scan` without execution."""
    scan(path=path, file_type=file_type, ai=ai, execute=False)


@app.command()
def undo(
    last: int = typer.Option(1, "--last", "-n", help="Undo the last n moves."),
    all_today: bool = typer.Option(False, "--all", help="Undo all moves made today."),
) -> None:
    """Undo file moves."""
    _require_initialized()
    from fileflow.executor.rollback import RollbackEngine
    paths = resolve_app_paths()
    engine = RollbackEngine(paths.database_file)

    if all_today:
        results = engine.undo_all_today()
    else:
        results = engine.undo_last(last)

    if not results:
        console.print("[yellow]No moves to undo.[/yellow]")
        return

    for r in results:
        if r["success"]:
            console.print(f"  [green]Rolled back[/green] {r['message']}")
        else:
            console.print(f"  [red]Failed[/red] {r['message']}")

    success_count = sum(1 for r in results if r["success"])
    console.print(f"\nRolled back {success_count}/{len(results)} operation(s).")


@app.command()
def history(
    limit: int = typer.Option(20, "--limit", "-n", help="Number of records to show."),
) -> None:
    """Show move history."""
    _require_initialized()
    from fileflow.executor.rollback import RollbackEngine
    paths = resolve_app_paths()
    engine = RollbackEngine(paths.database_file)
    records = engine.get_history(limit)

    if not records:
        console.print("[yellow]No history yet.[/yellow]")
        return

    table = Table(title="Move History")
    table.add_column("ID", style="dim")
    table.add_column("File", max_width=25)
    table.add_column("Target", max_width=30)
    table.add_column("Status")
    table.add_column("Time", style="dim")

    for r in records:
        status_str = {
            "completed": "[green]completed[/green]",
            "rolled_back": "[red]rolled back[/red]",
            "preview": "[dim]preview[/dim]",
            "failed": "[red]failed[/red]",
        }.get(r["status"], r["status"])

        table.add_row(
            str(r["id"]),
            Path(r["source_path"]).name,
            r["target_path"],
            status_str,
            r.get("created_at", ""),
        )
    console.print(table)


def _render_rules(
    limit: int = typer.Option(20, "--limit", "-n", help="Number of rules to show."),
    match_type: str | None = typer.Option(
        None,
        "--type",
        help="Filter by rule type: exact, pattern, type_dir.",
    ),
) -> None:
    _require_initialized()
    paths = resolve_app_paths()
    from fileflow.learning.rules import RuleManager

    manager = RuleManager(Database(paths.database_file))
    entries = manager.list_rules(limit=limit, match_type=match_type)

    if not entries:
        console.print("[yellow]No learned rules yet.[/yellow]")
        return

    table = Table(title="Learned Rules")
    table.add_column("Type", style="dim")
    table.add_column("Match", max_width=26)
    table.add_column("Target", max_width=24)
    table.add_column("Confidence", justify="right")
    table.add_column("Hits", justify="right")
    table.add_column("Last Hit", style="dim")

    for entry in entries:
        table.add_row(
            entry.match_type,
            entry.match_key,
            entry.target_path,
            f"{entry.confidence:.2f}",
            str(entry.hit_count),
            entry.last_hit or "-",
        )

    console.print(table)


@rules_app.callback()
def rules_callback(
    ctx: typer.Context,
    limit: int = typer.Option(20, "--limit", "-n", help="Number of rules to show."),
    match_type: str | None = typer.Option(
        None,
        "--type",
        help="Filter by rule type: exact, pattern, type_dir.",
    ),
) -> None:
    """Show learned rules from the rule cache."""
    if ctx.invoked_subcommand is None:
        _render_rules(limit=limit, match_type=match_type)


@rules_app.command("add-pattern")
def rules_add_pattern(
    pattern: str = typer.Argument(..., help="Regex pattern matched against full filename."),
    target_path: str = typer.Argument(..., help="Relative target path, e.g. 文档/归档"),
    confidence: float = typer.Option(0.95, "--confidence", min=0.0, max=1.0),
) -> None:
    """Add or update a manual regex-based rule."""
    _require_initialized()
    paths = resolve_app_paths()
    from fileflow.ai.decision import normalize_target_path
    from fileflow.learning.rules import RuleManager

    config = load_config()
    safe_target = normalize_target_path(
        target_path,
        allowed_top_levels=config.categories.top_level,
        fallback_top_level="其他",
        max_depth=config.categories.max_depth,
    )
    RuleManager(Database(paths.database_file)).add_pattern_rule(pattern, safe_target, confidence)
    console.print(f"[green]Added pattern rule[/green] {pattern} -> {safe_target}")


@rules_app.command("add-exact")
def rules_add_exact(
    filename: str = typer.Argument(..., help="Exact filename including extension, e.g. invoice_202403.pdf"),
    target_path: str = typer.Argument(..., help="Relative target path, e.g. 文档/归档"),
    confidence: float = typer.Option(0.99, "--confidence", min=0.0, max=1.0),
) -> None:
    """Add or update an exact filename rule."""
    _require_initialized()
    paths = resolve_app_paths()
    from fileflow.ai.decision import normalize_target_path
    from fileflow.learning.rules import RuleManager

    config = load_config()
    safe_target = normalize_target_path(
        target_path,
        allowed_top_levels=config.categories.top_level,
        fallback_top_level="其他",
        max_depth=config.categories.max_depth,
    )
    RuleManager(Database(paths.database_file)).add_exact_rule(filename, safe_target, confidence)
    console.print(f"[green]Added exact rule[/green] {filename} -> {safe_target}")


@rules_app.command("add-type-dir")
def rules_add_type_dir(
    extension: str = typer.Argument(..., help="File extension, e.g. .exe or exe"),
    parent_dir: str = typer.Argument(..., help="Source parent directory name, e.g. Downloads"),
    target_path: str = typer.Argument(..., help="Relative target path, e.g. 安装包/开发工具"),
    confidence: float = typer.Option(0.9, "--confidence", min=0.0, max=1.0),
) -> None:
    """Add or update an extension + source-directory rule."""
    _require_initialized()
    paths = resolve_app_paths()
    from fileflow.ai.decision import normalize_target_path
    from fileflow.learning.rules import RuleManager

    config = load_config()
    safe_target = normalize_target_path(
        target_path,
        allowed_top_levels=config.categories.top_level,
        fallback_top_level="其他",
        max_depth=config.categories.max_depth,
    )
    RuleManager(Database(paths.database_file)).add_type_dir_rule(
        extension=extension,
        parent_dir=parent_dir,
        target_path=safe_target,
        confidence=confidence,
    )
    console.print(
        f"[green]Added type_dir rule[/green] {extension.lower()}:{parent_dir} -> {safe_target}"
    )


@feedback_app.command("apply")
def feedback_apply(
    move_id: int = typer.Argument(..., help="Move record id from `fileflow history`."),
    target_path: str = typer.Argument(..., help="Correct relative target path, e.g. 文档/财务/发票"),
) -> None:
    """Apply a user correction and teach the rule cache."""
    _require_initialized()
    config = load_config()
    paths = resolve_app_paths()
    from fileflow.learning.feedback import FeedbackEngine

    engine = FeedbackEngine(config, Database(paths.database_file))
    result = engine.apply_correction(move_id, target_path)
    if not result.success:
        console.print(f"[red]{result.message}[/red]")
        raise typer.Exit(code=1)

    console.print(
        f"[green]Correction applied[/green] #{result.move_record_id}: "
        f"{result.original_target} -> {result.corrected_target}"
    )
    if result.final_path:
        console.print(f"Final path: {result.final_path}")


@feedback_app.command("list")
def feedback_list(
    limit: int = typer.Option(20, "--limit", "-n", help="Number of corrections to show."),
) -> None:
    """Show recent user corrections."""
    _require_initialized()
    paths = resolve_app_paths()
    database = Database(paths.database_file)
    corrections = database.get_corrections(limit)

    if not corrections:
        console.print("[yellow]No corrections yet.[/yellow]")
        return

    table = Table(title="Corrections")
    table.add_column("ID", style="dim")
    table.add_column("Move ID", style="dim")
    table.add_column("File", max_width=24)
    table.add_column("From", max_width=24)
    table.add_column("To", max_width=24)
    table.add_column("Time", style="dim")

    for item in corrections:
        table.add_row(
            str(item["id"]),
            str(item["move_record_id"]),
            Path(item["source_path"]).name if item.get("source_path") else "-",
            item["original_target"],
            item["corrected_target"],
            item["created_at"],
        )
    console.print(table)


@app.command()
def watch(
    execute: bool = typer.Option(False, "--execute", "-e", help="Move files automatically (default is preview)."),
    ai: bool = typer.Option(False, "--ai", help="Use AI classification."),
) -> None:
    """Watch source folders for new files in real-time."""
    _require_initialized()
    config = load_config()
    paths = resolve_app_paths()
    from fileflow.watcher import start_watching
    start_watching(config, paths.database_file, execute=execute, use_ai=ai)


@app.command()
def dedup(
    path: Path | None = typer.Option(None, help="Scan a specific path instead of configured sources."),
) -> None:
    """Find duplicate files."""
    _require_initialized()
    config = load_config()
    scanner = FileScanner(config)
    result = scanner.scan(scan_path=path)

    if not result.files:
        console.print("[yellow]No files found.[/yellow]")
        return

    from fileflow.analyzer.dedup import find_duplicates
    all_paths = [m.path for m in result.files]
    duplicates = find_duplicates(all_paths)

    if not duplicates:
        console.print(f"[green]No duplicates found among {len(all_paths)} files.[/green]")
        return

    table = Table(title="Duplicate Files")
    table.add_column("Hash (short)", style="dim")
    table.add_column("Files")
    table.add_column("Size (KB)", justify="right")

    total_wasted = 0
    for h, files in duplicates.items():
        size = files[0].stat().st_size
        total_wasted += size * (len(files) - 1)
        file_list = "\n".join(str(f) for f in files)
        table.add_row(h[:12], file_list, f"{size / 1024:.1f}")

    console.print(table)
    dup_count = sum(len(f) - 1 for f in duplicates.values())
    console.print(
        f"\n[yellow]{dup_count} duplicate(s) in {len(duplicates)} group(s), "
        f"~{total_wasted / 1024 / 1024:.1f} MB wasted.[/yellow]"
    )


app.add_typer(source_app, name="source")
app.add_typer(config_app, name="config")
app.add_typer(feedback_app, name="feedback")
app.add_typer(rules_app, name="rules")


def main() -> None:
    configure_logging()
    app()


if __name__ == "__main__":
    main()
