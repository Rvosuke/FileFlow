SCHEMA = """
CREATE TABLE IF NOT EXISTS move_records (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_path TEXT NOT NULL,
    target_path TEXT NOT NULL,
    file_hash TEXT,
    file_size INTEGER,
    category TEXT,
    confidence REAL,
    reason TEXT,
    status TEXT DEFAULT 'completed',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS rule_cache (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    match_type TEXT NOT NULL,
    match_key TEXT NOT NULL,
    target_path TEXT NOT NULL,
    confidence REAL,
    hit_count INTEGER DEFAULT 1,
    last_hit TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS corrections (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    move_record_id INTEGER REFERENCES move_records(id),
    original_target TEXT NOT NULL,
    corrected_target TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS scan_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_path TEXT NOT NULL,
    files_found INTEGER,
    files_moved INTEGER,
    files_skipped INTEGER,
    files_cached INTEGER,
    llm_calls INTEGER,
    duration_ms INTEGER,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_rule_cache_match ON rule_cache(match_type, match_key);
"""
