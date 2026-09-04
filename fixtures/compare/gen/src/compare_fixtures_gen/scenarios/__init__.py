"""Registry of the 17 scenarios (docs/briefs/R1-07.md Goal 3), in order."""

from __future__ import annotations

from compare_fixtures_gen.scenarios import (
    s01_identical,
    s02_move_door,
    s03_dim_value,
    s04_text_change,
    s05_added,
    s06_removed,
    s07_hatch_regen,
    s08_layer_only,
    s09_mtext_format_only,
    s10_move_tiny,
    s11_blockdef_change,
    s12_whole_redraw,
    s13_multi_sheet,
    s14_sheet_added_removed,
    s15_frame_shift,
    s16_unrecognized,
    s17_scale_50,
)

_MODULES = [
    s01_identical,
    s02_move_door,
    s03_dim_value,
    s04_text_change,
    s05_added,
    s06_removed,
    s07_hatch_regen,
    s08_layer_only,
    s09_mtext_format_only,
    s10_move_tiny,
    s11_blockdef_change,
    s12_whole_redraw,
    s13_multi_sheet,
    s14_sheet_added_removed,
    s15_frame_shift,
    s16_unrecognized,
    s17_scale_50,
]

#: scenario id -> module (each exposing ``SCENARIO_ID`` and ``generate(out_root)``).
SCENARIOS: dict[str, object] = {m.SCENARIO_ID: m for m in _MODULES}

ALL_SCENARIO_IDS: list[str] = [m.SCENARIO_ID for m in _MODULES]
