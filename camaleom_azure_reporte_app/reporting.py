from __future__ import annotations

from datetime import date
from pathlib import Path
import re

import pandas as pd

from .config import OUT_DIR
from .html_report import guardar_html_integrado


def datos_camaleom_visibles(df: pd.DataFrame) -> pd.DataFrame:
    columnas_internas = ["HorasNum", "DescripcionLimpia", "DescripcionKey", "ReporteID"]
    return df.drop(columns=[col for col in columnas_internas if col in df.columns], errors="ignore")


def cruce_visible(df: pd.DataFrame | None) -> pd.DataFrame | None:
    if df is None:
        return None
    visible = df.copy()
    if "Match Score" in visible.columns:
        visible = visible.rename(columns={"Match Score": "Similitud"})
    columnas_ocultas = ["Remaining Work Azure", "Match Tipo"]
    return visible.drop(columns=[col for col in columnas_ocultas if col in visible.columns], errors="ignore")


def _iteration_sprint(value: object) -> str:
    text = "" if pd.isna(value) else str(value)
    match = re.search(r"Sprint\s*\d+", text, flags=re.IGNORECASE)
    if match:
        return " ".join(match.group(0).split()).title()
    return text.split("\\")[-1] if "\\" in text else text


def azure_visible(df: pd.DataFrame | None) -> pd.DataFrame | None:
    if df is None:
        return None
    visible = df.copy()
    if "Tipo" in visible.columns:
        visible = visible[visible["Tipo"].astype(str).str.lower().eq("task")].copy()
    if "IterationPath" in visible.columns:
        visible["IterationPath"] = visible["IterationPath"].map(_iteration_sprint)
    columnas_ocultas = ["TituloKey", "DescripcionAzureKey", "ParentTipo"]
    return visible.drop(columns=[col for col in columnas_ocultas if col in visible.columns], errors="ignore")


def resumen_hu_visible(df: pd.DataFrame | None) -> pd.DataFrame | None:
    if df is None:
        return None
    columnas_ocultas = ["Match Score Promedio"]
    return df.drop(columns=[col for col in columnas_ocultas if col in df.columns], errors="ignore")


def guardar_excel_integrado(
    salida: Path,
    resumen_dia: pd.DataFrame,
    detalle_por_descripcion: pd.DataFrame,
    total_por_descripcion: pd.DataFrame,
    datos_camaleom: pd.DataFrame,
    azure_df: pd.DataFrame | None,
    comparativo: pd.DataFrame | None,
    resumen_hu: pd.DataFrame | None,
):
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    with pd.ExcelWriter(salida, engine="openpyxl") as writer:
        resumen_dia.to_excel(writer, index=False, sheet_name="Resumen por dia")
        total_por_descripcion.to_excel(writer, index=False, sheet_name="Total por descripcion")
        detalle_por_descripcion.to_excel(writer, index=False, sheet_name="Detalle desc fecha")
        if azure_df is not None:
            azure_visible(azure_df).to_excel(writer, index=False, sheet_name="Sprint Azure")
        if comparativo is not None:
            cruce_visible(comparativo).to_excel(writer, index=False, sheet_name="Cruce Azure Camaleom")
        if resumen_hu is not None:
            resumen_hu_visible(resumen_hu).to_excel(writer, index=False, sheet_name="Resumen por HU")

    salida_html = salida.with_suffix(".html")
    guardar_html_integrado(
        salida_html,
        resumen_dia,
        detalle_por_descripcion,
        total_por_descripcion,
        datos_camaleom,
        azure_visible(azure_df),
        comparativo,
        resumen_hu_visible(resumen_hu),
    )
    print(f"Archivo HTML generado: {salida_html}")

def imprimir_resumen(
    fecha_inicio: date,
    fecha_fin: date,
    resumen_dia: pd.DataFrame,
    total_por_descripcion: pd.DataFrame,
    azure_df: pd.DataFrame | None,
    comparativo: pd.DataFrame | None,
    resumen_hu: pd.DataFrame | None,
):
    print(f"\nPeriodo: {fecha_inicio} a {fecha_fin}")
    if resumen_dia is not None and not resumen_dia.empty:
        print("\nRESUMEN POR DIA")
        print(resumen_dia.to_string(index=False))

    cols = ["DescripcionLimpia", "TotalHoras", "VecesReportada", "Reportes", "Fechas"]
    if total_por_descripcion is not None and all(col in total_por_descripcion.columns for col in cols):
        print("\nTOTAL POR TASK / DESCRIPCION CAMALEOM")
        print(total_por_descripcion[cols].to_string(index=False))

    if azure_df is not None:
        print("\nSPRINT AZURE DESCARGADO")
        tasks_azure = int((azure_df["Tipo"].astype(str).str.lower() == "task").sum()) if not azure_df.empty and "Tipo" in azure_df else 0
        print(f"Work items: {len(azure_df)}")
        print(f"Tasks Azure: {tasks_azure}")
        if not azure_df.empty:
            cols_azure = ["AzureID", "Tipo", "Titulo", "Estado", "Original Estimate", "Remaining Work", "Completed Work", "Tags", "HU"]
            cols_azure = [col for col in cols_azure if col in azure_df.columns]
            print(azure_df[cols_azure].to_string(index=False))

    if comparativo is not None:
        print("\nCRUCE AZURE VS CAMALEOM")
        cols = [
            "AzureID",
            "Tipo",
            "Titulo Azure",
            "Original Estimate Azure",
            "Completed Work Azure",
            "Horas Camaleom",
            "Diferencia Camaleom vs Completed",
            "Match Score",
            "Veces reportada",
            "Reportes Camaleom",
            "Fechas reales",
            "Estado reporte",
        ]
        cols = [col for col in cols if col in comparativo.columns]
        visible = comparativo[cols].rename(columns={"Match Score": "Similitud"})
        print(visible.to_string(index=False))

    if resumen_hu is not None:
        print("\nRESUMEN POR HU")
        print(resumen_hu_visible(resumen_hu).to_string(index=False))
