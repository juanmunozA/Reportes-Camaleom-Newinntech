
from __future__ import annotations

import html
import re
from pathlib import Path
from typing import Any

import pandas as pd


def strip_html(value: Any) -> str:
    raw = "" if pd.isna(value) else str(value)
    raw = re.sub(r"<[^>]+>", " ", raw)
    raw = html.unescape(raw)
    return re.sub(r"\s+", " ", raw).strip()


def fmt_value(value: Any) -> str:
    if pd.isna(value):
        return ""
    if isinstance(value, float):
        return f"{value:.2f}".rstrip("0").rstrip(".")
    return strip_html(value)


def df_records(df: pd.DataFrame | None) -> list[dict[str, str]]:
    if df is None or df.empty:
        return []
    clean = df.copy()
    for col in clean.columns:
        clean[col] = clean[col].map(fmt_value)
    return clean.to_dict(orient="records")


def metric(label: str, value: Any, tone: str = "") -> str:
    return f'<div class="metric {tone}"><span>{html.escape(label)}</span><strong>{html.escape(fmt_value(value))}</strong></div>'


def table_view(view_id: str, title: str, df: pd.DataFrame | None, description: str = "") -> str:
    records = df_records(df)
    columns = list(df.columns) if df is not None and not df.empty else []
    if not records:
        body = '<div class="empty">Sin datos para esta vista.</div>'
    else:
        thead = "".join(f"<th>{html.escape(str(col))}</th>" for col in columns)
        rows = []
        for rec in records:
            cells = []
            for col in columns:
                value = rec.get(str(col), "")
                compact = value.replace(".", "", 1).replace("-", "", 1)
                cls = "num" if compact.isdigit() else ""
                cells.append(f'<td class="{cls}">{html.escape(value)}</td>')
            rows.append("<tr>" + "".join(cells) + "</tr>")
        body = '<div class="table-wrap"><table><thead><tr>' + thead + '</tr></thead><tbody>' + ''.join(rows) + '</tbody></table></div>'
    return f'''
    <section id="{view_id}" class="view">
      <div class="view-head">
        <div><h2>{html.escape(title)}</h2><p>{html.escape(description)}</p></div>
        <input class="search" type="search" placeholder="Buscar en esta vista" data-target="{view_id}">
      </div>
      {body}
    </section>
    '''


def limpiar_datos_camaleom(df: pd.DataFrame | None) -> pd.DataFrame | None:
    if df is None or df.empty:
        return df
    columnas_internas = ["HorasNum", "DescripcionLimpia", "DescripcionKey", "ReporteID"]
    return df.drop(columns=[col for col in columnas_internas if col in df.columns], errors="ignore")


def tone_for_diff(diff: float) -> str:
    return "ok" if abs(diff) < 0.01 else "bad"


def cruce_cards_view(df: pd.DataFrame | None) -> str:
    if df is None or df.empty:
        body = '<div class="empty">Sin datos para esta vista.</div>'
    else:
        cards = []
        for _, row in df.iterrows():
            estado = fmt_value(row.get("Estado reporte", ""))
            estado_class = "ok" if estado == "Reportada" else ("warn" if estado == "Solo Camaleom" else "bad")
            try:
                diff = float(row.get("Diferencia Camaleom vs Completed", 0) or 0)
            except Exception:
                diff = 0.0
            title = fmt_value(row.get("Titulo Azure", "")) or fmt_value(row.get("Descripcion Camaleom", "")) or "Sin titulo"
            azure_id = fmt_value(row.get("AzureID", "")) or "Camaleom"
            azure_desc = fmt_value(row.get("Descripcion Azure", "")) or title
            cam_desc = fmt_value(row.get("Descripcion Camaleom", "")) or "Sin match Camaleom"
            search_text = " ".join(fmt_value(row.get(col, "")) for col in df.columns).lower()
            status_key = estado.lower()
            has_diff = "1" if abs(diff) >= 0.01 else "0"
            cards.append(f'''
            <article class="match-card" data-search="{html.escape(search_text)}" data-status="{html.escape(status_key)}" data-diff="{has_diff}">
              <div class="card-main">
                <div class="card-title-row">
                  <span class="id">{html.escape(azure_id)}</span>
                  <h3>{html.escape(title)}</h3>
                  <span class="pill {estado_class}">{html.escape(estado)}</span>
                </div>
                <div class="subline">HU: {html.escape(fmt_value(row.get('HU', '')))}</div>
                <div class="compare-grid">
                  <section><h4>Azure</h4><p>{html.escape(azure_desc)}</p><div class="tags">{html.escape(fmt_value(row.get('Tags Azure', '')))}</div></section>
                  <section><h4>Camaleom</h4><p>{html.escape(cam_desc)}</p><div class="tags">Reportes: {html.escape(fmt_value(row.get('Reportes Camaleom', '')))} | Fechas: {html.escape(fmt_value(row.get('Fechas reales', '')))}</div></section>
                </div>
              </div>
              <aside class="card-metrics">
                <div><span>Completed</span><strong>{html.escape(fmt_value(row.get('Completed Work Azure', 0)))}</strong></div>
                <div><span>Camaleom</span><strong>{html.escape(fmt_value(row.get('Horas Camaleom', 0)))}</strong></div>
                <div class="{tone_for_diff(diff)}"><span>Diferencia</span><strong>{html.escape(fmt_value(diff))}</strong></div>
                <div><span>Similitud</span><strong>{html.escape(fmt_value(row.get('Match Score', 0)))}</strong></div>
              </aside>
            </article>
            ''')
        body = '<div class="cards-wrap">' + ''.join(cards) + '</div>'
    return f'''
    <section id="cruce" class="view">
      <div class="view-head">
        <div><h2>Cruce Azure Camaleom</h2><p>Lectura por task: Azure vs Camaleom, horas, diferencia y similitud por descripcion.</p></div>
        <div class="cruce-tools">
          <div class="filter-block">
            <span class="filter-label">Estado</span>
            <div class="filter-group status-filter" data-card-target="cruce">
              <button class="filter-btn active" type="button" data-status="">Todos</button>
              <button class="filter-btn" type="button" data-status="reportada">Reportada</button>
              <button class="filter-btn" type="button" data-status="falta reportar">Falta por reportar</button>
              <button class="filter-btn" type="button" data-status="solo camaleom">Solo Camaleom</button>
            </div>
          </div>
          <div class="filter-block">
            <span class="filter-label">Diferencia</span>
            <div class="filter-group diff-filter" data-card-target="cruce">
              <button class="filter-btn active" type="button" data-diff="">Todas</button>
              <button class="filter-btn" type="button" data-diff="1">Con diferencia</button>
              <button class="filter-btn" type="button" data-diff="0">Sin diferencia</button>
            </div>
          </div>
          <input class="search cards-search" type="search" placeholder="Buscar task, HU, estado o descripcion" data-card-target="cruce">
        </div>
      </div>
      {body}
    </section>
    '''


def build_dashboard(resumen_dia, total_por_descripcion, azure_df, comparativo, resumen_hu) -> str:
    horas_cam = float(total_por_descripcion["TotalHoras"].sum()) if total_por_descripcion is not None and "TotalHoras" in total_por_descripcion else 0.0
    completed = float(azure_df["Completed Work"].sum()) if azure_df is not None and not azure_df.empty and "Completed Work" in azure_df else 0.0
    diferencia = horas_cam - completed
    work_items = len(azure_df) if azure_df is not None else 0
    tasks_azure = 0
    if azure_df is not None and not azure_df.empty and "Tipo" in azure_df:
        tasks_azure = int((azure_df["Tipo"].astype(str).str.lower() == "task").sum())
    faltantes = 0
    solo_cam = 0
    match_prom = 0.0
    if comparativo is not None and not comparativo.empty:
        if "Estado reporte" in comparativo:
            faltantes = int((comparativo["Estado reporte"] == "Falta reportar").sum())
            solo_cam = int((comparativo["Estado reporte"] == "Solo Camaleom").sum())
        if "Match Score" in comparativo:
            scores = pd.to_numeric(comparativo["Match Score"], errors="coerce")
            positives = scores[scores > 0]
            match_prom = float(positives.mean()) if not positives.empty else 0.0
    return f'''
    <section id="dashboard" class="view active">
      <div class="hero"><div><h1>Reporte Camaleom vs Azure</h1><p>Comparativo de horas reportadas contra Completed Work por task, con similitud por descripcion.</p></div></div>
      <div class="metrics">
        {metric("Horas Camaleom", horas_cam)}{metric("Completed Work Azure", completed)}{metric("Diferencia", diferencia, "bad" if abs(diferencia) > 0.01 else "ok")}{metric("Tasks Azure", tasks_azure)}{metric("Work items Azure", work_items)}{metric("Faltan reportar", faltantes, "bad" if faltantes else "ok")}{metric("Solo Camaleom", solo_cam)}{metric("Similitud promedio", f"{match_prom:.2f}")}
      </div>
    </section>
    '''


def guardar_html_integrado(salida_html: Path, resumen_dia: pd.DataFrame, detalle_por_descripcion: pd.DataFrame, total_por_descripcion: pd.DataFrame, datos_camaleom: pd.DataFrame, azure_df: pd.DataFrame | None, comparativo: pd.DataFrame | None, resumen_hu: pd.DataFrame | None) -> None:
    tabs = [("dashboard", "Resumen"), ("cruce", "Cruce"), ("resumen-hu", "Por HU"), ("azure", "Azure"), ("camaleom-total", "Camaleom"), ("dia", "Por dia"), ("detalle", "Detalle")]
    nav = "".join(f'<button class="tab {"active" if i == 0 else ""}" data-view="{view}">{label}</button>' for i, (view, label) in enumerate(tabs))
    sections = [build_dashboard(resumen_dia, total_por_descripcion, azure_df, comparativo, resumen_hu), cruce_cards_view(comparativo), table_view("resumen-hu", "Resumen por HU", resumen_hu, "Totales agrupados por historia de usuario o parent."), table_view("azure", "Sprint Azure", azure_df, "Work items del sprint con Original Estimate, Remaining Work y Completed Work."), table_view("camaleom-total", "Total por descripcion Camaleom", total_por_descripcion, "Horas agregadas por descripcion reportada en Camaleom."), table_view("dia", "Resumen por dia", resumen_dia, "Validacion diaria de horas reportadas."), table_view("detalle", "Detalle descripcion fecha", detalle_por_descripcion, "Detalle por descripcion y fecha real.")]
    css = '''
    :root { color-scheme: light; --bg:#f6f7f9; --panel:#fff; --text:#1d232b; --muted:#68717d; --line:#dfe3e8; --brand:#1f7a4d; --bad:#b42318; --ok:#147a4d; }
    * { box-sizing: border-box; } body { margin:0; font-family: Segoe UI, Arial, sans-serif; background:var(--bg); color:var(--text); }
    header { position:sticky; top:0; z-index:5; background:var(--panel); border-bottom:1px solid var(--line); padding:12px 18px; display:flex; align-items:center; gap:16px; }
    .brand { font-weight:700; color:var(--brand); white-space:nowrap; } nav { display:flex; gap:6px; overflow:auto; }
    .tab { border:1px solid var(--line); background:#fff; padding:8px 12px; border-radius:6px; cursor:pointer; font-weight:600; color:#2d3640; } .tab.active { background:var(--brand); color:#fff; border-color:var(--brand); }
    main { padding:18px; } .view { display:none; } .view.active { display:block; }
    .hero { background:#e8f3ec; border:1px solid #cfe5d7; padding:18px 20px; border-radius:8px; margin-bottom:14px; } h1, h2 { margin:0 0 6px; letter-spacing:0; } p { margin:0; color:var(--muted); }
    .metrics { display:grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap:10px; margin-bottom:16px; } .metric { background:var(--panel); border:1px solid var(--line); border-radius:8px; padding:12px; } .metric span { display:block; color:var(--muted); font-size:12px; margin-bottom:6px; } .metric strong { font-size:24px; } .metric.bad strong { color:var(--bad); } .metric.ok strong { color:var(--ok); }
    .view-head { display:flex; justify-content:space-between; gap:12px; align-items:end; margin:0 0 12px; } .search { min-width:280px; padding:9px 10px; border:1px solid var(--line); border-radius:6px; background:#fff; } .cruce-tools { display:flex; align-items:end; justify-content:flex-end; gap:14px; flex-wrap:wrap; } .filter-block { display:flex; flex-direction:column; gap:5px; padding:8px 10px; border:1px solid var(--line); border-radius:8px; background:#f9fbfa; } .filter-label { color:var(--muted); font-size:11px; font-weight:800; text-transform:uppercase; letter-spacing:.04em; } .filter-group { display:flex; gap:6px; flex-wrap:wrap; } .filter-btn { border:1px solid var(--line); background:#fff; color:#394452; border-radius:999px; padding:8px 11px; cursor:pointer; font-weight:700; } .filter-btn.active { border-color:var(--brand); background:#e4f4eb; color:var(--brand); }
    .table-wrap { background:var(--panel); border:1px solid var(--line); border-radius:8px; overflow:auto; max-height: calc(100vh - 170px); } table { width:100%; border-collapse:separate; border-spacing:0; font-size:13px; } th, td { border-bottom:1px solid var(--line); padding:8px 10px; vertical-align:top; text-align:left; max-width:520px; } th { position:sticky; top:0; background:#f0f3f5; z-index:2; font-size:12px; color:#38424d; } tbody tr:hover { background:#f7fbf8; } td.num { text-align:right; white-space:nowrap; } .empty { background:var(--panel); border:1px solid var(--line); border-radius:8px; padding:22px; color:var(--muted); }
    .cards-wrap { display:grid; gap:12px; } .match-card { display:grid; grid-template-columns:minmax(0, 1fr) 220px; gap:14px; background:var(--panel); border:1px solid var(--line); border-radius:8px; padding:14px; } .card-title-row { display:flex; align-items:flex-start; gap:10px; } .card-title-row h3 { margin:0; font-size:16px; line-height:1.35; } .id { font-weight:700; color:var(--brand); white-space:nowrap; } .subline { color:var(--muted); font-size:12px; margin:5px 0 10px; } .pill { margin-left:auto; padding:4px 8px; border-radius:999px; font-size:12px; font-weight:700; white-space:nowrap; background:#eef1f4; } .pill.ok { color:#0f6b3d; background:#e4f4eb; } .pill.bad { color:#9f1d16; background:#fde8e6; } .pill.warn { color:#7a4b00; background:#fff3d6; }
    .compare-grid { display:grid; grid-template-columns:1fr 1fr; gap:12px; } .compare-grid section { border:1px solid var(--line); border-radius:8px; padding:10px; background:#fbfcfd; } .compare-grid h4 { margin:0 0 6px; font-size:12px; color:var(--muted); text-transform:uppercase; } .compare-grid p { color:var(--text); line-height:1.35; } .tags { margin-top:8px; font-size:12px; color:var(--muted); }
    .card-metrics { display:grid; grid-template-columns:1fr 1fr; gap:8px; align-content:start; } .card-metrics div { border:1px solid var(--line); border-radius:8px; padding:10px; background:#fff; } .card-metrics span, .card-metrics small { display:block; color:var(--muted); font-size:12px; } .card-metrics strong { display:block; font-size:22px; margin-top:3px; } .card-metrics .bad strong { color:var(--bad); } .card-metrics .ok strong { color:var(--ok); }
    @media (max-width: 900px) { .match-card { grid-template-columns:1fr; } .compare-grid { grid-template-columns:1fr; } } @media (max-width: 760px) { header { align-items:flex-start; flex-direction:column; } .view-head { align-items:stretch; flex-direction:column; } .search { min-width:0; width:100%; } .cruce-tools { justify-content:flex-start; } }
    '''
    js = '''
    document.querySelectorAll('.tab').forEach(btn => btn.addEventListener('click', () => { document.querySelectorAll('.tab').forEach(b => b.classList.remove('active')); document.querySelectorAll('.view').forEach(v => v.classList.remove('active')); btn.classList.add('active'); document.getElementById(btn.dataset.view).classList.add('active'); }));
    document.querySelectorAll('.search[data-target]').forEach(input => input.addEventListener('input', () => { const view = document.getElementById(input.dataset.target); const q = input.value.trim().toLowerCase(); view.querySelectorAll('tbody tr').forEach(row => { row.style.display = row.innerText.toLowerCase().includes(q) ? '' : 'none'; }); }));
    function applyCardFilters(viewId) { const view = document.getElementById(viewId); if (!view) return; const search = view.querySelector('.cards-search'); const statusBtn = view.querySelector('.status-filter .filter-btn.active'); const diffBtn = view.querySelector('.diff-filter .filter-btn.active'); const q = search ? search.value.trim().toLowerCase() : ''; const status = statusBtn ? statusBtn.dataset.status : ''; const diff = diffBtn ? diffBtn.dataset.diff : ''; view.querySelectorAll('.match-card').forEach(card => { const okText = !q || card.dataset.search.includes(q); const okStatus = !status || card.dataset.status === status; const okDiff = !diff || card.dataset.diff === diff; card.style.display = okText && okStatus && okDiff ? '' : 'none'; }); }
    document.querySelectorAll('.cards-search').forEach(input => input.addEventListener('input', () => applyCardFilters(input.dataset.cardTarget)));
    document.querySelectorAll('.filter-group').forEach(group => group.addEventListener('click', event => { const btn = event.target.closest('.filter-btn'); if (!btn) return; group.querySelectorAll('.filter-btn').forEach(b => b.classList.remove('active')); btn.classList.add('active'); applyCardFilters(group.dataset.cardTarget); }));
    '''
    doc = f'''<!doctype html><html lang="es"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>Reporte Camaleom vs Azure</title><style>{css}</style></head><body><header><div class="brand">Camaleom + Azure</div><nav>{nav}</nav></header><main>{''.join(sections)}</main><script>{js}</script></body></html>'''
    salida_html.parent.mkdir(parents=True, exist_ok=True)
    salida_html.write_text(doc, encoding="utf-8")
