"""Smoke tests: infra stack reachability.

Run: `docker compose up -d` first, then:
    uv run pytest tests/smoke -v -m integration
"""

from __future__ import annotations

import socket
import urllib.request

import pytest

pytestmark = pytest.mark.integration


def _tcp_reachable(host: str, port: int, timeout: float = 2.0) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def _http_ok(url: str, timeout: float = 5.0) -> bool:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            return 200 <= resp.status < 400
    except Exception:
        return False


def test_postgres_port_open() -> None:
    assert _tcp_reachable("localhost", 5432)


def test_redis_port_open() -> None:
    assert _tcp_reachable("localhost", 6379)


def test_meilisearch_health() -> None:
    assert _http_ok("http://localhost:7700/health")


def test_jaeger_ui() -> None:
    assert _http_ok("http://localhost:16686/")


def test_jaeger_otlp_grpc_port_open() -> None:
    assert _tcp_reachable("localhost", 4317)


def test_prometheus_ready() -> None:
    assert _http_ok("http://localhost:9090/-/ready")


def test_grafana_health() -> None:
    assert _http_ok("http://localhost:3000/api/health")
