from fastapi import FastAPI
from pydantic import BaseModel
import requests, math, csv, threading, time
from datetime import datetime

# ============================================================
# APP
# ============================================================

app = FastAPI(
    title="Fast Delivery – Hilla (All-in-One Server)",
    version="3.0"
)

# ============================================================
# CONSTANTS
# ============================================================

LAT_MIN, LAT_MAX = 32.1, 32.8
LON_MIN, LON_MAX = 44.1, 44.8

GRID_KM = 5.0
KM_LAT = 111.0
KM_LON = 94.0

UAV_SPEED_KMH = 40
STEP_TIME = 1.0   # seconds

# ============================================================
# DATA MODELS
# ============================================================

class Order(BaseModel):
    order_id: int
    place: str

# ============================================================
# UAV STORAGE (GLOBAL STATE)
# ============================================================

UAVS = {}

def init_uavs():
    for gx in range(0, 10):
        for gy in range(0, 10):
            uav_id = f"UAV_{gx}_{gy}"
            lat = LAT_MIN + (gy + 0.5) * GRID_KM / KM_LAT
            lon = LON_MIN + (gx + 0.5) * GRID_KM / KM_LON
            UAVS[uav_id] = {
                "uav_id": uav_id,
                "lat": lat,
                "lon": lon,
                "status": "idle",
                "target": None
            }

init_uavs()

# ============================================================
# GEOCODING
# ============================================================

def geocode(place):
    url = "https://nominatim.openstreetmap.org/search"
    headers = {"User-Agent": "FastDelivery-Hilla/3.0"}
    q = f"{place} الحلة العراق"
    try:
        r = requests.get(url, params={"q": q, "format": "json", "limit": 1},
                         headers=headers, timeout=10)
        if r.json():
            return float(r.json()[0]["lat"]), float(r.json()[0]["lon"])
    except:
        pass
    return None, None

# ============================================================
# GRID
# ============================================================

def latlon_to_grid(lat, lon):
    gx = int(((lon - LON_MIN) * KM_LON) // GRID_KM)
    gy = int(((lat - LAT_MIN) * KM_LAT) // GRID_KM)
    return gx, gy

# ============================================================
# DISTANCE
# ============================================================

def haversine(lat1, lon1, lat2, lon2):
    R = 6371
    dlat = math.radians(lat2-lat1)
    dlon = math.radians(lon2-lon1)
    a = math.sin(dlat/2)**2 + math.cos(math.radians(lat1)) \
        * math.cos(math.radians(lat2)) * math.sin(dlon/2)**2
    return 2 * R * math.asin(math.sqrt(a))

# ============================================================
# UAV MOVEMENT LOOP
# ============================================================

def uav_loop():
    while True:
        for u in UAVS.values():
            if u["target"]:
                t = u["target"]
                d = haversine(u["lat"], u["lon"], t["lat"], t["lon"])
                if d < 0.05:
                    u["lat"], u["lon"] = t["lat"], t["lon"]
                    u["status"] = "idle"
                    u["target"] = None
                else:
                    step = (UAV_SPEED_KMH/3600) * STEP_TIME
                    u["lat"] += (t["lat"] - u["lat"]) * step / d
                    u["lon"] += (t["lon"] - u["lon"]) * step / d
        time.sleep(STEP_TIME)

threading.Thread(target=uav_loop, daemon=True).start()

# ============================================================
# LOGGING
# ============================================================

def log_order(order_id, place, uav, eta):
    with open("orders_log.csv", "a", newline="", encoding="utf-8") as f:
        csv.writer(f).writerow([
            datetime.now(), order_id, place, uav, round(eta, 2)
        ])

# ============================================================
# API
# ============================================================

@app.get("/")
def root():
    return {"status": "Fast Delivery Server Running"}

@app.get("/uavs")
def get_uavs():
    return {"uavs": list(UAVS.values())}

@app.post("/order")
def create_order(order: Order):
    lat, lon = geocode(order.place)
    if lat is None:
        return {"status": "failed", "reason": "Location not found"}

    gx, gy = latlon_to_grid(lat, lon)
    uav_id = f"UAV_{gx}_{gy}"
    uav = UAVS[uav_id]

    dist = haversine(uav["lat"], uav["lon"], lat, lon)
    eta = (dist / UAV_SPEED_KMH) * 60

    uav["target"] = {"lat": lat, "lon": lon}
    uav["status"] = "delivering"

    log_order(order.order_id, order.place, uav_id, eta)

    return {
        "order_id": order.order_id,
        "place": order.place,
        "assigned_uav": uav_id,
        "eta_minutes": round(eta,1),
        "location": {"lat": lat, "lon": lon},
        "status": "accepted"
    }
