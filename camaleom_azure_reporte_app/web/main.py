from __future__ import annotations

import shutil
import uuid
from datetime import date, datetime
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, Response
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from ..azure_devops import AzureDevOpsClient
from ..config import (APP_SECRET_KEY, AZURE_DEVOPS_PAT, AZURE_ORG, AZURE_PROJECT,
                      AZURE_TEAM, DOWNLOAD_DIR, GEMINI_API_KEY)
from . import db, gemini, jobs

STATIC_DIR = Path(__file__).resolve().parent / "static"
DAILY_LIMIT = 8

app = FastAPI(title="Reportes Camaleom + Azure")

if not APP_SECRET_KEY:
    raise RuntimeError("Falta APP_SECRET_KEY para firmar la sesion.")

app.add_middleware(SessionMiddleware, secret_key=APP_SECRET_KEY, same_site="lax", https_only=False)


@app.on_event("startup")
def _startup() -> None:
    db.init_db()


def current_user(request: Request) -> dict | None:
    user_id = request.session.get("user_id")
    if not user_id:
        return None
    return db.get_user_by_id(user_id)


def require_user(request: Request) -> dict:
    user = current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="No autenticado")
    return user


def _parse_date(value: str) -> date:
    value = (value or "").strip()
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y"):
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            continue
    raise HTTPException(status_code=400, detail=f"Fecha invalida: {value}")


# ---------- Paginas ----------

@app.get("/", response_class=HTMLResponse)
def index(request: Request):
    if current_user(request):
        return FileResponse(STATIC_DIR / "app.html")
    return FileResponse(STATIC_DIR / "login.html")


@app.get("/report", response_class=HTMLResponse)
def report_page(request: Request):
    if not current_user(request):
        return FileResponse(STATIC_DIR / "login.html")
    return FileResponse(STATIC_DIR / "report.html")


# ---------- Auth ----------

@app.post("/api/register")
async def register(request: Request):
    body = await request.json()
    email = (body.get("email") or "").strip().lower()
    password = body.get("password") or ""
    if not email or not password or len(password) < 6:
        raise HTTPException(status_code=400, detail="Email y password (min 6 caracteres) son requeridos.")
    if db.get_user_by_email(email):
        raise HTTPException(status_code=409, detail="Ya existe una cuenta con ese email.")
    user_id = db.create_user(email, password)
    request.session["user_id"] = user_id
    return {"ok": True}


@app.post("/api/login")
async def login(request: Request):
    body = await request.json()
    email = (body.get("email") or "").strip().lower()
    password = body.get("password") or ""
    user = db.get_user_by_email(email)
    if not user or not db.verify_password(password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="Email o password incorrectos.")
    request.session["user_id"] = user["id"]
    return {"ok": True}


@app.post("/api/logout")
def logout(request: Request):
    request.session.clear()
    return {"ok": True}


@app.get("/api/me")
def me(request: Request):
    user = require_user(request)
    profile = db.get_profile(user["id"]) or {}
    return {
        "email": user["email"],
        "gemini_enabled": bool(GEMINI_API_KEY),
        "runs_today": db.count_runs_today(user["id"]),
        "daily_limit": DAILY_LIMIT,
        "profile": {
            "azure_org": profile.get("azure_org") or AZURE_ORG,
            "azure_project": profile.get("azure_project") or AZURE_PROJECT,
            "azure_team": profile.get("azure_team") or AZURE_TEAM,
            "azure_full_name": profile.get("azure_full_name") or "",
        },
    }


@app.post("/api/profile")
async def save_profile(request: Request):
    user = require_user(request)
    body = await request.json()
    db.save_profile(
        user["id"],
        body.get("azure_org") or AZURE_ORG,
        body.get("azure_project") or AZURE_PROJECT,
        body.get("azure_team") or AZURE_TEAM,
        body.get("azure_full_name") or "",
        (db.get_profile(user["id"]) or {}).get("camaleom_user") or "",
        None,
    )
    return {"ok": True}


# ---------- Azure helper ----------

@app.get("/api/azure/sprint-range")
def sprint_range(sprints: str, azure_org: str = "", azure_project: str = "", azure_team: str = ""):
    if not AZURE_DEVOPS_PAT:
        raise HTTPException(status_code=500, detail="El servidor no tiene configurado AZURE_DEVOPS_PAT.")
    cliente = AzureDevOpsClient(azure_org or AZURE_ORG, azure_project or AZURE_PROJECT, azure_team or AZURE_TEAM, pat=AZURE_DEVOPS_PAT)
    nums = [int(s.strip()) for s in sprints.split(",") if s.strip()]
    if not nums:
        raise HTTPException(status_code=400, detail="Indica al menos un sprint.")
    finishes = []
    for numero in nums:
        it = cliente.buscar_iteracion_sprint(numero)
        attrs = it.get("attributes") or {}
        if attrs.get("finishDate"):
            finishes.append(datetime.fromisoformat(attrs["finishDate"].replace("Z", "+00:00")).date())
    return {"fecha_fin": max(finishes).isoformat() if finishes else None}


# ---------- Ejecucion ----------

@app.post("/api/run")
async def run_reporte(
    request: Request,
    camaleom_excel: UploadFile = File(...),
    fecha_final: str = Form(...),
    dias_atras: int = Form(21),
    sprints: str = Form(""),
    diferenciador: str = Form(""),
    azure_org: str = Form(""),
    azure_project: str = Form(""),
    azure_team: str = Form(""),
):
    user = require_user(request)

    if db.count_runs_today(user["id"]) >= DAILY_LIMIT:
        raise HTTPException(status_code=429, detail=f"Alcanzaste el limite de {DAILY_LIMIT} ejecuciones por dia.")

    fecha_final_d = _parse_date(fecha_final)

    filename = camaleom_excel.filename or "camaleom.xlsx"
    if not filename.lower().endswith((".xlsx", ".xls")):
        raise HTTPException(status_code=400, detail="El archivo de Camaleom debe ser un Excel (.xlsx o .xls).")

    DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)
    excel_path = DOWNLOAD_DIR / f"upload_{user['id']}_{uuid.uuid4().hex}{Path(filename).suffix or '.xlsx'}"
    with excel_path.open("wb") as fh:
        shutil.copyfileobj(camaleom_excel.file, fh)

    org = azure_org or AZURE_ORG
    project = azure_project or AZURE_PROJECT
    team = azure_team or AZURE_TEAM
    db.save_profile(user["id"], org, project, team, diferenciador or "", (db.get_profile(user["id"]) or {}).get("camaleom_user") or "", None)

    params = {
        "excel_path": str(excel_path),
        "fecha_final": fecha_final_d,
        "dias_atras": int(dias_atras),
        "sprints_txt": sprints,
        "diferenciador": diferenciador,
        "azure_org": org,
        "azure_project": project,
        "azure_team": team,
    }
    job_id = jobs.start_job(user["id"], params)
    return {"job_id": job_id}


@app.get("/api/run/{job_id}/status")
def run_status(job_id: str, request: Request):
    user = require_user(request)
    job = jobs.get_job(job_id)
    if not job or job.get("user_id") != user["id"]:
        raise HTTPException(status_code=404, detail="Job no encontrado.")
    return {
        "state": job.get("state"),
        "last_lines": job.get("last_lines", []),
        "error": job.get("error"),
        "attempt": job.get("attempt", 0),
        "max_attempts": job.get("max_attempts", 1),
        "run_id": job.get("run_id"),
    }


# ---------- Runs (historial) ----------

@app.get("/api/runs")
def runs_list(request: Request):
    user = require_user(request)
    rows = db.list_runs(user["id"])
    for r in rows:
        r["created_at"] = r["created_at"].isoformat() if r.get("created_at") else None
        r["periodo_inicio"] = r["periodo_inicio"].isoformat() if r.get("periodo_inicio") else None
        r["periodo_fin"] = r["periodo_fin"].isoformat() if r.get("periodo_fin") else None
    return {"runs": rows}


@app.get("/api/runs/{run_id}")
def run_get(run_id: int, request: Request):
    user = require_user(request)
    run = db.get_run(user["id"], run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Ejecucion no encontrada.")
    data = run["data"]
    data["id"] = run["id"]
    data["created_at"] = run["created_at"].isoformat() if run.get("created_at") else None
    return data


@app.get("/api/runs/{run_id}/excel")
def run_excel(run_id: int, request: Request):
    user = require_user(request)
    xlsx = db.get_run_xlsx(user["id"], run_id)
    if not xlsx:
        raise HTTPException(status_code=404, detail="Excel no disponible.")
    return Response(
        content=xlsx,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="reporte_{run_id}.xlsx"'},
    )


# ---------- Chatbot Gemini ----------

@app.post("/api/chat")
async def chat(request: Request):
    user = require_user(request)
    body = await request.json()
    run_id = body.get("run_id")
    pregunta = (body.get("question") or "").strip()
    historial = body.get("history") or []
    if not pregunta:
        raise HTTPException(status_code=400, detail="Escribe una pregunta.")
    run = db.get_run(user["id"], int(run_id)) if run_id else None
    if not run:
        raise HTTPException(status_code=404, detail="Primero genera o abre un reporte para poder preguntar sobre el.")
    try:
        answer = gemini.preguntar(run["data"], pregunta, historial)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc))
    return {"answer": answer}


@app.get("/health")
def health():
    return {"status": "ok"}


app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
