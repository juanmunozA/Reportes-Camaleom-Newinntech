from __future__ import annotations

import time
from datetime import date
from typing import Any

from selenium import webdriver
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys

from .browser import click_cdp, click_texto, elemento_visible_por_css
from .config import SELECTORES_CAMALEOM
from .text_utils import normalizar_texto

def inputs_fecha_camaleom(driver: webdriver.Chrome) -> tuple[Any, Any]:
    candidatos = driver.execute_script(
        """
        const norm = (txt) => (txt || '')
            .normalize('NFD').replace(/[\u0300-\u036f]/g, '')
            .toLowerCase();
        const inputs = Array.from(document.querySelectorAll('input'));
        const encontrados = [];
        for (const el of inputs) {
            const visible = !!(el.offsetWidth || el.offsetHeight || el.getClientRects().length);
            if (!visible || el.disabled || el.readOnly) continue;
            const rect = el.getBoundingClientRect();
            const container = el.closest('.form-group, .col-md-4, .col-sm-4, div') || el.parentElement || el;
            const text = norm([
                el.type, el.name, el.id, el.placeholder, el.getAttribute('aria-label'),
                container.innerText, container.textContent
            ].join(' '));
            const esFecha = text.includes('fecha') || text.includes('date') || text.includes('dd/mm/aaaa') ||
                text.includes('desde') || text.includes('hasta') || text.includes('inicial') || text.includes('final');
            if (!esFecha) continue;
            let rol = text.includes('final') || text.includes('hasta') ? 'fin' : 'inicio';
            encontrados.push({el, rol, left: rect.left, top: rect.top, width: rect.width});
        }
        encontrados.sort((a, b) => (a.top - b.top) || (a.left - b.left));
        const inicio = encontrados.find(x => x.rol === 'inicio') || encontrados[0];
        const fin = encontrados.find(x => x.rol === 'fin' && x.el !== inicio?.el) || encontrados.find(x => x.el !== inicio?.el);
        return [inicio?.el || null, fin?.el || null];
        """
    )
    if len(candidatos) < 2 or candidatos[0] is None or candidatos[1] is None:
        raise TimeoutException("No detecte los dos campos de fecha del reporte Camaleom")
    return candidatos[0], candidatos[1]

def valor_input(driver: webdriver.Chrome, el) -> str:
    try:
        return driver.execute_script("return arguments[0].value || '';", el) or ""
    except Exception:
        return ""


def escribir_fecha_elemento(driver: webdriver.Chrome, el, valor: date, formato_web: str):
    fecha = valor.strftime(formato_web)
    formatos = [fecha, valor.strftime("%d/%m/%Y"), valor.strftime("%Y-%m-%d")]
    vistos: list[str] = []

    for intento, candidato in enumerate(dict.fromkeys(formatos), start=1):
        try:
            driver.execute_script("arguments[0].scrollIntoView({block:'center', inline:'center'});", el)
            el.click()
            el.send_keys(Keys.CONTROL, "a")
            el.send_keys(Keys.BACKSPACE)
            el.send_keys(candidato)
            el.send_keys(Keys.TAB)
            time.sleep(0.12)
        except Exception:
            pass

        actual = valor_input(driver, el)
        vistos.append(actual)
        if str(valor.year) in actual and any(sep in actual for sep in ["/", "-"]):
            agente_log(f"fecha escrita: {candidato} -> {actual}")
            return

        try:
            driver.execute_script(
                """
                const el = arguments[0];
                const value = arguments[1];
                const setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set;
                el.focus();
                setter.call(el, '');
                el.dispatchEvent(new InputEvent('input', {bubbles:true, inputType:'deleteContentBackward'}));
                setter.call(el, value);
                el.dispatchEvent(new InputEvent('input', {bubbles:true, inputType:'insertText', data:value}));
                el.dispatchEvent(new Event('change', {bubbles:true}));
                el.dispatchEvent(new Event('blur', {bubbles:true}));
                """,
                el,
                candidato,
            )
            time.sleep(0.12)
        except Exception:
            pass

        actual = valor_input(driver, el)
        vistos.append(actual)
        if str(valor.year) in actual and any(sep in actual for sep in ["/", "-"]):
            agente_log(f"fecha escrita por JS: {candidato} -> {actual}")
            return

    raise RuntimeError(f"No pude escribir fecha {fecha}. Valores vistos: {vistos}")


def fechas_camaleom_ok(driver: webdriver.Chrome, fecha_inicio: date, fecha_fin: date) -> bool:
    try:
        inicio, fin = inputs_fecha_camaleom(driver)
        valor_inicio = valor_input(driver, inicio)
        valor_fin = valor_input(driver, fin)
        agente_log(f"fechas visibles: inicio='{valor_inicio}' fin='{valor_fin}'")
        return str(fecha_inicio.year) in valor_inicio and str(fecha_fin.year) in valor_fin
    except Exception as exc:
        agente_log(f"no pude validar fechas: {exc}")
        return False

def click_texto_js(driver: webdriver.Chrome, textos: list[str], segundos: int = 15) -> bool:
    limite = time.time() + segundos
    textos_norm = [normalizar_texto(t) for t in textos]
    while time.time() < limite:
        try:
            clicked = driver.execute_script(
                """
                const textos = arguments[0];
                const norm = (txt) => (txt || '')
                    .normalize('NFD').replace(/[\\u0300-\\u036f]/g, '')
                    .toLowerCase().replace(/[^a-z0-9]+/g, ' ').trim();
                const candidatos = Array.from(document.querySelectorAll(
                    'button, a, li, div, span, [role="button"], [ng-click], .menu-item'
                ));
                for (const el of candidatos) {
                    const visible = !!(el.offsetWidth || el.offsetHeight || el.getClientRects().length);
                    const texto = norm(el.innerText || el.textContent || el.value);
                    if (visible && textos.some(t => texto.includes(t))) {
                        el.scrollIntoView({block: 'center'});
                        el.click();
                        return true;
                    }
                }
                return false;
                """,
                textos_norm,
            )
            if clicked:
                return True
        except Exception:
            pass
        if click_texto(driver, textos, segundos=1):
            return True
        time.sleep(0.5)
    return False

def campos_fecha_visibles(driver: webdriver.Chrome) -> bool:
    try:
        elemento_visible_por_css(driver, SELECTORES_CAMALEOM["fecha_desde"], segundos=1)
        elemento_visible_por_css(driver, SELECTORES_CAMALEOM["fecha_hasta"], segundos=1)
        return True
    except Exception:
        return False


def agente_log(mensaje: str) -> None:
    print(f"[agente-camaleom] {mensaje}", flush=True)


def pagina_contiene(driver: webdriver.Chrome, texto: str) -> bool:
    try:
        body = driver.find_element(By.TAG_NAME, "body").text
    except Exception:
        return False
    return normalizar_texto(texto) in normalizar_texto(body)


def click_objetivo_realtime(
    driver: webdriver.Chrome,
    objetivo: str,
    aliases: list[str] | None = None,
    segundos: float = 1.2,
    preferir_derecha: bool = False,
    intervalo: float = 0.05,
) -> bool:
    """Observa elementos visibles y hace click en el mejor candidato.

    Es deliberadamente rapido: ciclos cortos de DOM visible -> scoring -> click -> verificar.
    """
    limite = time.perf_counter() + segundos
    aliases_norm = [normalizar_texto(x) for x in (aliases or [objetivo])]
    ultimo_texto = ""

    while time.perf_counter() < limite:
        try:
            resultado = driver.execute_script(
                """
                const aliases = arguments[0];
                const preferRight = arguments[1];
                const norm = (txt) => (txt || '')
                    .normalize('NFD').replace(/[\\u0300-\\u036f]/g, '')
                    .toLowerCase().replace(/[^a-z0-9]+/g, ' ').trim();
                const tokens = (txt) => new Set(norm(txt).split(' ').filter(Boolean));
                const aliasTokens = aliases.map(tokens);
                const candidatos = Array.from(document.querySelectorAll(
                    'button, a, li, div, span, [role="button"], [ng-click], .menu-item, .nav-link, .dropdown-item'
                ));
                const matches = [];
                for (const el of candidatos) {
                    const rect = el.getBoundingClientRect();
                    if (rect.width <= 0 || rect.height <= 0) continue;
                    const style = window.getComputedStyle(el);
                    if (style.visibility === 'hidden' || style.display === 'none' || style.pointerEvents === 'none') continue;
                    const raw = (el.innerText || el.textContent || el.value || el.getAttribute('aria-label') || '').trim();
                    const text = norm(raw);
                    if (!text || text.length > 180) continue;

                    let score = 0;
                    for (let i = 0; i < aliases.length; i++) {
                        const alias = aliases[i];
                        if (!alias) continue;
                        if (text === alias) score = Math.max(score, 1000);
                        if (text.includes(alias)) score = Math.max(score, 850 - Math.max(0, text.length - alias.length));
                        if (alias.includes(text) && text.length >= 5) score = Math.max(score, 650);
                        const tks = tokens(text);
                        const ats = aliasTokens[i];
                        let inter = 0;
                        for (const t of ats) if (tks.has(t)) inter++;
                        if (ats.size && inter === ats.size) score = Math.max(score, 720 - text.length);
                        else if (inter > 0) score = Math.max(score, inter * 90);
                    }
                    if (score <= 0) continue;

                    const clickable = el.closest('button, a, li, [role="button"], [ng-click], .menu-item, .nav-link, .dropdown-item') || el;
                    const crect = clickable.getBoundingClientRect();
                    if (crect.width <= 0 || crect.height <= 0) continue;
                    const area = crect.width * crect.height;
                    const depth = (() => { let d = 0, n = clickable; while (n && n.parentElement) { d++; n = n.parentElement; } return d; })();
                    matches.push({el, clickable, raw, text, score, area, depth, rect: crect});
                }
                matches.sort((a, b) =>
                    (b.score - a.score) ||
                    (b.depth - a.depth) ||
                    (a.area - b.area)
                );
                const best = matches[0];
                if (!best) return {clicked:false, reason:'no-match'};

                const target = best.clickable;
                target.scrollIntoView({block:'center', inline:'center'});
                const r = target.getBoundingClientRect();
                const x = preferRight && r.width > 50 ? r.right - 24 : r.left + r.width / 2;
                const y = r.top + r.height / 2;
                const pointTarget = document.elementFromPoint(x, y) || target;
                for (const node of [target, pointTarget]) {
                    if (!node) continue;
                    node.dispatchEvent(new MouseEvent('mouseover', {bubbles:true, clientX:x, clientY:y}));
                    node.dispatchEvent(new MouseEvent('mousemove', {bubbles:true, clientX:x, clientY:y}));
                    node.dispatchEvent(new MouseEvent('mousedown', {bubbles:true, clientX:x, clientY:y, button:0}));
                    node.dispatchEvent(new MouseEvent('mouseup', {bubbles:true, clientX:x, clientY:y, button:0}));
                    node.dispatchEvent(new MouseEvent('click', {bubbles:true, clientX:x, clientY:y, button:0}));
                }
                try { target.click(); } catch (e) {}
                return {clicked:true, text: best.raw, score: best.score, x: Math.round(x), y: Math.round(y)};
                """,
                aliases_norm,
                preferir_derecha,
            )
            if resultado and resultado.get("clicked"):
                agente_log(f"click '{objetivo}' -> {resultado.get('text')} rank={resultado.get('score')}")
                return True
            ultimo_texto = str(resultado.get("reason") if resultado else "sin resultado")
        except Exception as exc:
            ultimo_texto = str(exc)[:120]
        time.sleep(intervalo)

    agente_log(f"no encontre objetivo '{objetivo}' en {segundos}s ({ultimo_texto})")
    return False


def abrir_reporte_actividades_realtime(driver: webdriver.Chrome, segundos: int = 18) -> bool:
    """Navega Reportes -> Generar Reporte mis Actividades con feedback continuo."""
    limite = time.perf_counter() + segundos
    intento = 0
    while time.perf_counter() < limite:
        intento += 1
        if campos_fecha_visibles(driver):
            agente_log("formulario de fechas visible")
            return True

        if pagina_contiene(driver, "Generar Reporte mis Actividades"):
            agente_log("veo Generar Reporte mis Actividades; clic directo")
            click_objetivo_realtime(
                driver,
                "Generar Reporte mis Actividades",
                ["Generar Reporte mis Actividades", "Mis Actividades", "Actividades"],
                segundos=0.9,
            )
            time.sleep(0.12)
            if campos_fecha_visibles(driver):
                agente_log("entre al formulario de actividades")
                return True

        agente_log(f"intento {intento}: abriendo Reportes")
        click_objetivo_realtime(
            driver,
            "Reportes",
            ["Reportes", "Reporte"],
            segundos=0.8,
            preferir_derecha=True,
        )
        time.sleep(0.12)

        if click_objetivo_realtime(
            driver,
            "Generar Reporte mis Actividades",
            ["Generar Reporte mis Actividades", "Mis Actividades", "Mis actividades realizadas"],
            segundos=0.9,
        ):
            time.sleep(0.15)
            if campos_fecha_visibles(driver):
                agente_log("formulario abierto despues de submenu")
                return True

        time.sleep(0.08)

    return campos_fecha_visibles(driver)

def esperar_formulario_reporte_camaleom(driver: webdriver.Chrome, segundos: int = 120) -> bool:
    limite = time.time() + segundos
    while time.time() < limite:
        if campos_fecha_visibles(driver):
            return True
        time.sleep(1)
    return False

def click_menu_lateral_camaleom(driver: webdriver.Chrome, textos: list[str], segundos: int = 15) -> bool:
    limite = time.time() + segundos
    textos_norm = [normalizar_texto(t) for t in textos]
    while time.time() < limite:
        try:
            elementos = driver.find_elements(By.XPATH, "//*[self::a or self::li or self::div or self::span][normalize-space(.) != '']")
            for el in elementos:
                if not el.is_displayed():
                    continue
                texto = normalizar_texto(el.text)
                if not any(t in texto for t in textos_norm):
                    continue

                clickable = el
                try:
                    ancestros = el.find_elements(By.XPATH, "./ancestor-or-self::*[self::a or self::li or @role='button' or @ng-click][1]")
                    if ancestros:
                        clickable = ancestros[-1]
                except Exception:
                    pass

                driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", clickable)
                size = clickable.size
                ActionChains(driver).move_to_element(clickable).pause(0.1).click().perform()
                time.sleep(0.5)
                if size.get("width", 0) > 40:
                    ActionChains(driver).move_to_element_with_offset(
                        clickable,
                        max(1, int(size["width"] / 2) - 15),
                        0,
                    ).pause(0.1).click().perform()
                return True
        except Exception:
            pass

        try:
            clicked = driver.execute_script(
                """
                const textos = arguments[0];
                const norm = (txt) => (txt || '')
                    .normalize('NFD').replace(/[\\u0300-\\u036f]/g, '')
                    .toLowerCase().replace(/[^a-z0-9]+/g, ' ').trim();
                const candidatos = Array.from(document.querySelectorAll('li, a, div, span'));
                for (const el of candidatos) {
                    const visible = !!(el.offsetWidth || el.offsetHeight || el.getClientRects().length);
                    const texto = norm(el.innerText || el.textContent || '');
                    if (!visible || !textos.some(t => texto.includes(t))) continue;

                    const clickable = el.closest('a, button, li, [role="button"], [ng-click]') || el;
                    clickable.scrollIntoView({block: 'center'});
                    clickable.click();

                    const rect = clickable.getBoundingClientRect();
                    const target = document.elementFromPoint(rect.right - 25, rect.top + rect.height / 2);
                    if (target && target !== clickable) target.click();
                    return true;
                }
                return false;
                """,
                textos_norm,
            )
            if clicked:
                return True
        except Exception:
            pass
        time.sleep(0.5)
    return False

def rect_por_texto(driver: webdriver.Chrome, texto_objetivo: str) -> dict[str, float] | None:
    texto_norm = normalizar_texto(texto_objetivo)
    return driver.execute_script(
        """
        const textoObjetivo = arguments[0];
        const norm = (txt) => (txt || '')
            .normalize('NFD').replace(/[\\u0300-\\u036f]/g, '')
            .toLowerCase().replace(/[^a-z0-9]+/g, ' ').trim();
        const candidatos = Array.from(document.querySelectorAll('a, li, div, span, button'));
        const matches = [];
        for (const el of candidatos) {
            const rect = el.getBoundingClientRect();
            const texto = norm(el.innerText || el.textContent || '');
            if (rect.width <= 0 || rect.height <= 0 || !texto.includes(textoObjetivo)) continue;
            matches.push({left: rect.left, top: rect.top, right: rect.right, bottom: rect.bottom, width: rect.width, height: rect.height});
        }
        matches.sort((a, b) => (b.width * b.height) - (a.width * a.height));
        return matches[0] || null;
        """,
        texto_norm,
    )

def click_texto_cdp(driver: webdriver.Chrome, texto_objetivo: str, segundos: int = 10, preferir_derecha: bool = False) -> bool:
    limite = time.time() + segundos
    while time.time() < limite:
        rect = rect_por_texto(driver, texto_objetivo)
        if rect:
            x = rect["right"] - 25 if preferir_derecha and rect["width"] > 50 else rect["left"] + rect["width"] / 2
            y = rect["top"] + rect["height"] / 2
            click_cdp(driver, x, y)
            return True
        time.sleep(0.5)
    return False

def click_exportar_actividades_realtime(driver: webdriver.Chrome, segundos: float = 1.5) -> bool:
    aliases = ["Exportar Actividades", "Exportar", "Descargar", "Excel"]
    if click_objetivo_realtime(driver, "Exportar Actividades", aliases, segundos=segundos):
        return True
    return click_texto_js(driver, aliases, segundos=1)


def abrir_reportes_camaleom(driver: webdriver.Chrome, segundos: int = 8) -> bool:
    limite = time.perf_counter() + segundos
    while time.perf_counter() < limite:
        if pagina_contiene(driver, "Generar Reporte mis Actividades"):
            return True
        if click_objetivo_realtime(driver, "Reportes", ["Reportes", "Reporte"], segundos=0.8, preferir_derecha=True):
            time.sleep(0.12)
            if pagina_contiene(driver, "Generar Reporte mis Actividades"):
                return True
        time.sleep(0.05)
    return False

def abrir_generar_reporte_actividades_camaleom(driver: webdriver.Chrome, segundos: int = 8) -> bool:
    limite = time.perf_counter() + segundos
    while time.perf_counter() < limite:
        if campos_fecha_visibles(driver):
            return True
        if click_objetivo_realtime(
            driver,
            "Generar Reporte mis Actividades",
            ["Generar Reporte mis Actividades", "Mis Actividades", "Mis actividades realizadas"],
            segundos=0.9,
        ):
            time.sleep(0.15)
            if campos_fecha_visibles(driver):
                return True
        time.sleep(0.05)
    return False
