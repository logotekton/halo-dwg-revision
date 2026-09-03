"""``<name>.halo`` project bundle: layout, creation/opening, and the original-file write guard.

``layout.py`` -- the fixed directory layout and the default bundle location.
``guard.py`` -- ``assert_writable_path`` (CLAUDE.md rule 1: original drawings
are never written to; a code guard must refuse it). ``originals.py`` --
copies a source file into ``originals/<sha256><ext>`` and chmods it 0444.
``create.py`` -- ``create_bundle`` / ``open_bundle`` ->
:class:`~halo_engine.bundle.create.BundleHandle`.
"""
