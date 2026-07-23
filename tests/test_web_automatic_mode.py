import asyncio
import os
import subprocess
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("APP_SECRET_KEY", "test-secret")
os.environ.setdefault("DATABASE_URL", "postgresql://test:test@localhost/test")
os.environ.setdefault("ENCRYPTION_KEY", "test-encryption-key")

from fastapi import HTTPException

from camaleom_azure_reporte_app.web import main, pipeline


class AutomaticCamaleomTests(unittest.TestCase):
    def test_download_subprocess_returns_reported_existing_path(self):
        with tempfile.TemporaryDirectory() as directory:
            report = Path(directory) / "camaleom.xlsx"
            report.touch()
            completed = subprocess.CompletedProcess(
                args=[],
                returncode=0,
                stdout=f"Abriendo reporte\nPATHRESULT::{report}\n",
                stderr="",
            )
            with patch.object(pipeline.subprocess, "run", return_value=completed):
                result = pipeline.descargar_camaleom_subproceso(
                    "user", "secret", date(2026, 7, 1), date(2026, 7, 23)
                )
            self.assertEqual(result, str(report))

    def test_download_subprocess_surfaces_login_failure(self):
        completed = subprocess.CompletedProcess(
            args=[],
            returncode=3,
            stdout="LOGINFAIL::Credenciales incorrectas\n",
            stderr="",
        )
        with patch.object(pipeline.subprocess, "run", return_value=completed):
            with self.assertRaisesRegex(RuntimeError, "Credenciales incorrectas"):
                pipeline.descargar_camaleom_subproceso(
                    "user", "bad-secret", date(2026, 7, 1), date(2026, 7, 23)
                )

    def test_run_rejects_unknown_source(self):
        with (
            patch.object(main, "require_user", return_value={"id": 7}),
            patch.object(main.db, "get_profile", return_value={}),
        ):
            with self.assertRaises(HTTPException) as raised:
                asyncio.run(
                    main.run_reporte(
                        request=object(),
                        source="unknown",
                        fecha_final="2026-07-23",
                    )
                )
        self.assertEqual(raised.exception.status_code, 400)


if __name__ == "__main__":
    unittest.main()
