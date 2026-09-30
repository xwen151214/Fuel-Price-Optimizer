import csv
import re
from functools import lru_cache

from django.conf import settings

STATE_NAME_TO_ABBR = {
    "alabama": "AL", "alaska": "AK", "arizona": "AZ", "arkansas": "AR",
    "california": "CA", "colorado": "CO", "connecticut": "CT", "delaware": "DE",
    "florida": "FL", "georgia": "GA", "hawaii": "HI", "idaho": "ID",
    "illinois": "IL", "indiana": "IN", "iowa": "IA", "kansas": "KS",
    "kentucky": "KY", "louisiana": "LA", "maine": "ME", "maryland": "MD",
    "massachusetts": "MA", "michigan": "MI", "minnesota": "MN",
    "mississippi": "MS", "missouri": "MO", "montana": "MT", "nebraska": "NE",
    "nevada": "NV", "new hampshire": "NH", "new jersey": "NJ",
    "new mexico": "NM", "new york": "NY", "north carolina": "NC",
    "north dakota": "ND", "ohio": "OH", "oklahoma": "OK", "oregon": "OR",
    "pennsylvania": "PA", "rhode island": "RI", "south carolina": "SC",
    "south dakota": "SD", "tennessee": "TN", "texas": "TX", "utah": "UT",
    "vermont": "VT", "virginia": "VA", "washington": "WA",
    "west virginia": "WV", "wisconsin": "WI", "wyoming": "WY",
    "district of columbia": "DC",
}


class LocalGeocodeError(Exception):
    pass


@lru_cache(maxsize=1)
def _lookup():
    table = {}
    with open(settings.CITIES_CSV_PATH, encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            key = (row["city"].strip().lower(), row["state_id"].strip().upper())
            table[key] = (float(row["lat"]), float(row["lng"]))
    return table


def _parse(place: str):
    parts = [p.strip() for p in re.split(r",", place) if p.strip()]
    if len(parts) < 2:
        raise LocalGeocodeError(
            f"Give '{place}' as 'City, ST' (e.g. 'Los Angeles, CA')"
        )
    city, region = parts[0], parts[-1]
    region_key = region.lower()
    abbr = STATE_NAME_TO_ABBR.get(region_key, region.upper())
    return city, abbr


def geocode_local(place: str):
    city, state = _parse(place)
    hit = _lookup().get((city.lower(), state))
    if hit is None:
        raise LocalGeocodeError(f"Unknown city/state: {place}")
    return hit