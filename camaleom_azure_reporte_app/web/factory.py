from __future__ import annotations

import copy
import re
from typing import Any


def hu_id(hu: Any) -> str:
    m = re.match(r"\s*(\d+)", str(hu or ""))
    return m.group(1) if m else str(hu or "").strip()


def _num(v: Any) -> float:
    try:
        return float(v or 0)
    except (TypeError, ValueError):
        return 0.0


def build_hu_list(data: dict[str, Any]) -> list[dict[str, Any]]:
    """Lista de HUs del reporte con conteo de tasks y horas estimadas."""
    tables = data.get("tables", {})
    rows = tables.get("cruce", []) or []
    hus: dict[str, dict[str, Any]] = {}
    for t in rows:
        hu = t.get("HU", "")
        hid = hu_id(hu)
        if not hid:
            continue
        e = hus.setdefault(hid, {"id": hid, "hu": hu, "tasks": 0, "estimadas": 0.0, "sprint": t.get("Sprint", "")})
        e["tasks"] += 1
        e["estimadas"] += _num(t.get("Original Estimate Azure"))
    for e in hus.values():
        e["estimadas"] = round(e["estimadas"], 1)
    return sorted(hus.values(), key=lambda x: x["id"])


def apply(data: dict[str, Any], factory_ids: list[str] | None) -> dict[str, Any]:
    """Marca las tasks de HUs fabrica, las excluye del pendiente y recalcula metricas."""
    d = copy.deepcopy(data)
    fset = {str(x) for x in (factory_ids or [])}
    if not fset:
        # Sin fabricas: no ensuciar con columna "Fábrica"; solo aportar la lista de HUs.
        d["hu_list"] = build_hu_list(data)
        d["factory"] = []
        return d
    tables = d.get("tables", {})

    def marcar(rows):
        for t in rows:
            t["Fábrica"] = "Sí" if hu_id(t.get("HU", "")) in fset else ""
        return rows

    for k in ("cruce", "tasks_reportadas", "tasks_sin_reportar", "azure_items", "revision_manual"):
        if k in tables and tables[k]:
            tables[k] = marcar(tables[k])

    # Las tasks de fabrica no son tuyas: se sacan de "sin reportar".
    if tables.get("tasks_sin_reportar"):
        tables["tasks_sin_reportar"] = [t for t in tables["tasks_sin_reportar"] if t.get("Fábrica") != "Sí"]

    # Recalcula metricas afectadas excluyendo fabrica.
    m = d.get("metrics", {})
    cruce = tables.get("cruce", []) or []
    sin_rep = parcial = excedida = reportada = pend = fab = completas = 0
    horas_falt = 0.0
    tasks_no_fab = 0
    for t in cruce:
        if t.get("Fábrica") == "Sí":
            fab += 1
            continue
        tasks_no_fab += 1
        est = _num(t.get("Original Estimate Azure"))
        comp = _num(t.get("Completed Work Azure"))
        bench = comp if comp > 0 else est
        rep = _num(t.get("Horas Camaleom"))
        estado = t.get("Estado reporte")
        if estado == "Falta reportar":
            sin_rep += 1
        elif estado == "Parcial":
            parcial += 1
        elif estado == "Excedida":
            excedida += 1
        elif estado == "Reportada":
            reportada += 1
        if bench > 0 and rep >= bench:
            completas += 1
        if bench > rep:
            pend += 1
            horas_falt += bench - rep

    m["tasks_sin_reportar"] = sin_rep
    m["tasks_parciales"] = parcial
    m["tasks_excedidas"] = excedida
    m["tasks_reportadas"] = reportada
    m["tasks_pendientes_horas"] = pend
    m["total_horas_faltantes"] = round(horas_falt, 1)
    m["tasks_fabrica"] = fab
    if tasks_no_fab:
        m["cobertura_horas"] = round(100.0 * completas / tasks_no_fab, 1)

    # --- Descontar las horas de fabrica de "Horas por dia", grafico y total reportado ---
    registros = data.get("registros_hu", []) or []
    por_dia: dict[str, float] = {}
    total_fab = 0.0
    if registros:
        for r in registros:
            if hu_id(r.get("hu", "")) in fset:
                f = str(r.get("fecha", ""))
                h = _num(r.get("horas"))
                por_dia[f] = por_dia.get(f, 0.0) + h
                total_fab += h
    else:
        # Reporte viejo sin detalle por dia: al menos descontamos del total global.
        for t in cruce:
            if t.get("Fábrica") == "Sí":
                total_fab += _num(t.get("Horas Camaleom"))

    for row in tables.get("horas_dia", []) or []:
        q = por_dia.get(str(row.get("FechaRealPruebasUnitarias", "")), 0.0)
        if q:
            rep = max(_num(row.get("Horas reportadas")) - q, 0.0)
            debe = _num(row.get("Debe tener"))
            diff = round(rep - debe, 2)
            row["Horas reportadas"] = round(rep, 2)
            row["Diferencia"] = diff
            row["Estado"] = "OK" if abs(diff) < 0.01 else (("Falta %.1f" % abs(diff)) if diff < 0 else ("Sobra %.1f" % diff))

    for g in d.get("grafico", []) or []:
        q = por_dia.get(str(g.get("fecha", "")), 0.0)
        if q:
            g["reportadas"] = round(max(_num(g.get("reportadas")) - q, 0.0), 2)

    if total_fab:
        m["total_reportado"] = round(_num(m.get("total_reportado")) - total_fab, 1)
        m["balance"] = round(_num(m.get("total_reportado")) - _num(m.get("total_esperado")), 1)

    d["hu_list"] = build_hu_list(data)
    d["factory"] = sorted(fset)
    return d
