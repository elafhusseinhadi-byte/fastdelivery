
from fastapi import FastAPI
from pydantic import BaseModel
import requests
import math

app = FastAPI(title="Fast Delivery – Hilla (Geocoding Server)")

# ============================================================
# CONSTANTS – HILLA / BABYLON
# ============================================================

LAT_MIN = 32.1
LON_MIN = 44.1

LAT_MAX = 32.8
LON_MAX = 44.8

GRID_KM = 5
KM_PER_DEG_LAT = 111
KM_PER_DEG_LON = 94

# ============================================================
# DATA MODELS
# ============================================================

class Order(BaseModel):
    order_id: int
    place: str   # اسم الشارع أو المنطقة

# ============================================================
# GEOCODING – OpenStreetMap (Nominatim)
# ============================================================

def geocode_osm(place_name: str):
    url = "https://nominatim.openstreetmap.org/search"
    params = {
        "q": place_name + " الحلة العراق",
        "format": "json",
        "limit": 1
    }

    headers = {
        "User-Agent": "FastDelivery-Hilla/1.0"
    }

    r = requests.get(url, params=params, headers=headers, timeout=10)

    if r.status_code != 200:
        return None, None

    data = r.json()
    if not data:
        return None, None

    lat = float(data[0]["lat"])
    lon = float(data[0]["lon"])
    return lat, lon

# ============================================================
# GRID COMPUTATION
# ============================================================

def latlon_to_grid(lat, lon):
    x = (lon - LON_MIN) * KM_PER_DEG_LON
    y = (lat - LAT_MIN) * KM_PER_DEG_LAT

    gx = int(x // GRID_KM)
    gy = int(y // GRID_KM)

    return gx, gy

# ============================================================
# API ENDPOINTS
# ============================================================

@app.get("/")
def root():
    return {"service": "Fast Delivery – Hilla", "status": "running"}

@app.post("/order")
def create_order(order: Order):

    # 1) Geocoding
    lat, lon = geocode_osm(order.place)

    if lat is None:
        return {
            "order_id": order.order_id,
            "status": "failed",
            "reason": "Location not found"
        }

    # 2) Check if inside Hilla
    if not (LAT_MIN <= lat <= LAT_MAX and LON_MIN <= lon <= LON_MAX):
        return {
            "order_id": order.order_id,
            "status": "rejected",
            "reason": "Outside Hilla service area",
            "location": {"lat": lat, "lon": lon}
        }

    # 3) Grid
    gx, gy = latlon_to_grid(lat, lon)

    # 4) Assign UAV (1 UAV per Grid)
    assigned_uav = f"UAV_{gx}_{gy}"

    return {
        "order_id": order.order_id,
        "input_place": order.place,
        "location": {"lat": lat, "lon": lon},
        "grid": [gx, gy],
        "assigned_uav": assigned_uav,
        "status": "accepted"
    }
