from __future__ import annotations

import importlib
import pkgutil
import re
import sqlite3
from pathlib import Path
from types import ModuleType


MIGRATION_PACKAGE = "aegis_alpha.db_migrations_files"
_MIGRATION_RE = re.compile(r"^m(?P<version>\d{4})_")


def _connect(db_path: str | Path) -> sqlite3.Connection:
    path = Path(db_path).expanduser()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    return conn


def _ensure_version_table(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS schema_versions (
            version INTEGER PRIMARY KEY,
            name TEXT NOT NULL,
            applied_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
        """
    )


def _available_migrations() -> list[tuple[int, str, ModuleType]]:
    package = importlib.import_module(MIGRATION_PACKAGE)
    migrations: list[tuple[int, str, ModuleType]] = []
    for info in pkgutil.iter_modules(package.__path__):
        match = _MIGRATION_RE.match(info.name)
        if match is None:
            continue
        module = importlib.import_module(f"{MIGRATION_PACKAGE}.{info.name}")
        migrations.append((int(match.group("version")), info.name, module))
    return sorted(migrations)


def current_version(db_path: str | Path) -> int:
    with _connect(db_path) as conn:
        _ensure_version_table(conn)
        row = conn.execute("SELECT COALESCE(MAX(version), 0) FROM schema_versions").fetchone()
    return int(row[0] if row else 0)


def apply_migrations(db_path: str | Path) -> int:
    with _connect(db_path) as conn:
        _ensure_version_table(conn)
        applied = {
            int(row[0])
            for row in conn.execute("SELECT version FROM schema_versions").fetchall()
        }
        for version, name, module in _available_migrations():
            if version in applied:
                continue
            upgrade = getattr(module, "upgrade", None)
            if not callable(upgrade):
                raise RuntimeError(f"Migration {name} does not define upgrade(conn)")
            upgrade(conn)
            conn.execute(
                "INSERT INTO schema_versions (version, name) VALUES (?, ?)",
                (version, name),
            )
        row = conn.execute("SELECT COALESCE(MAX(version), 0) FROM schema_versions").fetchone()
    return int(row[0] if row else 0)
