import sqlite3
import pandas as pd
import os
import glob
import re

DB_PATH = os.path.join(os.path.dirname(__file__), "insights.db")
DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data")


def ensure_db_initialized() -> None:
    """Initialize the local DB/FTS index if it's missing or incomplete."""
    if not os.path.exists(DB_PATH):
        init_db()
        return

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    try:
        cursor.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='movies' LIMIT 1"
        )
        has_movies = cursor.fetchone() is not None

        cursor.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='documents' LIMIT 1"
        )
        has_documents = cursor.fetchone() is not None
    finally:
        conn.close()

    if not has_movies or not has_documents:
        init_db()


def _chunk_paragraphs(text: str) -> list[str]:
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", text or "") if p.strip()]
    return paragraphs


def _extract_pdf_text(pdf_path: str) -> str:
    try:
        from pypdf import PdfReader  # type: ignore
    except Exception:
        return ""

    try:
        reader = PdfReader(pdf_path)
        parts: list[str] = []
        for page in reader.pages:
            page_text = page.extract_text() or ""
            page_text = page_text.strip()
            if page_text:
                parts.append(page_text)
        return "\n\n".join(parts)
    except Exception:
        return ""

def init_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # Load structured data (CSVs)
    csv_files = glob.glob(os.path.join(DATA_DIR, "*.csv"))
    for csv_file in csv_files:
        table_name = os.path.basename(csv_file).replace(".csv", "")
        df = pd.read_csv(csv_file)
        df.to_sql(table_name, conn, if_exists="replace", index=False)
        print(f"Loaded {table_name} into database.")

    # Setup Full-Text Search for unstructured data
    cursor.execute("DROP TABLE IF EXISTS documents;")
    cursor.execute("CREATE VIRTUAL TABLE documents USING fts5(title, content);")
    
    # Load unstructured data (Markdown / PDFs)
    md_files = glob.glob(os.path.join(DATA_DIR, "*.md"))
    for md_file in md_files:
        title = os.path.basename(md_file).replace(".md", "")
        with open(md_file, 'r', encoding='utf-8') as f:
            content = f.read()
            paragraphs = _chunk_paragraphs(content)
            for p in paragraphs:
                cursor.execute("INSERT INTO documents (title, content) VALUES (?, ?)", (title, p))
        print(f"Loaded document {title} into FTS table.")

    pdf_files = glob.glob(os.path.join(DATA_DIR, "*.pdf"))
    for pdf_file in pdf_files:
        title = os.path.basename(pdf_file).replace(".pdf", "")
        content = _extract_pdf_text(pdf_file)
        if not content.strip():
            print(f"Skipped PDF {title} (no extractable text or missing pypdf).")
            continue

        paragraphs = _chunk_paragraphs(content)
        for p in paragraphs:
            cursor.execute("INSERT INTO documents (title, content) VALUES (?, ?)", (title, p))
        print(f"Loaded PDF document {title} into FTS table.")
    
    conn.commit()
    conn.close()
    print("Database initialization complete.")

def execute_sql(query: str):
    """Executes a strictly read-only SQL query against the database."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    # Basic security check
    if not query.strip().upper().startswith("SELECT"):
        return {"error": "Only SELECT queries are allowed for security."}
    
    try:
        cursor.execute(query)
        columns = [description[0] for description in cursor.description]
        rows = cursor.fetchall()
        result = [dict(zip(columns, row)) for row in rows]
        conn.close()
        return result
    except Exception as e:
        conn.close()
        return {"error": f"SQL Error: {str(e)}"}

def search_documents(keyword: str):
    """Searches unstructured text content using FTS5."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    try:
        keyword = (keyword or "").strip()
        if not keyword:
            conn.close()
            return []

        def run_fts(match_query: str):
            if not match_query:
                return []

            try:
                cursor.execute(
                    "SELECT title, content FROM documents WHERE documents MATCH ? ORDER BY rank LIMIT 5",
                    (match_query,),
                )
                return cursor.fetchall()
            except Exception:
                # Some SQLite builds may not expose `rank`; fall back to bm25.
                try:
                    cursor.execute(
                        "SELECT title, content FROM documents WHERE documents MATCH ? ORDER BY bm25(documents) LIMIT 5",
                        (match_query,),
                    )
                    return cursor.fetchall()
                except Exception:
                    # Syntax errors and other MATCH issues should not surface as tool errors.
                    return []

        # 1) Try a sanitized query first (best precision, avoids FTS syntax errors).
        # Allow alphanumerics, spaces, quotes, and prefix wildcard '*'.
        safe_keyword = re.sub(r"[^A-Za-z0-9\s\"\*]", " ", keyword)
        safe_keyword = re.sub(r"\s+", " ", safe_keyword).strip()

        rows = run_fts(safe_keyword)
        if rows:
            result = [{"title": row[0], "content": row[1]} for row in rows]
            conn.close()
            return result

        # 2) Fallback: build a more forgiving query (prefix matching + OR) to handle
        # plurals and multi-term natural language.
        tokens = re.findall(r"[A-Za-z0-9]+", keyword.lower())
        stopwords = {
            "a", "an", "and", "are", "as", "at", "be", "but", "by",
            "compare", "comparison", "for", "from", "how", "in", "into",
            "is", "it", "of", "on", "or", "recent", "recently", "the",
            "their", "this", "to", "vs", "versus", "what", "when", "where",
            "which", "why", "with",
        }
        filtered = []
        seen = set()
        for tok in tokens:
            if tok in stopwords:
                continue
            if len(tok) < 2:
                continue
            if tok in seen:
                continue
            seen.add(tok)
            filtered.append(tok)

        if filtered:
            # Prefix search for non-trivial tokens improves recall (budget -> budgets).
            expanded = [f"{t}*" if len(t) >= 4 else t for t in filtered]
            or_query = " OR ".join(expanded[:12])
            rows = run_fts(or_query)
            if rows:
                result = [{"title": row[0], "content": row[1]} for row in rows]
                conn.close()
                return result

        # 3) Last resort: substring match.
        like_query = f"%{keyword}%"
        cursor.execute(
            "SELECT title, content FROM documents WHERE title LIKE ? OR content LIKE ? LIMIT 5",
            (like_query, like_query),
        )
        rows = cursor.fetchall()
        result = [{"title": row[0], "content": row[1]} for row in rows]
        conn.close()
        return result
    except Exception as e:
        conn.close()
        return {"error": f"Search Error: {str(e)}"}

if __name__ == "__main__":
    init_db()