from __future__ import annotations

import io
import os
import re
import subprocess
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

import pandas as pd

from ..azure_devops import AzureDevOpsClient
from ..camaleom_excel import construir_resumen_camaleom, leer_reporte_camaleom
from ..config import AZURE_DEVOPS_PAT, CAMALEOM_URL
from ..matcher import cruzar_azure_camaleom, es_task_azure

HORAS_DIA = 8.0


def descargar_camaleom_subproceso(user: str, password: str, fecha_inicio: date, fecha_fin: date, log=lambda m: None) -> str:
    """Lanza la descarga de Camaleom en un subproceso aislado, con logs en vivo."""
    if not user or not password:
        raise RuntimeError("Para el modo Camaleom automatico necesitas guardar tu usuario y contrasena de Camaleom en Perfil.")
    env = os.environ.copy()
    env.update({
        "CAM_USER": user, "CAM_PASS": password, "CAM_URL": CAMALEOM_URL,
        "CAM_FI": fecha_inicio.isoformat(), "CAM_FF": fecha_fin.isoformat(),
        "HEADLESS": "true", "PYTHONUNBUFFERED": "1",
    })
    log("Modo Camaleom automatico: abriendo el navegador en el servidor...")

    proc = subprocess.Popen(
        [sys.executable, "-m", "camaleom_azure_reporte_app.web.camaleom_download"],
        env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1,
    )

    # Watchdog: mata el proceso si excede el limite, para no colgar la ejecucion.
    import threading
    matado = {"v": False}
    def _kill():
        matado["v"] = True
        try:
            proc.kill()
        except Exception:
            pass
    timer = threading.Timer(140, _kill)
    timer.start()

    ruta = None
    loginfail = None
    try:
        assert proc.stdout is not None
        for linea in proc.stdout:
            linea = linea.rstrip()
            if not linea:
                continue
            if linea.startswith("PATHRESULT::"):
                ruta = linea.split("PATHRESULT::", 1)[1].strip()
            elif linea.startswith("LOGINFAIL::"):
                loginfail = linea.split("LOGINFAIL::", 1)[1].strip()
                log("Camaleom: " + loginfail)
            else:
                log("Camaleom: " + linea[:150])
        proc.wait()
    finally:
        timer.cancel()

    if matado["v"]:
        raise RuntimeError("Camaleom tardo demasiado (probable MFA/Authenticator que no se puede aprobar en el servidor). Usa el modo Archivo XLSX.")
    if loginfail:
        raise RuntimeError(loginfail)
    if ruta and Path(ruta).exists():
        return ruta
    raise RuntimeError("No pude descargar el reporte de Camaleom automaticamente. Revisa las credenciales o usa el modo Archivo XLSX.")


def _num(v: Any) -> float:
    try:
        return float(v or 0)
    except (TypeError, ValueError):
        return 0.0


def _fecha(v: Any) -> date | None:
    if v is None:
        return None
    try:
        return datetime.fromisoformat(str(v).replace("Z", "+00:00")).date()
    except Exception:
        return None


def find_sprints_by_range(cliente: AzureDevOpsClient, inicio: date, fin: date) -> list[int]:
    """Encuentra numeros de sprint cuyo rango de fechas se cruza con [inicio, fin]."""
    arbol = cliente.obtener_arbol_iteraciones()
    encontrados: list[tuple[int, date]] = []

    def recorrer(nodo: dict[str, Any]):
        name = str(nodo.get("name", ""))
        m = re.search(r"Sprint\s*(\d+)", name, flags=re.IGNORECASE)
        if m:
            attrs = nodo.get("attributes") or {}
            s = _fecha(attrs.get("startDate"))
            f = _fecha(attrs.get("finishDate"))
            if s and f and s <= fin and f >= inicio:
                encontrados.append((int(m.group(1)), s))
        for hijo in nodo.get("children", []) or []:
            recorrer(hijo)

    recorrer(arbol)
    # Dedup por numero, ordenado por fecha de inicio
    vistos: dict[int, date] = {}
    for numero, s in encontrados:
        if numero not in vistos or s < vistos[numero]:
            vistos[numero] = s
    return [n for n, _ in sorted(vistos.items(), key=lambda kv: kv[1])]


def _records(df: pd.DataFrame | None, columnas: list[str] | None = None) -> list[dict[str, Any]]:
    if df is None or df.empty:
        return []
    clean = df.copy()
    if columnas:
        cols = [c for c in columnas if c in clean.columns]
        clean = clean[cols]
    out = []
    for _, row in clean.iterrows():
        rec = {}
        for col in clean.columns:
            val = row[col]
            if isinstance(val, float):
                rec[str(col)] = round(val, 2)
            elif pd.isna(val):
                rec[str(col)] = ""
            else:
                rec[str(col)] = str(val)
        out.append(rec)
    return out


def compute(azure_df, comparativo, resumen_dia, total_por_descripcion) -> dict[str, Any]:
    items_azure = int(len(azure_df)) if azure_df is not None else 0
    tasks_azure = 0
    hu_azure = 0
    if azure_df is not None and not azure_df.empty and "Tipo" in azure_df:
        tasks_azure = int(azure_df["Tipo"].apply(es_task_azure).sum())
        hu_azure = int((~azure_df["Tipo"].apply(es_task_azure)).sum())

    tasks_reportadas = tasks_sin_reportar = tasks_asociadas = tasks_completas = registros_asociados = 0
    total_reportado = 0.0
    horas_faltantes = 0.0
    if comparativo is not None and not comparativo.empty:
        solo_tasks = comparativo[comparativo["Tipo"].apply(es_task_azure)]
        tasks_reportadas = int((solo_tasks["Estado reporte"] == "Reportada").sum())
        tasks_sin_reportar = int((solo_tasks["Estado reporte"] == "Falta reportar").sum())
        tasks_asociadas = int((solo_tasks["Descripcion Camaleom"].astype(str).str.len() > 0).sum())
        for _, r in solo_tasks.iterrows():
            est = _num(r.get("Original Estimate Azure"))
            hrs = _num(r.get("Horas Camaleom"))
            registros_asociados += int(_num(r.get("Veces reportada")))
            if est > 0 and hrs >= est:
                tasks_completas += 1
            if est > hrs:
                horas_faltantes += est - hrs

    if total_por_descripcion is not None and not total_por_descripcion.empty and "TotalHoras" in total_por_descripcion:
        total_reportado = float(total_por_descripcion["TotalHoras"].sum())

    total_esperado = float(resumen_dia["Debe tener"].sum()) if resumen_dia is not None and not resumen_dia.empty and "Debe tener" in resumen_dia else 0.0
    balance = total_reportado - total_esperado
    tasks_pendientes = tasks_azure - tasks_completas

    def pct(a, b):
        return round(100.0 * a / b, 1) if b else 0.0

    return {
        "items_azure": items_azure,
        "hu_azure": hu_azure,
        "tasks_azure": tasks_azure,
        "tasks_reportadas": tasks_reportadas,
        "tasks_sin_reportar": tasks_sin_reportar,
        "cobertura_tasks": pct(tasks_reportadas, tasks_azure),
        "registros_camaleom_asociados": registros_asociados,
        "tasks_asociadas": tasks_asociadas,
        "tasks_completas": tasks_completas,
        "tasks_pendientes_horas": tasks_pendientes,
        "cobertura_asociacion": pct(tasks_asociadas, tasks_azure),
        "cobertura_horas": pct(tasks_completas, tasks_azure),
        "total_reportado": round(total_reportado, 1),
        "total_esperado": round(total_esperado, 1),
        "balance": round(balance, 1),
        "total_horas_faltantes": round(horas_faltantes, 1),
    }


def _build_xlsx(azure_df, comparativo, resumen_dia, total_por_descripcion) -> bytes:
    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        if resumen_dia is not None:
            resumen_dia.to_excel(writer, index=False, sheet_name="Horas por dia")
        if total_por_descripcion is not None:
            total_por_descripcion.to_excel(writer, index=False, sheet_name="Total Camaleom")
        if azure_df is not None:
            azure_df.to_excel(writer, index=False, sheet_name="Sprint Azure")
        if comparativo is not None:
            comparativo.to_excel(writer, index=False, sheet_name="Cruce")
    return buffer.getvalue()


def sprint_bounds(cliente: AzureDevOpsClient, sprint: int) -> tuple[date | None, date | None]:
    it = cliente.buscar_iteracion_sprint(sprint)
    attrs = it.get("attributes") or {}
    return _fecha(attrs.get("startDate")), _fecha(attrs.get("finishDate"))


def ejecutar(
    fecha_final: date,
    sprints_txt: str,
    diferenciador: str,
    azure_org: str,
    azure_project: str,
    azure_team: str,
    source: str = "xlsx",
    excel_path: str | None = None,
    camaleom_user: str = "",
    camaleom_pass: str = "",
    log=lambda m: None,
) -> dict[str, Any]:
    if not AZURE_DEVOPS_PAT:
        raise RuntimeError("El servidor no tiene AZURE_DEVOPS_PAT configurado.")

    log("Conectando a Azure DevOps...")
    cliente = AzureDevOpsClient(azure_org, azure_project, azure_team, pat=AZURE_DEVOPS_PAT)

    sprints = [int(s.strip()) for s in str(sprints_txt or "").replace(" ", "").split(",") if s.strip()]
    if not sprints:
        log(f"Sin sprint indicado: detectando el sprint de la fecha {fecha_final}...")
        sprints = find_sprints_by_range(cliente, fecha_final, fecha_final)
        log(f"Sprint(s) detectado(s): {sprints or 'ninguno'}")
    if not sprints:
        raise RuntimeError("No encontre un sprint para esa fecha final. Indica el/los sprint(s) manualmente.")

    # El periodo va del INICIO del sprint hasta el fin real del sprint, recortado por la fecha final.
    starts, finishes = [], []
    sprint_ranges = []
    for s in sprints:
        try:
            ini, fin = sprint_bounds(cliente, s)
            if ini:
                starts.append(ini)
            if fin:
                finishes.append(fin)
            sprint_ranges.append({"sprint": s, "inicio": ini.isoformat() if ini else None, "fin": fin.isoformat() if fin else None})
            log(f"Sprint {s}: {ini} -> {fin}")
        except Exception as exc:
            log(f"No pude leer fechas del sprint {s}: {exc}")
    fecha_inicio = min(starts) if starts else fecha_final
    fin_sprint = max(finishes) if finishes else fecha_final
    fecha_fin = min(fin_sprint, fecha_final)  # fin efectivo = min(fin real del sprint, fecha limite)
    if fecha_fin < fecha_inicio:
        fecha_fin = fecha_inicio
    log(f"Periodo del analisis: {fecha_inicio} -> {fecha_fin} (fin real sprint {fin_sprint}, limite {fecha_final})")

    # Camaleom: por archivo subido o intento automatico por navegador
    if source == "camaleom":
        excel_path = descargar_camaleom_subproceso(camaleom_user, camaleom_pass, fecha_inicio, fecha_fin, log=log)
        log("Excel de Camaleom descargado automaticamente.")
    if not excel_path:
        raise RuntimeError("No hay Excel de Camaleom (sube el archivo o usa el modo automatico).")

    log("Leyendo y filtrando el Excel de Camaleom...")
    datos_camaleom, meta = leer_reporte_camaleom(Path(excel_path), fecha_inicio, fecha_fin)
    resumen_dia, detalle, total_por_descripcion = construir_resumen_camaleom(
        datos_camaleom, meta, fecha_inicio, fecha_fin, HORAS_DIA, incluir_fines_semana=False
    )

    # Azure
    diff = diferenciador.strip() or None
    dfs = []
    for sprint in sprints:
        log(f"Consultando Azure sprint {sprint}...")
        df_sprint, _ = cliente.descargar_sprint(sprint, solo_mias=False, assigned_to_name=diff)
        dfs.append(df_sprint)
    azure_df = pd.concat(dfs, ignore_index=True) if dfs else pd.DataFrame()
    if not azure_df.empty:
        azure_df = azure_df.drop_duplicates(subset=["AzureID"]).reset_index(drop=True)

    log("Cruzando Azure vs Camaleom...")
    comparativo, resumen_hu = cruzar_azure_camaleom(azure_df, total_por_descripcion)

    metrics = compute(azure_df, comparativo, resumen_dia, total_por_descripcion)

    solo_tasks = comparativo[comparativo["Tipo"].apply(es_task_azure)] if not comparativo.empty else comparativo
    tareas_cols = ["AzureID", "HU", "Titulo Azure", "Estado Azure", "Original Estimate Azure",
                   "Completed Work Azure", "Horas Camaleom", "Diferencia Camaleom vs Completed",
                   "Match Score", "Veces reportada", "Fechas reales", "Estado reporte"]

    reportadas = solo_tasks[solo_tasks["Estado reporte"] == "Reportada"] if not comparativo.empty else comparativo
    sin_reportar = solo_tasks[solo_tasks["Estado reporte"] == "Falta reportar"] if not comparativo.empty else comparativo
    solo_camaleom = comparativo[comparativo["Estado reporte"] == "Solo Camaleom"] if not comparativo.empty else comparativo
    if not comparativo.empty:
        rev = solo_tasks[(solo_tasks["Descripcion Camaleom"].astype(str).str.len() > 0)
                         & (pd.to_numeric(solo_tasks["Match Score"], errors="coerce") < 0.6)]
    else:
        rev = comparativo

    azure_cols = ["AzureID", "Tipo", "Titulo", "Estado", "Original Estimate", "Remaining Work", "Completed Work", "Tags", "HU"]

    grafico = []
    if resumen_dia is not None and not resumen_dia.empty:
        for _, r in resumen_dia.iterrows():
            grafico.append({
                "fecha": str(r.get("FechaRealPruebasUnitarias", "")),
                "reportadas": round(_num(r.get("Horas reportadas")), 2),
                "esperadas": round(_num(r.get("Debe tener")), 2),
            })

    return {
        "meta": {
            "periodo_inicio": fecha_inicio.isoformat(),
            "periodo_fin": fecha_fin.isoformat(),
            "sprint_ranges": sprint_ranges,
            "sprints": sprints,
            "persona": diff or "Todos",
        },
        "metrics": metrics,
        "tables": {
            "horas_dia": _records(resumen_dia, ["FechaRealPruebasUnitarias", "Horas reportadas", "Debe tener", "Diferencia", "Estado"]),
            "azure_items": _records(azure_df, azure_cols),
            "tasks_reportadas": _records(reportadas, tareas_cols),
            "tasks_sin_reportar": _records(sin_reportar, tareas_cols),
            "camaleom_sin_coincidencia": _records(solo_camaleom, ["Descripcion Camaleom", "Horas Camaleom", "Veces reportada", "Reportes Camaleom", "Fechas reales"]),
            "revision_manual": _records(rev, tareas_cols + ["Descripcion Camaleom", "Match Tipo"]),
            "cruce": _records(solo_tasks, tareas_cols),
        },
        "grafico": grafico,
        "_xlsx": _build_xlsx(azure_df, comparativo, resumen_dia, total_por_descripcion),
    }
