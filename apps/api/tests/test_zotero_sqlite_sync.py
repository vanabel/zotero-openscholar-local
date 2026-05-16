"""zotero.sqlite 只读元数据同步（最小库 fixture）。"""
from __future__ import annotations

import sqlite3
from pathlib import Path

from app.services.zotero_sqlite_sync import storage_folder_key, sync_zotero_metadata_to_papers


def test_storage_folder_key_resolves_under_storage() -> None:
    root = Path("/zotero/storage")
    pdf = Path("/zotero/storage/ABCD1234/paper.pdf")
    assert storage_folder_key(pdf, root) == "ABCD1234"


def test_storage_folder_key_outside_returns_none() -> None:
    root = Path("/zotero/storage")
    pdf = Path("/other/paper.pdf")
    assert storage_folder_key(pdf, root) is None


def _create_minimal_zotero_db(path: Path) -> None:
    conn = sqlite3.connect(path)
    try:
        conn.executescript(
            """
            PRAGMA foreign_keys=OFF;
            CREATE TABLE libraries (
              libraryID INTEGER PRIMARY KEY,
              type TEXT NOT NULL,
              editable INT NOT NULL,
              filesEditable INT NOT NULL,
              version INT NOT NULL DEFAULT 0,
              storageVersion INT NOT NULL DEFAULT 0,
              lastSync INT NOT NULL DEFAULT 0,
              archived INT NOT NULL DEFAULT 0,
              isAdmin INT NOT NULL DEFAULT 0
            );
            INSERT INTO libraries VALUES (1,'user',1,1,0,0,0,0,0);

            CREATE TABLE itemTypes (
              itemTypeID INTEGER PRIMARY KEY,
              typeName TEXT,
              templateItemTypeID INT,
              display INT DEFAULT 1
            );
            INSERT INTO itemTypes VALUES (1,'journalArticle',NULL,1),(2,'attachment',NULL,1);

            CREATE TABLE items (
              itemID INTEGER PRIMARY KEY,
              itemTypeID INT NOT NULL,
              dateAdded TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
              dateModified TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
              clientDateModified TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
              libraryID INT NOT NULL,
              key TEXT NOT NULL,
              version INT NOT NULL DEFAULT 0,
              synced INT NOT NULL DEFAULT 0,
              UNIQUE (libraryID, key)
            );
            INSERT INTO items (itemID, itemTypeID, libraryID, key, version, synced)
              VALUES (100, 1, 1, 'PARENTK1', 0, 0);
            INSERT INTO items (itemID, itemTypeID, libraryID, key, version, synced)
              VALUES (101, 2, 1, 'KEYFOLDER1', 0, 0);

            CREATE TABLE itemAttachments (
              itemID INTEGER PRIMARY KEY,
              parentItemID INT,
              linkMode INT,
              contentType TEXT,
              charsetID INT,
              path TEXT,
              syncState INT DEFAULT 0,
              storageModTime INT,
              storageHash TEXT,
              lastProcessedModificationTime INT,
              lastRead INT
            );
            INSERT INTO itemAttachments VALUES (101, 100, 0, 'application/pdf', NULL, 'test.pdf', 0, NULL, NULL, NULL, NULL);

            CREATE TABLE fieldsCombined (
              fieldID INT NOT NULL,
              fieldName TEXT NOT NULL,
              label TEXT,
              fieldFormatID INT,
              custom INT NOT NULL,
              PRIMARY KEY (fieldID)
            );
            INSERT INTO fieldsCombined VALUES
              (1,'title',NULL,NULL,0),
              (2,'DOI',NULL,NULL,0),
              (3,'date',NULL,NULL,0),
              (4,'publicationTitle',NULL,NULL,0);

            CREATE TABLE itemDataValues (valueID INTEGER PRIMARY KEY, value UNIQUE);
            INSERT INTO itemDataValues VALUES (1,'Synced Paper Title'),(2,'10.1000/test.doi'),(3,'2023-05-01'),(4,'Test Venue');

            CREATE TABLE itemData (
              itemID INT,
              fieldID INT,
              valueID INT,
              PRIMARY KEY (itemID, fieldID)
            );
            INSERT INTO itemData VALUES (100,1,1),(100,2,2),(100,3,3),(100,4,4);

            CREATE TABLE creatorTypes (creatorTypeID INTEGER PRIMARY KEY, creatorType TEXT);
            INSERT INTO creatorTypes VALUES (1,'author');

            CREATE TABLE creators (
              creatorID INTEGER PRIMARY KEY,
              firstName TEXT,
              lastName TEXT,
              fieldMode INT,
              UNIQUE (lastName, firstName, fieldMode)
            );
            INSERT INTO creators VALUES (1,'Jane','Doe',0);

            CREATE TABLE itemCreators (
              itemID INT NOT NULL,
              creatorID INT NOT NULL,
              creatorTypeID INT NOT NULL DEFAULT 1,
              orderIndex INT NOT NULL DEFAULT 0,
              PRIMARY KEY (itemID, creatorID, creatorTypeID, orderIndex),
              UNIQUE (itemID, orderIndex)
            );
            INSERT INTO itemCreators VALUES (100, 1, 1, 0);

            CREATE TABLE tags (tagID INTEGER PRIMARY KEY, name TEXT NOT NULL UNIQUE);
            INSERT INTO tags VALUES (1,'machine-learning');

            CREATE TABLE itemTags (itemID INT NOT NULL, tagID INT NOT NULL, type INT NOT NULL, PRIMARY KEY (itemID, tagID));
            INSERT INTO itemTags VALUES (100, 1, 0);

            CREATE TABLE collections (
              collectionID INTEGER PRIMARY KEY,
              collectionName TEXT NOT NULL,
              parentCollectionID INT DEFAULT NULL,
              clientDateModified TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
              libraryID INT NOT NULL,
              key TEXT NOT NULL,
              version INT NOT NULL DEFAULT 0,
              synced INT NOT NULL DEFAULT 0,
              UNIQUE (libraryID, key)
            );
            INSERT INTO collections VALUES (1,'My Collection',NULL,CURRENT_TIMESTAMP,1,'COLK1',0,0);

            CREATE TABLE collectionItems (
              collectionID INT NOT NULL,
              itemID INT NOT NULL,
              orderIndex INT NOT NULL DEFAULT 0,
              PRIMARY KEY (collectionID, itemID)
            );
            INSERT INTO collectionItems VALUES (1, 100, 0);

            CREATE TABLE deletedItems (itemID INTEGER PRIMARY KEY, dateDeleted TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
            """
        )
        conn.commit()
    finally:
        conn.close()


def test_sync_zotero_metadata_updates_paper(monkeypatch, tmp_path) -> None:
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    storage = tmp_path / "zstorage"
    key_dir = storage / "KEYFOLDER1"
    key_dir.mkdir(parents=True)
    pdf = key_dir / "test.pdf"
    pdf.write_bytes(b"%PDF-1.4 minimal")

    zpath = tmp_path / "zotero.sqlite"
    _create_minimal_zotero_db(zpath)

    monkeypatch.setattr("app.config.settings.data_dir", data_dir)
    monkeypatch.setattr("app.config.settings.zotero_sqlite_path", zpath)

    from app.db import init_db, save_kv

    init_db()
    save_kv("zotero_storage_path", str(storage))

    pdf_resolved = str(pdf.resolve())
    from app.db import get_db

    with get_db() as conn:
        conn.execute(
            """
            INSERT INTO papers(
              id, pdf_path, file_name, file_size, mtime, sha256,
              parse_status, index_status, deleted, created_at, updated_at
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                "paperfixture01",
                pdf_resolved,
                "test.pdf",
                len(b"%PDF-1.4 minimal"),
                0.0,
                "deadbeef" * 4 + "deadbeef"[:8],
                "pending",
                "pending",
                0,
                "2024-01-01T00:00:00+00:00",
                "2024-01-01T00:00:00+00:00",
            ),
        )

    out = sync_zotero_metadata_to_papers(include_deleted=False)
    assert out.get("ok") is True
    assert out.get("updated") == 1
    assert out.get("errors") == 0

    with get_db() as conn:
        row = conn.execute("SELECT * FROM papers WHERE id = ?", ("paperfixture01",)).fetchone()
        assert row is not None
        assert row["zotero_key"] == "KEYFOLDER1"
        assert row["title"] == "Synced Paper Title"
        assert "Doe" in (row["authors"] or "")
        assert row["year"] == 2023
        assert row["venue"] == "Test Venue"
        assert row["doi"] == "10.1000/test.doi"
        assert "machine-learning" in (row["zotero_tags"] or "")
        assert "My Collection" in (row["zotero_collections"] or "")


def test_sync_skips_when_sqlite_missing(monkeypatch, tmp_path) -> None:
    data_dir = tmp_path / "d2"
    data_dir.mkdir()
    monkeypatch.setattr("app.config.settings.data_dir", data_dir)
    monkeypatch.setattr("app.config.settings.zotero_sqlite_path", tmp_path / "nonexistent.sqlite")

    from app.db import init_db

    init_db()
    out = sync_zotero_metadata_to_papers()
    assert out.get("skipped")
