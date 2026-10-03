"""Run a .sql file against a SQLite database and print every result, continuing past errors.

Usage:  python scripts/run_sql.py <database.db> <queries.sql>
Dot-commands (.headers, .mode) are ignored. Needs only Python, not the sqlite3 command line tool.
The database is opened read-only.
"""
import sqlite3
import sys
from pathlib import Path

MAX_ROWS = 40
MAX_CELL = 60


def statements(sql: str) -> list[tuple[str, str]]:
    """Split a file into (comment block, statement) pairs, ignoring dot-commands."""
    out, comments, buffer = [], [], []
    for line in sql.splitlines():
        stripped = line.strip()
        if not buffer and (not stripped or stripped.startswith(".")):
            continue
        if not buffer and stripped.startswith("--"):
            comments.append(stripped.lstrip("- ").strip())
            continue
        if stripped.startswith("--"):
            continue
        buffer.append(line)
        if stripped.endswith(";"):
            out.append((" ".join(c for c in comments if c)[:110], "\n".join(buffer)))
            comments, buffer = [], []
    return out


def show(cursor: sqlite3.Cursor) -> None:
    rows = cursor.fetchall()
    names = [d[0] for d in cursor.description or []]
    if not names:
        print("   (no result)")
        return
    cells = [[str(v)[:MAX_CELL] if v is not None else "NULL" for v in row]
             for row in rows[:MAX_ROWS]]
    widths = [max(len(n), *(len(c[i]) for c in cells)) if cells else len(n)
              for i, n in enumerate(names)]
    print("   " + "  ".join(n.ljust(w) for n, w in zip(names, widths)))
    print("   " + "  ".join("-" * w for w in widths))
    for row in cells:
        print("   " + "  ".join(c.ljust(w) for c, w in zip(row, widths)))
    extra = len(rows) - MAX_ROWS
    print(f"   ({len(rows)} row(s)" + (f", showing {MAX_ROWS}" if extra > 0 else "") + ")")


def main() -> int:
    if len(sys.argv) != 3:
        print(__doc__)
        return 2
    db_path, sql_path = Path(sys.argv[1]), Path(sys.argv[2])
    if not db_path.exists():
        print(f"database not found: {db_path}")
        return 1
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    for i, (label, stmt) in enumerate(statements(sql_path.read_text()), start=1):
        print(f"\n[{i}] {label}")
        try:
            show(conn.execute(stmt))
        except sqlite3.Error as exc:
            print(f"   ERROR: {exc}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
