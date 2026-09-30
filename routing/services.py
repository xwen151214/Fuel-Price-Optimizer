import requests
from django.core.cache import cache
from functools import lru_cache

from .cache import geocode_local, LocalGeocodeError

NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
OSRM_URL = "https://router.project-osrm.org/route/v1/driving"
USER_AGENT = "fuel-route-assessment/1.0"
METERS_PER_MILE = 1609.344
CACHE_TTL = 60 * 60 * 24


class RoutingError(Exception):
    pass


def geocode(place: str, allow_remote_fallback: bool = False):
    try:
        return geocode_local(place)
    except LocalGeocodeError as e:
        if not allow_remote_fallback:
            raise RoutingError(str(e))

    key = "geo:" + place.strip().lower()
    hit = cache.get(key)
    if hit:
        return hit

    resp = requests.get(
        NOMINATIM_URL,
        params={"q": place, "format": "json", "limit": 1, "countrycodes": "us"},
        headers={"User-Agent": USER_AGENT},
        timeout=10,
    )
    resp.raise_for_status()
    data = resp.json()
    if not data:
        raise RoutingError(f"Could not find a USA location for: {place}")

    result = (float(data[0]["lat"]), float(data[0]["lon"]))
    cache.set(key, result, CACHE_TTL)
    return result


def get_route(start_ll, end_ll):
    (slat, slng), (elat, elng) = start_ll, end_ll
    key = f"route:{slat:.4f},{slng:.4f}:{elat:.4f},{elng:.4f}"
    hit = cache.get(key)
    if hit:
        return hit

    resp = requests.get(
        f"{OSRM_URL}/{slng},{slat};{elng},{elat}",
        params={"overview": "simplified", "geometries": "geojson"},
        timeout=20,
    )
    resp.raise_for_status()
    data = resp.json()
    if data.get("code") != "Ok":
        raise RoutingError("No driving route found between those locations")

    route = data["routes"][0]
    result = (route["geometry"]["coordinates"], route["distance"] / METERS_PER_MILE)
    cache.set(key, result, CACHE_TTL)
    return result


@lru_cache(maxsize=1)
def load_stations():
    from .models import FuelStation

    return tuple(
        {
            "truck_stop_name": s["truck_stop_name"],
            "city": s["city"],
            "state": s["state"],
            "retail_price": float(s["retail_price"]),
            "lat": s["lat"],
            "lng": s["lng"],
        }
        for s in FuelStation.objects.filter(lat__isnull=False, lng__isnull=False)
        .values("truck_stop_name", "city", "state", "retail_price", "lat", "lng")
    )