from __future__ import annotations

import re
from difflib import SequenceMatcher
from typing import Any

import pandas as pd

from .selenium_utils import normalizar_texto

STOPWORDS = {
    "de", "del", "la", "las", "el", "los", "en", "y", "o", "para", "por", "con", "sin",
    "un", "una", "unos", "unas", "a", "al", "que", "se", "su", "sus", "parte", "realizar",
    "crear", "implementar", "implementacion", "validar", "validacion", "ejecutar", "revision",
    "revisar", "configurar", "configuracion", "analisis", "inicial",
}


def tokens_importantes(texto: str) -> set[str]:
    tokens = set(normalizar_texto(texto).split())
    return {t for t in tokens if len(t) >= 3 and t not in STOPWORDS}


def texto_azure_match(row: pd.Series) -> str:
    partes = [
        str(row.get("Titulo", "")),
        str(row.get("Descripcion Azure", "")),
        str(row.get("ParentTitle", "")),
        str(row.get("Tags", "")),
    ]
    return " ".join(p for p in partes if p and p.lower() != "nan")


def score_textos(azure_texto: str, camaleom_texto: str) -> tuple[float, str]:
    az_norm = normalizar_texto(azure_texto)
    cam_norm = normalizar_texto(camaleom_texto)
    if not az_norm or not cam_norm:
        return 0.0, "Sin texto"

    if az_norm == cam_norm:
        return 1.0, "Exacto"
    if az_norm in cam_norm or cam_norm in az_norm:
        corto = min(len(az_norm), len(cam_norm))
        largo = max(len(az_norm), len(cam_norm))
        return max(0.82, corto / largo), "Contiene"

    az_tokens = tokens_importantes(az_norm)
    cam_tokens = tokens_importantes(cam_norm)
    if not az_tokens or not cam_tokens:
        return 0.0, "Sin tokens"

    inter = az_tokens & cam_tokens
    union = az_tokens | cam_tokens
    jaccard = len(inter) / len(union) if union else 0.0
    cobertura_azure = len(inter) / len(az_tokens) if az_tokens else 0.0
    cobertura_camaleom = len(inter) / len(cam_tokens) if cam_tokens else 0.0
    sequence = SequenceMatcher(None, az_norm, cam_norm).ratio()

    score = max(
        jaccard,
        cobertura_azure * 0.92,
        cobertura_camaleom * 0.86,
        sequence * 0.75,
    )

    if cobertura_azure >= 0.70:
        tipo = "Cobertura Azure"
    elif cobertura_camaleom >= 0.70:
        tipo = "Cobertura Camaleom"
    elif jaccard >= 0.45:
        tipo = "Tokens compartidos"
    else:
        tipo = "Similaridad baja"
    return round(float(score), 4), tipo


def encontrar_match_camaleom(azure_row: pd.Series, total_camaleom: pd.DataFrame, usados: set[str] | None = None) -> tuple[pd.Series | None, float, str]:
    if total_camaleom.empty:
        return None, 0.0, "Sin Camaleom"

    usados = usados or set()
    azure_texto = texto_azure_match(azure_row)
    candidatos = total_camaleom.copy()
    candidatos["Key"] = candidatos["DescripcionLimpia"].apply(normalizar_texto)
    candidatos = candidatos[~candidatos["Key"].isin(usados)]
    if candidatos.empty:
        return None, 0.0, "Sin candidatos"

    scores: list[dict[str, Any]] = []
    for idx, cam in candidatos.iterrows():
        score, tipo = score_textos(azure_texto, str(cam.get("DescripcionLimpia", "")))
        scores.append({"idx": idx, "score": score, "tipo": tipo})

    mejor = max(scores, key=lambda item: item["score"])
    if mejor["score"] >= 0.42:
        return candidatos.loc[mejor["idx"]], float(mejor["score"]), str(mejor["tipo"])
    return None, float(mejor["score"]), "Sin match confiable"


def es_task_azure(valor: object) -> bool:
    return normalizar_texto(valor) == "task"


def cruzar_azure_camaleom(azure_df: pd.DataFrame, total_camaleom: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    rows = []
    camaleom_matched_keys: set[str] = set()
    azure_tasks = azure_df[azure_df["Tipo"].apply(es_task_azure)].copy() if azure_df is not None and not azure_df.empty else pd.DataFrame()
    for _, az in azure_tasks.iterrows():
        match, match_score, match_tipo = encontrar_match_camaleom(az, total_camaleom, camaleom_matched_keys)
        completed = float(az.get("Completed Work", 0) or 0)
        if match is not None:
            horas = float(match.get("TotalHoras", 0) or 0)
            desc_cam = match.get("DescripcionLimpia", "")
            reportes = match.get("Reportes", "")
            fechas = match.get("Fechas", "")
            veces = int(match.get("VecesReportada", 0) or 0)
            estado_reporte = "Reportada" if horas > 0 else "Sin horas"
            camaleom_matched_keys.add(normalizar_texto(desc_cam))
        else:
            horas = 0.0
            desc_cam = ""
            reportes = ""
            fechas = ""
            veces = 0
            estado_reporte = "Falta reportar"

        rows.append(
            {
                "HU": az.get("HU", ""),
                "ParentID": az.get("ParentID", ""),
                "ParentTitle": az.get("ParentTitle", ""),
                "AzureID": az.get("AzureID", ""),
                "Tipo": az.get("Tipo", ""),
                "Titulo Azure": az.get("Titulo", ""),
                "Descripcion Azure": az.get("Descripcion Azure", ""),
                "Estado Azure": az.get("Estado", ""),
                "Tags Azure": az.get("Tags", ""),
                "Original Estimate Azure": float(az.get("Original Estimate", 0) or 0),
                "Remaining Work Azure": float(az.get("Remaining Work", 0) or 0),
                "Completed Work Azure": completed,
                "Descripcion Camaleom": desc_cam,
                "Horas Camaleom": horas,
                "Diferencia Camaleom vs Completed": horas - completed,
                "Match Score": match_score,
                "Match Tipo": match_tipo,
                "Veces reportada": veces,
                "Reportes Camaleom": reportes,
                "Fechas reales": fechas,
                "Estado reporte": estado_reporte,
            }
        )

    for _, cam in total_camaleom.iterrows():
        desc_cam = cam.get("DescripcionLimpia", "")
        if normalizar_texto(desc_cam) in camaleom_matched_keys:
            continue

        horas = float(cam.get("TotalHoras", 0) or 0)
        rows.append(
            {
                "HU": "Sin HU Azure",
                "ParentID": "",
                "ParentTitle": "",
                "AzureID": "",
                "Tipo": "Camaleom",
                "Titulo Azure": "",
                "Descripcion Azure": "",
                "Estado Azure": "",
                "Tags Azure": "",
                "Original Estimate Azure": 0.0,
                "Remaining Work Azure": 0.0,
                "Completed Work Azure": 0.0,
                "Descripcion Camaleom": desc_cam,
                "Horas Camaleom": horas,
                "Diferencia Camaleom vs Completed": horas,
                "Match Score": 0.0,
                "Match Tipo": "Solo Camaleom",
                "Veces reportada": int(cam.get("VecesReportada", 0) or 0),
                "Reportes Camaleom": cam.get("Reportes", ""),
                "Fechas reales": cam.get("Fechas", ""),
                "Estado reporte": "Solo Camaleom",
            }
        )

    comparativo = pd.DataFrame(rows)
    if comparativo.empty:
        resumen_hu = pd.DataFrame(columns=["HU", "Horas Camaleom", "Completed Work Azure", "Diferencia Camaleom vs Completed", "Tasks Azure", "Tasks reportadas", "Tasks faltantes"])
    else:
        resumen_hu = (
            comparativo.groupby("HU", dropna=False)
            .agg(
                HorasCamaleom=("Horas Camaleom", "sum"),
                CompletedWorkAzure=("Completed Work Azure", "sum"),
                DiferenciaCamaleomVsCompleted=("Diferencia Camaleom vs Completed", "sum"),
                MatchPromedio=("Match Score", "mean"),
                TasksAzure=("Tipo", lambda s: sum(es_task_azure(x) for x in s)),
                TasksReportadas=("Estado reporte", lambda s: sum(x == "Reportada" for x in s)),
                TasksFaltantes=("Estado reporte", lambda s: sum(x == "Falta reportar" for x in s)),
                Faltantes=("Titulo Azure", lambda s: " | ".join(s[comparativo.loc[s.index, "Estado reporte"] == "Falta reportar"].astype(str))),
            )
            .reset_index()
            .rename(
                columns={
                    "HorasCamaleom": "Horas Camaleom",
                    "CompletedWorkAzure": "Completed Work Azure",
                    "DiferenciaCamaleomVsCompleted": "Diferencia Camaleom vs Completed",
                    "MatchPromedio": "Match Score Promedio",
                    "TasksAzure": "Tasks Azure",
                    "TasksReportadas": "Tasks reportadas",
                    "TasksFaltantes": "Tasks faltantes",
                }
            )
        )
    return comparativo, resumen_hu
