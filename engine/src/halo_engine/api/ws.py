"""``/api/v1/ws`` -- the sidecar's one WebSocket endpoint (``docs/PLAN.md`` §3.6,
``docs/contracts/wave-3.md``).

Events: ``job.progress`` / ``job.done`` / ``job.failed`` (broadcast by
``api/jobs.py`` as an import job runs) and ``convert.request`` (broadcast by
this module's :class:`ConnectionManager` when a DWG needs the desktop's
``dxfOut()``). ``model.changed`` is in the contract's event list but has no
producer yet (W3+ editing/reconstruction).

Authentication is the first frame, not a header (contract, brief W3-03
Defaults for ambiguity): ``{"type": "auth", "token": "..."}``, compared
against the same bearer token the HTTP routes use
(``halo_engine.api.main``'s middleware). A client that sends anything else
first, or nothing within :data:`AUTH_TIMEOUT_S`, is closed.
"""

from __future__ import annotations

import asyncio
import logging
import secrets
from typing import Any

from fastapi import APIRouter, FastAPI, WebSocket, WebSocketDisconnect

logger = logging.getLogger("halo_engine.api.ws")

router = APIRouter()

#: How long a client has to send its {"type": "auth", ...} first frame.
AUTH_TIMEOUT_S = 10.0
#: Private-use WS close code (RFC 6455 §7.4.2: 4000-4999) for a failed handshake.
CLOSE_UNAUTHORIZED = 4401


class ConnectionManager:
    """Broadcasts engine -> client events, and resolves the ``convert.request``
    -> ``POST /files/{id}/converted`` round trip.

    One instance per running app (``get_connection_manager`` lazily creates
    and caches it on ``app.state``), shared by every WS connection and by
    ``api/jobs.py``'s import orchestrator.
    """

    def __init__(self) -> None:
        self._clients: set[WebSocket] = set()
        self._pending: dict[str, asyncio.Future[dict[str, Any]]] = {}

    def has_clients(self) -> bool:
        return bool(self._clients)

    def register(self, websocket: WebSocket) -> None:
        self._clients.add(websocket)

    def unregister(self, websocket: WebSocket) -> None:
        self._clients.discard(websocket)

    async def broadcast(self, message: dict[str, Any]) -> None:
        """Best-effort: a client that errors out on send is dropped, not retried."""
        dead: list[WebSocket] = []
        for websocket in list(self._clients):
            try:
                await websocket.send_json(message)
            except Exception:  # noqa: BLE001 - a broken client must not break the others
                dead.append(websocket)
        for websocket in dead:
            self.unregister(websocket)

    async def request_conversion(
        self, *, file_id: str, dwg_path: str, out_path: str, timeout_s: float
    ) -> dict[str, Any]:
        """Send ``convert.request`` and wait up to ``timeout_s`` for the matching
        ``POST /files/{id}/converted`` (brief W3-03: "최대 10분 대기").

        Raises :class:`ConnectionError` if no client is connected right now,
        and :class:`TimeoutError` if none answers in time -- the caller
        (``api/jobs.py``) treats either as "no desktop available" and moves
        on to the acad-ts fallback, if one is configured.
        """
        if not self.has_clients():
            raise ConnectionError("no WS client connected")

        loop = asyncio.get_running_loop()
        future: asyncio.Future[dict[str, Any]] = loop.create_future()
        self._pending[file_id] = future
        try:
            await self.broadcast(
                {
                    "type": "convert.request",
                    "file_id": file_id,
                    "dwg_path": dwg_path,
                    "out_path": out_path,
                }
            )
            try:
                return await asyncio.wait_for(future, timeout=timeout_s)
            except TimeoutError as exc:
                raise TimeoutError(
                    f"no `converted` callback for file {file_id} within {timeout_s}s"
                ) from exc
        finally:
            self._pending.pop(file_id, None)

    def resolve_conversion(self, file_id: str, payload: dict[str, Any]) -> bool:
        """Called by ``POST /files/{id}/converted``. False if nothing was waiting on it."""
        future = self._pending.get(file_id)
        if future is None or future.done():
            return False
        future.set_result(payload)
        return True


def get_connection_manager(app: FastAPI) -> ConnectionManager:
    manager = getattr(app.state, "connection_manager", None)
    if manager is None:
        manager = ConnectionManager()
        app.state.connection_manager = manager
    return manager


async def _authenticate(websocket: WebSocket, *, token: str | None) -> bool:
    try:
        first_frame = await asyncio.wait_for(websocket.receive_json(), timeout=AUTH_TIMEOUT_S)
    except (TimeoutError, WebSocketDisconnect, ValueError):
        return False
    if not isinstance(first_frame, dict) or first_frame.get("type") != "auth":
        return False
    if token is None:
        return True
    provided = first_frame.get("token")
    return isinstance(provided, str) and secrets.compare_digest(provided, token)


@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket) -> None:
    settings = websocket.app.state.settings
    await websocket.accept()

    if not await _authenticate(websocket, token=settings.token):
        await websocket.close(code=CLOSE_UNAUTHORIZED)
        return

    manager = get_connection_manager(websocket.app)
    manager.register(websocket)
    try:
        while True:
            try:
                message = await websocket.receive_json()
            except WebSocketDisconnect:
                break
            except ValueError:
                continue
            # The only inbound traffic this contract defines is the desktop's
            # `converted` result, and that arrives over HTTP
            # (`POST /files/{id}/converted`), not this socket -- any frame
            # actually received here is unexpected but non-fatal.
            logger.debug("ws: unexpected client frame: %r", message)
    finally:
        manager.unregister(websocket)


__all__ = [
    "AUTH_TIMEOUT_S",
    "CLOSE_UNAUTHORIZED",
    "ConnectionManager",
    "get_connection_manager",
    "router",
]
