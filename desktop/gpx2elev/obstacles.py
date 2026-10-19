"""OpenStreetMap barrier crossings in GPX travel order.

Geometry is evaluated locally. Missing OSM data never means a route is safe.
Linear barriers must cross the trace; nearby point obstacles are uncertain.
"""
from collections import defaultdict
from dataclasses import dataclass
import hashlib
import json
import math
from pathlib import Path
import time

from .providers import Http, atomic_write

ENDPOINT = "https://overpass-api.de/api/interpreter"
MAX_BYTES = 16 * 1024 * 1024
TTL = 7 * 86400
MODES = ("foot", "bicycle", "motor_vehicle")
SOLID = {"fence", "wall", "city_wall", "hedge", "retaining_wall", "jersey_barrier"}
PASSAGES = {"gate", "lift_gate", "swing_gate", "kissing_gate", "stile", "entrance", "gap", "cycle_barrier"}
LABELS = {"fence": "Clôture", "wall": "Mur", "hedge": "Haie", "gate": "Portail",
          "lift_gate": "Barrière levante", "swing_gate": "Barrière pivotante", "stile": "Échalier",
          "kissing_gate": "Portillon", "bollard": "Borne", "cycle_barrier": "Chicane",
          "block": "Bloc", "chain": "Chaîne", "entrance": "Passage", "gap": "Ouverture"}


# Access keys from the most specific to the most general, for each mode.
ACCESS_KEYS = {"foot": ("foot", "access"), "bicycle": ("bicycle", "vehicle", "access"),
               "motor_vehicle": ("motor_vehicle", "vehicle", "access")}


def access(tags, mode, direction=None):
    for key in ACCESS_KEYS[mode]:
        if direction and f"{key}:{direction}" in tags:
            return tags[f"{key}:{direction}"]
        if key in tags:
            return tags[key]
    return None


def status(tags, mode, direction=None, parent=None):
    """Return blocked / uncertain / passable and a reason, never infer a gate is shut."""
    kind = tags.get("barrier", "entrance" if "entrance" in tags else "yes")
    if tags.get("entrance") == "no":
        return "blocked", "Entrée condamnée"
    if kind in ("no", "kerb", "flush", "lowered"):
        return "passable", "Passage autorisé"
    keys = ACCESS_KEYS[mode]
    combined = {**(parent or {}), **tags}
    # The obstacle's own access rules take precedence; the way supplies missing ones.
    source = tags if access(tags, mode, direction) is not None else (parent or {})
    value = access(source, mode, direction)
    rank = next((r for r, key in enumerate(keys) if direction and f"{key}:{direction}" in source or key in source),
                len(keys))
    conditions = [keys.index(k.split(":")[0]) for k in combined if k.split(":")[0] in keys and "conditional" in k]
    conditional_direction = {f"oneway:{mode}:conditional"} | ({"oneway:conditional", "oneway:vehicle:conditional"} if mode != "foot" else set())
    if value in ("no", "private", "use_sidepath"):
        # An explicit prohibition only yields to a condition on a key at least as specific as the one
        # that sets it: opening hours or a general access:conditional never lift foot=no.
        doubtful = any(r <= rank for r in conditions)
    else:
        doubtful = bool(conditions) or any(k in combined for k in conditional_direction) or bool(combined.get("opening_hours"))
    if doubtful:
        return "uncertain", "Accès soumis à des conditions ou horaires"
    directional = any(k.endswith((":forward", ":backward")) and k.split(":")[0] in keys for k in combined)
    oneway = (parent or {}).get(f"oneway:{mode}", (parent or {}).get("oneway") if mode != "foot" else None)
    if direction is None and (directional or oneway in ("yes", "1", "true", "-1")):
        return "uncertain", "Sens de la voie OSM indéterminé"
    if oneway in ("yes", "1", "true") and direction == "backward" or oneway == "-1" and direction == "forward":
        return "blocked", "Passage interdit dans ce sens"
    if value in ("no", "private", "use_sidepath"):
        return "blocked", "Accès interdit ou privé"
    if tags.get("entrance") in ("exit", "entrance", "emergency"):
        return "uncertain", "Entrée à usage ou sens limité"
    if tags.get("locked") == "yes":
        if mode != "motor_vehicle" and value in ("yes", "designated", "permissive"):
            return "uncertain", "Portail verrouillé, passage autorisé à confirmer"
        return "blocked", "Barrière verrouillée"
    if value in ("yes", "designated", "permissive", "official"):
        return "passable", "Passage autorisé"
    if value is not None:
        return "uncertain", "Accès limité ou à confirmer"
    if kind in ("entrance", "gap"):
        if "entrance" in tags and "barrier" not in tags:
            return "uncertain", "Ouverture cartographiée, accès à confirmer"
        return "passable", "Ouverture cartographiée"
    if kind in SOLID:
        return "blocked", "Obstacle linéaire traversé sans ouverture cartographiée"
    if mode == "motor_vehicle" and kind in {"bollard", "block", "stile", "kissing_gate", "cycle_barrier", "bus_trap", "sump_buster"}:
        return "blocked", "Obstacle physique pour ce mode de déplacement"
    if mode == "foot" and kind in {"bollard", "cycle_barrier", "stile", "kissing_gate", "cattle_grid"}:
        return "passable", "Passage piéton possible"
    return "uncertain", "Franchissement à vérifier sur place"


def project(point, origin):
    lat, lon = point
    delta = (lon - origin[1] + 180) % 360 - 180
    return delta * 111195.08 * max(.00001, math.cos(math.radians(origin[0]))), (lat - origin[0]) * 111195.08


def sub(a, b):
    return a[0] - b[0], a[1] - b[1]


def dot(a, b):
    return a[0] * b[0] + a[1] * b[1]


def nearest(p, a, b):
    v = sub(b, a)
    t = max(0., min(1., dot(sub(p, a), v) / (dot(v, v) or 1)))
    return math.hypot(p[0] - a[0] - t * v[0], p[1] - a[1] - t * v[1]), t


def crossing(a, b, c, d):
    v, w = sub(b, a), sub(d, c)
    def cross(x, y):
        return x[0] * y[1] - x[1] * y[0]
    den = cross(v, w)
    if abs(den) < 1e-8:  # Parallel or following the barrier.
        return None
    t, u = cross(sub(c, a), w) / den, cross(sub(c, a), v) / den
    return max(0., min(1., t)) if -1e-8 <= t <= 1 + 1e-8 and -1e-8 <= u <= 1 + 1e-8 else None


@dataclass
class Edge:
    segment: int
    index: int
    a: tuple
    b: tuple
    start: float
    length: float


class Route:
    def __init__(self, prepared, check=lambda: None):
        self.prepared = prepared
        self.origin = tuple(prepared.segments[0].coordinates[0])
        self.grid = defaultdict(list)
        self.offsets = []
        offset = 0.
        for s, segment in enumerate(prepared.segments):
            check()
            self.offsets.append(offset)
            points = [project(p, self.origin) for p in segment.coordinates]
            for i, (a, b) in enumerate(zip(points, points[1:])):
                if i % 10000 == 0:
                    check()
                edge = Edge(s, i, a, b, offset + float(segment.distance[i]), float(segment.distance[i + 1] - segment.distance[i]))
                for cell in self.cells(a, b):
                    self.grid[cell].append(edge)
            offset += float(segment.distance[-1])

    @staticmethod
    def bounds(a, b, margin):
        return (math.floor((min(a[0], b[0]) - margin) / 100), math.floor((max(a[0], b[0]) + margin) / 100),
                math.floor((min(a[1], b[1]) - margin) / 100), math.floor((max(a[1], b[1]) + margin) / 100))

    @classmethod
    def cells(cls, a, b, margin=0):
        left, right, bottom, top = cls.bounds(a, b, margin)
        return ((x, y) for x in range(left, right + 1) for y in range(bottom, top + 1))

    def candidates(self, a, b, margin=8):
        left, right, bottom, top = self.bounds(a, b, margin)
        cells = self.cells(a, b, margin)
        # A full OSM way can extend far beyond the query corridor.
        if (right - left + 1) * (top - bottom + 1) > len(self.grid):
            cells = (c for c in self.grid if left <= c[0] <= right and bottom <= c[1] <= top)
        seen = set()
        for cell in cells:
            for edge in self.grid.get(cell, ()):
                key = edge.segment, edge.index
                if key not in seen:
                    seen.add(key)
                    yield edge


def geometry(element):
    raw = [element] if element.get("type") == "node" else element.get("geometry", [])
    points = []
    for p in raw:
        if not isinstance(p, dict) or not isinstance(p.get("lat"), (int, float)) or not isinstance(p.get("lon"), (int, float)):
            return []
        if not (math.isfinite(p["lat"]) and math.isfinite(p["lon"]) and -90 <= p["lat"] <= 90 and -180 <= p["lon"] <= 180):
            return []
        points.append((p["lat"], p["lon"]))
    return points


def analyze(prepared, elements, mode="foot", reverse=False, check=lambda: None):
    if mode not in MODES or type(reverse) is not bool:
        raise ValueError("Options des obstacles invalides.")
    route = Route(prepared, check)
    parents, openings = defaultdict(list), []
    for el in elements:
        check()
        if el.get("type") == "way" and "highway" in el.get("tags", {}):
            for i, node in enumerate(el.get("nodes", [])):
                parents[node].append((el, i))
        if el.get("type") == "node" and el.get("tags", {}).get("entrance") != "no" and el.get("tags", {}).get("barrier", "entrance" if "entrance" in el.get("tags", {}) else "") in PASSAGES and geometry(el):
            openings.append((el, project(geometry(el)[0], route.origin)))
    events = []

    def add(el, edge, t, separation=0., linear=False, obstacle_a=None, obstacle_b=None):
        tags = el.get("tags", {})
        p = (edge.a[0] + t * (edge.b[0] - edge.a[0]), edge.a[1] + t * (edge.b[1] - edge.a[1]))
        if linear and any(math.dist(point, p) <= 3 and (n["id"] in el.get("nodes", []) or nearest(point, obstacle_a, obstacle_b)[0] <= .5)
                          for n, point in openings):
            return
        contexts = []
        for road, index in parents.get(el.get("id"), []) if el["type"] == "node" else ():
            geom = geometry(road)
            if len(geom) != len(road.get("nodes", [])) or len(geom) < 2:
                continue
            a = project(geom[max(0, index - 1)], route.origin)
            b = project(geom[min(len(geom) - 1, index + 1)], route.origin)
            v, w = sub(edge.b, edge.a), sub(b, a)
            alignment = dot(v, w) / (math.hypot(*v) * math.hypot(*w) or 1)
            if abs(alignment) >= .5:
                direction = "forward" if (alignment > 0) != reverse else "backward"
                contexts.append(status(tags, mode, direction, road.get("tags", {})))
        if contexts and all(c == contexts[0] for c in contexts):
            severity, reason = contexts[0]
        elif contexts:
            severity, reason = "uncertain", "Sens de la voie OSM indéterminé"
        else:
            severity, reason = status(tags, mode)
        if severity == "passable":
            return
        if separation > 3:
            severity, reason = "uncertain", "Obstacle proche de la trace, position à confirmer"
        if linear:
            # A tangential touch, start/end on a fence, or an unknown level is ambiguous.
            points = prepared.segments[edge.segment].coordinates
            before = project(points[max(0, edge.index - 1)], route.origin)
            after = project(points[min(len(points) - 1, edge.index + 2)], route.origin)
            w = sub(obstacle_b, obstacle_a)
            def side(q):
                v = sub(q, obstacle_a)
                return w[0] * v[1] - w[1] * v[0]
            if side(before) * side(after) >= 0 or tags.get("layer", "0") != "0":
                severity, reason = "uncertain", "Intersection ou niveau de franchissement à confirmer"
        distance = edge.start + t * edge.length
        segment = prepared.segments[edge.segment]
        a, b = segment.coordinates[edge.index:edge.index + 2]
        lon = (a[1] + t * ((b[1] - a[1] + 180) % 360 - 180) + 180) % 360 - 180
        kind = tags.get("barrier", "entrance")
        events.append({"osm_type": el["type"], "osm_id": el["id"], "kind": kind, "label": LABELS.get(kind, "Barrière"),
                       "name": tags.get("name", ""), "status": severity, "reason": reason,
                       "segment": edge.segment, "distance_m": prepared.length - distance if reverse else distance,
                       "route_distance_m": distance, "lat": float(a[0] + t * (b[0] - a[0])), "lon": float(lon),
                       "start_m": max(route.offsets[edge.segment], distance - 25),
                       "end_m": min(route.offsets[edge.segment] + float(segment.distance[-1]), distance + 25),
                       "tags": tags, "separation_m": separation, "_heading": sub(edge.b, edge.a)})

    for el in elements:
        check()
        tags = el.get("tags", {})
        if "barrier" not in tags and "entrance" not in tags:
            continue
        geom = geometry(el)
        if el.get("type") == "node" and geom:
            p = project(geom[0], route.origin)
            hits = []
            for edge in route.candidates(p, p):
                separation, t = nearest(p, edge.a, edge.b)
                if separation <= 8:
                    hits.append((edge, t, separation))
            groups = []
            for hit in sorted(hits, key=lambda h: h[0].start + h[1] * h[0].length):
                distance = hit[0].start + hit[1] * hit[0].length
                previous = groups[-1][-1] if groups else None
                if previous is None or hit[0].segment != previous[0].segment or distance - (previous[0].start + previous[1] * previous[0].length) > 15 or dot(sub(hit[0].b, hit[0].a), sub(previous[0].b, previous[0].a)) < 0:
                    groups.append([])
                groups[-1].append(hit)
            for group in groups:
                edge, t, separation = min(group, key=lambda h: h[2])
                add(el, edge, t, separation)
        elif el.get("type") == "way":
            for c, d in zip(geom, geom[1:]):
                a, b = project(c, route.origin), project(d, route.origin)
                for edge in route.candidates(a, b, 0):
                    t = crossing(edge.a, edge.b, a, b)
                    if t is not None:
                        add(el, edge, t, linear=True, obstacle_a=a, obstacle_b=b)
    events.sort(key=lambda e: e["distance_m"])
    unique, recent = [], {}
    for event in events:
        key = event["osm_type"], event["osm_id"], event["segment"]
        if key not in recent or event["distance_m"] - recent[key]["distance_m"] >= 10 or dot(event["_heading"], recent[key]["_heading"]) < 0:
            unique.append(event)
            recent[key] = event
    for event in unique:
        del event["_heading"]
    return unique


def simplify(points, tolerance=3, check=lambda: None):
    """Iterative Douglas-Peucker; preserve bends in the query corridor."""
    if len(points) <= 2:
        return points
    xy = [project(p, points[0]) for p in points]
    keep, stack = {0, len(points) - 1}, [(0, len(points) - 1)]
    while stack:
        check()
        first, last = stack.pop()
        if last <= first + 1:
            continue
        distance, index = max((nearest(xy[i], xy[first], xy[last])[0], i) for i in range(first + 1, last))
        if distance > tolerance:
            keep.add(index)
            stack.extend(((first, index), (index, last)))
    return [points[i] for i in sorted(keep)]


def queries(prepared, check=lambda: None):
    result = []
    for segment in prepared.segments:
        check()
        points = simplify([tuple(p) for p in segment.coordinates], check=check)
        for i in range(0, len(points) - 1, 79):
            coords = ",".join(f"{v:.7f}" for p in points[i:i + 80] for v in p)
            around = f"(around:30,{coords})"
            result.append('[out:json][timeout:25][maxsize:16777216];'
                          f'(node["barrier"]{around};way["barrier"]{around};node["entrance"]{around};)->.barriers;'
                          '(.barriers;way(bn.barriers)["highway"];node(w.barriers)["barrier"];node(w.barriers)["entrance"];);out body geom;')
            if len(result) > 64:
                raise ValueError("Trace trop complexe pour la vérification des obstacles (64 requêtes maximum).")
    return result


def validate_response(data):
    if not isinstance(data, dict) or data.get("remark") or not isinstance(data.get("elements"), list):
        raise ValueError("Réponse OSM incomplète : obstacles non vérifiés.")
    if any(not isinstance(e, dict) or e.get("type") not in ("node", "way") or type(e.get("id")) is not int
           or not isinstance(e.get("tags", {}), dict) or not all(isinstance(k, str) and isinstance(v, str) for k, v in e.get("tags", {}).items())
           or not geometry(e) for e in data["elements"]):
        raise ValueError("Réponse OSM invalide : obstacles non vérifiés.")
    return data


def cache_path(prepared, directory):
    key = hashlib.sha256(b"barriers-v1")
    for segment in prepared.segments:
        key.update(str(len(segment.coordinates)).encode())
        key.update(segment.coordinates.astype(">f8").tobytes())
    return Path(directory) / "tiles" / f"obstacles_{key.hexdigest()}.json"


def obtain(prepared, directory, online=True, mode="foot", reverse=False, cancel=None, refresh=False):
    if mode not in MODES or type(reverse) is not bool:
        raise ValueError("Options des obstacles invalides.")
    path, cached = cache_path(prepared, directory), None
    try:
        if path.stat().st_size <= MAX_BYTES:
            candidate = validate_response(json.loads(path.read_bytes()))
            if type(candidate.get("fetched_at")) in (int, float) and 0 < candidate["fetched_at"] <= time.time() + 60:
                cached = candidate
    except (OSError, ValueError, TypeError):
        pass
    http = Http(cancel)
    try:
        http.check()
        if cached and (not online or (not refresh and time.time() - cached["fetched_at"] < TTL)):
            data, from_cache = cached, True
        elif not online:
            return {"state": "unavailable", "message": "Hors connexion : obstacles non vérifiés.", "events": [], "mode": mode, "reverse": reverse}
        else:
            elements = {}
            for query in queries(prepared, http.check):
                http.check()
                raw, _ = http.fetch(ENDPOINT, form={"data": query}, timeout=(10, 40), max_bytes=MAX_BYTES)
                response = validate_response(json.loads(raw))
                for el in response["elements"]:
                    elements[el["type"], el["id"]] = el
                if len(elements) > 100000:
                    raise ValueError("Réponse OSM trop volumineuse : obstacles non vérifiés.")
            data = {"elements": list(elements.values()), "fetched_at": time.time()}
            raw = json.dumps(data, ensure_ascii=False).encode("utf-8")
            if len(raw) > MAX_BYTES:
                raise ValueError("Réponse OSM trop volumineuse : obstacles non vérifiés.")
            http.check()
            try:
                atomic_write(path, raw)
            except OSError:
                pass
            from_cache = False
        events = analyze(prepared, data["elements"], mode, reverse, http.check)
        return {"state": "ready", "events": events, "mode": mode, "reverse": reverse,
                "fetched_at": data["fetched_at"], "from_cache": from_cache, "stale": time.time() - data["fetched_at"] > TTL}
    finally:
        http.close()


def route_view(prepared):
    offset, segments = 0., []
    for segment in prepared.segments:
        segments.append([[float(p[0]), float(p[1]), offset + float(d)] for p, d in zip(segment.coordinates, segment.distance)])
        offset += float(segment.distance[-1])
    return {"segments": segments, "length_m": prepared.length}
