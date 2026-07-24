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

    rangos = meta.get("sprint_ranges") or []
    rangos_txt = "\n".join(f"- Sprint {r.get('sprint')}: del {r.get('inicio')} al {r.get('fin')} (fechas reales de Azure DevOps)" for r in rangos) or "(no disponibles en este reporte)"

    partes = [
        f"PERIODO: {meta.get('periodo_inicio')} a {meta.get('periodo_fin')}. Persona: {meta.get('persona')}. Sprints: {meta.get('sprints')}.",
        "",
        "FECHAS REALES DE CADA SPRINT (tomadas de Azure DevOps; NO inventes otras):",
        rangos_txt,
        "",
        "METRICAS GLOBALES:",
        f"- Items Azure: {m.get('items_azure')}, HU: {m.get('hu_azure')}, Tasks: {m.get('tasks_azure')}",
        f"- Tasks reportadas (completas): {m.get('tasks_reportadas')}, Parciales (les faltan horas): {m.get('tasks_parciales')}, Excedidas (mas horas de las trabajadas): {m.get('tasks_excedidas')}, SIN reportar (0 horas): {m.get('tasks_sin_reportar')}",
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
    "Eres un asistente experto y versatil en gestion de tiempo y control de horas (Azure DevOps + Camaleom). "
    "Tienes el contexto del reporte del usuario (metricas, tasks, horas, fechas del periodo). Ayudas de forma clara, "
    "util y conversacional: respondes preguntas con numeros concretos, pero tambien razonas, priorizas, das "
    "recomendaciones y ARMAS plantillas de reporte para Camaleom cuando te lo piden, usando los campos disponibles "
    "(descripcion/titulo de la task, horas estimadas vs reportadas, horas faltantes, fechas del periodo). "
    "Camaleom normalmente registra por dia: Fecha, Descripcion/Actividad y TiempoReal (horas). Si te piden una plantilla, "
    "construyela concreta con esos campos y con los datos de la task (sugiere las horas faltantes repartidas en dias laborales del periodo). "
    "NO te limites a decir 'no esta en los datos': se practico y propon lo mejor posible con lo que hay. "
    "IMPORTANTE sobre fechas: usa EXCLUSIVAMENTE las fechas reales de cada sprint que aparecen en el contexto; "
    "NUNCA inventes ni asumas fechas. Los sprints van normalmente de martes a lunes (si el lunes de cierre es festivo en "
    "Colombia, el ultimo dia habil es el viernes previo). Si te preguntan por las fechas de un sprint, responde con el rango exacto provisto. "
    "Responde en espanol, con formato claro (listas y negritas). Se completo; no cortes la respuesta a la mitad."
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
        json={"contents": contents, "generationConfig": {"temperature": 0.5, "maxOutputTokens": 10000, "topP": 0.95}},
        timeout=60,
    )
    if resp.status_code >= 400:
        raise RuntimeError(f"Gemini error {resp.status_code}: {resp.text[:300]}")
    body = resp.json()
    try:
        return body["candidates"][0]["content"]["parts"][0]["text"].strip()
    except (KeyError, IndexError):
        return "No pude generar una respuesta. Intenta reformular la pregunta."
