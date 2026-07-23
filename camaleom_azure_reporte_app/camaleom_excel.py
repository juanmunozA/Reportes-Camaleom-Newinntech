from __future__ import annotations

import re
import tempfile
import zipfile
from datetime import date
from pathlib import Path
from typing import Any

import pandas as pd

from .selenium_utils import normalizar_texto

def normalizar_columnas(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df.columns = [str(c).strip() for c in df.columns]
    return df

def convertir_horas(valor: Any) -> float:
    if pd.isna(valor):
        return 0.0
    if isinstance(valor, (int, float)):
        return float(valor)
    texto = str(valor).strip()
    if not texto:
        return 0.0
    if "," in texto:
        texto = texto.replace(".", "").replace(",", ".")
    texto = re.sub(r"[^0-9.\-]", "", texto)
    try:
        return float(texto)
    except ValueError:
        return 0.0

def escoger_columna(df: pd.DataFrame, opciones: list[str], obligatoria: bool = True) -> str | None:
    def norm_col(c: str) -> str:
        return normalizar_texto(c).replace(" ", "")

    cols_norm = {norm_col(c): c for c in df.columns}
    for opcion in opciones:
        key = norm_col(opcion)
        if key in cols_norm:
            return cols_norm[key]
    if obligatoria:
        raise RuntimeError(f"No encontrÃ© ninguna columna entre estas opciones: {opciones}. Columnas: {list(df.columns)}")
    return None

def _xlsx_reparado_para_openpyxl(ruta: Path) -> Path:
    """Crea una copia temporal del XLSX corrigiendo atributos float vacios."""
    temp_file = tempfile.NamedTemporaryFile(prefix="camaleom_reparado_", suffix=".xlsx", delete=False)
    temp = Path(temp_file.name)
    temp_file.close()

    atributos_float = ("left", "right", "top", "bottom", "header", "footer")
    patron = re.compile(r'\b(' + "|".join(atributos_float) + r')=""')

    with zipfile.ZipFile(ruta, "r") as zin, zipfile.ZipFile(temp, "w", compression=zipfile.ZIP_DEFLATED) as zout:
        for info in zin.infolist():
            data = zin.read(info.filename)
            if info.filename.startswith("xl/worksheets/") and info.filename.endswith(".xml"):
                xml = data.decode("utf-8", errors="replace")
                xml = patron.sub(lambda match: f'{match.group(1)}="0"', xml)
                data = xml.encode("utf-8")
            zout.writestr(info, data)
    return temp


def leer_excel_tolerante(ruta: Path) -> pd.DataFrame:
    try:
        return pd.read_excel(ruta)
    except TypeError as exc:
        if "expected <class 'float'>" not in str(exc):
            raise
        reparado = _xlsx_reparado_para_openpyxl(ruta)
        try:
            print(f"Excel Camaleom reparado temporalmente para lectura: {reparado}")
            return pd.read_excel(reparado)
        finally:
            try:
                reparado.unlink()
            except FileNotFoundError:
                pass


def leer_reporte_camaleom(ruta: Path, fecha_inicio: date, fecha_fin: date) -> tuple[pd.DataFrame, dict[str, str | None]]:
    if ruta.suffix.lower() == ".csv":
        df = pd.read_csv(ruta, sep=None, engine="python")
    else:
        df = leer_excel_tolerante(ruta)

    df = normalizar_columnas(df)
    col_fecha = escoger_columna(df, ["FechaRealPruebasUnitarias", "Fecha Real Pruebas Unitarias"])
    col_horas = escoger_columna(df, ["TiempoReal", "Tiempo Real", "Horas", "Horas reales"])
    col_desc = escoger_columna(df, ["Descripcion", "DescripciÃ³n", "Actividad"], obligatoria=False)
    col_id = escoger_columna(df, ["id", "ID", "Id"], obligatoria=False)

    if not col_desc:
        raise RuntimeError("No encontrÃ© columna Descripcion/DescripciÃ³n/Actividad para agrupar por task.")

    fechas_parseadas = pd.to_datetime(df[col_fecha], errors="coerce", format="%Y-%m-%d")
    if fechas_parseadas.isna().all():
        fechas_parseadas = pd.to_datetime(df[col_fecha], errors="coerce", dayfirst=True)
    df[col_fecha] = fechas_parseadas.dt.date
    df["HorasNum"] = df[col_horas].apply(convertir_horas)
    df = df[df[col_fecha].between(fecha_inicio, fecha_fin)].copy()
    df["DescripcionLimpia"] = df[col_desc].fillna("SIN DESCRIPCIÃ“N").astype(str).str.strip()
    df["DescripcionKey"] = df["DescripcionLimpia"].apply(normalizar_texto)
    df["ReporteID"] = df[col_id].astype(str) if col_id else ""

    meta = {
        "col_fecha": col_fecha,
        "col_horas": col_horas,
        "col_desc": col_desc,
        "col_id": col_id,
    }
    return df, meta

def construir_resumen_camaleom(df: pd.DataFrame, meta: dict[str, str | None], fecha_inicio: date, fecha_fin: date, horas_dia: float, incluir_fines_semana: bool):
    col_fecha = meta["col_fecha"]

    resumen_dia = (
        df.groupby(col_fecha, dropna=False)["HorasNum"]
        .sum()
        .reset_index()
        .rename(columns={col_fecha: "FechaRealPruebasUnitarias", "HorasNum": "Horas reportadas"})
    )

    fechas = pd.date_range(fecha_inicio, fecha_fin).date
    if not incluir_fines_semana:
        fechas = [f for f in fechas if f.weekday() < 5]
    fechas_periodo = pd.DataFrame({"FechaRealPruebasUnitarias": fechas})

    resumen_dia = fechas_periodo.merge(resumen_dia, how="left", on="FechaRealPruebasUnitarias")
    resumen_dia["Horas reportadas"] = resumen_dia["Horas reportadas"].fillna(0)
    resumen_dia["Debe tener"] = horas_dia
    resumen_dia["Diferencia"] = resumen_dia["Horas reportadas"] - resumen_dia["Debe tener"]
    resumen_dia["Estado"] = resumen_dia["Diferencia"].apply(
        lambda x: "OK" if abs(x) < 0.01 else (f"Falta {abs(x):.1f}" if x < 0 else f"Sobra {x:.1f}")
    )

    detalle_por_descripcion = (
        df.groupby(["DescripcionLimpia", col_fecha], dropna=False)
        .agg(
            Horas=("HorasNum", "sum"),
            Reportes=("ReporteID", lambda s: ", ".join(sorted({x for x in s.astype(str) if x and x.lower() != "nan"}))),
        )
        .reset_index()
        .rename(columns={col_fecha: "FechaRealPruebasUnitarias"})
        .sort_values(["FechaRealPruebasUnitarias", "DescripcionLimpia"])
    )

    total_por_descripcion = (
        df.groupby("DescripcionLimpia", dropna=False)
        .agg(
            TotalHoras=("HorasNum", "sum"),
            VecesReportada=("ReporteID", "count"),
            Reportes=("ReporteID", lambda s: ", ".join(sorted({x for x in s.astype(str) if x and x.lower() != "nan"}))),
            Fechas=(col_fecha, lambda s: ", ".join(str(x) for x in sorted({x for x in s if pd.notna(x)}))),
        )
        .reset_index()
        .sort_values("DescripcionLimpia")
    )

    return resumen_dia, detalle_por_descripcion, total_por_descripcion
