import math

import pytest

from rhizo.graph import scoring
from rhizo.graph.client import GraphClient
from rhizo.models import BlastRadiusRequest
from rhizo.services import impact


def test_path_confidence_is_the_product_of_edge_confidences() -> None:
    assert scoring.path_confidence([0.9, 0.8, 0.95]) == pytest.approx(0.684)
    assert scoring.path_confidence([]) == 1.0


def test_cypher_reduce_matches_python_product(tiny_graph: GraphClient) -> None:
    result = impact.blast_radius(tiny_graph.topology(), BlastRadiusRequest(service="C"))
    confs = {i.service.name: i.path_confidence for i in result.data.items}
    assert confs == {"B": 0.8, "A": round(scoring.path_confidence([0.9, 0.8]), 3)}


def test_risk_score_formula() -> None:
    assert scoring.risk_score([(1, 0.9), (3, 0.5)]) == round(100 * (1 - math.exp(-3.2 / 3)))
    assert scoring.risk_score([]) == 0
    assert scoring.risk_score([(None, 1.0)]) == scoring.risk_score([(2, 1.0)])


def test_risk_score_is_bounded_and_monotonic() -> None:
    many = [(1, 1.0)] * 50
    assert scoring.risk_score(many) == 100
    assert scoring.risk_score([(3, 0.5)]) < scoring.risk_score([(1, 0.5)])


def test_worst_basis() -> None:
    assert scoring.worst_basis(["declared", "inferred", "observed"]) == "inferred"
    assert scoring.worst_basis(["declared", "observed"]) == "observed"
    assert scoring.worst_basis(["declared", "connectivity_fallback"]) == "connectivity_fallback"
    assert scoring.worst_basis([]) == "n/a"


def test_suspect_score_prefers_close_recently_changed_dependencies() -> None:
    assert scoring.suspect_score(1, 0, 1.0) == 1.0
    assert scoring.suspect_score(1, 3, 0.9) > scoring.suspect_score(2, 3, 0.9)
    assert scoring.suspect_score(1, 5, 0.9) > scoring.suspect_score(1, 0, 0.9)
