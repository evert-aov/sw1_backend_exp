"""Regresión de configuración PostgreSQL y arranque; no sustituye integración real."""

from __future__ import annotations

import asyncio
from contextlib import redirect_stderr
from io import StringIO
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from sqlalchemy.engine import make_url
from app.core.config import BACKEND_ROOT, Settings
from app.core import database
from scripts import check_database
from main import app, lifespan


class DatabaseConfigurationTests(unittest.TestCase):
    """Comprueba selección, codificación y lectura estable del entorno."""

    def configuration(self, **values) -> Settings:
        """Crea configuración independiente del .env y de variables del proceso."""
        with patch.dict(os.environ, {}, clear=True):
            return Settings(_env_file=None, JWT_SECRET="test-secret-only", DB_USER="tester",
                            DB_PASS="secret@:/?#%", DB_NAME="test_db", **values)

    def test_dotenv_path_is_absolute(self):
        """El .env se resuelve desde el backend, independientemente del directorio actual."""
        self.assertEqual(Settings.model_config["env_file"], BACKEND_ROOT / ".env")
        previous = Path.cwd()
        try:
            with tempfile.TemporaryDirectory() as directory:
                os.chdir(directory)
                self.assertEqual(Settings().database_url, database.settings.database_url)
        finally:
            os.chdir(previous)

    def test_password_characters_roundtrip(self):
        """Los símbolos de la contraseña no cambian host ni nombre de base."""
        url = make_url(self.configuration().database_url)
        self.assertEqual(url.password, "secret@:/?#%")
        self.assertEqual(url.database, "test_db")
        self.assertEqual(url.drivername, "postgresql+psycopg2")

    def test_database_url_takes_priority(self):
        """La URL explícita prevalece y conserva opciones de conexión remota."""
        config = self.configuration(DATABASE_URL="postgres://remote:password@remote.invalid:5433/remote_db?sslmode=require")
        url = make_url(config.database_url)
        self.assertEqual(url.host, "remote.invalid")
        self.assertEqual(url.port, 5433)
        self.assertEqual(url.query["sslmode"], "require")

    def test_sqlite_is_rejected(self):
        """Una URL SQLite no permite activar una base alternativa."""
        with self.assertRaisesRegex(ValueError, "PostgreSQL"):
            _ = self.configuration(DATABASE_URL="sqlite:///:memory:").database_url

    def test_engine_creation_does_not_probe_other_hosts(self):
        """Construir el motor no abre conexiones ni consulta DB_HOST por separado."""
        fake_engine = MagicMock()
        with patch.object(database, "create_engine", return_value=fake_engine) as create:
            engine, url = database._build_engine()
        self.assertIs(engine, fake_engine)
        self.assertEqual(url, database.settings.database_url)
        self.assertTrue(create.call_args.kwargs["hide_parameters"])
        fake_engine.connect.assert_not_called()

    def test_connection_failure_propagates(self):
        """Un fallo PostgreSQL se propaga sin crear SQLite ni sembrar datos."""
        with patch.object(database, "engine") as engine:
            engine.begin.side_effect = ConnectionError("unavailable")
            with self.assertRaises(ConnectionError):
                database.init_db()

    def test_startup_checks_connection_and_schema_without_creating_tables(self):
        """El arranque comprueba estructura además de conectividad sin mutar la base."""
        with patch.object(database.settings, "DB_SYNCHRONIZE", False), patch.object(database, "engine") as engine, patch.object(database.Base.metadata, "create_all") as create, patch("app.core.schema.validate_database_schema") as validate:
            database.init_db()
            connection = engine.begin.return_value.__enter__.return_value
            self.assertEqual(str(connection.execute.call_args.args[0]), "SELECT 1")
            validate.assert_called_once_with(connection)
            create.assert_not_called()

    def test_development_startup_runs_migrations_in_startup_transaction(self):
        """La opción existente del .env prepara la base con Alembic antes de servir."""
        with patch.object(database.settings, "DB_SYNCHRONIZE", True), patch.object(database, "engine") as engine, patch("app.core.migrations.migrate_connection") as migrate, patch.object(database.Base.metadata, "create_all") as create, patch.object(database, "seed_database") as seed:
            database.init_db()
            connection = engine.begin.return_value.__enter__.return_value
            migrate.assert_called_once_with(connection)
            create.assert_not_called()
            seed.assert_not_called()

    def test_migration_failure_aborts_startup_transaction(self):
        """No atiende peticiones ni confirma una migración parcialmente fallida."""
        failure = RuntimeError("migration failed")
        with patch.object(database.settings, "DB_SYNCHRONIZE", True), patch.object(database, "engine") as engine, patch("app.core.migrations.migrate_connection", side_effect=failure):
            with self.assertRaisesRegex(RuntimeError, "migration failed"):
                database.init_db()
            self.assertIs(engine.begin.return_value.__exit__.call_args.args[1], failure)


class StartupTests(unittest.IsolatedAsyncioTestCase):
    """Comprueba que lifespan espere PostgreSQL y no oculte errores."""

    async def test_failure_prevents_startup(self):
        """Una conexión fallida impide entrar al estado de servicio."""
        with patch("asyncio.to_thread", new=AsyncMock(side_effect=ConnectionError("unavailable"))):
            with self.assertRaises(ConnectionError):
                async with lifespan(app):
                    self.fail("El servicio no debe aceptar tráfico sin PostgreSQL")

    async def test_shutdown_disposes_pool(self):
        """El pool se libera después del cierre normal."""
        with patch("asyncio.to_thread", new=AsyncMock()) as initialize, patch.object(database, "engine") as engine:
            async with lifespan(app):
                initialize.assert_awaited_once()
            engine.dispose.assert_called_once()


class PsqlCommandTests(unittest.TestCase):
    """Comprueba que psql recibe el destino real sin credenciales en argv."""

    def test_psql_environment_and_redaction(self):
        """Pasa credenciales por entorno, fuerza solo lectura y oculta errores sensibles."""
        password = "special-password@:/"
        fake_settings = MagicMock()
        fake_settings.database_url = "postgresql+psycopg2://tester:special-password%40%3A%2F@remote.invalid:5433/test_db?sslmode=require"
        result = subprocess.CompletedProcess([], 2, stdout="", stderr=password)
        output = StringIO()
        with patch.object(check_database, "settings", fake_settings), patch.object(check_database.shutil, "which", return_value="psql"), patch.object(check_database.subprocess, "run", return_value=result) as run, redirect_stderr(output):
            self.assertEqual(check_database.main(), 2)
        command = run.call_args.args[0]
        env = run.call_args.kwargs["env"]
        self.assertNotIn(password, " ".join(command))
        self.assertEqual(env["PGHOST"], "remote.invalid")
        self.assertEqual(env["PGPORT"], "5433")
        self.assertEqual(env["PGDATABASE"], "test_db")
        self.assertEqual(env["PGPASSWORD"], password)
        self.assertEqual(env["PGSSLMODE"], "require")
        self.assertIn("default_transaction_read_only=on", env["PGOPTIONS"])
        self.assertNotIn(password, output.getvalue())


if __name__ == "__main__":
    unittest.main()
