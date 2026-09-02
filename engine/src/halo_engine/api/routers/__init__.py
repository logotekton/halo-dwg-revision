"""API routers, mounted under ``/api/v1/*`` by :func:`halo_engine.api.main.create_app`.

``system`` (health/capabilities/shutdown, W1-02) and ``crosscheck``
(``POST /api/v1/files/crosscheck``, W2-04) exist today. Job-runner and
WebSocket routers (``jobs``, ``ws``) land in W2-01 / W8-05 — this module is
their registration point, kept empty on purpose.
"""
