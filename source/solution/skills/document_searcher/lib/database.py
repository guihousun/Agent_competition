"""Simplified database for document search."""

import sqlite3
from pathlib import Path

class DocumentDatabase:
    def __init__(self, db_path: str):
        self.db_path = db_path
        self.conn = sqlite3.connect(db_path)
        self.conn.row_factory = sqlite3.Row
        self._init_schema()

    def _init_schema(self):
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS documents (
                id TEXT PRIMARY KEY,
                filename TEXT NOT NULL,
                content TEXT NOT NULL,
                upload_date TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)
        # FTS5 virtual table - standalone mode (no content option)
        self.conn.execute("""
            CREATE VIRTUAL TABLE IF NOT EXISTS fts5_documents USING fts5(
                filename, content
            )
        """)
        self.conn.commit()

    def close(self):
        self.conn.close()
