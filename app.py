import os, requests
from typing import List, Optional
from fastapi import FastAPI, Request, Form, Query
from fastapi.responses import HTMLResponse, FileResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from dotenv import load_dotenv
from generator import generate

load_dotenv()
app = FastAPI()
app.mount("/static", StaticFiles(directory="static"), name="static")

import os
os.makedirs("output", exist_ok=True)
from fastapi.staticfiles import StaticFiles
app.mount("/output", StaticFiles(directory="output"), name="output")
templates = Jinja2Templates(directory="templates")

@app.get("/", response_class=HTMLResponse)
def index(request: Request,
          start_city: str = "", start_lat: float | None = None, start_lon: float | None = None,
          end_city: str = "", end_lat: float | None = None, end_lon: float | None = None):
    return templates.TemplateResponse("index.html", {"request": request,
                                                     "start_city": start_city or "", "start_lat": start_lat or "", "start_lon": start_lon or "",
                                                     "end_city": end_city or "", "end_lat": end_lat or "", "end_lon": end_lon or ""})

@app.get("/invert")
def invert(start_city: str, start_lat: float, start_lon: float,
           end_city: str, end_lat: float, end_lon: float):
    # Swap start and end then redirect to index with query params
    return RedirectResponse(url=f"/?start_city={end_city}&start_lat={end_lat}&start_lon={end_lon}"
                                f"&end_city={start_city}&end_lat={start_lat}&end_lon={start_lon}")

@app.get("/geocode")
def geocode(q: str = Query(..., min_length=2)):
    url = "https://nominatim.openstreetmap.org/search"
    params = {"q": q, "format":"json", "addressdetails": 1, "limit": 5}
    headers = {"User-Agent":"roadbook-app/1.0"}
    r = requests.get(url, params=params, headers=headers, timeout=15)
    r.raise_for_status()
    data = r.json()
    results = [{
        "label": d.get("display_name"),
        "lat": float(d["lat"]),
        "lon": float(d["lon"])
    } for d in data]
    return JSONResponse(results)

@app.post("/generate", response_class=HTMLResponse)
async def generate_route(
    request: Request,
    start_city: str = Form(...),
    start_lat: float = Form(...),
    start_lon: float = Form(...),
    end_city: str   = Form(...),
    end_lat: float  = Form(...),
    end_lon: float  = Form(...),
    start_date: str = Form(...),
    end_date: str   = Form(...),
    vehicle: str    = Form("voiture"),             # voiture | moto
    routing_mode: str = Form("rapide"),            # rapide | decouverte | sinueux
    day_start: str  = Form("08:30"),
    day_end: str    = Form("19:00"),
    max_drive: int  = Form(120),
    style: str      = Form("culture_nature"),
    stop_name: Optional[List[str]] = Form(None),
    stop_lat: Optional[List[str]]  = Form(None),
    stop_lon: Optional[List[str]]  = Form(None),
):
    waypoints = [ {"name": start_city, "lat": float(start_lat), "lon": float(start_lon)} ]
    if stop_name and stop_lat and stop_lon:
        for n, la, lo in zip(stop_name, stop_lat, stop_lon):
            if n and la and lo:
                try:
                    waypoints.append({"name": n, "lat": float(la), "lon": float(lo)})
                except ValueError:
                    continue
    waypoints.append({"name": end_city, "lat": float(end_lat), "lon": float(end_lon)})

    cfg = {
        "title": f"Roadbook {start_city} → {end_city} ({start_date} → {end_date})",
        "day_start": day_start,
        "day_end": day_end,
        "max_drive_block_minutes": max_drive,
        "base": {"name": end_city, "lat": float(end_lat), "lon": float(end_lon)},
        "vehicle": vehicle,
        "routing_mode": routing_mode,
        "days": [
            {
                "label": f"{start_city} → {end_city} (avec arrêts personnalisés)" if len(waypoints)>2 else f"{start_city} → {end_city}",
                "intro": "Trajet optimisé avec vos préférences : véhicule et mode de parcours. Segments ≤ 2h, pauses intégrées si nécessaire.",
                "waypoints": waypoints,
                "lunch_hint": "Pause sur une aire premium ou un bourg proche."
            },
            {
                "label": f"{end_city} – Centre historique",
                "intro": "Journée culturelle et pédestre. Sélection de sites patrimoniaux.",
                "waypoints": [
                    {"name": end_city, "lat": float(end_lat), "lon": float(end_lon)},
                    {"name": end_city, "lat": float(end_lat), "lon": float(end_lon)}
                ],
                "walks": [
                    {"near": end_city, "duration_min": 90, "route": "Boucle monuments majeurs, pas à pas."}
                ],
                "lunch_hint": "Brasserie chic au centre."
            }
        ]
    }
    paths = generate(cfg, out_dir="output")
    return templates.TemplateResponse("results.html", {
        "request": request,
        "title": cfg["title"],
        "subtitle": paths["subtitle"],
        "map_url": f"/output/{paths['map_url_suffix']}",
        "days": paths["days_render"],
        "zip_url": f"/download?path={paths['zip']}",
        "invert_url": f"/invert?start_city={start_city}&start_lat={start_lat}&start_lon={start_lon}&end_city={end_city}&end_lat={end_lat}&end_lon={end_lon}"
    })

@app.get("/download")
def download(path: str):
    filename = os.path.basename(path)
    return FileResponse(path, filename=filename, media_type="application/zip")

# --- Diags simples ---
from fastapi.responses import JSONResponse
import os, requests

# Crée le dossier output au démarrage (utile sur Render)
os.makedirs("output", exist_ok=True)

@app.get("/health")
def health():
    return {"status": "ok"}

@app.get("/debug/ors")
def debug_ors():
    key = os.getenv("ORS_API_KEY", "")
    masked = (key[:6] + "…" + key[-4:]) if key else ""
    try:
        # Appel réel à ORS (itinéraire Montpellier -> Lyon)
        r = requests.post(
            "https://api.openrouteservice.org/v2/directions/driving-car",
            headers={"Authorization": key, "Content-Type": "application/json", "User-Agent":"roadbook-app/1.0"},
            json={"coordinates": [[3.8777, 43.6117], [4.8357, 45.7640]]},
            timeout=15
        )
        # On renvoie le code et un extrait JSON (utile pour diagnostiquer 401/403)
        try:
            payload = r.json()
        except Exception:
            payload = {"text": r.text[:300]}
        return JSONResponse({
            "has_env_var": bool(key),
            "ors_key_masked": masked,
            "status_code": r.status_code,
            "response": payload
        })
    except Exception as e:
        return JSONResponse({
            "has_env_var": bool(key),
            "ors_key_masked": masked,
            "error": str(e)
        })
