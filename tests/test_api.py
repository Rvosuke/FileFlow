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
    config_response = client.get("/config")
    assert config_response.status_code == 404


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

    config_response = client.get("/config")
    assert config_response.status_code == 200
    config_body = config_response.json()
    assert config_body["llm"]["provider"] == "openclaw"
    assert isinstance(config_body["sources"]["paths"], list)

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


def test_rules_write_endpoints(monkeypatch, tmp_path: Path) -> None:
    app_home = tmp_path / "app"
    monkeypatch.setenv("FILEFLOW_HOME", str(app_home))
    initialize_app(home=app_home)

    client = TestClient(create_app())

    exact_response = client.post(
        "/rules/exact",
        json={
            "filename": "salary_slip.pdf",
            "target_path": "文档/财务",
            "confidence": 0.99,
        },
    )
    assert exact_response.status_code == 201
    exact_item = exact_response.json()["item"]
    assert exact_item["match_type"] == "exact"
    assert exact_item["match_key"] == "salary_slip.pdf"

    pattern_response = client.post(
        "/rules/pattern",
        json={
            "pattern": r"invoice_\d+\.pdf",
            "target_path": "文档/归档",
            "confidence": 0.95,
        },
    )
    assert pattern_response.status_code == 201
    pattern_item = pattern_response.json()["item"]
    assert pattern_item["match_type"] == "pattern"

    type_dir_response = client.post(
        "/rules/type-dir",
        json={
            "extension": "exe",
            "parent_dir": "Downloads",
            "target_path": "其他/安装包",
            "confidence": 0.9,
        },
    )
    assert type_dir_response.status_code == 201
    type_dir_item = type_dir_response.json()["item"]
    assert type_dir_item["match_type"] == "type_dir"
    assert type_dir_item["match_key"] == ".exe:Downloads"

    rules_response = client.get("/rules")
    assert rules_response.status_code == 200
    assert len(rules_response.json()["items"]) == 3

    delete_response = client.delete(f"/rules/{exact_item['id']}")
    assert delete_response.status_code == 200
    assert delete_response.json() == {"deleted": True, "id": exact_item["id"]}

    missing_delete = client.delete(f"/rules/{exact_item['id']}")
    assert missing_delete.status_code == 404
