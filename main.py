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
    title="Fast Delivery – Hilla (Central Hub)",
    description="Real-Time UAV Fast Delivery System",
    version="4.0"
)

# ============================================================
# SERVICE AREA (HILLA)
# ============================================================

LAT_MIN, LAT_MAX = 32.1, 32.8
LON_MIN, LON_MAX = 44.1, 44.8

# ============================================================
# HUB (Central Launch Point)
# ============================================================

HUB_LAT = 32.4810
HUB_LON = 44.4320

# ============================================================
# UAV PARAMETERS
# ============================================================

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
    for i in range(15):  # عدد الطائرات
        UAVS[f"UAV_{i}"] = {
            "uav_id": f"UAV_{i}",
            "lat": HUB_LAT,
            "lon": HUB_LON,
            "status": "idle",      # idle | delivering | returning
            "target": None
        }

init_uavs()

# ============================================================
# GEOCODING (OpenStreetMap)
# ============================================================

def geocode_osm(place: str):
    url = "https://nominatim.openstreetmap.org/search"
    headers = {"User-Agent": "FastDelivery-Hilla/4.0"}

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
# DISTANCE (HAVERSINE)
# ============================================================

def haversine(lat1, lon1, lat2, lon2):
    R = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat/2)**2 + math.cos(math.radians(lat1)) \
        * math.cos(math.radians(lat2)) * math.sin(dlon/2)**2
    return 2 * R * math.asin(math.sqrt(a))

# ============================================================
# UAV SELECTION
# ============================================================

def get_free_uav():
    for u in UAVS.values():
        if u["status"] == "idle":
            return u
    return None

# ============================================================
# REAL-TIME UAV MOVEMENT
# ============================================================

def uav_movement_loop():
    while True:
        for u in UAVS.values():
            if u["target"] is None:
                continue

            t = u["target"]
            dist = haversine(u["lat"], u["lon"], t["lat"], t["lon"])

            if dist < 0.03:  # ~30 meters
                u["lat"] = t["lat"]
                u["lon"] = t["lon"]

                if u["status"] == "delivering":
                    u["target"] = {"lat": HUB_LAT, "lon": HUB_LON}
                    u["status"] = "returning"
                else:
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

    lat, lon = geocode_osm(order.place)
    if lat is None:
        return {
            "order_id": order.order_id,
            "status": "failed",
            "reason": "Location not found"
        }

    if not (LAT_MIN <= lat <= LAT_MAX and LON_MIN <= lon <= LON_MAX):
        return {
            "order_id": order.order_id,
            "status": "rejected",
            "reason": "Outside service area",
            "location": {"lat": lat, "lon": lon}
        }

    uav = get_free_uav()
    if uav is None:
        return {
            "order_id": order.order_id,
            "status": "rejected",
            "reason": "No available UAVs"
        }

    dist = haversine(uav["lat"], uav["lon"], lat, lon)
    eta_min = (dist / UAV_SPEED_KMH) * 60.0

    uav["target"] = {"lat": lat, "lon": lon}
    uav["status"] = "delivering"

    log_order(order.order_id, order.place, uav["uav_id"], eta_min)

    return {
        "order_id": order.order_id,
        "place": order.place,
        "assigned_uav": uav["uav_id"],
        "eta_minutes": round(eta_min, 1),
        "status": "accepted"
    }
