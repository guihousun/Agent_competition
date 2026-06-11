"""FTS5 search manager."""

class FTSManager:
    def __init__(self, db):
        self.db = db

    def add_document(self, doc_id: str, filename: str, content: str):
        """Add document to database and FTS index."""
        self.db.conn.execute(
            "INSERT INTO documents (id, filename, content) VALUES (?, ?, ?)",
            (doc_id, filename, content)
        )
        self.db.conn.execute(
            "INSERT INTO fts5_documents (filename, content) VALUES (?, ?)",
            (filename, content)
        )
        self.db.conn.commit()

    def search(self, query: str, limit: int = 10) -> list:
        """Full-text search with BM25 ranking."""
        cursor = self.db.conn.cursor()
        # Search directly in FTS5 table
        cursor.execute("""
            SELECT rowid, filename, content, rank
            FROM fts5_documents
            WHERE fts5_documents MATCH ?
            ORDER BY rank
            LIMIT ?
        """, (query, limit))

        results = []
        for row in cursor.fetchall():
            content = row[2] if len(row) > 2 else ""
            snippet = content[:200] if content else ""
            results.append({
                'doc_id': str(row[0]),
                'filename': row[1],
                'snippet': snippet,
                'rank': row[3] if len(row) > 3 else 0
            })
        return results
