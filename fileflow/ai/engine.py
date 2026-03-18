"""Decision engine — orchestrates rule cache, heuristic, and LLM classifiers."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from fileflow.ai.decision import ClassifyResult, HeuristicClassifier
from fileflow.ai.rule_cache import RuleCache
from fileflow.db.operations import Database

if TYPE_CHECKING:
    from fileflow.analyzer.meta import FileMeta
    from fileflow.config import FileFlowConfig

logger = logging.getLogger("fileflow.engine")


class DecisionEngine:
    """Orchestrates classification through cache -> LLM -> heuristic fallback."""

    def __init__(self, config: "FileFlowConfig", db: Database):
        self.config = config
        self.db = db
        self.rule_cache = RuleCache(db)
        self.heuristic = HeuristicClassifier()
        self._llm_client = None  # lazy init

    @property
    def llm_client(self):
        if self._llm_client is None:
            try:
                from fileflow.ai.llm_client import LLMClient
                self._llm_client = LLMClient(self.config)
            except ImportError:
                logger.warning("httpx not installed, LLM classification unavailable")
                self._llm_client = None
        return self._llm_client

    def classify(self, files: list["FileMeta"]) -> list[ClassifyResult]:
        """Classify files using the three-tier strategy:
        1. Rule cache lookup
        2. LLM batch classification (if available)
        3. Heuristic fallback
        """
        results_by_path: dict[str, ClassifyResult] = {}
        uncached: list["FileMeta"] = []
        cache_hits = 0

        # Step 1: Check rule cache
        for f in files:
            cached = self.rule_cache.lookup(f)
            if cached and cached.confidence >= 0.8:
                results_by_path[str(f.path)] = cached
                cache_hits += 1
            else:
                uncached.append(f)

        if cache_hits:
            logger.info("Rule cache hits: %d / %d", cache_hits, len(files))

        if not uncached:
            return [results_by_path[str(f.path)] for f in files if str(f.path) in results_by_path]

        # Step 2: Try LLM classification
        llm_results = self._try_llm_classify(uncached)

        if llm_results:
            # Store high-confidence results in cache
            uncached_by_path = {str(meta.path): meta for meta in uncached}
            llm_classified_paths = set()
            for result in llm_results:
                result_path = str(result.original_path)
                meta = uncached_by_path.get(result_path)
                if meta is None:
                    continue
                results_by_path[result_path] = result
                llm_classified_paths.add(result_path)
                if result.confidence >= 0.8:
                    self.rule_cache.store(result, meta)

            # Any files not returned by LLM fall through to heuristic
            still_uncached = [
                f for f in uncached
                if str(f.path) not in llm_classified_paths
            ]
        else:
            still_uncached = uncached

        # Step 3: Heuristic fallback
        if still_uncached:
            heuristic_results = self.heuristic.classify_batch(still_uncached)
            for result in heuristic_results:
                results_by_path[str(result.original_path)] = result
            logger.info("Heuristic fallback for %d files", len(still_uncached))

        return [results_by_path[str(f.path)] for f in files if str(f.path) in results_by_path]

    def _try_llm_classify(self, files: list["FileMeta"]) -> list[ClassifyResult]:
        """Try LLM classification in batches. Returns empty list on failure."""
        client = self.llm_client
        if client is None:
            return []

        all_results: list[ClassifyResult] = []
        batch_size = self.config.llm.batch_size

        for i in range(0, len(files), batch_size):
            batch = files[i:i + batch_size]
            try:
                batch_results = client.classify(
                    batch,
                    top_level_categories=self.config.categories.top_level,
                    existing_tree=self._get_existing_tree(),
                    max_depth=self.config.categories.max_depth,
                )
                all_results.extend(batch_results)
                logger.info("LLM classified batch %d-%d (%d results)",
                            i, i + len(batch), len(batch_results))
            except Exception as exc:
                logger.warning("LLM classification failed for batch: %s", exc)
                # Don't add results for this batch — will fall through to heuristic
                continue

        return all_results

    def _get_existing_tree(self) -> str:
        """Get the current target directory tree for context."""
        from pathlib import Path

        target_root = Path(self.config.general.target_root)
        if not target_root.exists():
            return "(empty)"

        lines = []
        for p in sorted(target_root.rglob("*")):
            if p.is_dir():
                rel = p.relative_to(target_root)
                depth = len(rel.parts)
                if depth <= self.config.categories.max_depth:
                    indent = "  " * (depth - 1)
                    lines.append(f"{indent}- {p.name}/")

        return "\n".join(lines[:50]) if lines else "(empty)"
