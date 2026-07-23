from __future__ import annotations

import base64
import re
import time
from typing import Any, Iterable

import pandas as pd
import requests
from requests import Session
from selenium import webdriver

from .config import *
from .selenium_utils import microsoft_login, normalizar_texto

def normalizar_iteration_path(path: str, project: str) -> str:
    partes = [p for p in str(path or "").strip("\\").split("\\") if p]
    if len(partes) >= 2 and partes[0].lower() == project.lower() and partes[1].lower() == "iteration":
        partes.pop(1)
    return "\\".join(partes)


def candidatos_iteration_path(path: str, project: str) -> list[str]:
    base = normalizar_iteration_path(path, project)
    candidatos = [base]
    original = str(path or "").strip("\\")
    if original and original not in candidatos:
        candidatos.append(original)
    if base.lower().startswith(project.lower() + "\\"):
        sin_project = base.split("\\", 1)[1]
        if sin_project not in candidatos:
            candidatos.append(sin_project)
    return [c for c in candidatos if c]


def numero_azure(valor: Any) -> float:
    if valor in (None, ""):
        return 0.0
    try:
        return float(valor)
    except (TypeError, ValueError):
        return 0.0


class AzureDevOpsClient:
    def __init__(self, org: str, project: str, team: str, session: Session | None = None, pat: str | None = None):
        self.org = org
        self.project = project
        self.team = team
        self.base = f"https://dev.azure.com/{org}/{project}"
        self.session = session or requests.Session()
        self.session.headers.update({"Accept": "application/json"})
        if pat:
            token = base64.b64encode(f":{pat}".encode()).decode()
            self.session.headers.update({"Authorization": f"Basic {token}"})

    def request(self, method: str, url: str, **kwargs) -> Any:
        resp = self.session.request(method, url, timeout=60, **kwargs)
        ctype = resp.headers.get("content-type", "")
        if resp.status_code >= 400:
            raise RuntimeError(f"Azure DevOps API error {resp.status_code}: {resp.text[:800]}")
        if "text/html" in ctype.lower():
            raise RuntimeError(
                "Azure DevOps devolviÃ³ HTML, no JSON. Probablemente no quedÃ³ autenticado. "
                "Usa AZURE_DEVOPS_PAT o inicia sesiÃ³n/MFA correctamente con AZURE_EMAIL/AZURE_PASS."
            )
        if resp.text.strip():
            return resp.json()
        return {}

    def get(self, path_or_url: str, **params) -> Any:
        url = path_or_url if path_or_url.startswith("http") else f"{self.base}{path_or_url}"
        return self.request("GET", url, params=params)

    def post(self, path_or_url: str, json: dict[str, Any], **params) -> Any:
        url = path_or_url if path_or_url.startswith("http") else f"{self.base}{path_or_url}"
        headers = {"Content-Type": "application/json"}
        return self.request("POST", url, json=json, params=params, headers=headers)

    def obtener_arbol_iteraciones(self) -> dict[str, Any]:
        return self.get("/_apis/wit/classificationnodes/iterations", **{"$depth": 20, "api-version": "7.1"})

    def buscar_iteracion_sprint(self, sprint: int) -> dict[str, Any]:
        arbol = self.obtener_arbol_iteraciones()
        objetivo = f"Sprint {sprint}"
        encontrados: list[dict[str, Any]] = []

        def recorrer(nodo: dict[str, Any]):
            if nodo.get("name") == objetivo:
                encontrados.append(nodo)
            for hijo in nodo.get("children", []) or []:
                recorrer(hijo)

        recorrer(arbol)
        if not encontrados:
            raise RuntimeError(f"No encontrÃ© la iteraciÃ³n '{objetivo}' en el proyecto {self.project}.")

        def puntaje(nodo: dict[str, Any]) -> tuple[int, str]:
            path = nodo.get("path", "")
            tiene_team = 1 if f"\\{self.team}\\" in path or path.endswith(f"\\{self.team}") else 0
            return (tiene_team, path)

        encontrados = sorted(encontrados, key=puntaje, reverse=True)
        return encontrados[0]

    def wiql_ids_por_iteracion(self, iteration_path: str, solo_mias: bool = True) -> list[int]:
        filtro_mias = " AND [System.AssignedTo] = @Me" if solo_mias else ""
        errores: list[str] = []
        for candidato in candidatos_iteration_path(iteration_path, self.project):
            path = candidato.replace("'", "''")
            print(f"Azure iteration path WIQL: {path}")
            query = f"""
            SELECT [System.Id]
            FROM WorkItems
            WHERE [System.TeamProject] = '{self.project}'
              AND [System.IterationPath] UNDER '{path}'
              {filtro_mias}
            ORDER BY [System.WorkItemType], [System.Id]
            """
            try:
                data = self.post("/_apis/wit/wiql", json={"query": query}, **{"api-version": "7.1"})
                return [int(x["id"]) for x in data.get("workItems", [])]
            except RuntimeError as exc:
                mensaje = str(exc)
                errores.append(mensaje[:300])
                if "TF51011" not in mensaje and "IterationPath" not in mensaje:
                    raise
        raise RuntimeError("No pude consultar Azure con ningun iteration path candidato: " + " | ".join(errores))

    def obtener_work_items(self, ids: list[int]) -> list[dict[str, Any]]:
        if not ids:
            return []
        items: list[dict[str, Any]] = []
        for chunk in chunks(ids, 200):
            ids_str = ",".join(map(str, chunk))
            data = self.get(
                "/_apis/wit/workitems",
                ids=ids_str,
                **{"$expand": "relations", "api-version": "7.1"},
            )
            items.extend(data.get("value", []))
        return items

    def descargar_sprint(
        self,
        sprint: int,
        solo_mias: bool = True,
        assigned_to_name: str | None = None,
    ) -> tuple[pd.DataFrame, dict[str, Any]]:
        iteracion = self.buscar_iteracion_sprint(sprint)
        iteration_path = normalizar_iteration_path(iteracion["path"], self.project)
        print(f"Azure iteration node path: {iteracion.get('path', '')}")
        print(f"Azure iteration normalized: {iteration_path}")
        ids = self.wiql_ids_por_iteracion(iteration_path, solo_mias=solo_mias and not assigned_to_name)
        items = self.obtener_work_items(ids)

        parent_ids = sorted({pid for pid in (extraer_parent_id(wi) for wi in items) if pid})
        parents = {wi["id"]: wi for wi in self.obtener_work_items(parent_ids)} if parent_ids else {}

        rows = []
        for wi in items:
            fields = wi.get("fields", {})
            pid = extraer_parent_id(wi)
            parent = parents.get(pid, {}) if pid else {}
            pfields = parent.get("fields", {})
            assigned = fields.get("System.AssignedTo", {})
            if isinstance(assigned, dict):
                assigned_to = assigned.get("displayName") or assigned.get("uniqueName") or ""
                assigned_email = assigned.get("uniqueName") or ""
            else:
                assigned_to = str(assigned or "")
                assigned_email = ""

            rows.append(
                {
                    "AzureID": wi.get("id"),
                    "Tipo": fields.get("System.WorkItemType", ""),
                    "Titulo": fields.get("System.Title", ""),
                    "Descripcion Azure": fields.get("System.Description", ""),
                    "Estado": fields.get("System.State", ""),
                    "Tags": fields.get("System.Tags", ""),
                    "Original Estimate": numero_azure(fields.get("Microsoft.VSTS.Scheduling.OriginalEstimate")),
                    "Remaining Work": numero_azure(fields.get("Microsoft.VSTS.Scheduling.RemainingWork")),
                    "Completed Work": numero_azure(fields.get("Microsoft.VSTS.Scheduling.CompletedWork")),
                    "AsignadoA": assigned_to,
                    "AsignadoEmail": assigned_email,
                    "IterationPath": fields.get("System.IterationPath", ""),
                    "ParentID": pid or "",
                    "ParentTitle": pfields.get("System.Title", ""),
                    "ParentTipo": pfields.get("System.WorkItemType", ""),
                }
            )

        df = pd.DataFrame(rows)
        if not df.empty:
            if assigned_to_name:
                asignado_key = normalizar_texto(assigned_to_name)
                asignado_email = normalizar_texto(AZURE_ASSIGNED_TO_EMAIL)
                df = df[
                    df.apply(
                        lambda row: (
                            asignado_email and asignado_email == normalizar_texto(row.get("AsignadoEmail", ""))
                        )
                        or asignado_key in normalizar_texto(row.get("AsignadoA", ""))
                        or normalizar_texto(row.get("AsignadoA", "")) in asignado_key,
                        axis=1,
                    )
                ].copy()
            df["HU"] = df.apply(
                lambda r: f"{r['ParentID']} - {r['ParentTitle']}" if r.get("ParentID") else f"{r['AzureID']} - {r['Titulo']}",
                axis=1,
            )
            df["TituloKey"] = df["Titulo"].apply(normalizar_texto)
            df["DescripcionAzureKey"] = df["Descripcion Azure"].apply(normalizar_texto)
            df = df.sort_values(["ParentID", "Tipo", "AzureID"])
        else:
            df = pd.DataFrame(
                columns=[
                    "AzureID",
                    "Tipo",
                    "Titulo",
                    "Descripcion Azure",
                    "Estado",
                    "Tags",
                    "Original Estimate",
                    "Remaining Work",
                    "Completed Work",
                    "AsignadoA",
                    "AsignadoEmail",
                    "IterationPath",
                    "ParentID",
                    "ParentTitle",
                    "ParentTipo",
                    "HU",
                    "TituloKey",
                    "DescripcionAzureKey",
                ]
            )

        return df, iteracion

def chunks(lista: list[int], n: int) -> Iterable[list[int]]:
    for i in range(0, len(lista), n):
        yield lista[i : i + n]

def extraer_parent_id(work_item: dict[str, Any]) -> int | None:
    fields = work_item.get("fields", {})
    if "System.Parent" in fields:
        try:
            return int(fields["System.Parent"])
        except Exception:
            pass

    for rel in work_item.get("relations", []) or []:
        if rel.get("rel") == "System.LinkTypes.Hierarchy-Reverse":
            url = rel.get("url", "")
            m = re.search(r"workItems/(\d+)$", url)
            if m:
                return int(m.group(1))
    return None

def session_desde_selenium(driver: webdriver.Chrome) -> Session:
    session = requests.Session()
    for cookie in driver.get_cookies():
        session.cookies.set(cookie["name"], cookie["value"], domain=cookie.get("domain"))
    session.headers.update({"User-Agent": "Mozilla/5.0", "Accept": "application/json"})
    return session

def crear_cliente_azure(driver: webdriver.Chrome | None, usar_browser: bool) -> AzureDevOpsClient:
    if AZURE_DEVOPS_PAT:
        return AzureDevOpsClient(AZURE_ORG, AZURE_PROJECT, AZURE_TEAM, pat=AZURE_DEVOPS_PAT)

    if not usar_browser:
        raise RuntimeError(
            "No hay AZURE_DEVOPS_PAT y desactivaste el navegador. "
            "Configura AZURE_DEVOPS_PAT o permite login con AZURE_EMAIL/AZURE_PASS."
        )

    if not AZURE_EMAIL or not AZURE_PASS:
        raise RuntimeError("Faltan AZURE_EMAIL y/o AZURE_PASS para iniciar sesiÃ³n en Azure DevOps.")

    if driver is None:
        raise RuntimeError("Se requiere driver Selenium para login de Azure DevOps.")

    url = f"https://dev.azure.com/{AZURE_ORG}/{AZURE_PROJECT}/"
    microsoft_login(driver, AZURE_EMAIL, AZURE_PASS, url)
    driver.get(url)
    time.sleep(5)
    return AzureDevOpsClient(AZURE_ORG, AZURE_PROJECT, AZURE_TEAM, session=session_desde_selenium(driver))
