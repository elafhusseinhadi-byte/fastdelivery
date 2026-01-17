from fastapi import FastAPI
from pydantic import BaseModel
import requests
import math
import csv
from datetime import datetime

# ============================================================
# APP
# ============================================================

app = FastAPI(
    title="Fast Delivery – Hilla (Babylon)",
    description="Fast Delivery Server using OpenStreetMap + UAV Integration",
    version="2.0"
)

# ============================================================
# CONSTANTS – HILLA (BABYLON)
# ============================================================

LAT_MIN = 32.1
LAT_MAX = 32.8
LON_MIN = 44.1
LON_MAX = 44.8

GRID_KM = 5.0
KM_PER_DEG_LAT = 111.0
KM_PER_DEG_LON = 94.0

UAV_SPEED_KMH = 40
UAV_SERVER = "https://drns-1.onrender.com"

# ============================================================
# DATA MODELS
# ============================================================

class Order(BaseModel):
    order_id: int
    place: str

# ============================================================
# OPENSTREETMAP GEOCODING
# ============================================================

def geocode_osm(place_name: str):
    url = "https://nominatim.openstreetmap.org/search"
    headers = {"User-Agent": "FastDelivery-Hilla/2.0"}

    queries = [
        f"{place_name} الحلة العراق",
        f"{place_name} الحلة",
        f"{place_name} بابل العراق",
        f"{place_name} Hilla Iraq",
        f"{place_name} Babylon Iraq"
    ]

    for q in queries:
        try:
            params = {"q": q, "format": "json", "limit": 1}
            r = requests.get(url, params=params, headers=headers, timeout=10)
            if r.status_code == 200 and r.json():
                lat = float(r.json()[0]["lat"])
                lon = float(r.json()[0]["lon"])
                return lat, lon
        except:
            continue

    return None, None

# ============================================================
# GRID COMPUTATION
# ============================================================

def latlon_to_grid(lat, lon):
    x_km = (lon - LON_MIN) * KM_PER_DEG_LON
    y_km = (lat - LAT_MIN) * KM_PER_DEG_LAT
    return int(x_km // GRID_KM), int(y_km // GRID_KM)

# ============================================================
# DISTANCE + ETA
# ============================================================

def haversine(lat1, lon1, lat2, lon2):
    R = 6371
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat/2)**2 + math.cos(math.radians(lat1)) \
        * math.cos(math.radians(lat2)) * math.sin(dlon/2)**2
    return 2 * R * math.asin(math.sqrt(a))

def estimate_eta(distance_km):
    return (distance_km / UAV_SPEED_KMH) * 60

# ============================================================
# UAV SERVER COMMUNICATION
# ============================================================

def send_to_uav(uav_id, lat, lon):
    payload = {
        "uav_id": uav_id,
        "target": {"lat": lat, "lon": lon}
    }
    try:
        requests.post(f"{UAV_SERVER}/assign", json=payload, timeout=5)
    except:
        pass

# ============================================================
# LOGGING
# ============================================================

def log_order(order_id, place, gx, gy, uav, eta):
    with open("orders_log.csv", "a", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow([
            datetime.now(),
            order_id,
            place,
            gx,
            gy,
            uav,
            round(eta, 2)
        ])

# ============================================================
# API ENDPOINTS
# ============================================================

@app.get("/")
def root():
    return {"service": "Fast Delivery – Hilla", "status": "running"}

@app.get("/healthz")
def health_check():
    return {"status": "ok"}

@app.post("/order")
def create_order(order: Order):

    # 1) Geocode
    lat, lon = geocode_osm(order.place)
    if lat is None:
        return {"order_id": order.order_id, "status": "failed", "reason": "Location not found"}

    # 2) Boundary check
    if not (LAT_MIN <= lat <= LAT_MAX and LON_MIN <= lon <= LON_MAX):
        return {
            "order_id": order.order_id,
            "status": "rejected",
            "reason": "Outside Hilla service area",
            "location": {"lat": lat, "lon": lon}
        }

    # 3) Grid
    gx, gy = latlon_to_grid(lat, lon)
    assigned_uav = f"UAV_{gx}_{gy}"

    # 4) ETA (نفترض UAV بمركز الـ Grid)
    uav_lat = LAT_MIN + (gy + 0.5) * GRID_KM / KM_PER_DEG_LAT
    uav_lon = LON_MIN + (gx + 0.5) * GRID_KM / KM_PER_DEG_LON
    distance_km = haversine(uav_lat, uav_lon, lat, lon)
    eta_min = estimate_eta(distance_km)

    # 5) Send mission to UAV server
    send_to_uav(assigned_uav, lat, lon)

    # 6) Log order
    log_order(order.order_id, order.place, gx, gy, assigned_uav, eta_min)

    return {
        "order_id": order.order_id,
        "input_place": order.place,
        "location": {"lat": lat, "lon": lon},
        "grid": [gx, gy],
        "assigned_uav": assigned_uav,
        "eta_minutes": round(eta_min, 1),
        "status": "accepted"
    }

# ============================================================
# RUN APP
# ============================================================

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=10000)
