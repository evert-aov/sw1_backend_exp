"""Comprueba PostgreSQL con psql y el .env del backend, sin modificar datos."""

from __future__ import annotations

import os
from pathlib import Path
import shutil
import subprocess
import sys
from urllib.parse import quote

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy.engine import make_url
from app.core.config import settings


def main() -> int:
    """Consulta metadatos en modo de solo lectura sin exponer credenciales."""
    if sys.version_info[:3] != (3, 14, 6):
        print("Se requiere Python 3.14.6.", file=sys.stderr)
        return 1
    executable = shutil.which("psql")
    if not executable:
        print("Instala el cliente psql de PostgreSQL.", file=sys.stderr)
        return 1
    url = make_url(settings.database_url)
    parameters = url.translate_connect_args(username="user", database="dbname")
    parameters.update(url.query)
    parameters["connect_timeout"] = "5"
    parameters["options"] = (
        str(parameters.get("options", ""))
        + " -c default_transaction_read_only=on -c statement_timeout=5000"
    ).strip()
    environment_names = {
        "host": "PGHOST", "port": "PGPORT", "dbname": "PGDATABASE",
        "user": "PGUSER", "password": "PGPASSWORD", "options": "PGOPTIONS",
        "connect_timeout": "PGCONNECT_TIMEOUT", "sslmode": "PGSSLMODE",
        "sslrootcert": "PGSSLROOTCERT", "sslcert": "PGSSLCERT", "sslkey": "PGSSLKEY",
        "sslpassword": "PGSSLPASSWORD", "application_name": "PGAPPNAME",
        "channel_binding": "PGCHANNELBINDING", "target_session_attrs": "PGTARGETSESSIONATTRS",
        "gssencmode": "PGGSSENCMODE", "hostaddr": "PGHOSTADDR",
    }
    if any(key not in environment_names for key in parameters):
        print("La URL usa una opción libpq todavía no admitida por este comprobador.", file=sys.stderr)
        return 1
    environment = {key: value for key, value in os.environ.items() if not key.startswith("PG")}
    environment.update({environment_names[key]: str(value) for key, value in parameters.items()})
    query = """
        SELECT current_database() AS database, current_user AS role,
               current_setting('server_version') AS postgres_version;
        SELECT table_name FROM information_schema.tables
        WHERE table_schema = 'public' ORDER BY table_name;
    """
    try:
        result = subprocess.run(
            [executable, "-X", "-w", "-v", "ON_ERROR_STOP=1", "-c", query],
            env=environment,
            capture_output=True, text=True, timeout=15,
        )
    except subprocess.TimeoutExpired:
        print("PostgreSQL no respondió dentro del límite de conexión.", file=sys.stderr)
        return 1
    secrets = [settings.database_url, url.password, quote(url.password or "", safe=""), url.query.get("sslpassword")]
    for stream, output in [(sys.stdout, result.stdout), (sys.stderr, result.stderr)]:
        for secret in secrets:
            if secret:
                output = output.replace(secret, "[REDACTED]")
        if output:
            print(output, file=stream, end="")
    return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())
