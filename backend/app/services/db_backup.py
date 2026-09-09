"""Dump e restore dell'intero DB via pg_dump/psql (Admin).

Uso previsto: scaricare un dump da un ambiente (es. prod) e ricaricarlo in
un altro (es. staging) per riprodurre un comportamento visto solo li'. Il
restore sovrascrive completamente il DB su cui gira — vedi i controlli in
app/routers/db_backup.py (password aggiuntiva + ALLOW_DB_RESTORE)."""
import os
import subprocess

from app.config import settings


def _pg_env() -> dict:
    return {**os.environ, "PGPASSWORD": settings.db_password}


def create_dump() -> bytes:
    """Dump SQL in chiaro, con DROP IF EXISTS prima di ogni oggetto (si
    puo' ricaricare anche su un DB non vuoto) e senza owner/privilegi
    (evita fallimenti se l'utente Postgres ha nome diverso tra ambienti)."""
    result = subprocess.run(
        [
            "pg_dump", "--format=plain", "--clean", "--if-exists",
            "--no-owner", "--no-privileges",
            "-h", settings.db_host, "-p", str(settings.db_port),
            "-U", settings.db_user, settings.db_name,
        ],
        env=_pg_env(), capture_output=True, timeout=300,
    )
    if result.returncode != 0:
        raise RuntimeError(f"pg_dump fallito: {result.stderr.decode('utf-8', errors='replace')}")
    return result.stdout


def restore_dump(sql_bytes: bytes) -> None:
    result = subprocess.run(
        [
            "psql", "-h", settings.db_host, "-p", str(settings.db_port),
            "-U", settings.db_user, "-d", settings.db_name,
            "--set", "ON_ERROR_STOP=1",
        ],
        input=sql_bytes, env=_pg_env(), capture_output=True, timeout=300,
    )
    if result.returncode != 0:
        raise RuntimeError(f"Restore fallito: {result.stderr.decode('utf-8', errors='replace')}")
