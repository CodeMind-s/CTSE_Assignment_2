"""Local codebase keyword search tool."""
from pathlib import Path
from typing import TypedDict


class SearchResult(TypedDict):
    matches: list[dict]
    total_files_scanned: int
    error: str | None


def codebase_searcher(keyword: str, directory: str = "data/mock_codebase") -> SearchResult:
    """Search a local codebase directory for files containing a keyword.

    Walks the directory tree, reads each .py/.js/.ts/.java file, and returns
    the file path plus the first matching line for each match.

    Args:
        keyword: Keyword to search for (case-insensitive, min 3 chars).
        directory: Root directory to search. Defaults to 'data/mock_codebase'.

    Returns:
        SearchResult with:
            matches: List of {file, line_number, line_content} dicts
            total_files_scanned: int
            error: None on success, error string on failure

    Raises:
        Never raises — all failures are returned as error dicts.

    Example:
        >>> codebase_searcher("login")
        {'matches': [{'file': 'auth.py', 'line_number': 12, ...}], ...}
    """
    if not isinstance(keyword, str) or len(keyword.strip()) < 3:
        return {"matches": [], "total_files_scanned": 0,
                "error": "keyword must be at least 3 characters. "
                         "Provide a meaningful search term."}

    root = Path(directory)
    if not root.exists() or not root.is_dir():
        return {"matches": [], "total_files_scanned": 0,
                "error": f"Directory '{directory}' does not exist. "
                         f"Ensure the mock codebase is at data/mock_codebase/."}

    allowed_exts = {".py", ".js", ".ts", ".java", ".go", ".rs"}
    matches: list[dict] = []
    scanned = 0
    keyword_lower = keyword.lower()

    for path in root.rglob("*"):
        if not path.is_file() or path.suffix not in allowed_exts:
            continue
        scanned += 1
        try:
            with path.open("r", encoding="utf-8", errors="ignore") as f:
                for lineno, line in enumerate(f, 1):
                    if keyword_lower in line.lower():
                        matches.append({
                            "file": str(path.relative_to(root)),
                            "line_number": lineno,
                            "line_content": line.strip()[:200],
                        })
                        break
        except OSError:
            continue

    return {"matches": matches[:10], "total_files_scanned": scanned, "error": None}
