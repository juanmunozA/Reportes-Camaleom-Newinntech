from __future__ import annotations

import time
from datetime import date
from pathlib import Path

from selenium import webdriver
from selenium.common.exceptions import StaleElementReferenceException, TimeoutException
from selenium.webdriver.common.keys import Keys

from .config import *
from .selenium_utils import *

def login_camaleom(driver: webdriver.Chrome):
    if not CAMALEOM_USER or not CAMALEOM_PASS:
        raise RuntimeError("Faltan variables de entorno CAMALEOM_USER y/o CAMALEOM_PASS")

    driver.get(CAMALEOM_URL)
    time.sleep(0.8)

    # Si Camaleom redirige a Microsoft, esto tambiÃ©n funciona con los ids i0116/i0118.
    try:
        usuario = elemento_visible_por_css(driver, SELECTORES_CAMALEOM["usuario"], segundos=0.8)
        escribir_texto_login(driver, usuario, CAMALEOM_USER)
        if not click_boton_login(driver, TEXTOS_CAMALEOM["siguiente"], segundos=1.2):
            click_css_si_existe(driver, SELECTORES_CAMALEOM["submit"], segundos=0.8)
        usuario.send_keys(Keys.ENTER)
        time.sleep(0.6)
    except TimeoutException:
        return

    try:
        password = elemento_password_login(driver, segundos=8)
        escribir_texto_login(driver, password, CAMALEOM_PASS, es_password=True)
        time.sleep(0.4)
        try:
            valor_password = password.get_attribute("value") or ""
        except StaleElementReferenceException:
            valor_password = CAMALEOM_PASS
        if len(valor_password) < len(CAMALEOM_PASS):
            print("No pude escribir la contraseña automáticamente. Escríbela en el navegador y pulsa Siguiente. Continúo apenas detecte el home...")
            esperar_salida_login(driver, segundos=120)
            return
        if not click_boton_login_fisico(driver, TEXTOS_CAMALEOM["siguiente"], segundos=1.0):
            click_boton_login(driver, TEXTOS_CAMALEOM["siguiente"], segundos=0.8)
        if not esperar_salida_login(driver, segundos=4):
            try:
                password.send_keys(Keys.ENTER)
            except StaleElementReferenceException:
                driver.switch_to.active_element.send_keys(Keys.ENTER)
            esperar_salida_login(driver, segundos=120)
    except TimeoutException:
        pass

    click_css_si_existe(driver, ["#idBtn_Back", "#idSIButton9"], segundos=1.2)

    if any(x in driver.current_url.lower() for x in ["microsoftonline", "login", "signin"]):
        print("Si aparece MFA/Authenticator para Camaleom, apruÃ©balo. Espero hasta 90 segundos...")
        time.sleep(90)

def esperar_descarga(antes: set[Path], timeout: int = 120) -> Path:
    limite = time.time() + timeout
    while time.time() < limite:
        archivos = set(DOWNLOAD_DIR.glob("*"))
        nuevos = [a for a in archivos - antes if a.suffix.lower() in [".xlsx", ".xls", ".csv"]]
        incompletos = list(DOWNLOAD_DIR.glob("*.crdownload"))
        if nuevos and not incompletos:
            return max(nuevos, key=lambda p: p.stat().st_mtime)
        time.sleep(0.2)
    raise TimeoutException("No se descargÃ³ ningÃºn Excel/CSV dentro del tiempo esperado")

def descargar_reporte_camaleom(driver: webdriver.Chrome, fecha_inicio: date, fecha_fin: date, formato_fecha: str) -> Path:
    antes = set(DOWNLOAD_DIR.glob("*"))

    esperar_salida_login(driver, segundos=8)
    if not campos_fecha_visibles(driver):
        print("Agente navegando en tiempo real a Reportes > Generar Reporte mis Actividades...")
        abrir_reporte_actividades_realtime(driver, segundos=18)

    if not campos_fecha_visibles(driver):
        print("No pude abrir el reporte automaticamente. En el navegador entra a Reportes > Mis Actividades. Continuo apenas vea los campos de fecha...")
        if not esperar_formulario_reporte_camaleom(driver, segundos=180):
            raise RuntimeError("No detecte los campos de fecha de Camaleom. Abre manualmente Reportes > Mis Actividades y vuelve a ejecutar.")

    fecha_desde, fecha_hasta = inputs_fecha_camaleom(driver)
    escribir_fecha_elemento(driver, fecha_desde, fecha_inicio, formato_fecha)
    escribir_fecha_elemento(driver, fecha_hasta, fecha_fin, formato_fecha)

    if not fechas_camaleom_ok(driver, fecha_inicio, fecha_fin):
        raise RuntimeError("Las fechas no quedaron escritas en Camaleom; no exporto para evitar descarga vacia.")

    if not click_exportar_actividades_realtime(driver, segundos=1.5):
        raise RuntimeError("No pude hacer click en Exportar Actividades.")

    return esperar_descarga(antes)
