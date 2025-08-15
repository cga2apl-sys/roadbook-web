# Roadbook Web Pro — PDF + GPX + Carte (Autocomplete, Moto/Voiture, Inversion, Modes de route)

Application **FastAPI** pour créer des **roadbooks** : PDF (une page/jour), GPX (points), carte interactive, interface web avec **auto‑complétion** des villes, **arrêts personnalisés**, **moyen de transport (moto/voiture)**, **modes d’itinéraire** (Rapide/Découverte/Sinueux) et **inversion** Départ/Arrivée.

## 🚀 Démarrage local
```bash
python -m venv venv
source venv/bin/activate   # Windows: venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env       # (facultatif) ORS_API_KEY si vous voulez des trajets précis
uvicorn app:app --reload
```
Ouvrez http://127.0.0.1:8000

## 🔑 Clé OpenRouteService (optionnelle)
Sans clé, l’appli utilise une estimation (distance haversine, vitesse moyenne selon le mode).  
Avec clé (`ORS_API_KEY`), les trajets sont calculés avec OpenRouteService.

## 🧭 Modes d’itinéraire
- **Rapide** : `preference=fastest` (autoroutes autorisées)
- **Découverte** : `preference=fastest` + `avoid_features=["highways"]` (sans autoroute)
- **Sinueux** : `preference=shortest` + `avoid_features=["highways"]` (favorise les routes secondaires)
> ORS ne propose pas "départementales uniquement" ; le mode *Sinueux* est une approximation robuste.

## 🏍️ Moto / 🚗 Voiture
Le moteur ORS utilise le profil `driving-car`. Le choix moto/voiture est indiqué dans le PDF et l’UI ; le calcul reste `driving-car` (profil moto dédié non disponible côté ORS).

## ➕ Arrêts personnalisés
Ajoutez des étapes (Nom + Lat + Lon). Elles seront respectées **dans l’ordre** entre Départ et Arrivée.

## ↔ Inverser départ/arrivée
Bouton en haut de la page d’accueil et lien sur la page de résultat.  
Techniquement : redirection vers `/?start=...&end=...` avec les valeurs inversées.

## 📄 Exports
- **PDF** : `output/roadbook_*.pdf` (mise en page ReportLab, 1 page/jour)
- **GPX** : `output/points_*.gpx` (points uniquement)
- **Carte** : `output/carte_*.html` (Folium/Leaflet)
- **ZIP** : `output/pack_*.zip` (PDF + GPX + carte)

## 🌐 Déploiement
- **Render / Railway / VPS** : `uvicorn app:app --host=0.0.0.0 --port=$PORT`
- Nginx (optionnel) en reverse‑proxy vers l’appli pour votre domaine/HTTPS.

## 📁 Structure
```
.
├─ app.py
├─ generator.py
├─ requirements.txt
├─ .env.example
├─ templates/
│  ├─ base.html
│  ├─ index.html
│  └─ results.html
├─ static/
│  └─ style.css
└─ output/
```

## ⚠️ Notes
- Respect des règles : ≤ 2h entre tronçons, départ/arrivée quotidiennes configurables, pauses automatiques.  
- L’auto‑complétion utilise **Nominatim** (OpenStreetMap) via `/geocode` (5 résultats).  
- Personnalisez le **bandeau héro** (image moto) dans `static/style.css` (classe `.hero-illu`).

Bon voyage !
