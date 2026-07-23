from __future__ import annotations

import json
import re
from typing import Any

import requests
from selenium import webdriver

from .browser import click_cdp
from .config import GEMINI_API_KEY, GEMINI_MODEL, USAR_GEMINI_NAV

def texto_gemini(data: dict[str, Any]) -> str:
    if isinstance(data.get("output_text"), str):
        return data["output_text"]
    textos: list[str] = []

    def recorrer(valor: Any):
        if isinstance(valor, dict):
            if isinstance(valor.get("text"), str):
                textos.append(valor["text"])
            for v in valor.values():
                recorrer(v)
        elif isinstance(valor, list):
            for v in valor:
                recorrer(v)

    recorrer(data)
    return "\n".join(textos)

def json_desde_texto(texto: str) -> dict[str, Any] | None:
    texto = (texto or "").strip()
    texto = re.sub(r"^```(?:json)?\s*", "", texto)
    texto = re.sub(r"\s*```$", "", texto)
    ini = texto.find("{")
    fin = texto.rfind("}")
    if ini >= 0 and fin > ini:
        texto = texto[ini : fin + 1]
    try:
        return json.loads(texto)
    except Exception:
        return None

def candidatos_visibles(driver: webdriver.Chrome) -> list[dict[str, Any]]:
    return driver.execute_script(
        """
        const norm = (txt) => (txt || '').normalize('NFD')
            .replace(/[\\u0300-\\u036f]/g, '')
            .replace(/\\s+/g, ' ').trim();
        const nodos = Array.from(document.querySelectorAll('a, li, div, span, button, input'));
        const out = [];
        for (const el of nodos) {
            const r = el.getBoundingClientRect();
            const txt = norm(el.innerText || el.textContent || el.value || el.getAttribute('aria-label') || '');
            if (r.width <= 0 || r.height <= 0 || !txt || txt.length > 100) continue;
            out.push({
                index: out.length,
                tag: el.tagName.toLowerCase(),
                text: txt,
                left: Math.round(r.left),
                top: Math.round(r.top),
                right: Math.round(r.right),
                bottom: Math.round(r.bottom),
                width: Math.round(r.width),
                height: Math.round(r.height)
            });
            if (out.length >= 90) break;
        }
        return out;
        """
    )

def decision_gemini(objetivo: str, candidatos: list[dict[str, Any]]) -> dict[str, Any] | None:
    if not (USAR_GEMINI_NAV and GEMINI_API_KEY):
        return None
    prompt = (
        "Necesito automatizar Camaleom. Elige el elemento visible que debo clicar para lograr el objetivo. "
        "Responde SOLO JSON valido con index, prefer_right y razon. "
        "Si el objetivo es abrir Reportes, suele servir clicar la fila Reportes o su flecha derecha. "
        "Si el objetivo es abrir Generar Reporte mis Actividades, elige ese texto exacto si aparece.\n"
        f"Objetivo: {objetivo}\n"
        f"Elementos visibles: {json.dumps(candidatos, ensure_ascii=False)}"
    )
    try:
        resp = requests.post(
            "https://generativelanguage.googleapis.com/v1beta/interactions",
            headers={"x-goog-api-key": GEMINI_API_KEY, "Content-Type": "application/json"},
            json={
                "model": GEMINI_MODEL,
                "system_instruction": "Eres un agente de navegacion web. No pidas credenciales. No modifiques Azure. Responde solo JSON.",
                "input": prompt,
                "generation_config": {"thinking_level": "low", "temperature": 0},
            },
            timeout=20,
        )
        if resp.status_code >= 400:
            print(f"Gemini fallo HTTP {resp.status_code}: {resp.text[:200]}")
            return None
        return json_desde_texto(texto_gemini(resp.json()))
    except Exception as exc:
        print(f"Gemini no disponible: {exc}")
        return None

def click_gemini(driver: webdriver.Chrome, objetivo: str) -> bool:
    candidatos = candidatos_visibles(driver)
    decision = decision_gemini(objetivo, candidatos)
    if not decision:
        return False
    try:
        index = int(decision.get("index"))
    except Exception:
        return False
    if index < 0 or index >= len(candidatos):
        return False
    item = candidatos[index]
    x = item["right"] - 20 if decision.get("prefer_right") and item["width"] > 40 else item["left"] + item["width"] / 2
    y = item["top"] + item["height"] / 2
    print(f"Gemini click: {item['text']} - {decision.get('razon', '')}")
    click_cdp(driver, x, y)
    return True
