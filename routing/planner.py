import numpy as np

EARTH_RADIUS_MI = 3958.8


def _haversine(lat1, lng1, lat2, lng2):
    lat1, lng1, lat2, lng2 = map(np.radians, (lat1, lng1, lat2, lng2))
    a = (
        np.sin((lat2 - lat1) / 2) ** 2
        + np.cos(lat1) * np.cos(lat2) * np.sin((lng2 - lng1) / 2) ** 2
    )
    return 2 * EARTH_RADIUS_MI * np.arcsin(np.sqrt(a))


def stations_on_route(coords, stations, corridor_miles=10.0, spacing_miles=0.5):
    pts = np.asarray(coords, dtype=float)
    lng, lat = pts[:, 0], pts[:, 1]
    seg = _haversine(lat[:-1], lng[:-1], lat[1:], lng[1:])
    cum = np.concatenate(([0.0], np.cumsum(seg)))

    keep = np.unique(np.searchsorted(cum, np.arange(0, cum[-1], spacing_miles)))
    keep = np.unique(np.append(keep, len(cum) - 1))
    r_lat, r_lng, r_mile = lat[keep], lng[keep], cum[keep]

    if not stations:
        return []

    pad = corridor_miles / 69.0 + 0.05
    s_lat = np.array([s["lat"] for s in stations], dtype=float)
    s_lng = np.array([s["lng"] for s in stations], dtype=float)
    box = (
        (s_lat >= r_lat.min() - pad) & (s_lat <= r_lat.max() + pad)
        & (s_lng >= r_lng.min() - pad * 1.5) & (s_lng <= r_lng.max() + pad * 1.5)
    )
    idxs = np.flatnonzero(box)

    result = []
    for start in range(0, len(idxs), 200):
        chunk = idxs[start:start + 200]
        d = _haversine(
            s_lat[chunk][:, None], s_lng[chunk][:, None], r_lat[None, :], r_lng[None, :]
        )
        nearest = d.argmin(axis=1)
        best = d[np.arange(len(chunk)), nearest]
        for i, j, dist in zip(chunk, nearest, best):
            if dist <= corridor_miles:
                result.append({**stations[i], "mile": float(r_mile[j]),
                               "off_route_miles": float(dist)})

    result.sort(key=lambda s: s["mile"])
    return result


def plan_fuel(stations, total_miles, range_miles=500.0, mpg=10.0):
    sts = sorted(stations, key=lambda s: s["mile"])
    pos, fuel, cur = 0.0, range_miles, None
    stops, cost = [], 0.0

    def buy_at(station, miles_of_fuel):
        nonlocal cost
        if miles_of_fuel <= 1e-9:
            return 0.0
        gallons = miles_of_fuel / mpg
        spent = gallons * station["retail_price"]
        cost += spent
        stops.append({**station, "gallons": round(gallons, 2),
                      "cost": round(spent, 2)})
        return miles_of_fuel

    while True:
        reach = pos + (fuel if cur is None else range_miles)
        window = [s for s in sts if pos < s["mile"] <= reach]
        bought = 0.0

        if cur is None:
            if total_miles <= reach:
                break
            if not window:
                raise ValueError("No fuel station within range of the start")
            target = min(window, key=lambda s: s["retail_price"])
        else:
            cheaper = next((s for s in window if s["retail_price"] < cur["retail_price"]), None)
            if total_miles <= reach and (cheaper is None or cheaper["mile"] > total_miles):
                buy_at(cur, total_miles - pos - fuel)
                break
            if cheaper:
                target = cheaper
                bought = buy_at(cur, max(0.0, target["mile"] - pos - fuel))
            else:
                if not window:
                    raise ValueError(f"No fuel station within {range_miles:.0f} miles after mile {pos:.0f}")
                target = min(window, key=lambda s: s["retail_price"])
                bought = buy_at(cur, range_miles - fuel)

        fuel += bought - (target["mile"] - pos)
        pos, cur = target["mile"], target

    gallons = sum(s["gallons"] for s in stops)
    return stops, round(cost, 2), round(gallons, 2)