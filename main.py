from fastapi import FastAPI
from pydantic import BaseModel
import requests
import math
import csv
import threading
import time
from datetime import datetime

# ============================================================
# APP
# ============================================================

app = FastAPI(
    title="Fast Delivery – Hilla (All-in-One)",
    description="Single server for customer orders, UAV management, movement, ETA, and monitoring",
    version="3.1"
)

# ============================================================
# CONSTANTS (HILLA)
# ============================================================

LAT_MIN, LAT_MAX = 32.1, 32.8
LON_MIN, LON_MAX = 44.1, 44.8

GRID_KM = 5.0
KM_PER_DEG_LAT = 111.0
KM_PER_DEG_LON = 94.0

UAV_SPEED_KMH = 40.0
STEP_TIME = 1.0  # seconds

# ============================================================
# DATA MODELS
# ============================================================

class Order(BaseModel):
    order_id: int
    place: str

# ============================================================
# GLOBAL UAV STATE
# ============================================================

UAVS = {}

def init_uavs():
    # one UAV per grid cell
    for gx in range(0, 10):
        for gy in range(0, 10):
            uav_id = f"UAV_{gx}_{gy}"
            lat = LAT_MIN + (gy + 0.5) * GRID_KM / KM_PER_DEG_LAT
            lon = LON_MIN + (gx + 0.5) * GRID_KM / KM_PER_DEG_LON
            UAVS[uav_id] = {
                "uav_id": uav_id,
                "lat": lat,
                "lon": lon,
                "status": "idle",
                "target": None
            }

init_uavs()

# ============================================================
# GEOCODING (OpenStreetMap)
# ============================================================

def geocode_osm(place: str):
    url = "https://nominatim.openstreetmap.org/search"
    headers = {"User-Agent": "FastDelivery-Hilla/3.1"}

    queries = [
        f"{place} الحلة العراق",
        f"{place} الحلة",
        f"{place} Babylon Iraq",
        f"{place} Hilla Iraq"
    ]

    for q in queries:
        try:
            r = requests.get(
                url,
                params={"q": q, "format": "json", "limit": 1},
                headers=headers,
                timeout=10
            )
            if r.status_code == 200 and r.json():
                lat = float(r.json()[0]["lat"])
                lon = float(r.json()[0]["lon"])
                return lat, lon
        except:
            continue

    return None, None

# ============================================================
# GRID
# ============================================================

def latlon_to_grid(lat, lon):
    gx = int(((lon - LON_MIN) * KM_PER_DEG_LON) // GRID_KM)
    gy = int(((lat - LAT_MIN) * KM_PER_DEG_LAT) // GRID_KM)
    return gx, gy

# ============================================================
# DISTANCE
# ============================================================

def haversine(lat1, lon1, lat2, lon2):
    R = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat/2)**2 + math.cos(math.radians(lat1)) \
        * math.cos(math.radians(lat2)) * math.sin(dlon/2)**2
    return 2 * R * math.asin(math.sqrt(a))

# ============================================================
# UAV MOVEMENT LOOP
# ============================================================

def uav_movement_loop():
    while True:
        for u in UAVS.values():
            if u["target"] is not None:
                t = u["target"]
                dist = haversine(u["lat"], u["lon"], t["lat"], t["lon"])

                if dist < 0.05:  # arrived (~50 m)
                    u["lat"] = t["lat"]
                    u["lon"] = t["lon"]
                    u["status"] = "idle"
                    u["target"] = None
                else:
                    step_km = (UAV_SPEED_KMH / 3600.0) * STEP_TIME
                    u["lat"] += (t["lat"] - u["lat"]) * step_km / dist
                    u["lon"] += (t["lon"] - u["lon"]) * step_km / dist

        time.sleep(STEP_TIME)

threading.Thread(target=uav_movement_loop, daemon=True).start()

# ============================================================
# LOGGING
# ============================================================

def log_order(order_id, place, uav_id, eta):
    with open("orders_log.csv", "a", newline="", encoding="utf-8") as f:
        csv.writer(f).writerow([
            datetime.now(),
            order_id,
            place,
            uav_id,
            round(eta, 2)
        ])

# ============================================================
# API ENDPOINTS
# ============================================================

@app.get("/")
def root():
    return {"status": "Fast Delivery Server Running"}

@app.get("/healthz")
def health_check():
    return {"status": "ok"}

@app.get("/uavs")
def get_uavs():
    return {"uavs": list(UAVS.values())}

@app.post("/order")
def create_order(order: Order):

    # 1) Geocode
    lat, lon = geocode_osm(order.place)
    if lat is None:
        return {
            "order_id": order.order_id,
            "status": "failed",
            "reason": "Location not found"
        }

    # 2) Boundary check
    if not (LAT_MIN <= lat <= LAT_MAX and LON_MIN <= lon <= LON_MAX):
        return {
            "order_id": order.order_id,
            "status": "rejected",
            "reason": "Outside service area",
            "location": {"lat": lat, "lon": lon}
        }

    # 3) Grid + UAV assignment
    gx, gy = latlon_to_grid(lat, lon)
    uav_id = f"UAV_{gx}_{gy}"
    uav = UAVS[uav_id]

    # 4) ETA
    dist = haversine(uav["lat"], uav["lon"], lat, lon)
    eta_min = (dist / UAV_SPEED_KMH) * 60.0

    # 5) Assign mission
    uav["target"] = {"lat": lat, "lon": lon}
    uav["status"] = "delivering"

    # 6) Log
    log_order(order.order_id, order.place, uav_id, eta_min)

    return {
        "order_id": order.order_id,
        "input_place": order.place,
        "location": {"lat": lat, "lon": lon},
        "grid": [gx, gy],
        "assigned_uav": uav_id,
        "eta_minutes": round(eta_min, 1),
        "status": "accepted"
    }
