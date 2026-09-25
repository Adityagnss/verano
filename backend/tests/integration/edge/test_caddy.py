"""
Edge proxy tests: the real infra/Caddyfile in a real Caddy container, in front of a small
stand-in backend running on the host.

1. A client-supplied X-Forwarded-For is discarded and replaced with the address Caddy
   actually saw, so the backend (which trusts only Caddy) can never be fed a fake IP.
2. Server-Sent Events on the API route are not buffered: the first event reaches the
   client while the upstream is still holding the connection open. (Caddy flushes
   text/event-stream by itself; `flush_interval -1` makes it explicit, and this test
   guards the behavior whatever changes in front of the backend later.)
"""

import http.server
import json
import threading
import time
from collections.abc import Iterator
from dataclasses import dataclass

import httpx
import pytest
from testcontainers.core.container import DockerContainer
from testcontainers.core.wait_strategies import LogMessageWaitStrategy

from tests.helpers import ROOT

pytestmark = [pytest.mark.integration, pytest.mark.edge]

CADDY_IMAGE = "caddy:2.11.4-alpine"
CADDYFILE = ROOT.parent / "infra/Caddyfile"
SECOND_EVENT_DELAY_S = 1.5
FIRST_EVENT_BUDGET_S = 0.5
PROGRESS_PATH = "/api/v1/experiments/0190a5c2-0000-7000-8000-000000000001/progress"


class StandInBackend(http.server.BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        if self.path.endswith("/progress"):
            self._stream_events()
        else:
            self._echo_headers()

    def _echo_headers(self) -> None:
        body = json.dumps({"x_forwarded_for": self.headers.get("x-forwarded-for")}).encode()
        self.send_response(200)
        self.send_header("content-type", "application/json")
        self.send_header("content-length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _stream_events(self) -> None:
        self.send_response(200)
        self.send_header("content-type", "text/event-stream")
        self.send_header("cache-control", "no-cache")
        self.end_headers()
        self.wfile.write(b'event: progress\ndata: {"done": 1}\n\n')
        self.wfile.flush()
        time.sleep(SECOND_EVENT_DELAY_S)
        self.wfile.write(b'event: progress\ndata: {"done": 2}\n\n')
        self.wfile.flush()

    def log_message(self, *_: object) -> None:
        return None


@dataclass(frozen=True)
class Edge:
    url: str


@pytest.fixture(scope="module")
def edge() -> Iterator[Edge]:
    upstream = http.server.ThreadingHTTPServer(("0.0.0.0", 0), StandInBackend)
    threading.Thread(target=upstream.serve_forever, daemon=True).start()
    port = upstream.server_address[1]
    caddy = (
        DockerContainer(CADDY_IMAGE)
        .with_volume_mapping(str(CADDYFILE), "/etc/caddy/Caddyfile", "ro")
        .with_env("BACKEND_UPSTREAM", f"host.docker.internal:{port}")
        .with_env("FRONTEND_UPSTREAM", f"host.docker.internal:{port}")
        .with_kwargs(extra_hosts={"host.docker.internal": "host-gateway"})
        .with_exposed_ports(80)
        .waiting_for(LogMessageWaitStrategy("serving initial configuration"))
    )
    with caddy:
        yield Edge(url=f"http://{caddy.get_container_host_ip()}:{caddy.get_exposed_port(80)}")
    upstream.shutdown()


def test_a_spoofed_forwarded_for_is_replaced_with_the_address_caddy_saw(edge: Edge) -> None:
    honest = httpx.get(f"{edge.url}/api/v1/whoami").json()["x_forwarded_for"]
    spoofed = httpx.get(f"{edge.url}/api/v1/whoami", headers={"X-Forwarded-For": "6.6.6.6"}).json()["x_forwarded_for"]
    assert honest
    assert spoofed == honest
    assert "6.6.6.6" not in spoofed


def test_server_sent_events_reach_the_client_immediately_through_caddy(edge: Edge) -> None:
    started = time.perf_counter()
    arrivals: list[float] = []
    with httpx.stream("GET", f"{edge.url}{PROGRESS_PATH}", timeout=10) as response:
        assert response.headers["content-type"].startswith("text/event-stream")
        for line in response.iter_lines():
            if line.startswith("data:"):
                arrivals.append(time.perf_counter() - started)
    assert len(arrivals) == 2
    assert arrivals[0] < FIRST_EVENT_BUDGET_S
    assert arrivals[1] >= SECOND_EVENT_DELAY_S
