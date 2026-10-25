"""Read-only SQL validation for LLM-generated queries.

This is defense in depth, not a security boundary. The real protection is running
queries with read-only credentials on the Gold tables only.
"""
import re

ALLOWED_TABLES = {"gold_daily_zone_stats", "gold_daily_summary"}

FORBIDDEN_KEYWORDS = {
    "insert", "update", "delete", "drop", "alter", "create", "truncate", "merge",
    "grant", "revoke", "copy", "attach", "detach", "pragma", "call", "replace",
    "into", "optimize", "vacuum", "set", "use", "load", "install", "export",
}

_COMMENT_RE = re.compile(r"--[^\n]*|/\*.*?\*/", re.DOTALL)
_TABLE_REF_RE = re.compile(r"\b(?:from|join)\s+([a-zA-Z_][\w.`\"]*)", re.IGNORECASE)
_CTE_RE = re.compile(r"(?:\bwith\b|,)\s*([a-zA-Z_]\w*)\s+as\s*\(", re.IGNORECASE)


class UnsafeSQLError(ValueError):
    """Raised when generated SQL fails validation."""


def _strip_string_literals(sql: str) -> str:
    return re.sub(r"'(?:[^']|'')*'", "''", sql)


def validate_sql(sql: str, allowed_tables=ALLOWED_TABLES) -> str:
    """Return cleaned SQL if it is a single read-only SELECT on allowed tables, else raise."""
    cleaned = _COMMENT_RE.sub(" ", sql).strip()
    cleaned = cleaned.rstrip(";").strip()
    if not cleaned:
        raise UnsafeSQLError("empty query")
    if ";" in _strip_string_literals(cleaned):
        raise UnsafeSQLError("multiple statements are not allowed")

    probe = _strip_string_literals(cleaned).lower()
    if not re.match(r"^(select|with)\b", probe):
        raise UnsafeSQLError("only SELECT queries are allowed")

    for word in re.findall(r"[a-z_]+", probe):
        if word in FORBIDDEN_KEYWORDS:
            raise UnsafeSQLError(f"forbidden keyword: {word}")

    ctes = {m.lower() for m in _CTE_RE.findall(probe)}
    for ref in _TABLE_REF_RE.findall(probe):
        name = ref.replace("`", "").replace('"', "").split(".")[-1]
        if name not in allowed_tables and name not in ctes:
            raise UnsafeSQLError(f"table not allowed: {name}")
    return cleaned
