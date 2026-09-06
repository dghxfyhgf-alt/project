from __future__ import annotations

import math
import random
from dataclasses import dataclass
from typing import Any

import networkx as nx


@dataclass
class RouteResult:
    nodes: list[Any]
    distance: float
    duration: float


def haversine_m(a: tuple[float, float], b: tuple[float, float]) -> float:
    lat1, lon1 = map(math.radians, a)
    lat2, lon2 = map(math.radians, b)
    dlat, dlon = lat2 - lat1, lon2 - lon1
    value = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    return 6_371_000 * 2 * math.atan2(math.sqrt(value), math.sqrt(1 - value))


class BidirectionalGeneticRouter:
    """Genetic path optimizer seeded by a bidirectional graph search."""

    def __init__(self, graph: nx.MultiDiGraph, preferences: dict[str, Any], seed: int = 42) -> None:
        self.graph = graph
        self.preferences = preferences
        self.random = random.Random(seed)

    def _edge(self, left: Any, right: Any) -> dict[str, Any] | None:
        edges = self.graph.get_edge_data(left, right)
        if not edges:
            return None
        return min(edges.values(), key=lambda item: float(item.get("length", 1)))

    def _edge_cost(self, left: Any, right: Any) -> float:
        edge = self._edge(left, right)
        if edge is None:
            return math.inf
        slope = float(edge.get("max_slope_percent", edge.get("incline_percent", edge.get("slope", 0))) or 0)
        stairs = bool(edge.get("is_stairs")) or str(edge.get("highway", "")).lower() == "steps"
        profile = self.preferences.get("profile", "normal")
        if (self.preferences.get("avoid_stairs") or profile in {"luggage", "stroller", "wheelchair"}) and stairs:
            return math.inf
        maximum = self.preferences.get("max_slope")
        if maximum is not None and slope > float(maximum):
            return math.inf
        if (self.preferences.get("wheelchair") or profile == "wheelchair") and slope > 8:
            return math.inf
        if profile in {"luggage", "stroller"} and slope > 10:
            return math.inf
        length = float(edge.get("length", 1))
        return length * (1 + slope / 100) + (length * 2 if stairs else 0)

    def _fitness(self, path: list[Any]) -> float:
        if len(path) < 2 or len(path) != len(set(path)):
            return math.inf
        costs = [self._edge_cost(a, b) for a, b in zip(path, path[1:])]
        return sum(costs) if all(math.isfinite(cost) for cost in costs) else math.inf

    def _bidirectional_seed(self, origin: Any, destination: Any) -> list[Any]:
        if origin == destination:
            return [origin]
        forward = {origin: None}
        backward = {destination: None}
        front_forward, front_backward = {origin}, {destination}
        meeting = None
        while front_forward and front_backward:
            if len(front_forward) <= len(front_backward):
                next_front = set()
                for node in front_forward:
                    for candidate in self.graph.successors(node):
                        if self._edge_cost(node, candidate) == math.inf:
                            continue
                        if candidate not in forward:
                            forward[candidate] = node
                            next_front.add(candidate)
                        if candidate in backward:
                            meeting = candidate
                            break
                    if meeting is not None:
                        break
                front_forward = next_front
            else:
                next_front = set()
                for node in front_backward:
                    for candidate in self.graph.predecessors(node):
                        if self._edge_cost(candidate, node) == math.inf:
                            continue
                        if candidate not in backward:
                            backward[candidate] = node
                            next_front.add(candidate)
                        if candidate in forward:
                            meeting = candidate
                            break
                    if meeting is not None:
                        break
                front_backward = next_front
            if meeting is not None:
                break
        if meeting is None:
            raise nx.NetworkXNoPath
        left = []
        current = meeting
        while current is not None:
            left.append(current)
            current = forward[current]
        left.reverse()
        right = []
        current = backward[meeting]
        while current is not None:
            right.append(current)
            current = backward[current]
        return left + right

    def _mutate(self, path: list[Any]) -> list[Any]:
        if len(path) < 3:
            return path[:]
        index = self.random.randrange(1, len(path) - 1)
        alternatives = [
            node for node in self.graph.successors(path[index - 1])
            if node not in path[:index] and self._edge_cost(path[index - 1], node) < math.inf
        ]
        if not alternatives:
            return path[:]
        candidate = path[:index] + [self.random.choice(alternatives)]
        for _ in range(len(path) - index - 1):
            options = [node for node in self.graph.successors(candidate[-1]) if node not in candidate]
            if not options:
                return path[:]
            candidate.append(self.random.choice(options))
        return candidate if candidate[-1] == path[-1] and self._fitness(candidate) < math.inf else path[:]

    def _crossover(self, first: list[Any], second: list[Any]) -> list[Any] | None:
        common = [node for node in first[1:-1] if node in second[1:-1]]
        if not common:
            return None
        meeting = self.random.choice(common)
        child = first[: first.index(meeting)] + second[second.index(meeting):]
        return child if self._fitness(child) < math.inf else None

    def search(self, origin: Any, destination: Any) -> list[Any]:
        seed = self._bidirectional_seed(origin, destination)
        population = [seed]
        for _ in range(31):
            candidate = self._mutate(seed)
            if candidate not in population:
                population.append(candidate)
        for _ in range(40):
            population.sort(key=self._fitness)
            population = population[:32]
            children = [
                child
                for first in population
                for second in population
                for child in [self._crossover(first, second)]
                if child is not None
            ]
            population.extend(children)
            population.extend(self._mutate(path) for path in population[:16])
        return min(population, key=self._fitness)


def shortest_route(
    graph: nx.MultiDiGraph,
    origin: Any,
    destination: Any,
    preferences: dict[str, Any] | None = None,
) -> RouteResult:
    preferences = preferences or {}
    nodes = BidirectionalGeneticRouter(graph, preferences).search(origin, destination)
    distance = 0.0
    for current, following in zip(nodes, nodes[1:]):
        edge = min((graph.get_edge_data(current, following) or {}).values(), key=lambda item: float(item.get("length", 1)))
        distance += float(edge.get("length", 1))
    speed = 25 / 3.6 if preferences.get("prefer_bus") else 5 / 3.6
    return RouteResult(nodes=nodes, distance=distance, duration=distance / speed)
