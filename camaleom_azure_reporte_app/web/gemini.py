from __future__ import annotations

import json
from typing import Any

import requests

from ..config import GEMINI_API_KEY, GEMINI_MODEL

MODEL = GEMINI_MODEL if GEMINI_MODEL and GEMINI_MODEL.startswith("gemini") else "gemini-flash-latest"
_ENDPOINT = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"


def _contexto(data: dict[str, Any]) -> str:
    meta = data.get("meta", {})
    m = data.get("metrics", {})
    tables = data.get("tables", {})

    def resumen_tareas(items, limite=40):
        out = []
        for t in items[:limite]:
            out.append(
                f"- [{t.get('AzureID','')}] {t.get('Titulo Azure','')} | HU: {t.get('HU','')} | "
                f"estimado: {t.get('Original Estimate Azure','')}h | reportado Camaleom: {t.get('Horas Camaleom','')}h | "
                f"estado: {t.get('Estado reporte','')} | fechas: {t.get('Fechas reales','')}"
            )
        return "\n".join(out) or "(ninguna)"

    partes = [
        f"PERIODO: {meta.get('periodo_inicio')} a {meta.get('periodo_fin')}. Persona: {meta.get('persona')}. Sprints: {meta.get('sprints')}.",
        "",
        "METRICAS GLOBALES:",
        f"- Items Azure: {m.get('items_azure')}, HU: {m.get('hu_azure')}, Tasks: {m.get('tasks_azure')}",
        f"- Tasks reportadas: {m.get('tasks_reportadas')}, Tasks SIN reportar: {m.get('tasks_sin_reportar')}",
        f"- Tasks completas (horas ok): {m.get('tasks_completas')}, Tasks pendientes de horas: {m.get('tasks_pendientes_horas')}",
        f"- Total reportado: {m.get('total_reportado')}h, Total esperado: {m.get('total_esperado')}h, Balance: {m.get('balance')}h",
        f"- Total horas faltantes por reportar: {m.get('total_horas_faltantes')}h",
        f"- Cobertura tasks: {m.get('cobertura_tasks')}%, cobertura horas: {m.get('cobertura_horas')}%",
        "",
        "TASKS SIN REPORTAR (te faltan por reportar en Camaleom):",
        resumen_tareas(tables.get("tasks_sin_reportar", [])),
        "",
        "TASKS YA REPORTADAS:",
        resumen_tareas(tables.get("tasks_reportadas", [])),
        "",
        "HORAS POR DIA:",
        "\n".join(
            f"- {d.get('FechaRealPruebasUnitarias','')}: reportadas {d.get('Horas reportadas','')}h / esperadas {d.get('Debe tener','')}h ({d.get('Estado','')})"
            for d in tables.get("horas_dia", [])
        ) or "(sin datos)",
    ]
    return "\n".join(partes)


SYSTEM = (
    "Eres un asistente experto en control de horas que analiza el cruce entre Azure DevOps y Camaleom. "
    "Respondes en espanol, claro y conciso, con numeros concretos. Usa SOLO los datos del contexto; "
    "si algo no esta en los datos, dilo. Cuando te pregunten que falta por reportar, lista las tasks con su AzureID y horas."
)


def preguntar(data: dict[str, Any], pregunta: str, historial: list[dict] | None = None) -> str:
    if not GEMINI_API_KEY:
        raise RuntimeError("El servidor no tiene GEMINI_API_KEY configurada.")

    contexto = _contexto(data)
    contents = [{"role": "user", "parts": [{"text": f"{SYSTEM}\n\n===== DATOS DEL REPORTE =====\n{contexto}"}]},
                {"role": "model", "parts": [{"text": "Entendido, tengo los datos del reporte. Preguntame lo que quieras."}]}]
    for h in (historial or [])[-6:]:
        role = "user" if h.get("role") == "user" else "model"
        contents.append({"role": role, "parts": [{"text": str(h.get("text", ""))}]})
    contents.append({"role": "user", "parts": [{"text": pregunta}]})

    resp = requests.post(
        _ENDPOINT.format(model=MODEL),
        params={"key": GEMINI_API_KEY},
        json={"contents": contents, "generationConfig": {"temperature": 0.3, "maxOutputTokens": 800}},
        timeout=45,
    )
    if resp.status_code >= 400:
        raise RuntimeError(f"Gemini error {resp.status_code}: {resp.text[:300]}")
    body = resp.json()
    try:
        return body["candidates"][0]["content"]["parts"][0]["text"].strip()
    except (KeyError, IndexError):
        return "No pude generar una respuesta. Intenta reformular la pregunta."
