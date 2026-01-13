from fastapi import FastAPI
from pydantic import BaseModel
import requests

# ============================================================
# APP
# ============================================================

app = FastAPI(
    title="Fast Delivery – Hilla (Babylon)",
    description="Fast Delivery Server using OpenStreetMap (Nominatim) + Grid-based UAV Assignment",
    version="1.0"
)

# ============================================================
# CONSTANTS – HILLA (BABYLON) BOUNDARY
# ============================================================

LAT_MIN = 32.1
LAT_MAX = 32.8
LON_MIN = 44.1
LON_MAX = 44.8

GRID_KM = 5.0
KM_PER_DEG_LAT = 111.0
KM_PER_DEG_LON = 94.0

# ============================================================
# DATA MODELS
# ============================================================

class Order(BaseModel):
    order_id: int
    place: str   # اسم الشارع / المنطقة

# ============================================================
# OPENSTREETMAP GEOCODING
# ============================================================

def geocode_osm(place_name: str):
    url = "https://nominatim.openstreetmap.org/search"
    params = {
        "q": f"{place_name} الحلة العراق",
        "format": "json",
        "limit": 1
    }
    headers = {
        "User-Agent": "FastDelivery-Hilla/1.0"
    }

    try:
        r = requests.get(url, params=params, headers=headers, timeout=10)
        if r.status_code != 200:
            return None, None

        data = r.json()
        if not data:
            return None, None

        lat = float(data[0]["lat"])
        lon = float(data[0]["lon"])
        return lat, lon

    except Exception:
        return None, None

# ============================================================
# GRID COMPUTATION
# ============================================================

def latlon_to_grid(lat, lon):
    x_km = (lon - LON_MIN) * KM_PER_DEG_LON
    y_km = (lat - LAT_MIN) * KM_PER_DEG_LAT

    gx = int(x_km // GRID_KM)
    gy = int(y_km // GRID_KM)

    return gx, gy

# ============================================================
# API ENDPOINTS
# ============================================================

@app.get("/")
def root():
    return {
        "service": "Fast Delivery – Hilla",
        "status": "running"
    }

@app.get("/healthz")
def health_check():
    return {"status": "ok"}

@app.post("/order")
def create_order(order: Order):

    # 1) Geocode address
    lat, lon = geocode_osm(order.place)

    if lat is None:
        return {
            "order_id": order.order_id,
            "status": "failed",
            "reason": "Location not found"
        }

    # 2) Check service boundary
    if not (LAT_MIN <= lat <= LAT_MAX and LON_MIN <= lon <= LON_MAX):
        return {
            "order_id": order.order_id,
            "status": "rejected",
            "reason": "Outside Hilla service area",
            "location": {"lat": lat, "lon": lon}
        }

    # 3) Grid calculation
    gx, gy = latlon_to_grid(lat, lon)

    # 4) Assign UAV (1 UAV per grid)
    assigned_uav = f"UAV_{gx}_{gy}"

    return {
        "order_id": order.order_id,
        "input_place": order.place,
        "location": {"lat": lat, "lon": lon},
        "grid": [gx, gy],
        "assigned_uav": assigned_uav,
        "status": "accepted"
    }

# ============================================================
# RUN APP (IMPORTANT FOR RENDER)
# ============================================================

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=10000)
