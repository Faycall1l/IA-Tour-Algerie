"""POI graph service: networkx-based tourist routing and tour optimization.

Builds a walkability graph connecting POIs within walking distance, then uses
fast graph algorithms for:
- Shortest walking path between any two POIs
- Time-bounded tour optimization (max POIs in X hours)
- POI clustering into walkable neighborhoods
- Betweenness centrality to find hub POIs
- Multi-POI route optimization (Christofides + 2-opt TSP)
"""

import math
from collections import defaultdict
from dataclasses import dataclass

import networkx as nx
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


WALK_SPEED_KMH = 4.5
WALK_TRANSFER_PENALTY_MIN = 5
DEFAULT_POI_DURATION_MIN = 90


def _haversine_m(lat1, lon1, lat2, lon2):
    R = 6_371_000
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (math.sin(dlat / 2) ** 2
         + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2))
         * math.sin(dlon / 2) ** 2)
    return R * 2 * math.asin(math.sqrt(a))


def _haversine_km(lat1, lon1, lat2, lon2):
    return _haversine_m(lat1, lon1, lat2, lon2) / 1000


def _walking_min(distance_m):
    return max(distance_m / (WALK_SPEED_KMH * 1000 / 60), 1.0)


@dataclass
class POINode:
    id: str
    name: str
    category: str
    subtype: str | None
    wilaya_id: int
    lat: float
    lon: float
    duration_min: int
    is_featured: bool
    fun_fact: str | None = None


@dataclass
class TourStop:
    poi_id: str
    poi_name: str
    category: str
    latitude: float
    longitude: float
    duration_min: int
    walk_from_prev_min: float
    cumulative_time_min: float
    fun_fact: str | None = None


@dataclass
class TourResult:
    stops: list[TourStop]
    total_pois: int
    total_walk_min: float
    total_visit_min: float
    total_time_min: float
    budget_hours: float
    wilaya_id: int
    walking_distance_km: float


@dataclass
class POICluster:
    cluster_id: int
    pois: list[POINode]
    center_lat: float
    center_lon: float
    radius_m: float
    walkable: bool


class POIGraphService:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._graph = nx.Graph()
            cls._instance._pois = {}
            cls._instance._wilaya_graphs = {}
            cls._instance._loaded = False
        return cls._instance

    def __init__(self):
        if hasattr(self, "_initialized"):
            return
        self._initialized = True

    @classmethod
    def reset(cls):
        if cls._instance:
            cls._instance._loaded = False
            cls._instance._graph.clear()
            cls._instance._pois.clear()
            cls._instance._wilaya_graphs.clear()

    async def load(self, db: AsyncSession):
        if self._loaded:
            return

        rows = await db.execute(text("""
            SELECT id, name, category, subtype, wilaya_id, latitude, longitude,
                   suggested_duration_min, is_featured, fun_fact
            FROM pois
            WHERE latitude IS NOT NULL AND longitude IS NOT NULL
              AND wilaya_id IS NOT NULL
              AND (is_featured = true OR category IN ('historical', 'natural', 'cultural', 'religious', 'museum', 'park'))
        """))

        for r in rows:
            pid = str(r[0])
            node = POINode(
                id=pid, name=r[1], category=r[2], subtype=r[3],
                wilaya_id=r[4], lat=r[5], lon=r[6],
                duration_min=r[7] or DEFAULT_POI_DURATION_MIN,
                is_featured=r[8] or False,
                fun_fact=r[9],
            )
            self._pois[pid] = node

        self._build_graph()
        self._loaded = True

    def _build_graph(self):
        self._graph.clear()
        self._wilaya_graphs = {}

        for pid, node in self._pois.items():
            self._graph.add_node(pid, **{
                "wilaya_id": node.wilaya_id,
                "lat": node.lat,
                "lon": node.lon,
                "category": node.category,
                "duration_min": node.duration_min,
                "is_featured": node.is_featured,
            })

        wilaya_pois: dict[int, list[str]] = defaultdict(list)
        for pid, node in self._pois.items():
            wilaya_pois[node.wilaya_id].append(pid)

        for w_id, poi_ids in wilaya_pois.items():
            if len(poi_ids) < 2:
                continue

            coords = [(pid, self._pois[pid].lat, self._pois[pid].lon) for pid in poi_ids]
            grid = defaultdict(list)
            cell_size = 0.01
            for pid, lat, lon in coords:
                row = int(lat / cell_size)
                col = int(lon / cell_size)
                grid[(row, col)].append(pid)

            nearby_pairs = set()
            for (row, col), cell_pois in grid.items():
                for dr in range(-2, 3):
                    for dc in range(-2, 3):
                        neighbor_cell = (row + dr, col + dc)
                        if neighbor_cell in grid:
                            for p1 in cell_pois:
                                for p2 in grid[neighbor_cell]:
                                    if p1 < p2:
                                        nearby_pairs.add((p1, p2))

            for p1, p2 in nearby_pairs:
                n1 = self._pois[p1]
                n2 = self._pois[p2]
                dist_m = _haversine_m(n1.lat, n1.lon, n2.lat, n2.lon)
                if dist_m < 5000:
                    walk_min = _walking_min(dist_m)
                    self._graph.add_edge(p1, p2, weight=walk_min, distance_m=dist_m)

            wilaya_graph = self._graph.subgraph(
                [pid for pid in poi_ids if pid in self._graph]
            ).copy()
            self._wilaya_graphs[w_id] = wilaya_graph

    async def shortest_path(
        self, db: AsyncSession, from_poi_id: str, to_poi_id: str
    ) -> list[str] | None:
        await self.load(db)
        try:
            return nx.shortest_path(self._graph, from_poi_id, to_poi_id, weight="weight")
        except (nx.NetworkXNoPath, nx.NodeNotFound):
            return None

    async def walking_time(
        self, db: AsyncSession, from_poi_id: str, to_poi_id: str
    ) -> float | None:
        await self.load(db)
        try:
            return nx.shortest_path_length(
                self._graph, from_poi_id, to_poi_id, weight="weight"
            )
        except (nx.NetworkXNoPath, nx.NodeNotFound):
            return None

    async def optimize_tour(
        self,
        db: AsyncSession,
        wilaya_id: int,
        budget_hours: float = 8.0,
        categories: list[str] | None = None,
        max_pois: int = 20,
        start_poi_id: str | None = None,
    ) -> TourResult | None:
        await self.load(db)

        candidates = [
            pid for pid, node in self._pois.items()
            if node.wilaya_id == wilaya_id
            and (not categories or node.category in categories)
        ]

        if not candidates:
            return None

        budget_min = budget_hours * 60

        if start_poi_id and start_poi_id in candidates:
            start_node = self._pois[start_poi_id]
        else:
            featured = [p for p in candidates if self._pois[p].is_featured]
            if featured:
                test_node = self._pois[featured[0]]
                nearest_dist = min(
                    _haversine_km(test_node.lat, test_node.lon, self._pois[p].lat, self._pois[p].lon)
                    for p in candidates if p != featured[0]
                ) if len(candidates) > 1 else 999
                if nearest_dist <= 5.0:
                    start_node = test_node
                else:
                    best_center = None
                    best_density = -1
                    for pid in candidates[:100]:
                        dists = sorted(
                            _haversine_km(self._pois[pid].lat, self._pois[pid].lon,
                                         self._pois[p].lat, self._pois[p].lon)
                            for p in candidates if p != pid
                        )
                        nearby = sum(1 for d in dists[:20] if d < 2.0)
                        if nearby > best_density:
                            best_density = nearby
                            best_center = pid
                    start_node = self._pois[best_center] if best_center else test_node
            else:
                start_node = self._pois[candidates[0]]

        def _dist(pid: str) -> float:
            n = self._pois[pid]
            return _haversine_km(start_node.lat, start_node.lon, n.lat, n.lon)

        cat_best: dict[str, str] = {}
        for pid in candidates:
            cat = self._pois[pid].category
            if cat not in cat_best or _dist(pid) < _dist(cat_best[cat]):
                cat_best[cat] = pid

        selected_map: dict[str, str] = {}
        for cat, pid in sorted(cat_best.items(), key=lambda x: _dist(x[1])):
            node = self._pois[pid]
            km = _dist(pid)
            walk = km * 12
            if walk + node.duration_min <= budget_min:
                selected_map[cat] = pid

        used_pids = set(selected_map.values())
        remaining = [p for p in candidates if p not in used_pids]

        total_used = sum(
            _dist(pid) * 12 + self._pois[pid].duration_min
            for pid in selected_map.values()
        )
        budget_left = budget_min - total_used

        last_pid = max(selected_map.values(), key=lambda p: _dist(p)) if selected_map else None

        from collections import Counter
        cat_counts = Counter(self._pois[pid].category for pid in used_pids)

        while len(used_pids) < max_pois and remaining and budget_left > 0:
            prev = self._pois[last_pid] if last_pid else start_node
            scored = []
            for pid in remaining:
                node = self._pois[pid]
                km = _haversine_km(prev.lat, prev.lon, node.lat, node.lon)
                walk = km * 12
                cost = walk + node.duration_min
                if cost > budget_left:
                    continue
                dup_penalty = 1.0 + 0.4 * cat_counts.get(node.category, 0)
                score = cost * dup_penalty
                scored.append((score, pid, cost))
            if not scored:
                break
            scored.sort(key=lambda x: x[0])
            _, best, cost = scored[0]
            remaining.remove(best)
            node = self._pois[best]
            budget_left -= cost
            used_pids.add(best)
            cat_counts[node.category] += 1
            last_pid = best

        if not used_pids:
            return None

        order = self._solve_tsp(list(used_pids))

        budget_min = budget_hours * 60
        stops = []
        cumulative = 0.0
        walk_total = 0.0
        prev_node = None

        for pid in order:
            node = self._pois[pid]
            walk_min = 0.0
            if prev_node:
                try:
                    walk_min = nx.shortest_path_length(
                        self._graph, prev_node.id, pid, weight="weight"
                    )
                except (nx.NetworkXNoPath, nx.NodeNotFound):
                    walk_min = _walking_min(
                        _haversine_m(prev_node.lat, prev_node.lon, node.lat, node.lon)
                    )

            arrival = cumulative + walk_min + node.duration_min
            if arrival > budget_min and stops:
                break

            cumulative += walk_min + node.duration_min
            walk_total += walk_min

            stops.append(TourStop(
                poi_id=pid,
                poi_name=node.name,
                category=node.category,
                latitude=node.lat,
                longitude=node.lon,
                duration_min=node.duration_min,
                walk_from_prev_min=round(walk_min, 1),
                cumulative_time_min=round(cumulative, 1),
                fun_fact=node.fun_fact,
            ))
            prev_node = node

        if not stops:
            return None

        walk_km = 0.0
        for i in range(1, len(stops)):
            n1 = self._pois[stops[i - 1].poi_id]
            n2 = self._pois[stops[i].poi_id]
            walk_km += _haversine_km(n1.lat, n1.lon, n2.lat, n2.lon)

        return TourResult(
            stops=stops,
            total_pois=len(stops),
            total_walk_min=round(walk_total, 1),
            total_visit_min=round(cumulative - walk_total, 1),
            total_time_min=round(cumulative, 1),
            budget_hours=budget_hours,
            wilaya_id=wilaya_id,
            walking_distance_km=round(walk_km, 2),
        )

    def _solve_tsp(self, poi_ids: list[str]) -> list[str]:
        if len(poi_ids) <= 1:
            return poi_ids

        if len(poi_ids) <= 8:
            return self._exact_tsp(poi_ids)

        return self._two_opt_tsp(poi_ids)

    def _exact_tsp(self, poi_ids: list[str]) -> list[str]:
        best_order = poi_ids[:]
        best_cost = self._tour_cost(poi_ids)

        def _permute(arr, l):
            nonlocal best_order, best_cost
            if l == len(arr):
                cost = self._tour_cost(arr)
                if cost < best_cost:
                    best_cost = cost
                    best_order = arr[:]
                return
            for i in range(l, len(arr)):
                arr[l], arr[i] = arr[i], arr[l]
                _permute(arr, l + 1)
                arr[l], arr[i] = arr[i], arr[l]

        arr = poi_ids[:]
        _permute(arr, 1)
        return best_order

    def _two_opt_tsp(self, poi_ids: list[str]) -> list[str]:
        order = poi_ids[:]
        improved = True
        while improved:
            improved = False
            for i in range(1, len(order) - 1):
                for j in range(i + 1, len(order)):
                    new_order = order[:i] + order[i:j + 1][::-1] + order[j + 1:]
                    if self._tour_cost(new_order) < self._tour_cost(order):
                        order = new_order
                        improved = True
        return order

    def _tour_cost(self, order: list[str]) -> float:
        if len(order) <= 1:
            return 0.0
        cost = 0.0
        for i in range(len(order) - 1):
            try:
                cost += nx.shortest_path_length(
                    self._graph, order[i], order[i + 1], weight="weight"
                )
            except (nx.NetworkXNoPath, nx.NodeNotFound):
                n1 = self._pois.get(order[i])
                n2 = self._pois.get(order[i + 1])
                if n1 and n2:
                    km = _haversine_km(n1.lat, n1.lon, n2.lat, n2.lon)
                    cost += km * 12 + 10
                else:
                    cost += 999
        return cost

    async def cluster_pois(
        self, db: AsyncSession, wilaya_id: int, radius_m: float = 1000.0
    ) -> list[POICluster]:
        await self.load(db)

        wilaya_pois = [
            self._pois[pid] for pid, node in self._pois.items()
            if node.wilaya_id == wilaya_id
        ]
        if not wilaya_pois:
            return []

        visited = set()
        clusters = []
        cid = 0

        for node in wilaya_pois:
            if node.id in visited:
                continue

            cluster_pois = [node]
            visited.add(node.id)

            for other in wilaya_pois:
                if other.id in visited:
                    continue
                dist = _haversine_m(node.lat, node.lon, other.lat, other.lon)
                if dist <= radius_m:
                    cluster_pois.append(other)
                    visited.add(other.id)

            center_lat = sum(p.lat for p in cluster_pois) / len(cluster_pois)
            center_lon = sum(p.lon for p in cluster_pois) / len(cluster_pois)
            max_radius = max(
                _haversine_m(center_lat, center_lon, p.lat, p.lon)
                for p in cluster_pois
            ) if len(cluster_pois) > 1 else 0

            clusters.append(POICluster(
                cluster_id=cid,
                pois=cluster_pois,
                center_lat=center_lat,
                center_lon=center_lon,
                radius_m=max_radius,
                walkable=max_radius < radius_m,
            ))
            cid += 1

        clusters.sort(key=lambda c: len(c.pois), reverse=True)
        return clusters

    async def hub_pois(
        self, db: AsyncSession, wilaya_id: int, top_n: int = 10
    ) -> list[dict]:
        await self.load(db)

        wilaya_graph = self._wilaya_graphs.get(wilaya_id)
        if not wilaya_graph or len(wilaya_graph) < 3:
            return [
                {
                    "poi_id": pid,
                    "name": self._pois[pid].name,
                    "category": self._pois[pid].category,
                    "betweenness": 0.0,
                    "degree": 0,
                }
                for pid in sorted(
                    [p for p, n in self._pois.items() if n.wilaya_id == wilaya_id],
                    key=lambda p: self._pois[p].is_featured,
                    reverse=True,
                )[:top_n]
            ]

        betweenness = nx.betweenness_centrality(wilaya_graph, weight="weight")
        degree = dict(wilaya_graph.degree())

        ranked = sorted(
            betweenness.keys(),
            key=lambda pid: (betweenness[pid], degree[pid]),
            reverse=True,
        )

        return [
            {
                "poi_id": pid,
                "name": self._pois[pid].name,
                "category": self._pois[pid].category,
                "betweenness": round(betweenness[pid], 4),
                "degree": degree[pid],
            }
            for pid in ranked[:top_n]
        ]
