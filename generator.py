import os, io, zipfile, math, requests, folium
from datetime import datetime
from dotenv import load_dotenv
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, PageBreak
from reportlab.lib.enums import TA_JUSTIFY

def ors_route(api_key, coords, profile="driving-car", mode="rapide"):
    import math, logging, requests

    # Secours local : Haversine + vitesse moyenne par mode (km/h)
    def fallback(a, b):
        R=6371.0
        la1,lo1,la2,lo2=map(math.radians,[a['lat'],a['lon'],b['lat'],b['lon']])
        dlat=la2-la1; dlon=lo2-lo1
        h=math.sin(dlat/2)**2+math.cos(la1)*math.cos(la2)*math.sin(dlon/2)**2
        d=2*R*math.asin(math.sqrt(h))
        speed = 90 if mode=='rapide' else (70 if mode=='decouverte' else 55)
        dur = (d/speed)*60.0
        return d, dur, []

    # Pas de clé → estimation immédiate
    if not api_key:
        logging.warning("ORS_API_KEY absente → fallback Haversine.")
        return fallback(coords[0], coords[1])

    url = f"https://api.openrouteservice.org/v2/directions/{profile}"
    body = {"coordinates": [[c["lon"], c["lat"]] for c in coords]}

    if mode == "rapide":
        body["preference"] = "fastest"
    elif mode == "decouverte":
        body["preference"] = "fastest"
        body["options"] = {"avoid_features": ["highways"]}
    elif mode == "sinueux":
        body["preference"] = "shortest"
        body["options"] = {"avoid_features": ["highways"]}
    else:
        body["preference"] = "fastest"

    headers = {"Authorization": api_key, "Content-Type":"application/json", "User-Agent":"roadbook-app/1.0"}

    try:
        r = requests.post(url, json=body, headers=headers, timeout=30)
        if r.status_code != 200:
            logging.warning("ORS HTTP %s: %s", r.status_code, r.text[:300])
            return fallback(coords[0], coords[1])

        data = r.json()
        if "features" in data and data["features"]:
            feat = data["features"][0]
            dist_km = feat["properties"]["summary"]["distance"]/1000.0
            dur_min = feat["properties"]["summary"]["duration"]/60.0
            geometry = feat.get("geometry", {}).get("coordinates", [])
            return dist_km, dur_min, geometry
        else:
            logging.warning("ORS sans 'features': %s", str(data)[:300])
            return fallback(coords[0], coords[1])

    except Exception as e:
        logging.exception("Appel ORS échoué → fallback: %s", e)
        return fallback(coords[0], coords[1])
    

def gpx_waypoints_xml(points):
    out = ['<?xml version="1.0" encoding="UTF-8"?>',
           '<gpx version="1.1" creator="Roadbook" xmlns="http://www.topografix.com/GPX/1/1">']
    for p in points:
        out.append(f'  <wpt lat="{p["lat"]}" lon="{p["lon"]}"><name>{p["name"]}</name></wpt>')
    out.append('</gpx>')
    return "\n".join(out)

def minutes(hhmm): 
    h, m = map(int, hhmm.split(":")); return h*60+m
def hhmm(mm): 
    return f"{mm//60:02d}:{mm%60:02d}"

def generate(cfg: dict, out_dir="output"):
    load_dotenv()
    ors_key = os.getenv("ORS_API_KEY") or cfg.get("ORS_API_KEY","")

    os.makedirs(out_dir, exist_ok=True)

    title      = cfg["title"]
    base       = cfg["base"]
    day_start  = minutes(cfg["day_start"])
    day_end    = minutes(cfg["day_end"])
    max_drive  = int(cfg.get("max_drive_block_minutes", 120))
    mode       = cfg.get("routing_mode","rapide")
    vehicle    = cfg.get("vehicle","voiture")
    profile    = "driving-car"  # ORS n'a pas de profil dédié moto ; on garde voiture côté API

    # Render banner subtitle
    subtitle = f"Voyage à {vehicle} – mode {mode}"

    # ----- Build content blocks per day (for PDF + web) -----
    days_render = []
    all_points = []
    fmap = folium.Map(location=[base["lat"], base["lon"]], zoom_start=6)

    for i, day in enumerate(cfg["days"], start=1):
        day_title = f'Jour {i} – {day["label"]}'
        day_intro = day.get("intro","")

        blocks = [{"type":"title", "text": day_title}, {"type":"intro", "text": day_intro}]
        t = day_start

        def add_stop(start, end, km, subtitle2, lines):
            head = f"{start} – {end} – {int(round(km))} km – {subtitle2} : "
            text = head + " ".join(lines)
            blocks.append({"type":"stop", "text": text})

        waypoints = day["waypoints"]
        for a, b in zip(waypoints[:-1], waypoints[1:]):
            dist, dur, _ = ors_route(ors_key, [a,b], profile=profile, mode=mode)
            if dur > max_drive:
                import math
                blocks_cnt = math.ceil(dur/max_drive)
                seg_dur = dur/blocks_cnt; seg_dist = dist/blocks_cnt
                for k in range(blocks_cnt):
                    start, end = hhmm(t), hhmm(t+int(seg_dur))
                    add_stop(start, end, seg_dist, f"Route (segment {k+1}/{blocks_cnt})",
                             ["Itinéraire respectant votre mode choisi.",
                              "Pause en fin de segment.",
                              "≤ 2h par tronçon.",
                              "Marge 5–10 min.",
                              "Suivi GPS conseillé."])
                    t += int(seg_dur) + 10
            else:
                start, end = hhmm(t), hhmm(t+int(dur))
                add_stop(start, end, dist, f'{a["name"]} → {b["name"]}',
                         ["Trajet optimisé sans zigzag.",
                          "Routes agréables privilégiées.",
                          "Pause brève si nécessaire.",
                          "Marge 5–10 min.",
                          "Conduite souple."])
                t += int(dur) + 10

            for w in day.get("walks", []):
                if w.get("near") == b["name"]:
                    wdur = int(w.get("duration_min", 45))
                    start, end = hhmm(t), hhmm(t+wdur)
                    add_stop(start, end, 2, f'Parcours pédestre – {b["name"]}',
                             [w.get("route","Boucle patrimoniale recommandée par l’OT."),
                              "Focus patrimoine/architecture.",
                              "Rythme confortable.",
                              "Sites emblématiques extérieurs.",
                              "Pause boisson / sanitaires."])
                    t += wdur + 10

            all_points.append({"name": b["name"], "lat": b["lat"], "lon": b["lon"]})
            folium.Marker([b["lat"], b["lon"]], tooltip=b["name"]).add_to(fmap)

        if 12*60 <= t <= 14*60:
            start, end = hhmm(t), hhmm(t+75)
            add_stop(start, end, 1, "Déjeuner (suggestion)",
                     [day.get("lunch_hint","Cuisine locale ; réservation conseillée en été."),
                      "Produits de saison / spécialités.",
                      "Alternative rapide si timing serré.",
                      "Hydratation / pause fraîcheur."])
            t += 80

        if t > day_end:
            add_stop(hhmm(t), hhmm(day_end), 0, "Ajustement planning",
                     ["Cumul visites/trajets > fenêtre journalière.",
                      "Réduire un arrêt l’après-midi ou avancer le départ.",
                      "Retour requis avant l’heure fixée.",
                      "Raccourci possible proposé.",
                      "Vérifier le lendemain."])

        days_render.append({"title": day_title, "blocks": blocks})

    # ----- Create PDF with ReportLab -----
    ts = datetime.now().strftime("%Y%m%d_%H%M")
    pdf_path = os.path.join(out_dir, f"roadbook_{ts}.pdf")

    doc = SimpleDocTemplate(pdf_path, pagesize=A4,
                            rightMargin=2*cm, leftMargin=2*cm, topMargin=2*cm, bottomMargin=2*cm)
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(name='Justify', alignment=TA_JUSTIFY, leading=14))

    story = [Paragraph(title, styles['Title']), Paragraph(subtitle, styles['Heading3']), Spacer(1, 12)]
    for day in days_render:
        story.append(Paragraph(day['title'], styles['Heading2']))
        for block in day['blocks']:
            if block['type'] in ('intro','stop'):
                story.append(Paragraph(block['text'], styles['Justify']))
                story.append(Spacer(1, 8))
        story.append(PageBreak())

    doc.build(story)

    # GPX (waypoints only)
    uniq = {}
    for p in all_points:
        uniq[(round(p["lat"],5), round(p["lon"],5), p["name"])] = p
    gpx_xml = gpx_waypoints_xml(list(uniq.values()))
    gpx_path = os.path.join(out_dir, f"points_{ts}.gpx")
    with open(gpx_path,"w",encoding="utf-8") as f: f.write(gpx_xml)

    # Carte Folium
    map_path = os.path.join(out_dir, f"carte_{ts}.html")
    folium.LayerControl().add_to(fmap)
    fmap.save(map_path)

    # ZIP
    zip_path = os.path.join(out_dir, f"pack_{ts}.zip")
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as z:
        z.write(pdf_path, os.path.basename(pdf_path))
        z.write(gpx_path,  os.path.basename(gpx_path))
        z.write(map_path,  os.path.basename(map_path))

    return {
        "pdf": pdf_path, "gpx": gpx_path, "map": map_path, "zip": zip_path,
        "days_render": days_render,
        "map_url_suffix": os.path.basename(map_path),
        "subtitle": subtitle,
    }
