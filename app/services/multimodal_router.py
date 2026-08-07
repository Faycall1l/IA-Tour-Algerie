"""Multi-modal inter-wilaya routing with generalized multi-hop.

Builds a connectivity graph from transport lines, then finds routes via
dynamic hubs using BFS up to 2 transfers. Each segment can use train,
flight, or intercity bus — whichever is available.

Combines:
1. WilayaDistance for driving data
2. TransportLine schedule/pricing for actual line data
3. TransportOperator for real contacts
4. TransitGraph Dijkstra for intra-city station-to-station routing
"""

import math
from collections import defaultdict
from dataclasses import dataclass, field

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.transit_routing import TransitGraph


def _haversine_km(lat1, lon1, lat2, lon2):
    earth_radius_km = 6371
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (
        math.sin(dlat / 2) ** 2
        + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2) ** 2
    )
    return earth_radius_km * 2 * math.asin(math.sqrt(a))


@dataclass
class OperatorContact:
    name: str
    mode: str
    phone: str | None = None
    website: str | None = None
    email: str | None = None


@dataclass
class RouteOption:
    mode: str
    line_name: str | None = None
    operator: str | None = None
    cost_dzd: float | None = None
    duration_min: int | None = None
    schedule: dict | None = None
    pricing: dict | None = None
    contacts: list[OperatorContact] = field(default_factory=list)
    segments: list[dict] = field(default_factory=list)
    transfers: int = 0


@dataclass
class Segment:
    """One leg of a multi-hop route."""

    mode: str
    line_name: str
    operator: str
    orig_wilaya: int
    dest_wilaya: int
    cost_dzd: float | None
    duration_min: int | None
    schedule: dict | None
    pricing: dict | None


class MultiModalRouter:
    def __init__(self):
        self._operators: list[dict] = []
        self._train_lines: list[dict] = []
        self._flight_lines: list[dict] = []
        self._all_intercity_lines: list[dict] = []  # train + flight + SOGRAL + taxi intercity
        self._graph = TransitGraph()
        self._loaded = False

        # Connectivity graph: adj[orig_wilaya][dest_wilaya] = list[Segment]
        self._adj: dict[int, dict[int, list[Segment]]] = defaultdict(lambda: defaultdict(list))
        # Hub ranking: wilaya_id → number of direct connections
        self._hub_ranking: list[int] = []

    async def load(self, db: AsyncSession):
        if self._loaded:
            return

        try:
            # Load operators
            rows = await db.execute(
                text("SELECT name, mode, phone, website, email FROM transport_operators")
            )
            self._operators = [dict(r._mapping) for r in rows]

            # Load ALL transport lines with multi-wilaya coverage
            # Excludes walking (pedestrian lines shouldn't cross wilaya boundaries)
            rows = await db.execute(
                text("""
                SELECT tl.id, tl.name, tl.operator, tl.mode, tl.schedule_info, tl.pricing_info,
                       array_agg(DISTINCT s.wilaya_id) as wilayas
                FROM transport_lines tl
                JOIN line_stops ls ON ls.line_id = tl.id
                JOIN stations s ON ls.station_id = s.id
                WHERE tl.mode != 'walking'
                GROUP BY tl.id, tl.name, tl.operator, tl.mode,
                         tl.schedule_info::text, tl.pricing_info::text
                HAVING COUNT(DISTINCT s.wilaya_id) >= 2
            """)
            )
            for r in rows:
                d = dict(r._mapping)
                wilayas = d["wilayas"] or []
                if len(wilayas) < 2:
                    continue
                mode = d["mode"]
                line_record = {
                    "id": d["id"],
                    "name": d["name"],
                    "operator": d["operator"],
                    "mode": mode,
                    "schedule_info": d["schedule_info"],
                    "pricing_info": d["pricing_info"],
                    "wilayas": wilayas,
                }
                if mode == "train":
                    self._train_lines.append(line_record)
                elif mode == "flight":
                    self._flight_lines.append(line_record)
                self._all_intercity_lines.append(line_record)

            # Build connectivity graph
            self._build_connectivity_graph()

            # Load transit graph for intra-city routing
            await self._graph.load(db)
        except Exception:
            self._operators = []
            self._train_lines = []
            self._flight_lines = []
            self._all_intercity_lines = []
            await db.rollback()

        self._loaded = True

    def _build_connectivity_graph(self):
        """Build adjacency list from transport lines."""
        for line in self._all_intercity_lines:
            wilayas = line["wilayas"]
            schedule = line["schedule_info"]
            pricing = line["pricing_info"]
            mode = line["mode"]
            duration = (
                int(schedule["travel_time_h"] * 60)
                if schedule and "travel_time_h" in schedule
                else None
            )

            # Determine cost based on mode
            cost = None
            if pricing:
                if mode == "train":
                    cost = pricing.get("2nd_class")
                elif mode == "flight":
                    cost = pricing.get("economy", 12000)
                elif mode == "bus":
                    cost = pricing.get("economy")
                elif mode == "taxi":
                    cost = pricing.get("per_person") or pricing.get("price_dzd")

            # Create segment for every pair of wilayas this line serves
            for i, w1 in enumerate(wilayas):
                for w2 in wilayas[i + 1 :]:
                    seg = Segment(
                        mode=mode,
                        line_name=line["name"],
                        operator=line["operator"],
                        orig_wilaya=w1,
                        dest_wilaya=w2,
                        cost_dzd=cost,
                        duration_min=duration,
                        schedule=schedule,
                        pricing=pricing,
                    )
                    self._adj[w1][w2].append(seg)
                    # Reverse direction
                    rev = Segment(
                        mode=mode,
                        line_name=line["name"],
                        operator=line["operator"],
                        orig_wilaya=w2,
                        dest_wilaya=w1,
                        cost_dzd=cost,
                        duration_min=duration,
                        schedule=schedule,
                        pricing=pricing,
                    )
                    self._adj[w2][w1].append(rev)

        # Rank hubs by connectivity
        hub_counts: dict[int, int] = defaultdict(int)
        for orig, dests in self._adj.items():
            hub_counts[orig] = len(dests)
        self._hub_ranking = sorted(hub_counts.keys(), key=lambda w: hub_counts[w], reverse=True)

    def _get_operator_contacts(self, mode: str) -> list[OperatorContact]:
        return [
            OperatorContact(
                name=o["name"],
                mode=o["mode"],
                phone=o["phone"],
                website=o["website"],
                email=o["email"],
            )
            for o in self._operators
            if o["mode"] == mode
        ]

    async def get_inter_wilaya_options(
        self, db: AsyncSession, origin_wilaya_id: int, dest_wilaya_id: int
    ) -> list[RouteOption]:
        await self.load(db)

        if origin_wilaya_id == dest_wilaya_id:
            return []

        # Get driving data
        a, b = (
            (origin_wilaya_id, dest_wilaya_id)
            if origin_wilaya_id < dest_wilaya_id
            else (dest_wilaya_id, origin_wilaya_id)
        )
        result = await db.execute(
            text(
                "SELECT * FROM wilaya_distances WHERE origin_wilaya_id = :a AND dest_wilaya_id = :b"
            ),
            {"a": a, "b": b},
        )
        wd = result.mappings().first()

        options: list[RouteOption] = []

        # ── Driving (always available if we have distance data) ──
        if wd:
            dist_km = wd["driving_distance_km"]
            drive_min = wd["driving_time_minutes"]
            bus_cost = round(dist_km * 6.0, -1)
            shared_taxi = round(dist_km * 10.0 / 4, -1)
            private_taxi = round(dist_km * 20.0, -1)
            options.append(
                RouteOption(
                    mode="driving",
                    cost_dzd=private_taxi,
                    duration_min=drive_min,
                    schedule={"type": "road", "road_class": wd.get("road_classification")},
                    pricing={
                        "bus": bus_cost,
                        "shared_taxi_per_person": shared_taxi,
                        "private_taxi": private_taxi,
                    },
                    contacts=self._get_operator_contacts("taxi"),
                )
            )

        # ── Direct connections (0 transfers) ──
        direct_segs = self._adj.get(origin_wilaya_id, {}).get(dest_wilaya_id, [])
        seen_modes = set()
        for seg in direct_segs:
            if seg.mode in seen_modes:
                continue  # one per mode
            seen_modes.add(seg.mode)
            options.append(self._seg_to_option(seg, transfers=0))

        # ── Multi-hop: 1 transfer (up to top 15 hubs) ──
        top_hubs = self._hub_ranking[:15]
        best_1hop: dict[str, RouteOption] = {}  # key: "mode_combo" → best option

        for hub in top_hubs:
            if hub in (origin_wilaya_id, dest_wilaya_id):
                continue
            segs1 = self._adj.get(origin_wilaya_id, {}).get(hub, [])
            segs2 = self._adj.get(hub, {}).get(dest_wilaya_id, [])
            if not segs1 or not segs2:
                continue

            for s1 in segs1:
                for s2 in segs2:
                    total_dur = (s1.duration_min or 120) + (s2.duration_min or 120) + 60
                    total_cost = (s1.cost_dzd or 0) + (s2.cost_dzd or 0)
                    key = f"{s1.mode}_{s2.mode}"
                    existing = best_1hop.get(key)
                    if existing is None or total_dur < (existing.duration_min or float("inf")):
                        best_1hop[key] = RouteOption(
                            mode=f"{s1.mode}+{s2.mode}",
                            line_name=f"{s1.line_name} → transfer ({self._wilaya_name(hub)}) → {s2.line_name}",  # noqa: E501
                            operator=f"{s1.operator}+{s2.operator}",
                            cost_dzd=total_cost if total_cost > 0 else None,
                            duration_min=total_dur,
                            transfers=1,
                            schedule={
                                "type": "1_hop",
                                "hub_wilaya": hub,
                                "seg1": s1.schedule,
                                "seg2": s2.schedule,
                            },
                            pricing={"total": total_cost, "seg1": s1.cost_dzd, "seg2": s2.cost_dzd},
                            contacts=self._get_operator_contacts(s1.mode),
                        )

        options.extend(best_1hop.values())

        # ── Multi-hop: 2 transfers (only for long distances > 500km with no direct/1-hop) ──
        if wd and wd["driving_distance_km"] > 500 and not direct_segs and not best_1hop:
            best_2hop = self._find_2hop(origin_wilaya_id, dest_wilaya_id, top_hubs)
            if best_2hop:
                options.append(best_2hop)

        return options

    def _find_2hop(self, orig: int, dest: int, hubs: list[int]) -> RouteOption | None:
        """Find best route with 2 transfers through hub1→hub2."""
        best: RouteOption | None = None
        # Only try top 8 hubs to keep complexity manageable
        for h1 in hubs[:8]:
            if h1 in (orig, dest):
                continue
            segs_a = self._adj.get(orig, {}).get(h1, [])
            if not segs_a:
                continue
            for h2 in hubs[:8]:
                if h2 in (orig, dest, h1):
                    continue
                segs_b = self._adj.get(h1, {}).get(h2, [])
                segs_c = self._adj.get(h2, {}).get(dest, [])
                if not segs_b or not segs_c:
                    continue
                # Pick best combo by duration
                for sa in segs_a:
                    for sb in segs_b:
                        for sc in segs_c:
                            total_dur = (
                                (sa.duration_min or 120)
                                + (sb.duration_min or 120)
                                + (sc.duration_min or 120)
                                + 120
                            )
                            total_cost = (
                                (sa.cost_dzd or 0) + (sb.cost_dzd or 0) + (sc.cost_dzd or 0)
                            )
                            candidate = RouteOption(
                                mode=f"{sa.mode}+{sb.mode}+{sc.mode}",
                                line_name=(
                                    f"{sa.line_name} → {self._wilaya_name(h1)} → "
                                    f"{sb.line_name} → {self._wilaya_name(h2)} → {sc.line_name}"
                                ),
                                cost_dzd=total_cost if total_cost > 0 else None,
                                duration_min=total_dur,
                                transfers=2,
                                pricing={"total": total_cost},
                                contacts=self._get_operator_contacts(sa.mode),
                            )
                            if best is None or total_dur < (best.duration_min or float("inf")):
                                best = candidate
        return best

    def _seg_to_option(self, seg: Segment, transfers: int = 0) -> RouteOption:
        return RouteOption(
            mode=seg.mode,
            line_name=seg.line_name,
            operator=seg.operator,
            cost_dzd=seg.cost_dzd,
            duration_min=seg.duration_min,
            schedule=seg.schedule,
            pricing=seg.pricing,
            contacts=self._get_operator_contacts(seg.mode),
            transfers=transfers,
        )

    def _wilaya_name(self, wid: int) -> str:
        names = {
            1: "Adrar",
            2: "Chlef",
            3: "Laghouat",
            4: "Oum El Bouaghi",
            5: "Batna",
            6: "Béjaïa",
            7: "Biskra",
            8: "Béchar",
            9: "Blida",
            10: "Bouira",
            11: "Tamanrasset",
            12: "Tébessa",
            13: "Tlemcen",
            14: "Tiaret",
            15: "Tizi Ouzou",
            16: "Alger",
            17: "Djelfa",
            18: "Jijel",
            19: "Sétif",
            20: "Saïda",
            21: "Skikda",
            22: "Sidi Bel Abbès",
            23: "Annaba",
            24: "Guelma",
            25: "Constantine",
            26: "Médéa",
            27: "Mostaganem",
            28: "M'sila",
            29: "Mascara",
            30: "Ouargla",
            31: "Oran",
            32: "El Bayadh",
            33: "Illizi",
            34: "Bordj Bou Arréridj",
            35: "Boumerdès",
            36: "El Tarf",
            37: "Tindouf",
            38: "Tissemsilt",
            39: "El Oued",
            40: "Khenchela",
            41: "Souk Ahras",
            42: "Tipaza",
            43: "Mila",
            44: "Aïn Defla",
            45: "Naâma",
            46: "Aïn Témouchent",
            47: "Ghardaïa",
            48: "Relizane",
            49: "Timimoun",
            50: "Béni Abbès",
            51: "Aïn Salah",
            52: "Aïn Guezzam",
            53: "Touggourt",
            54: "Djanet",
            55: "El M'Ghair",
            56: "El Meniaa",
            57: "Ouled Djellal",
            58: "Bordj Badji Mokhtar",
            59: "Timimoun",
            60: "Béni Abbès",
            61: "Tlemcen",
            62: "Biskra",
            63: "Tébessa",
            64: "M'sila",
            65: "Blida",
            66: "Bouira",
            67: "Médéa",
            68: "Djelfa",
        }
        return names.get(wid, f"Wilaya {wid}")

    def find_intra_city_route(
        self,
        from_lat: float,
        from_lng: float,
        to_lat: float,
        to_lng: float,
    ):
        """Find intra-city route via TransitGraph Dijkstra."""
        from_stations = self._graph.nearest_stations(from_lat, from_lng, limit=3)
        to_stations = self._graph.nearest_stations(to_lat, to_lng, limit=3)
        best = None
        best_cost = float("inf")
        for fs, _ in from_stations:
            for ts, _ in to_stations:
                route = self._graph.find_route(fs.id, ts.id)
                if (
                    route
                    and route.total_estimated_minutes
                    and route.total_estimated_minutes < best_cost
                ):
                    best = route
                    best_cost = route.total_estimated_minutes
        return best
