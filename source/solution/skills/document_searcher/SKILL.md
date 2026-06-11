---
name: document_searcher
description: Full-text search over large documents using SQLite FTS5. Supports PDF, DOCX, XLSX, CSV, PPTX, HTML, TXT, MD, and images (OCR). Ideal for multi-source knowledge retrieval tasks.
---

# Document Searcher Skill

## When to use
- Search through large documents (30+ pages) for specific information
- Multi-source knowledge retrieval tasks
- Find relevant sections across multiple documents
- Extract context around search matches

## Workflow
1. **Index**: Call `skill_run` with `action: "index"` and `file_path` to index a document
2. **Search**: Call `skill_run` with `action: "search"` and `query` to find relevant sections
3. **Retrieve**: Call `skill_run` with `action: "get_section"` to get full context
4. **Synthesize**: Use retrieved sections to answer the question

## Supported Formats
- Text: `.txt`, `.md`, `.csv`
- Web: `.html`, `.htm`
- Office: `.pdf`, `.docx`, `.xlsx`, `.pptx` (requires parsers)
- Images: `.png`, `.jpg`, `.jpeg` (requires OCR)

## Examples

### Index a document
```json
{
  "action": "index",
  "file_path": "files/report.pdf"
}
```

### Search for information
```json
{
  "action": "search",
  "query": "risk assessment methodology",
  "limit": 5
}
```

### Get full section
```json
{
  "action": "get_section",
  "doc_id": "uuid-here",
  "section_ref": "s2.1"
}
```

## Limitations
- Binary formats (PDF, DOCX, etc.) require external parsers
- Images require pytesseract for OCR
- For simple text files, works out of the box
