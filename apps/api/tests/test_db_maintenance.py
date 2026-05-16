import sqlite3

from app.config import settings
from app.db import get_db, init_db
from app.services.db_maintenance import maybe_vacuum_database_on_startup, vacuum_needed


def test_vacuum_needed_rules():
    assert vacuum_needed(force=True, freelist_ratio=0.0, threshold=0.25)
    assert not vacuum_needed(force=False, freelist_ratio=0.1, threshold=0.25)
    assert vacuum_needed(force=False, freelist_ratio=0.25, threshold=0.25)
    assert not vacuum_needed(force=False, freelist_ratio=0.9, threshold=0.0)


def test_skip_vacuum_when_ratio_low(isolated_test_data_dir, monkeypatch):
    monkeypatch.setattr(settings, "db_vacuum_on_startup", False)
    monkeypatch.setattr(settings, "db_vacuum_freelist_ratio", 0.5)
    init_db()
    out = maybe_vacuum_database_on_startup()
    assert out["vacuumed"] is False
    assert out["skipped"] == "below_threshold"


def test_vacuum_when_ratio_high(isolated_test_data_dir, monkeypatch):
    monkeypatch.setattr(settings, "db_vacuum_on_startup", False)
    monkeypatch.setattr(settings, "db_vacuum_freelist_ratio", 0.01)
    init_db()
    with get_db() as conn:
        conn.execute("CREATE TABLE IF NOT EXISTS _vacuum_bloat (x BLOB)")
        conn.executemany("INSERT INTO _vacuum_bloat VALUES(?)", [(b"x" * 500_000,) for _ in range(8)])
    with get_db() as conn:
        conn.execute("DROP TABLE _vacuum_bloat")

    out = maybe_vacuum_database_on_startup()
    assert out["vacuumed"] is True
    assert out["bytes_reclaimed"] >= 0
    assert out["freelist_count_after"] < out["freelist_count_before"]


def test_vacuum_forced_on_startup(isolated_test_data_dir, monkeypatch):
    monkeypatch.setattr(settings, "db_vacuum_on_startup", True)
    monkeypatch.setattr(settings, "db_vacuum_freelist_ratio", 0.0)
    init_db()
    out = maybe_vacuum_database_on_startup()
    assert out["vacuumed"] is True
    assert out["forced"] is True


def test_vacuum_ratio_disabled_only_force(isolated_test_data_dir, monkeypatch):
    monkeypatch.setattr(settings, "db_vacuum_on_startup", False)
    monkeypatch.setattr(settings, "db_vacuum_freelist_ratio", 0.0)
    init_db()
    assert maybe_vacuum_database_on_startup()["vacuumed"] is False

    monkeypatch.setattr(settings, "db_vacuum_on_startup", True)
    assert maybe_vacuum_database_on_startup()["vacuumed"] is True


def test_vacuum_no_database(isolated_test_data_dir, monkeypatch):
    db_path = settings.db_path
    if db_path.is_file():
        db_path.unlink()
    out = maybe_vacuum_database_on_startup()
    assert out["vacuumed"] is False
    assert out["skipped"] == "no_database"

    conn = sqlite3.connect(db_path)
    conn.close()
