"""API routers, mounted under ``/api/v1/*`` by :func:`halo_engine.api.main.create_app`.

Only ``system`` (health/capabilities/shutdown) exists in W1-02. Job-runner and
WebSocket routers (``jobs``, ``ws``) land in W2-01 / W8-05 — this module is
their registration point, kept empty on purpose.
"""
