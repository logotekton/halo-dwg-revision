"""API routers, mounted under ``/api/v1/*`` by :func:`halo_engine.api.main.create_app`.

``system`` (health/capabilities/shutdown, W1-02) and ``crosscheck``
(``POST /api/v1/files/crosscheck``, stateless, W2-04) existed first.
``projects`` (``/api/v1/projects``), ``drawing_sets`` (bare ``/api/v1``:
``POST /projects/{id}/drawing-sets`` + ``GET /drawing-sets/{id}/files``) and
``files`` (``/api/v1/files``: working-dxf stream, stats, the desktop's
``converted`` callback, and the stateful per-file ``crosscheck``) are W3-03.
The job runner and WebSocket routers live next to their state, not here --
``halo_engine.api.jobs`` and ``halo_engine.api.ws``.
"""
