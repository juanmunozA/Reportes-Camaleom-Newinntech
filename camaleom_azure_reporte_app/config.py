from __future__ import annotations

import os
from datetime import date
from pathlib import Path

# Camaleom
CAMALEOM_URL = os.getenv("CAMALEOM_URL", "https://camaleom.gruponutresa.com/")
CAMALEOM_USER = os.getenv("CAMALEOM_USER", "")
CAMALEOM_PASS = os.getenv("CAMALEOM_PASS", "")

# Azure DevOps
AZURE_ORG = os.getenv("AZURE_ORG", "GrupoNutresa")
AZURE_PROJECT = os.getenv("AZURE_PROJECT", "Shared")
AZURE_TEAM = os.getenv("AZURE_TEAM", "DevSecOps")
AZURE_EMAIL = os.getenv("AZURE_EMAIL", "")
AZURE_PASS = os.getenv("AZURE_PASS", "")
AZURE_DEVOPS_PAT = os.getenv("AZURE_DEVOPS_PAT", "")

# General
HEADLESS = os.getenv("HEADLESS", "false").lower() == "true"
DOWNLOAD_DIR = Path(os.getenv("DOWNLOAD_DIR", str(Path.cwd() / "descargas_reportes"))).resolve()
OUT_DIR = Path(os.getenv("OUT_DIR", str(Path.cwd() / "salidas_reportes"))).resolve()
DEFAULT_FECHA_INICIO = date(2026, 7, 14)
DEFAULT_FECHA_FIN = date(2026, 7, 17)
DEFAULT_AZURE_SPRINT = int(os.getenv("AZURE_SPRINT", "279"))
AZURE_ASSIGNED_TO_NAME = os.getenv("AZURE_ASSIGNED_TO_NAME", "")
AZURE_ASSIGNED_TO_EMAIL = os.getenv("AZURE_ASSIGNED_TO_EMAIL", AZURE_EMAIL)
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.5-flash")
USAR_GEMINI_NAV = os.getenv("USAR_GEMINI_NAV", "true").lower() == "true"

# Web app
DATABASE_URL = os.getenv("DATABASE_URL", "")
APP_SECRET_KEY = os.getenv("APP_SECRET_KEY", "")
ENCRYPTION_KEY = os.getenv("ENCRYPTION_KEY", "")

SELECTORES_CAMALEOM = {
    "usuario": ["input[name='username']", "input[name='user']", "input[type='email']", "#username", "#userName", "#i0116"],
    "password": [
        "input[name='password']", "input[type='password']", "input[autocomplete='current-password']",
        "input[placeholder*='contrase']", "input[aria-label*='contrase']", "input[id*='pass']",
        "input[name*='pass']", "#password", "#i0118",
    ],
    "submit": ["button[type='submit']", "input[type='submit']", "button", "[role='button']", "#idSIButton9"],
    "fecha_desde": [
        "input[name='fechaDesde']", "input[name='fechaInicio']", "input[type='date']",
        "input[id*='FechaInicio']", "input[id*='FechaInicial']", "input[id*='fechaInicial']",
        "input[id*='fechaInicio']", "input[placeholder*='Desde']", "input[placeholder*='Inicial']",
        "input[placeholder='dd/mm/aaaa']",
    ],
    "fecha_hasta": [
        "input[name='fechaHasta']", "input[name='fechaFin']", "input[type='date']",
        "input[id*='FechaFin']", "input[id*='FechaFinal']", "input[id*='fechaFinal']",
        "input[id*='fechaFin']", "input[placeholder*='Hasta']", "input[placeholder*='Final']",
        "input[placeholder='dd/mm/aaaa']",
    ],
}

TEXTOS_CAMALEOM = {
    "siguiente": ["Siguiente", "Continuar", "Iniciar sesi?n"],
    "reportes": ["Reportes", "Reporte"],
    "mis_actividades": ["Generar Reporte mis Actividades", "Mis Actividades", "Mis actividades", "Mis actividades realizadas", "Actividades"],
    "generar": ["Generar", "Consultar", "Buscar", "Generar reporte"],
    "descargar": ["Exportar Actividades", "Descargar", "Exportar", "Excel", "Exportar Excel"],
}
