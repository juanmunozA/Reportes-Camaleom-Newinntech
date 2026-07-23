from __future__ import annotations

import time

from selenium import webdriver
from selenium.common.exceptions import ElementNotInteractableException, StaleElementReferenceException, TimeoutException
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys

from .browser import click_css_si_existe, click_texto, elemento_visible_por_css
from .config import SELECTORES_CAMALEOM
from .text_utils import normalizar_texto

def escribir_texto_login(driver: webdriver.Chrome, elemento, valor: str, es_password: bool = False):
    try:
        driver.execute_script("arguments[0].scrollIntoView({block:'center', inline:'center'});", elemento)
        elemento.click()
        elemento.send_keys(Keys.CONTROL, "a")
        elemento.send_keys(Keys.BACKSPACE)
        if es_password:
            ActionChains(driver).click(elemento).send_keys(valor).perform()
        else:
            elemento.send_keys(valor)
    except ElementNotInteractableException:
        pass
    time.sleep(0.15)
    escrito = elemento.get_attribute("value") or ""
    if len(escrito) < len(valor):
        driver.execute_script(
            """
            const el = arguments[0];
            const value = arguments[1];
            const setter = Object.getOwnPropertyDescriptor(
                window.HTMLInputElement.prototype,
                'value'
            ).set;
            setter.call(el, value);
            el.dispatchEvent(new InputEvent('input', {bubbles:true, inputType:'insertText', data:value}));
            el.dispatchEvent(new Event('change', {bubbles:true}));
            """,
            elemento,
            valor,
        )
        time.sleep(0.15)

def elemento_password_login(driver: webdriver.Chrome, segundos: int = 20):
    limite = time.time() + segundos
    ultimo_error = None
    while time.time() < limite:
        driver.switch_to.default_content()
        frames = [None]
        try:
            frames.extend(driver.find_elements(By.CSS_SELECTOR, "iframe"))
        except Exception:
            pass

        for frame in frames:
            try:
                driver.switch_to.default_content()
                if frame is not None:
                    driver.switch_to.frame(frame)

                try:
                    return elemento_visible_por_css(driver, SELECTORES_CAMALEOM["password"], segundos=1)
                except Exception as exc:
                    ultimo_error = exc

                elemento = driver.execute_script(
                    """
                    const norm = (txt) => (txt || '')
                        .normalize('NFD').replace(/[\\u0300-\\u036f]/g, '')
                        .toLowerCase();
                    const inputs = Array.from(document.querySelectorAll('input, [contenteditable="true"]'));
                    for (const el of inputs) {
                        const visible = !!(el.offsetWidth || el.offsetHeight || el.getClientRects().length);
                        if (!visible || el.disabled || el.readOnly) continue;
                        const type = norm(el.getAttribute('type'));
                        const text = norm([
                            el.getAttribute('placeholder'),
                            el.getAttribute('aria-label'),
                            el.getAttribute('name'),
                            el.getAttribute('id'),
                            el.textContent
                        ].join(' '));
                        if (type === 'password' || text.includes('contrasena') || text.includes('password') || text.includes('pass')) {
                            return el;
                        }
                    }
                    return null;
                    """
                )
                if elemento is not None:
                    return elemento
            except Exception as exc:
                ultimo_error = exc

        time.sleep(0.15)

    driver.switch_to.default_content()
    raise TimeoutException("No encontré el campo de contraseña de Camaleom/CyberArk") from ultimo_error

def click_boton_login(driver: webdriver.Chrome, textos: list[str], segundos: int = 8) -> bool:
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
                    'button, [role="button"], input[type="submit"], a, div, span'
                ));
                for (const el of candidatos) {
                    const visible = !!(el.offsetWidth || el.offsetHeight || el.getClientRects().length);
                    const texto = norm(el.innerText || el.value || el.textContent);
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
        time.sleep(0.15)
    return False

def click_boton_login_fisico(driver: webdriver.Chrome, textos: list[str], segundos: int = 8) -> bool:
    limite = time.time() + segundos
    textos_norm = [normalizar_texto(t) for t in textos]
    while time.time() < limite:
        try:
            candidatos = driver.find_elements(By.CSS_SELECTOR, "button, [role='button'], input[type='submit'], a")
            for el in candidatos:
                if not el.is_displayed() or not el.is_enabled():
                    continue
                texto = normalizar_texto(el.text or el.get_attribute("value") or el.get_attribute("aria-label") or "")
                if any(t in texto for t in textos_norm):
                    driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", el)
                    ActionChains(driver).move_to_element(el).pause(0.05).click(el).perform()
                    return True
        except Exception:
            pass
        time.sleep(0.15)
    return False

def esperar_salida_login(driver: webdriver.Chrome, segundos: int = 120) -> bool:
    limite = time.time() + segundos
    while time.time() < limite:
        url = driver.current_url.lower()
        texto = normalizar_texto(driver.find_element(By.TAG_NAME, "body").text)
        if "camaleom.gruponutresa.com/home" in url or "bienvenido" in texto or "reportes" in texto:
            return True
        time.sleep(0.1)
    return False

def microsoft_login(driver: webdriver.Chrome, email: str, password: str, url: str):
    driver.get(url)
    time.sleep(2)

    # Campo usuario Microsoft.
    try:
        usuario = elemento_visible_por_css(
            driver,
            ["input[type='email']", "#i0116", "input[name='loginfmt']", "input[name='username']"],
            segundos=10,
        )
        usuario.clear()
        usuario.send_keys(email)
        usuario.send_keys(Keys.ENTER)
        time.sleep(2)
    except TimeoutException:
        # Puede que ya exista sesiÃ³n.
        return

    # Campo password Microsoft.
    try:
        pwd = elemento_visible_por_css(
            driver,
            ["input[type='password']", "#i0118", "input[name='passwd']", "input[name='password']"],
            segundos=20,
        )
        pwd.clear()
        pwd.send_keys(password)
        pwd.send_keys(Keys.ENTER)
        time.sleep(3)
    except TimeoutException:
        pass

    # Pantalla tÃ­pica: Â¿Mantener la sesiÃ³n iniciada?
    click_css_si_existe(driver, ["#idSIButton9", "#idBtn_Back"], segundos=5)

    # MFA / Authenticator manual.
    if any(x in driver.current_url.lower() for x in ["microsoftonline", "login", "signin"]):
        print("Si aparece MFA/Authenticator, apruÃ©balo. Espero hasta 90 segundos...")
        time.sleep(90)
