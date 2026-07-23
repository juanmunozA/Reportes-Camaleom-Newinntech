from __future__ import annotations

from datetime import date, datetime, timedelta

def semana_martes_lunes(hoy: date | None = None) -> tuple[date, date]:
    """Devuelve el periodo martes-lunes de la semana de reporte.

    Si hoy es lunes, devuelve martes anterior hasta ese lunes.
    Si hoy es martes-domingo, devuelve ese martes hasta el prÃ³ximo lunes.
    """
    hoy = hoy or date.today()
    dias_hasta_lunes = (0 - hoy.weekday()) % 7
    fecha_fin = hoy + timedelta(days=dias_hasta_lunes)
    fecha_inicio = fecha_fin - timedelta(days=6)
    return fecha_inicio, fecha_fin

def parse_fecha(valor: str | None) -> date | None:
    if not valor:
        return None
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y"):
        try:
            return datetime.strptime(valor, fmt).date()
        except ValueError:
            pass
    raise ValueError(f"Fecha invÃ¡lida: {valor}. Usa yyyy-mm-dd o dd/mm/yyyy")
