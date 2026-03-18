"""Watchdog-based real-time file monitoring."""

from __future__ import annotations

import logging
import threading
import time
from pathlib import Path
from typing import TYPE_CHECKING

from watchdog.events import FileSystemEventHandler, FileCreatedEvent, FileMovedEvent
from watchdog.observers import Observer

if TYPE_CHECKING:
    from fileflow.config import FileFlowConfig

logger = logging.getLogger("fileflow.watcher")

DEBOUNCE_SECONDS = 3.0


class _FileFlowHandler(FileSystemEventHandler):
    """Handle new/moved file events with debounce."""

    def __init__(
        self,
        config: "FileFlowConfig",
        db_path: Path,
        execute: bool = False,
        use_ai: bool = False,
    ):
        super().__init__()
        self.config = config
        self.db_path = db_path
        self.execute = execute
        self.use_ai = use_ai
        self._pending: dict[str, float] = {}
        self._lock = threading.Lock()
        self._timer: threading.Timer | None = None

    def on_created(self, event: FileCreatedEvent) -> None:
        if event.is_directory:
            return
        self._schedule(event.src_path)

    def on_moved(self, event: FileMovedEvent) -> None:
        if event.is_directory:
            return
        self._schedule(event.dest_path)

    def _schedule(self, path: str) -> None:
        with self._lock:
            self._pending[path] = time.time()
        if self._timer:
            self._timer.cancel()
        self._timer = threading.Timer(DEBOUNCE_SECONDS, self._process_pending)
        self._timer.daemon = True
        self._timer.start()

    def _process_pending(self) -> None:
        with self._lock:
            now = time.time()
            ready = {p: t for p, t in self._pending.items() if now - t >= DEBOUNCE_SECONDS}
            for p in ready:
                del self._pending[p]

        paths = [Path(p) for p in ready if Path(p).is_file()]
        if not paths:
            return
        self._classify_and_act(paths)

    def _classify_and_act(self, paths: list[Path]) -> None:
        from rich.console import Console
        from fileflow.analyzer.meta import collect_file_meta
        from fileflow.ai.decision import HeuristicClassifier
        from fileflow.db.operations import Database

        console = Console()
        metas = []
        for p in paths:
            try:
                metas.append(collect_file_meta(p))
            except OSError as exc:
                logger.warning("Cannot read %s: %s", p, exc)
        if not metas:
            return

        # Classify
        if self.use_ai:
            try:
                from fileflow.ai.engine import DecisionEngine
                db = Database(self.db_path)
                engine = DecisionEngine(self.config, db)
                classifications = engine.classify(metas)
            except Exception:
                classifications = HeuristicClassifier().classify_batch(metas)
        else:
            classifications = HeuristicClassifier().classify_batch(metas)

        for cr in classifications:
            if cr.action == "skip":
                continue
            tag = f"({cr.confidence:.0%})"
            if self.execute and cr.action == "move":
                from fileflow.executor.mover import FileMover
                mover = FileMover(
                    target_root=Path(self.config.general.target_root),
                    db_path=self.db_path,
                    create_shortcut=self.config.general.create_shortcut,
                )
                meta = next((m for m in metas if m.path == cr.original_path), None)
                record = mover.execute(cr, meta=meta, dry_run=False)
                if record.status == "completed":
                    console.print(f"  [green]Moved[/green] {cr.original_path.name} -> {cr.target_path} {tag}")
                else:
                    console.print(f"  [red]Failed[/red] {cr.original_path.name}")
            else:
                console.print(f"  [cyan]New[/cyan] {cr.original_path.name} -> {cr.target_path} {tag} [dim](preview)[/dim]")


def start_watching(
    config: "FileFlowConfig",
    db_path: Path,
    execute: bool = False,
    use_ai: bool = False,
) -> None:
    """Watch all configured source folders. Blocks until Ctrl+C."""
    from rich.console import Console
    console = Console()

    sources = config.sources.paths
    if not sources:
        console.print("[red]No source folders configured. Use `fileflow source add`.[/red]")
        return

    handler = _FileFlowHandler(config, db_path, execute=execute, use_ai=use_ai)
    observer = Observer()

    for src in sources:
        src_path = Path(src)
        if src_path.is_dir():
            observer.schedule(handler, str(src_path), recursive=False)
            console.print(f"  Watching: {src_path}")
        else:
            console.print(f"  [yellow]Skipping (not found): {src_path}[/yellow]")

    mode = "[green]execute[/green]" if execute else "[cyan]preview[/cyan]"
    console.print(f"\nFileFlow watcher running in {mode} mode. Press Ctrl+C to stop.\n")

    observer.start()
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        console.print("\n[yellow]Stopping watcher...[/yellow]")
        observer.stop()
    observer.join()
