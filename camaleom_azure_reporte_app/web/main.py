from __future__ import annotations

from datetime import date, datetime, timedelta
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from ..azure_devops import AzureDevOpsClient
from ..config import AZURE_DEVOPS_PAT, AZURE_ORG, AZURE_PROJECT, AZURE_TEAM, APP_SECRET_KEY
from . import db, jobs

STATIC_DIR = Path(__file__).resolve().parent / "static"

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


@app.get("/", response_class=HTMLResponse)
def index(request: Request):
    if current_user(request):
        return FileResponse(STATIC_DIR / "app.html")
    return FileResponse(STATIC_DIR / "login.html")


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
        "profile": {
            "azure_org": profile.get("azure_org") or AZURE_ORG,
            "azure_project": profile.get("azure_project") or AZURE_PROJECT,
            "azure_team": profile.get("azure_team") or AZURE_TEAM,
            "azure_full_name": profile.get("azure_full_name") or "",
            "camaleom_user": profile.get("camaleom_user") or "",
            "camaleom_pass_saved": bool(profile.get("camaleom_pass_enc")),
        },
    }


@app.get("/api/azure/sprint-range")
def sprint_range(sprints: str, azure_org: str = "", azure_project: str = "", azure_team: str = ""):
    if not AZURE_DEVOPS_PAT:
        raise HTTPException(status_code=500, detail="El servidor no tiene configurado AZURE_DEVOPS_PAT.")
    org = azure_org or AZURE_ORG
    project = azure_project or AZURE_PROJECT
    team = azure_team or AZURE_TEAM
    cliente = AzureDevOpsClient(org, project, team, pat=AZURE_DEVOPS_PAT)
    sprint_nums = [int(s.strip()) for s in sprints.split(",") if s.strip()]
    if not sprint_nums:
        raise HTTPException(status_code=400, detail="Debes indicar al menos un sprint.")

    starts: list[date] = []
    finishes: list[date] = []
    detalle = []
    for numero in sprint_nums:
        iteracion = cliente.buscar_iteracion_sprint(numero)
        attrs = iteracion.get("attributes") or {}
        start_raw = attrs.get("startDate")
        finish_raw = attrs.get("finishDate")
        start = datetime.fromisoformat(start_raw.replace("Z", "+00:00")).date() if start_raw else None
        finish = datetime.fromisoformat(finish_raw.replace("Z", "+00:00")).date() if finish_raw else None
        if start:
            starts.append(start)
        if finish:
            finishes.append(finish)
        detalle.append({"sprint": numero, "start": start.isoformat() if start else None, "finish": finish.isoformat() if finish else None})

    return {
        "sprints": detalle,
        "fecha_inicio": min(starts).isoformat() if starts else None,
        "fecha_fin": max(finishes).isoformat() if finishes else None,
    }


@app.post("/api/run")
async def run_reporte(request: Request):
    user = require_user(request)
    body = await request.json()

    sprints = str(body.get("sprints") or "").strip()
    fecha_inicio = body.get("fecha_inicio") or ""
    fecha_fin = body.get("fecha_fin") or ""
    camaleom_fecha_inicio = body.get("camaleom_fecha_inicio") or fecha_inicio
    camaleom_fecha_fin = body.get("camaleom_fecha_fin") or fecha_fin
    azure_org = body.get("azure_org") or AZURE_ORG
    azure_project = body.get("azure_project") or AZURE_PROJECT
    azure_team = body.get("azure_team") or AZURE_TEAM
    azure_full_name = body.get("azure_full_name") or ""
    camaleom_user = body.get("camaleom_user") or ""
    camaleom_pass = body.get("camaleom_pass") or ""

    if not sprints or not fecha_inicio or not fecha_fin or not camaleom_user:
        raise HTTPException(status_code=400, detail="Faltan campos requeridos (sprint, fechas, usuario Camaleom).")

    profile = db.get_profile(user["id"])
    if not camaleom_pass:
        if not profile or not profile.get("camaleom_pass_enc"):
            raise HTTPException(status_code=400, detail="No hay contrasena de Camaleom guardada, ingresala.")
        camaleom_pass = db.decrypt(profile["camaleom_pass_enc"])
        db.save_profile(user["id"], azure_org, azure_project, azure_team, azure_full_name, camaleom_user, None)
    else:
        db.save_profile(user["id"], azure_org, azure_project, azure_team, azure_full_name, camaleom_user, camaleom_pass)

    job_id = jobs.start_job(
        sprints=sprints,
        fecha_inicio=fecha_inicio,
        fecha_fin=fecha_fin,
        camaleom_fecha_inicio=camaleom_fecha_inicio,
        camaleom_fecha_fin=camaleom_fecha_fin,
        camaleom_user=camaleom_user,
        camaleom_pass=camaleom_pass,
        azure_org=azure_org,
        azure_project=azure_project,
        azure_team=azure_team,
        azure_full_name=azure_full_name,
    )
    jobs._set(job_id, user_id=user["id"])
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
    }


@app.get("/api/run/{job_id}/report", response_class=HTMLResponse)
def run_report(job_id: str, request: Request):
    user = require_user(request)
    job = jobs.get_job(job_id)
    if not job or job.get("user_id") != user["id"]:
        raise HTTPException(status_code=404, detail="Job no encontrado.")
    if job.get("state") != "ok":
        raise HTTPException(status_code=409, detail="El reporte aun no esta listo.")
    return FileResponse(job["html_path"])


@app.get("/api/run/{job_id}/excel")
def run_excel(job_id: str, request: Request):
    user = require_user(request)
    job = jobs.get_job(job_id)
    if not job or job.get("user_id") != user["id"]:
        raise HTTPException(status_code=404, detail="Job no encontrado.")
    if job.get("state") != "ok" or not job.get("xlsx_path"):
        raise HTTPException(status_code=409, detail="El Excel aun no esta listo.")
    return FileResponse(job["xlsx_path"], filename=Path(job["xlsx_path"]).name)


@app.get("/health")
def health():
    return {"status": "ok"}


app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
