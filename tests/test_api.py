from pathlib import Path
import sqlite3

from fastapi.testclient import TestClient

from fileflow.api.app import create_app
from fileflow.config import initialize_app
from fileflow.db.operations import Database


def test_health_endpoint() -> None:
    client = TestClient(create_app())
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_health_endpoint_includes_cors_headers() -> None:
    client = TestClient(create_app())
    response = client.options(
        "/health",
        headers={
            "Origin": "http://localhost:5173",
            "Access-Control-Request-Method": "GET",
        },
    )
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://localhost:5173"


def test_status_endpoint_requires_initialization(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("FILEFLOW_HOME", str(tmp_path / "app"))
    client = TestClient(create_app())
    response = client.get("/status")
    assert response.status_code == 404


def test_status_rules_history_and_corrections_endpoints(monkeypatch, tmp_path: Path) -> None:
    app_home = tmp_path / "app"
    monkeypatch.setenv("FILEFLOW_HOME", str(app_home))
    paths = initialize_app(home=app_home)
    database = Database(paths.database_file)
    database.upsert_rule_cache(
        match_type="exact",
        match_key="salary_slip.pdf",
        target_path="文档/财务",
        confidence=0.99,
    )

    with sqlite3.connect(paths.database_file) as connection:
        cur = connection.execute(
            """
            INSERT INTO move_records (
                source_path, target_path, file_hash, file_size, category, confidence, reason, status
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                str(tmp_path / "salary_slip.pdf"),
                str(Path("D:/Organized") / "文档" / "财务" / "salary_slip.pdf"),
                None,
                1234,
                "document",
                0.99,
                "exact rule",
                "completed",
            ),
        )
        move_id = cur.lastrowid
        connection.execute(
            """
            INSERT INTO scan_logs (
                source_path, files_found, files_moved, files_skipped, files_cached, llm_calls, duration_ms
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (str(tmp_path), 5, 3, 2, 1, 0, 42),
        )
        connection.execute(
            """
            INSERT INTO corrections (move_record_id, original_target, corrected_target)
            VALUES (?, ?, ?)
            """,
            (move_id, "文档/财务", "文档/归档"),
        )
        connection.commit()

    client = TestClient(create_app())

    status_response = client.get("/status")
    assert status_response.status_code == 200
    status_body = status_response.json()
    assert status_body["stats"]["rule_cache_rows"] >= 1
    assert status_body["stats"]["corrections"] >= 1

    rules_response = client.get("/rules", params={"type": "exact"})
    assert rules_response.status_code == 200
    assert rules_response.json()["items"][0]["match_key"] == "salary_slip.pdf"

    history_response = client.get("/history")
    assert history_response.status_code == 200
    assert history_response.json()["items"][0]["status"] == "completed"

    corrections_response = client.get("/corrections")
    assert corrections_response.status_code == 200
    assert corrections_response.json()["items"][0]["corrected_target"] == "文档/归档"

    scans_response = client.get("/scans")
    assert scans_response.status_code == 200
    assert scans_response.json()["items"][0]["files_found"] == 5
