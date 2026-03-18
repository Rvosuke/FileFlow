from __future__ import annotations

from dataclasses import asdict
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from fileflow.ai.decision import normalize_target_path
from fileflow.config import is_initialized, load_config, resolve_app_paths
from fileflow.db.operations import Database
from fileflow.learning.rules import RuleManager
from fileflow.executor.rollback import RollbackEngine


class ExactRulePayload(BaseModel):
    filename: str
    target_path: str
    confidence: float = Field(default=0.99, ge=0.0, le=1.0)


class PatternRulePayload(BaseModel):
    pattern: str
    target_path: str
    confidence: float = Field(default=0.95, ge=0.0, le=1.0)


class TypeDirRulePayload(BaseModel):
    extension: str
    parent_dir: str
    target_path: str
    confidence: float = Field(default=0.9, ge=0.0, le=1.0)


def _require_manager() -> tuple[RuleManager, list[str], int]:
    if not is_initialized():
        raise HTTPException(status_code=404, detail="FileFlow is not initialized")
    paths = resolve_app_paths()
    config = load_config()
    manager = RuleManager(Database(paths.database_file))
    return manager, config.categories.top_level, config.categories.max_depth


def _normalized_rule_target(target_path: str, top_levels: list[str], max_depth: int) -> str:
    fallback_top = top_levels[-1] if top_levels else "其他"
    return normalize_target_path(
        target_path,
        allowed_top_levels=top_levels,
        fallback_top_level=fallback_top,
        max_depth=max_depth,
    )


def _get_rule_entry(manager: RuleManager, match_type: str, match_key: str):
    for entry in manager.list_rules(limit=500, match_type=match_type):
        if entry.match_key == match_key:
            return entry
    raise HTTPException(status_code=500, detail="Rule was written but could not be read back")


def create_app() -> FastAPI:
    app = FastAPI(title="FileFlow API", version="0.1.0")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "http://localhost:3000",
            "http://127.0.0.1:3000",
            "http://localhost:4173",
            "http://127.0.0.1:4173",
            "http://localhost:5173",
            "http://127.0.0.1:5173",
        ],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

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

    @app.get("/config")
    def config_view() -> dict:
        if not is_initialized():
            raise HTTPException(status_code=404, detail="FileFlow is not initialized")
        config = load_config()
        return config.to_dict()

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

    @app.post("/rules/exact", status_code=201)
    def add_exact_rule(payload: ExactRulePayload) -> dict[str, dict]:
        manager, top_levels, max_depth = _require_manager()
        target_path = _normalized_rule_target(payload.target_path, top_levels, max_depth)
        manager.add_exact_rule(payload.filename, target_path, payload.confidence)
        entry = _get_rule_entry(manager, "exact", payload.filename)
        return {"item": asdict(entry)}

    @app.post("/rules/pattern", status_code=201)
    def add_pattern_rule(payload: PatternRulePayload) -> dict[str, dict]:
        manager, top_levels, max_depth = _require_manager()
        target_path = _normalized_rule_target(payload.target_path, top_levels, max_depth)
        manager.add_pattern_rule(payload.pattern, target_path, payload.confidence)
        entry = _get_rule_entry(manager, "pattern", payload.pattern)
        return {"item": asdict(entry)}

    @app.post("/rules/type-dir", status_code=201)
    def add_type_dir_rule(payload: TypeDirRulePayload) -> dict[str, dict]:
        manager, top_levels, max_depth = _require_manager()
        normalized_extension = payload.extension if payload.extension.startswith(".") else f".{payload.extension}"
        target_path = _normalized_rule_target(payload.target_path, top_levels, max_depth)
        manager.add_type_dir_rule(normalized_extension, payload.parent_dir, target_path, payload.confidence)
        entry = _get_rule_entry(manager, "type_dir", f"{normalized_extension.lower()}:{payload.parent_dir}")
        return {"item": asdict(entry)}

    @app.delete("/rules/{rule_id}")
    def delete_rule(rule_id: int) -> dict[str, int | bool]:
        if not is_initialized():
            raise HTTPException(status_code=404, detail="FileFlow is not initialized")
        paths = resolve_app_paths()
        deleted = RuleManager(Database(paths.database_file)).delete_rule(rule_id)
        if not deleted:
            raise HTTPException(status_code=404, detail="Rule not found")
        return {"deleted": True, "id": rule_id}

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

    @app.get("/scans")
    def scans(limit: int = Query(20, ge=1, le=500)) -> dict[str, list[dict]]:
        if not is_initialized():
            raise HTTPException(status_code=404, detail="FileFlow is not initialized")
        paths = resolve_app_paths()
        items = Database(paths.database_file).get_scan_logs(limit)
        return {"items": items}

    return app


app = create_app()
