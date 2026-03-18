from __future__ import annotations

from dataclasses import asdict
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query

from fileflow.config import is_initialized, load_config, resolve_app_paths
from fileflow.db.operations import Database
from fileflow.learning.rules import RuleManager
from fileflow.executor.rollback import RollbackEngine


def create_app() -> FastAPI:
    app = FastAPI(title="FileFlow API", version="0.1.0")

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/status")
    def status() -> dict:
        if not is_initialized():
            raise HTTPException(status_code=404, detail="FileFlow is not initialized")

        paths = resolve_app_paths()
        config = load_config()
        stats = Database(paths.database_file).get_stats()
        return {
            "home": str(paths.home),
            "config_file": str(paths.config_file),
            "database_file": str(paths.database_file),
            "sources": config.sources.paths,
            "target_root": config.general.target_root,
            "stats": {
                "move_records": stats.move_records,
                "rule_cache_rows": stats.rule_cache_rows,
                "corrections": stats.corrections,
                "scan_logs": stats.scan_logs,
                "last_scan_at": stats.last_scan_at,
            },
        }

    @app.get("/rules")
    def rules(
        limit: int = Query(20, ge=1, le=500),
        match_type: str | None = Query(None, alias="type"),
    ) -> dict[str, list[dict]]:
        if not is_initialized():
            raise HTTPException(status_code=404, detail="FileFlow is not initialized")
        paths = resolve_app_paths()
        entries = RuleManager(Database(paths.database_file)).list_rules(limit=limit, match_type=match_type)
        return {"items": [asdict(entry) for entry in entries]}

    @app.get("/history")
    def history(limit: int = Query(20, ge=1, le=500)) -> dict[str, list[dict]]:
        if not is_initialized():
            raise HTTPException(status_code=404, detail="FileFlow is not initialized")
        paths = resolve_app_paths()
        items = RollbackEngine(paths.database_file).get_history(limit)
        return {"items": items}

    @app.get("/corrections")
    def corrections(limit: int = Query(20, ge=1, le=500)) -> dict[str, list[dict]]:
        if not is_initialized():
            raise HTTPException(status_code=404, detail="FileFlow is not initialized")
        paths = resolve_app_paths()
        items = Database(paths.database_file).get_corrections(limit)
        return {"items": items}

    return app


app = create_app()
