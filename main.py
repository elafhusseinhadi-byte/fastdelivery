from fastapi import FastAPI
from pydantic import BaseModel
import requests
import math
import threading
import time

# ============================================================
# APP
# ============================================================

app = FastAPI(
    title="Fast Delivery – Grid Based UAV System",
    version="5.0"
)

# ============================================================
# HILLA BOUNDARY
# ============================================================

LAT_MIN, LAT_MAX = 32.1, 32.8
LON_MIN, LON_MAX = 44.1, 44.8

GRID_KM = 5.0
KM_LAT = 111.0
KM_LON = 94.0

UAV_SPEED_KMH = 40.0
STEP_TIME = 1.0

# ============================================================
# DATA MODEL
# ============================================================

class Order(BaseModel):
    order_id: int
    place: str

# ============================================================
# GLOBAL UAVS
# ============================================================

UAVS = {}

# ============================================================
# GRID FUNCTIONS
# ============================================================

def latlon_to_grid(lat, lon):
    gx = int(((lon - LON_MIN) * KM_LON) // GRID_KM)
    gy = int(((lat - LAT_MIN) * KM_LAT) // GRID_KM)
    return gx, gy

# ============================================================
# INIT UAVS (ONE PER GRID)
# ============================================================

def init_uavs():
    for gx in range(10):
        for gy in range(10):
            lat = LAT_MIN + (gy + 0.5) * GRID_KM / KM_LAT
            lon = LON_MIN + (gx + 0.5) * GRID_KM / KM_LON

            uav_id = f"UAV_{gx}_{gy}"
            UAVS[uav_id] = {
                "uav_id": uav_id,
                "lat": lat,
                "lon": lon,
                "home": {"lat": lat, "lon": lon},
                "status": "idle",
                "target": None
            }

init_uavs()

# ============================================================
# GEOCODING
# ============================================================

def geocode_osm(place):
    url = "https://nominatim.openstreetmap.org/search"
    headers = {"User-Agent": "FastDelivery-Grid"}

    queries = [
        f"{place} الحلة العراق",
        f"{place} الحلة",
        f"{place} Hilla Iraq"
    ]

    for q in queries:
        try:
            r = requests.get(url,
                params={"q": q, "format": "json", "limit": 1},
                headers=headers,
                timeout=10)
            if r.status_code == 200 and r.json():
                return float(r.json()[0]["lat"]), float(r.json()[0]["lon"])
        except:
            pass

    return None, None

# ============================================================
# DISTANCE
# ============================================================

def haversine(lat1, lon1, lat2, lon2):
    R = 6371.0
    dlat = math.radians(lat2-lat1)
    dlon = math.radians(lon2-lon1)
    a = math.sin(dlat/2)**2 + math.cos(math.radians(lat1)) \
        * math.cos(math.radians(lat2)) * math.sin(dlon/2)**2
    return 2*R*math.asin(math.sqrt(a))

# ============================================================
# REAL-TIME MOVEMENT
# ============================================================

def uav_movement_loop():
    while True:
        for u in UAVS.values():
            if u["target"] is None:
                continue

            t = u["target"]
            dist = haversine(u["lat"], u["lon"], t["lat"], t["lon"])

            if dist < 0.03:
                u["lat"] = t["lat"]
                u["lon"] = t["lon"]

                if u["status"] == "delivering":
                    u["target"] = u["home"]
                    u["status"] = "returning"
                else:
                    u["status"] = "idle"
                    u["target"] = None
            else:
                step = (UAV_SPEED_KMH/3600)*STEP_TIME
                u["lat"] += (t["lat"]-u["lat"])*step/dist
                u["lon"] += (t["lon"]-u["lon"])*step/dist

        time.sleep(STEP_TIME)

threading.Thread(target=uav_movement_loop, daemon=True).start()

# ============================================================
# API
# ============================================================

@app.get("/")
def root():
    return {"status": "Grid UAV Server Running"}

@app.get("/uavs")
def get_uavs():
    return {"uavs": list(UAVS.values())}

@app.post("/order")
def create_order(order: Order):

    lat, lon = geocode_osm(order.place)
    if lat is None:
        return {"status": "failed", "reason": "Location not found"}

    if not (LAT_MIN <= lat <= LAT_MAX and LON_MIN <= lon <= LON_MAX):
        return {"status": "rejected", "reason": "Outside service area"}

    gx, gy = latlon_to_grid(lat, lon)
    uav_id = f"UAV_{gx}_{gy}"
    uav = UAVS[uav_id]

    dist = haversine(uav["lat"], uav["lon"], lat, lon)
    eta = (dist / UAV_SPEED_KMH) * 60

    uav["target"] = {"lat": lat, "lon": lon}
    uav["status"] = "delivering"

    return {
        "order_id": order.order_id,
        "grid": [gx, gy],
        "assigned_uav": uav_id,
        "eta_minutes": round(eta, 2),
        "status": "accepted"
    }
