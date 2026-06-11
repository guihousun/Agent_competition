#!/usr/bin/env python3
"""
Document Searcher Skill - Execution Script
Full-text search over large documents using SQLite FTS5.
"""

import json
import sys
import uuid
from pathlib import Path

# Add lib to path
sys.path.insert(0, str(Path(__file__).parent.parent / 'lib'))

from database import DocumentDatabase
from fts import FTSManager

# Database path (relative to skill directory)
SKILL_DIR = Path(__file__).parent.parent
DB_PATH = SKILL_DIR / "data" / "documents.db"

def ensure_db():
    """Ensure database directory exists and initialize if needed."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    return DocumentDatabase(str(DB_PATH))

def index_document(db, file_path: str) -> dict:
    """Parse and index a document file."""
    file_path = Path(file_path)
    if not file_path.exists():
        return {"error": f"File not found: {file_path}"}

    # Generate document ID
    doc_id = str(uuid.uuid4())

    # Read file content based on extension
    ext = file_path.suffix.lower()
    content = ""

    try:
        if ext in ['.txt', '.md', '.csv']:
            content = file_path.read_text(encoding='utf-8')
        elif ext in ['.html', '.htm']:
            content = file_path.read_text(encoding='utf-8')
        else:
            # For binary formats, use parsers if available
            try:
                from parsers.text_parser import TextParser
                parser = TextParser()
                sections = parser.parse(str(file_path))
                content = "\n".join([s.get('content', '') for s in sections])
            except ImportError:
                return {"error": f"Unsupported format: {ext}. Install parsers or use text formats."}

        # Insert into database
        fts = FTSManager(db)
        fts.add_document(doc_id, file_path.name, content)

        # Count sections (approximate by newlines for simple text)
        sections_count = content.count('\n') + 1

        return {
            "doc_id": doc_id,
            "filename": file_path.name,
            "sections_count": sections_count,
            "status": "indexed"
        }
    except Exception as e:
        return {"error": f"Failed to index: {str(e)}"}

def search_document(db, query: str, limit: int = 10) -> dict:
    """Full-text search with BM25 ranking."""
    fts = FTSManager(db)
    results = fts.search(query, limit=limit)

    return {
        "query": query,
        "match_count": len(results),
        "results": [
            {
                "doc_id": r.get('doc_id', ''),
                "filename": r.get('filename', ''),
                "snippet": r.get('snippet', ''),
                "relevance": r.get('rank', 0)
            }
            for r in results[:limit]
        ]
    }

def get_section(db, doc_id: str, section_ref: str) -> dict:
    """Retrieve full text of a section."""
    # Simplified: return document content
    cursor = db.conn.cursor()
    cursor.execute("SELECT * FROM documents WHERE id = ?", (doc_id,))
    row = cursor.fetchone()
    if row:
        return {
            "doc_id": doc_id,
            "section_ref": section_ref,
            "content": row[2] if len(row) > 2 else ""
        }
    return {"error": f"Document not found: {doc_id}"}

def get_document_overview(db, doc_id: str) -> dict:
    """Get document metadata."""
    cursor = db.conn.cursor()
    cursor.execute("SELECT * FROM documents WHERE id = ?", (doc_id,))
    row = cursor.fetchone()
    if row:
        return {
            "doc_id": doc_id,
            "filename": row[1] if len(row) > 1 else "",
            "status": "found"
        }
    return {"error": f"Document not found: {doc_id}"}

def list_documents(db, limit: int = 100) -> dict:
    """List all indexed documents."""
    cursor = db.conn.cursor()
    cursor.execute("SELECT id, filename FROM documents LIMIT ?", (limit,))
    rows = cursor.fetchall()

    return {
        "count": len(rows),
        "documents": [
            {"doc_id": row[0], "filename": row[1]}
            for row in rows
        ]
    }

def delete_document(db, doc_id: str) -> dict:
    """Delete a document."""
    cursor = db.conn.cursor()
    cursor.execute("DELETE FROM documents WHERE id = ?", (doc_id,))
    db.conn.commit()

    return {
        "doc_id": doc_id,
        "status": "deleted"
    }

def get_statistics(db) -> dict:
    """Get aggregate statistics."""
    cursor = db.conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM documents")
    doc_count = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM fts5_documents")
    section_count = cursor.fetchone()[0]

    return {
        "doc_count": doc_count,
        "total_sections": section_count
    }

def main():
    """Main execution function."""
    # Read input from stdin
    input_data = sys.stdin.read().strip()
    if not input_data:
        input_data = '{}'

    try:
        params = json.loads(input_data)
    except json.JSONDecodeError:
        params = {}

    action = params.get('action', '')
    docs_dir = params.get('docs_dir', str(SKILL_DIR / "references" / "documents"))

    if not action:
        result = {"error": "action is required"}
        print(json.dumps(result, ensure_ascii=False))
        return

    # Initialize database
    try:
        db = ensure_db()
    except Exception as e:
        result = {"error": f"Database initialization failed: {str(e)}"}
        print(json.dumps(result, ensure_ascii=False))
        return

    # Execute action
    result = {}
    try:
        if action == 'index':
            file_path = params.get('file_path', '')
            if not file_path:
                result = {"error": "file_path is required for index action"}
            else:
                result = index_document(db, file_path)

        elif action == 'search':
            query = params.get('query', '')
            limit = params.get('limit', 10)
            if not query:
                result = {"error": "query is required for search action"}
            else:
                result = search_document(db, query, limit)

        elif action == 'get_section':
            doc_id = params.get('doc_id', '')
            section_ref = params.get('section_ref', '')
            if not doc_id or not section_ref:
                result = {"error": "doc_id and section_ref are required"}
            else:
                result = get_section(db, doc_id, section_ref)

        elif action == 'overview':
            doc_id = params.get('doc_id', '')
            if not doc_id:
                result = {"error": "doc_id is required"}
            else:
                result = get_document_overview(db, doc_id)

        elif action == 'list':
            limit = params.get('limit', 100)
            result = list_documents(db, limit)

        elif action == 'delete':
            doc_id = params.get('doc_id', '')
            if not doc_id:
                result = {"error": "doc_id is required"}
            else:
                result = delete_document(db, doc_id)

        elif action == 'stats':
            result = get_statistics(db)

        else:
            result = {"error": f"Unknown action: {action}"}

    except Exception as e:
        result = {"error": f"Action failed: {str(e)}"}

    # Output result
    print(json.dumps(result, ensure_ascii=False, indent=2))

if __name__ == '__main__':
    main()
