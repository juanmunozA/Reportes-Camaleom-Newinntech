"""Descarga aislada del Excel de Camaleom (se ejecuta en subproceso).

Corre en su propio proceso para que si Chromium falla o se queda sin memoria
no afecte al servidor web. Lee credenciales y fechas de variables de entorno e
imprime la ruta descargada como 'PATHRESULT::<ruta>'.
"""
from __future__ import annotations

import os
import sys
from datetime import date

from selenium.webdriver.common.by import By

from ..browser import crear_driver
from ..camaleom import descargar_reporte_camaleom, login_camaleom

_ERROR_SELECTORS = [
    "#passwordError", "#usernameError", "#i0118Error", "#i0116Error",
    ".alert-error", ".error", "[role='alert']", ".field-validation-error",
]
_ERROR_HINTS = ["incorrect", "incorrecta", "incorrecto", "invalid", "inválid",
                "no coincide", "no es correcta", "verifica", "wrong", "does not match"]


def _leer_error_login(driver) -> str:
    for sel in _ERROR_SELECTORS:
        try:
            for el in driver.find_elements(By.CSS_SELECTOR, sel):
                txt = (el.text or "").strip()
                if txt:
                    return txt[:200]
        except Exception:
            pass
    try:
        cuerpo = (driver.find_element(By.TAG_NAME, "body").text or "").lower()
        for hint in _ERROR_HINTS:
            if hint in cuerpo:
                return "La pagina de Camaleom/Microsoft reporto un problema con las credenciales."
    except Exception:
        pass
    return ""


def main() -> int:
    user = os.environ.get("CAM_USER", "")
    password = os.environ.get("CAM_PASS", "")
    url = os.environ.get("CAM_URL") or None
    fecha_inicio = date.fromisoformat(os.environ["CAM_FI"])
    fecha_fin = date.fromisoformat(os.environ["CAM_FF"])
    formato = os.environ.get("CAM_FMT", "%d/%m/%Y")

    driver = crear_driver()
    try:
        login_camaleom(driver, user=user, password=password, url=url)
        url_actual = (driver.current_url or "").lower()
        if any(x in url_actual for x in ["login", "signin", "microsoftonline", "sso"]):
            motivo = _leer_error_login(driver)
            if motivo:
                print(f"LOGINFAIL::Credenciales de Camaleom incorrectas: {motivo}", flush=True)
            else:
                print("LOGINFAIL::No se pudo iniciar sesion en Camaleom. Puede ser contrasena incorrecta o que requiere aprobar MFA/Authenticator (no se puede en el servidor). Usa el modo Archivo XLSX.", flush=True)
            return 3
        ruta = descargar_reporte_camaleom(driver, fecha_inicio, fecha_fin, formato)
        print(f"PATHRESULT::{ruta}", flush=True)
        return 0
    finally:
        try:
            driver.quit()
        except Exception:
            pass


if __name__ == "__main__":
    sys.exit(main())
