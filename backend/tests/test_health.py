"""Unit tests for the ``GET /health`` endpoint."""


def test_health_returns_200(client):
    resp = client.get("/health")
    assert resp.status_code == 200


def test_health_returns_json_content_type(client):
    resp = client.get("/health")
    assert resp.headers["content-type"].startswith("application/json")


def test_health_body_shape(client):
    resp = client.get("/health")
    body = resp.json()
    assert body["status"] == "healthy"
    assert "timestamp" in body


def test_health_timestamp_is_numeric(client):
    resp = client.get("/health")
    body = resp.json()
    assert isinstance(body["timestamp"], (int, float))


def test_health_requires_no_auth(client):
    """``/health`` is intentionally unauthenticated so external monitors can hit it."""
    # No Authorization header.
    resp = client.get("/health")
    assert resp.status_code == 200
