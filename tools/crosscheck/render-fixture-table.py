"""Render ``docs/spikes/crosscheck-fixtures.md`` from a directory of reports.

Called by ``tools/crosscheck.sh`` after every pairwise
``halo-engine crosscheck`` has written its ``<fixture>.<a>-vs-<b>.json``.
Pure stdlib so it runs under any interpreter uv hands it.

The document has three parts: the fixture x producer-pair status matrix, the
per-fixture cause list (AMBER lines carry the whitelist id that explains
them), and the whitelist entries actually cited. It is regenerated wholesale,
never hand edited.
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any

MARK = {"GREEN": "🟢", "AMBER": "🟡", "RED": "🔴"}

HEADER = """# 파서 교차검증 픽스처 결과표 (W2-04)

`tools/crosscheck.sh`가 생성한다 — **손으로 고치지 않는다.**
세 파서가 같은 R2018 DXF 바이트를 읽어 낸 `LayerStatsDocument`를 쌍별로 비교한 결과다
(ADR-0002 6, `docs/contracts/stats-definition.md` "비교 임계").

- 판정: 🟢 GREEN = 차이 없음, 🟡 AMBER = `halo_engine/validate/whitelist.yaml`이 사유와 함께
  설명하는 알려진 격차, 🔴 RED = 설명되지 않은 계약 위반.
- **카운트 격차(`count_by_type`, `text_count`, 한쪽에만 있는 버킷, INSERT 총개수 변화)는
  화이트리스트로 낮출 수 없다** — 아래 표의 AMBER에는 그런 항목이 없다.
- 재실행: `tools/crosscheck.sh` (`--no-build`로 빌드 생략, `--only F06`으로 한 픽스처만).
"""


def load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def pair_label(pair: str) -> str:
    a, b = pair.split("__")
    return f"{a} vs {b}"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--reports", required=True, type=Path)
    parser.add_argument("--fixtures", required=True)
    parser.add_argument("--pairs", required=True)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()

    fixtures = args.fixtures.split()
    pairs = args.pairs.split()

    reports: dict[tuple[str, str], dict[str, Any]] = {}
    for fixture in fixtures:
        for pair in pairs:
            a, b = pair.split("__")
            path = args.reports / f"{fixture}.{a}-vs-{b}.json"
            if path.is_file():
                reports[(fixture, pair)] = load(path)

    lines = [HEADER, "## 상태 표", ""]
    lines.append("| 픽스처 | " + " | ".join(pair_label(p) for p in pairs) + " | 레이어 수 |")
    lines.append("|---" * (len(pairs) + 2) + "|")

    overall: Counter[str] = Counter()
    for fixture in fixtures:
        cells = []
        layer_count = "-"
        for pair in pairs:
            report = reports.get((fixture, pair))
            if report is None:
                cells.append("—")
                continue
            status = report["status"]
            overall[status] += 1
            counts = report.get("counts", {})
            cells.append(
                f"{MARK[status]} {status}"
                + (
                    f" ({counts.get('AMBER', 0)}황)"
                    if status == "AMBER"
                    else (f" ({counts.get('RED', 0)}적)" if status == "RED" else "")
                )
            )
            layer_count = str(len(report.get("layers", [])))
        lines.append(f"| {fixture} | " + " | ".join(cells) + f" | {layer_count} |")

    lines.append("")
    lines.append(
        "총 {} 비교 — GREEN {} / AMBER {} / RED {}.".format(
            sum(overall.values()),
            overall.get("GREEN", 0),
            overall.get("AMBER", 0),
            overall.get("RED", 0),
        )
    )

    lines += ["", "## 차이 상세 (GREEN인 비교는 생략)", ""]
    any_detail = False
    for fixture in fixtures:
        for pair in pairs:
            report = reports.get((fixture, pair))
            if report is None or report["status"] == "GREEN":
                continue
            any_detail = True
            lines.append(f"### {fixture} — {pair_label(pair)} → {MARK[report['status']]} {report['status']}")
            lines.append("")
            lines.append("| 레이어 | 공간 | 상태 | 원인 | 근거 |")
            lines.append("|---|---|---|---|---|")
            for result in [*report["layers"], report["totals"]]:
                if result["status"] == "GREEN":
                    continue
                for difference in result["differences"]:
                    lines.append(
                        "| {} | {} | {} {} | `{}` | {} |".format(
                            result["layer"],
                            result["space"],
                            MARK[difference["severity"]],
                            difference["severity"],
                            difference["detail"].replace("|", "\\|"),
                            difference.get("whitelist_id") or "**없음 (계약 위반)**",
                        )
                    )
            lines.append("")
    if not any_detail:
        lines.append("모든 비교가 GREEN이다.")
        lines.append("")

    cited: dict[str, str] = {}
    for report in reports.values():
        for result in [*report["layers"], report["totals"]]:
            for difference in result["differences"]:
                if difference.get("whitelist_id") and difference.get("whitelist_reason"):
                    cited.setdefault(difference["whitelist_id"], difference["whitelist_reason"])
    lines += ["## 인용된 화이트리스트 항목", ""]
    if cited:
        for entry_id, reason in sorted(cited.items()):
            lines.append(f"- **{entry_id}** — {reason}")
    else:
        lines.append("없음.")
    lines.append("")

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text("\n".join(lines), encoding="utf-8")
    print(args.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
