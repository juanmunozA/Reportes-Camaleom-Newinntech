from __future__ import annotations

import os
from datetime import date

from selenium import webdriver
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

from .config import DOWNLOAD_DIR, HEADLESS
from .text_utils import normalizar_texto

def crear_driver() -> webdriver.Chrome:
    DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)

    options = Options()
    if HEADLESS:
        options.add_argument("--headless=new")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--disable-gpu")
        options.add_argument("--window-size=1920,1080")
    else:
        options.add_argument("--start-maximized")
    options.add_argument("--disable-notifications")
    chrome_bin = os.getenv("CHROME_BIN")
    if chrome_bin:
        options.binary_location = chrome_bin
    options.add_experimental_option(
        "prefs",
        {
            "download.default_directory": str(DOWNLOAD_DIR),
            "download.prompt_for_download": False,
            "download.directory_upgrade": True,
            "safebrowsing.enabled": True,
        },
    )
    chromedriver_path = os.getenv("CHROMEDRIVER_PATH")
    service = Service(executable_path=chromedriver_path) if chromedriver_path else Service()
    return webdriver.Chrome(options=options, service=service)

def wait(driver: webdriver.Chrome, segundos: int = 20) -> WebDriverWait:
    return WebDriverWait(driver, segundos)

def elemento_visible_por_css(driver: webdriver.Chrome, selectores: list[str], segundos: int = 12):
    ultimo_error = None
    for selector in selectores:
        try:
            return wait(driver, segundos).until(EC.visibility_of_element_located((By.CSS_SELECTOR, selector)))
        except Exception as exc:
            ultimo_error = exc
    raise TimeoutException(f"No encontrÃ© elemento con selectores: {selectores}") from ultimo_error

def click_css_si_existe(driver: webdriver.Chrome, selectores: list[str], segundos: int = 5) -> bool:
    for selector in selectores:
        try:
            el = wait(driver, segundos).until(EC.element_to_be_clickable((By.CSS_SELECTOR, selector)))
            el.click()
            return True
        except Exception:
            pass
    return False

def xpath_texto(texto: str) -> str:
    texto_norm = normalizar_texto(texto)
    return (
        "//*[self::button or self::a or self::span or self::div or self::li]"
        "[string-length(normalize-space(.)) > 0]"
        f"[contains(translate(normalize-space(.), "
        "'ABCDEFGHIJKLMNOPQRSTUVWXYZÃÃ‰ÃÃ“ÃšÃœÃ‘abcdefghijklmnopqrstuvwxyzÃ¡Ã©Ã­Ã³ÃºÃ¼Ã±', "
        "'abcdefghijklmnopqrstuvwxyzÃ¡Ã©Ã­Ã³ÃºÃ¼Ã±abcdefghijklmnopqrstuvwxyzÃ¡Ã©Ã­Ã³ÃºÃ¼Ã±'), "
        f"'{texto_norm}') or contains(normalize-space(.), '{texto}')]"
    )

def click_texto(driver: webdriver.Chrome, textos: list[str], segundos: int = 15) -> bool:
    for texto in textos:
        try:
            el = wait(driver, segundos).until(EC.element_to_be_clickable((By.XPATH, xpath_texto(texto))))
            driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", el)
            el.click()
            return True
        except Exception:
            pass
    return False

def escribir_fecha(driver: webdriver.Chrome, selectores: list[str], valor: date, formato_web: str = "%Y-%m-%d"):
    el = elemento_visible_por_css(driver, selectores, segundos=15)
    fecha = valor.strftime(formato_web)
    driver.execute_script(
        """
        const el = arguments[0];
        const value = arguments[1];
        el.focus();
        el.value = '';
        el.dispatchEvent(new Event('input', {bubbles:true}));
        el.value = value;
        el.dispatchEvent(new Event('input', {bubbles:true}));
        el.dispatchEvent(new Event('change', {bubbles:true}));
        el.blur();
        """,
        el,
        fecha,
    )

def click_cdp(driver: webdriver.Chrome, x: float, y: float):
    driver.execute_cdp_cmd("Input.dispatchMouseEvent", {"type": "mouseMoved", "x": x, "y": y})
    driver.execute_cdp_cmd("Input.dispatchMouseEvent", {"type": "mousePressed", "x": x, "y": y, "button": "left", "clickCount": 1})
    driver.execute_cdp_cmd("Input.dispatchMouseEvent", {"type": "mouseReleased", "x": x, "y": y, "button": "left", "clickCount": 1})
