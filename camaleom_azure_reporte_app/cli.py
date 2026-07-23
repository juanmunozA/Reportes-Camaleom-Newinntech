from __future__ import annotations

import argparse
import sys
from datetime import date, timedelta
from pathlib import Path

import pandas as pd

from .azure_devops import crear_cliente_azure
from .camaleom import descargar_reporte_camaleom, login_camaleom
from .camaleom_excel import construir_resumen_camaleom, leer_reporte_camaleom
from .config import *
from .dates import parse_fecha
from .matcher import cruzar_azure_camaleom
from .reporting import guardar_excel_integrado, imprimir_resumen
from .selenium_utils import crear_driver


def configurar_consola() -> None:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


def rango_meses_completos(fecha_inicio: date, fecha_fin: date) -> tuple[date, date]:
    inicio_mes = fecha_inicio.replace(day=1)
    if fecha_fin.month == 12:
        siguiente_mes = date(fecha_fin.year + 1, 1, 1)
    else:
        siguiente_mes = date(fecha_fin.year, fecha_fin.month + 1, 1)
    fin_mes = siguiente_mes - timedelta(days=1)
    return inicio_mes, fin_mes


def main():
    configurar_consola()
    parser = argparse.ArgumentParser(description="Descarga reporte Camaleom, descarga sprint Azure DevOps y cruza horas por task/HU.")
    parser.add_argument("--sprint", type=str, default=str(DEFAULT_AZURE_SPRINT), help="Numero(s) de sprint de Azure DevOps, separados por coma (ej: 278,279). Tambien puedes usar AZURE_SPRINT. Default: 279")
    parser.add_argument("--fecha-inicio", type=str, help="Fecha inicio yyyy-mm-dd o dd/mm/yyyy. Default: 2026-07-14.")
    parser.add_argument("--fecha-fin", type=str, help="Fecha fin yyyy-mm-dd o dd/mm/yyyy. Default: 2026-07-17.")
    parser.add_argument("--camaleom-creacion-inicio", type=str, help="Fecha inicial para exportar Camaleom por fecha de creacion. Default: primer dia del mes de --fecha-inicio.")
    parser.add_argument("--camaleom-creacion-fin", type=str, help="Fecha final para exportar Camaleom por fecha de creacion. Default: ultimo dia del mes de --fecha-fin.")
    parser.add_argument("--camaleom-excel", type=str, help="Usar un Excel ya descargado de Camaleom en vez de entrar al aplicativo.")
    parser.add_argument("--solo-camaleom", action="store_true", help="Solo analiza Camaleom, no descarga Azure DevOps.")
    parser.add_argument("--solo-azure", action="store_true", help="Solo descarga Azure DevOps, no analiza Camaleom.")
    parser.add_argument("--azure-todos", action="store_true", help="Trae todo el sprint, no solo los work items asignados a @Me.")
    parser.add_argument("--sin-browser-azure", action="store_true", help="No usar navegador para Azure. Requiere AZURE_DEVOPS_PAT.")
    parser.add_argument("--formato-fecha-camaleom", default=os.getenv("CAMALEOM_DATE_FORMAT", "%d/%m/%Y"), help="Formato para fechas en Camaleom. Ej: %%Y-%%m-%%d o %%d/%%m/%%Y")
    parser.add_argument("--horas-dia", type=float, default=float(os.getenv("HORAS_DIA", "8")), help="Horas esperadas por dÃ­a.")
    parser.add_argument("--incluir-fines-semana", action="store_true", help="Incluye sÃ¡bado y domingo en validaciÃ³n de 8 horas.")
    args = parser.parse_args()

    fecha_inicio = parse_fecha(args.fecha_inicio) or DEFAULT_FECHA_INICIO
    fecha_fin = parse_fecha(args.fecha_fin) or DEFAULT_FECHA_FIN
    camaleom_mes_inicio, camaleom_mes_fin = rango_meses_completos(fecha_inicio, fecha_fin)
    camaleom_creacion_inicio = parse_fecha(args.camaleom_creacion_inicio) or camaleom_mes_inicio
    camaleom_creacion_fin = parse_fecha(args.camaleom_creacion_fin) or camaleom_mes_fin

    driver = None
    azure_df = None
    comparativo = None
    resumen_hu = None
    resumen_dia = pd.DataFrame()
    detalle_por_descripcion = pd.DataFrame()
    total_por_descripcion = pd.DataFrame()
    datos_camaleom = pd.DataFrame()

    try:
        if not args.solo_azure:
            if args.camaleom_excel:
                reporte_camaleom = Path(args.camaleom_excel).resolve()
                if not reporte_camaleom.exists():
                    raise FileNotFoundError(reporte_camaleom)
            else:
                driver = crear_driver()
                login_camaleom(driver)
                if camaleom_creacion_inicio != fecha_inicio or camaleom_creacion_fin != fecha_fin:
                    print(
                        "Camaleom se exporta por fecha de creacion "
                        f"{camaleom_creacion_inicio} a {camaleom_creacion_fin}; "
                        f"el analisis se filtra por fecha real {fecha_inicio} a {fecha_fin}."
                    )
                reporte_camaleom = descargar_reporte_camaleom(
                    driver,
                    camaleom_creacion_inicio,
                    camaleom_creacion_fin,
                    args.formato_fecha_camaleom,
                )
                print(f"Reporte Camaleom descargado: {reporte_camaleom}")

            datos_camaleom, meta = leer_reporte_camaleom(reporte_camaleom, fecha_inicio, fecha_fin)
            resumen_dia, detalle_por_descripcion, total_por_descripcion = construir_resumen_camaleom(
                datos_camaleom,
                meta,
                fecha_inicio,
                fecha_fin,
                args.horas_dia,
                args.incluir_fines_semana,
            )

        if not args.solo_camaleom:
            sprints = [int(s.strip()) for s in str(args.sprint).split(",") if s.strip()]
            if not sprints:
                raise RuntimeError("Para descargar Azure DevOps debes enviar --sprint. Ejemplo: --sprint 278 o --sprint 278,279")
            if driver is None and not (AZURE_DEVOPS_PAT and args.sin_browser_azure):
                driver = crear_driver()
            cliente = crear_cliente_azure(driver, usar_browser=not args.sin_browser_azure)
            assigned_to_name = None if args.azure_todos else AZURE_ASSIGNED_TO_NAME
            dfs = []
            iteraciones = []
            for sprint in sprints:
                df_sprint, iteracion = cliente.descargar_sprint(
                    sprint,
                    solo_mias=False,
                    assigned_to_name=assigned_to_name,
                )
                print(f"Sprint {sprint} descargado: {iteracion.get('path', '')}")
                dfs.append(df_sprint)
                iteraciones.append(iteracion)
            azure_df = pd.concat(dfs, ignore_index=True) if dfs else pd.DataFrame()
            if assigned_to_name:
                print(f"Filtro asignado Azure: {assigned_to_name}")

            if not args.solo_azure and not total_por_descripcion.empty:
                comparativo, resumen_hu = cruzar_azure_camaleom(azure_df, total_por_descripcion)

    finally:
        if driver is not None:
            driver.quit()

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    nombre = f"reporte_integrado_{fecha_inicio}_a_{fecha_fin}"
    if args.sprint:
        nombre += f"_sprint_{str(args.sprint).replace(',', '-')}"
    salida = OUT_DIR / f"{nombre}.xlsx"
    guardar_excel_integrado(
        salida,
        resumen_dia,
        detalle_por_descripcion,
        total_por_descripcion,
        datos_camaleom,
        azure_df,
        comparativo,
        resumen_hu,
    )

    imprimir_resumen(fecha_inicio, fecha_fin, resumen_dia, total_por_descripcion, azure_df, comparativo, resumen_hu)
    print(f"\nArchivo generado: {salida}")


def run() -> None:
    try:
        main()
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)
