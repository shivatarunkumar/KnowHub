"""The two APIs must be interchangeable: same paths, parameters, bodies and responses.

This is what "RUN_ON switches the database, nothing else changes" rests on, so any
endpoint added to one backend and not the other fails here.
"""

import pytest
from app_bq.main import app as bq_app

from app.main import app as psql_app


def contract(app) -> tuple[dict, dict]:
    spec = app.openapi()
    operations = {
        (path, method): {k: v for k, v in op.items() if k in ("parameters", "requestBody", "responses")}
        for path, ops in spec["paths"].items()
        for method, op in ops.items()
    }
    return operations, spec.get("components", {}).get("schemas", {})


@pytest.fixture(scope="module")
def contracts():
    return contract(psql_app), contract(bq_app)


def test_same_endpoints(contracts):
    (psql_ops, _), (bq_ops, _) = contracts
    assert set(bq_ops) == set(psql_ops), {
        "only in backend-bq": sorted(set(bq_ops) - set(psql_ops)),
        "only in backend": sorted(set(psql_ops) - set(bq_ops)),
    }


def test_same_requests_and_responses(contracts):
    (psql_ops, _), (bq_ops, _) = contracts
    differing = [key for key in psql_ops if bq_ops.get(key) != psql_ops[key]]
    assert differing == []


def test_same_schemas(contracts):
    (_, psql_schemas), (_, bq_schemas) = contracts
    names = set(psql_schemas) | set(bq_schemas)
    assert [n for n in sorted(names) if psql_schemas.get(n) != bq_schemas.get(n)] == []
