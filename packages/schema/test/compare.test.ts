import { describe, expect, it } from "vitest";

import type { Change } from "../gen/ts/compare/change";
import type { Cluster } from "../gen/ts/compare/cluster";
import type { ClustersSidecar } from "../gen/ts/compare/clusters-sidecar";
import type { CompareSetSummary } from "../gen/ts/compare/compare-set";
import type { Run } from "../gen/ts/compare/run";
import type { SheetFrame } from "../gen/ts/compare/sheet-frame";
import type { SheetPair } from "../gen/ts/compare/sheet-pair";
import type { RevisionTruth } from "../gen/ts/compare/truth";
import { SCHEMA_IDS } from "../src/schemas";
import {
  clustersSidecarIntegrityFailures,
  formatErrors,
  validateChange,
  validateCluster,
  validateClustersSidecar,
  validateCompareSetSummary,
  validateRevisionTruth,
  validateRun,
  validateSheetFrame,
  validateSheetPair,
} from "../src/validate";
import { clone, loadExample } from "./helpers";

const frame = () => clone(loadExample("compare.sheet-frame.json")) as SheetFrame;
const pair = () => clone(loadExample("compare.sheet-pair.json")) as SheetPair;
const change = () => clone(loadExample("compare.change.json")) as Change;
const cluster = () => clone(loadExample("compare.cluster.json")) as Cluster;
const run = () => clone(loadExample("compare.run.json")) as Run;
const sidecar = () => clone(loadExample("compare.clusters-sidecar.json")) as ClustersSidecar;
const compareSet = () => clone(loadExample("compare.compare-set.json")) as CompareSetSummary;
const truth = () => clone(loadExample("compare.truth.json")) as RevisionTruth;

/** `record` with `key` deleted, for the "a required field is missing" cases. */
function without<T extends object>(record: T, key: string): Record<string, unknown> {
  const copy = { ...record } as Record<string, unknown>;
  delete copy[key];
  return copy;
}

describe("compare schema registry", () => {
  it("registers all eight compare schemas under the compare/ prefix", () => {
    const compareIds = Object.entries(SCHEMA_IDS)
      .filter(([, id]) => id.includes("/compare/"))
      .map(([, id]) => id.slice(id.lastIndexOf("/") + 1))
      .sort();
    expect(compareIds).toEqual([
      "change.schema.json",
      "cluster.schema.json",
      "clusters-sidecar.schema.json",
      "compare-set.schema.json",
      "run.schema.json",
      "sheet-frame.schema.json",
      "sheet-pair.schema.json",
      "truth.schema.json",
    ]);
  });
});

describe("SheetFrame", () => {
  it("accepts the recognised title block", () => {
    expect(validateSheetFrame(frame()), JSON.stringify(formatErrors(validateSheetFrame.errors))).toBe(
      true
    );
  });

  it("accepts a file that produced no title block at all", () => {
    const unrecognized = {
      ...frame(),
      kind: "unrecognized_file",
      titleblock_handle: null,
      block_name: null,
      sheet_no: null,
      sheet_title: null,
      scale_text: null,
      scale_denominator: null,
      date_text: null,
      norm_key: "A-100 평면도.DWG",
      attributes: null,
    };
    expect(validateSheetFrame(unrecognized)).toBe(true);
  });

  it("refuses a frame kind outside the closed set", () => {
    expect(validateSheetFrame({ ...frame(), kind: "layout" })).toBe(false);
  });

  it("refuses a frame without provenance", () => {
    expect(validateSheetFrame(without(frame(), "provenance"))).toBe(false);
  });

  it("refuses a box that is not four numbers", () => {
    expect(validateSheetFrame({ ...frame(), bbox: [0, 0, 84100] })).toBe(false);
    expect(validateSheetFrame({ ...frame(), bbox: { min: [0, 0], max: [1, 1] } })).toBe(false);
  });

  it("refuses an unknown field, so a renamed column cannot pass unnoticed", () => {
    expect(validateSheetFrame({ ...frame(), sheet_number: "A-101" })).toBe(false);
  });
});

describe("SheetPair", () => {
  it("accepts a matched pair with both frame summaries", () => {
    expect(validateSheetPair(pair()), JSON.stringify(formatErrors(validateSheetPair.errors))).toBe(
      true
    );
  });

  it("accepts a sheet that exists only in the after set", () => {
    const added = {
      ...pair(),
      before_frame_id: null,
      before_frame: null,
      status: "added",
      match_method: null,
      score: null,
    };
    expect(validateSheetPair(added)).toBe(true);
  });

  it("refuses a status the review screen has no column for", () => {
    expect(validateSheetPair({ ...pair(), status: "conflict" })).toBe(false);
  });

  it("refuses a match method outside number/title/position/manual", () => {
    expect(validateSheetPair({ ...pair(), match_method: "fingerprint" })).toBe(false);
  });
});

describe("Change", () => {
  it("accepts the moved door", () => {
    expect(validateChange(change()), JSON.stringify(formatErrors(validateChange.errors))).toBe(true);
  });

  it("refuses a change with no provenance at all", () => {
    expect(validateChange(without(change(), "provenance"))).toBe(false);
  });

  it("refuses a provenance object with neither side", () => {
    expect(validateChange({ ...change(), provenance: {} })).toBe(false);
  });

  it("accepts an added entity, which has an after side only", () => {
    const added = change();
    expect(
      validateChange({
        ...added,
        kind: "added",
        before_handle: null,
        provenance: { after: added.provenance.after },
      })
    ).toBe(true);
  });

  it("refuses a kind the compare DXF cannot draw", () => {
    expect(validateChange({ ...change(), kind: "recolored" })).toBe(false);
  });

  it("keeps the change id tied to the sequence number by shape", () => {
    expect(validateChange({ ...change(), id: "c1" })).toBe(false);
    expect(validateChange({ ...change(), id: "ch0" })).toBe(false);
  });

  it("accepts several fold reasons joined with +", () => {
    const folded = { ...change(), minor: true, minor_reason: "layer_only+color_only" };
    expect(validateChange(folded)).toBe(true);
  });

  it("refuses a fold reason that is not in the contract's list", () => {
    expect(validateChange({ ...change(), minor: true, minor_reason: "moved_a_bit" })).toBe(false);
    expect(validateChange({ ...change(), minor: true, minor_reason: "layer_only+" })).toBe(false);
  });

  it("leaves delta open, because the payload grows with the diff rules", () => {
    const withNewPayload = {
      ...change(),
      delta: { move: [1250, 0], distance: 1250, rotation_deg: 90 },
    };
    expect(validateChange(withNewPayload)).toBe(true);
  });
});

describe("Cluster", () => {
  it("accepts the cloud mark", () => {
    expect(validateCluster(cluster()), JSON.stringify(formatErrors(validateCluster.errors))).toBe(
      true
    );
  });

  it("refuses a misspelled decision instead of reading it as 미검토", () => {
    expect(validateCluster({ ...cluster(), decision: "aproved" })).toBe(false);
  });

  it("numbers clusters from 1, because 0 has no badge", () => {
    expect(validateCluster({ ...cluster(), number: 0, id: "c0" })).toBe(false);
  });

  it("refuses an empty cluster", () => {
    expect(validateCluster({ ...cluster(), change_ids: [] })).toBe(false);
  });

  it("requires three numbers per cloud vertex: x, y and the bulge", () => {
    const flat = cluster();
    flat.cloud.points = [
      [12450, 8150],
      [15200, 8150],
      [15200, 10450],
      [12450, 10450],
    ] as unknown as Cluster["cloud"]["points"];
    expect(validateCluster(flat)).toBe(false);
  });

  it("allows the handles to be null before the compare DXF is written", () => {
    const unwritten = cluster();
    unwritten.cloud.handle = null;
    unwritten.badge.shape_handle = null;
    unwritten.badge.text_handle = null;
    expect(validateCluster(unwritten)).toBe(true);
  });
});

describe("Run", () => {
  it("accepts a finished export", () => {
    expect(validateRun(run()), JSON.stringify(formatErrors(validateRun.errors))).toBe(true);
  });

  it("accepts the second export of the same date, layer suffix and all", () => {
    expect(validateRun({ ...run(), layer_name: "REV-20260904-2" })).toBe(true);
  });

  it("refuses a layer name that is not REV-<YYYYMMDD>", () => {
    expect(validateRun({ ...run(), layer_name: "REV-2026-09-04" })).toBe(false);
    expect(validateRun({ ...run(), layer_name: "REVISION-20260904" })).toBe(false);
  });

  it("refuses a scope other than all -- exporting chosen sheets is week 2", () => {
    expect(validateRun({ ...run(), scope: "selected" })).toBe(false);
  });

  it("refuses an output format the viewer cannot open", () => {
    const wrong = run();
    wrong.files[0].format = "pdf" as unknown as Run["files"][number]["format"];
    expect(validateRun(wrong)).toBe(false);
  });
});

describe("ClustersSidecar", () => {
  it("accepts the sidecar as clusters.json writes it", () => {
    expect(
      validateClustersSidecar(sidecar()),
      JSON.stringify(formatErrors(validateClustersSidecar.errors))
    ).toBe(true);
  });

  it("refuses the export's -n layer suffix: the compare DXF never carries it", () => {
    expect(validateClustersSidecar({ ...sidecar(), layer: "REV-20260904-2" })).toBe(false);
  });

  it("refuses a run date that is not YYYY-MM-DD", () => {
    expect(validateClustersSidecar({ ...sidecar(), run_date: "2026-9-4" })).toBe(false);
    expect(validateClustersSidecar({ ...sidecar(), run_date: "20260904" })).toBe(false);
  });

  it("refuses a handle map key that is not a DXF handle", () => {
    const bad = sidecar();
    bad.handle_to_cluster = { "2f1": "c1" };
    expect(validateClustersSidecar(bad)).toBe(false);
  });

  it("refuses a scale factor of zero, which would collapse every cloud mark", () => {
    const bad = sidecar();
    bad.frame.scale_factor = 0;
    expect(validateClustersSidecar(bad)).toBe(false);
  });
});

describe("clustersSidecarIntegrityFailures", () => {
  it("passes the example, which is what the engine is expected to write", () => {
    expect(clustersSidecarIntegrityFailures(sidecar())).toEqual([]);
  });

  it("catches a handle mapped to a cluster that is not in the file", () => {
    const dangling = clone(loadExample("compare.bad-sidecar-dangling-handle.json")) as ClustersSidecar;
    // The schema cannot express the reference, so it accepts the document ...
    expect(validateClustersSidecar(dangling)).toBe(true);
    // ... and this is the check that stops a click from selecting nothing.
    expect(clustersSidecarIntegrityFailures(dangling)).toEqual([
      "handle_to_cluster/2F3: references unknown cluster c2",
    ]);
  });

  it("catches a cluster listing a change that was never written", () => {
    const bad = sidecar();
    bad.clusters[0].change_ids = ["ch1", "ch9"];
    expect(clustersSidecarIntegrityFailures(bad)).toContain(
      "clusters/c1: change_ids references unknown change ch9"
    );
  });

  it("catches a change pointing back at a cluster that does not exist", () => {
    const bad = sidecar();
    bad.changes[1].cluster_id = "c7";
    expect(clustersSidecarIntegrityFailures(bad)).toContain(
      "changes/ch2: cluster_id references unknown cluster c7"
    );
  });

  it("catches an id that has drifted from its number", () => {
    const bad = sidecar();
    bad.clusters[0].id = "c2";
    const reasons = clustersSidecarIntegrityFailures(bad);
    expect(reasons).toContain("clusters: id c2 does not match number 1");
  });

  it("catches counts that disagree with the arrays", () => {
    const bad = sidecar();
    bad.counts.minor = 0;
    bad.counts.approved = 1;
    expect(clustersSidecarIntegrityFailures(bad)).toEqual([
      "counts/minor: written 0, actual 1",
      "counts/approved: written 1, actual 0",
    ]);
  });
});

describe("CompareSetSummary", () => {
  it("accepts a finished comparison", () => {
    expect(
      validateCompareSetSummary(compareSet()),
      JSON.stringify(formatErrors(validateCompareSetSummary.errors))
    ).toBe(true);
  });

  it("accepts a set that has only been ingested, with the later stages still null", () => {
    const ingested = { ...compareSet(), status: "ingested", frames: null, pairs: null, crosscheck: null };
    expect(validateCompareSetSummary(ingested)).toBe(true);
  });

  it("accepts ZWCAD being unavailable on this machine", () => {
    const mac = compareSet();
    mac.zwcad = {
      available: false,
      installed: false,
      version: null,
      prog_id: null,
      reason: "not_windows",
    };
    mac.converter = { before: "acad-ts", after: "acad-ts", mismatch_files: 0 };
    expect(validateCompareSetSummary(mac)).toBe(true);
  });

  it("refuses a ZWCAD reason that is not one of the four codes", () => {
    const bad = compareSet();
    bad.zwcad = { ...bad.zwcad, available: false, reason: "설치되지 않음" as never };
    expect(validateCompareSetSummary(bad)).toBe(false);
  });

  it("refuses a pipeline status that is not in the contract", () => {
    expect(validateCompareSetSummary({ ...compareSet(), status: "done" })).toBe(false);
  });

  it("refuses a converter name the ingest job never produces", () => {
    const bad = compareSet();
    bad.converter = { ...bad.converter, before: "autocad-com" as never };
    expect(validateCompareSetSummary(bad)).toBe(false);
  });
});

describe("RevisionTruth", () => {
  it("accepts a scenario's expectations", () => {
    expect(
      validateRevisionTruth(truth()),
      JSON.stringify(formatErrors(validateRevisionTruth.errors))
    ).toBe(true);
  });

  it("accepts handles it cannot know, which is what a whole-file copy leaves behind", () => {
    const copied = truth();
    const expectedChange = copied.expected_pairs[0].expected_changes?.[0];
    if (!expectedChange) throw new Error("fixture lost its expected change");
    expectedChange.before_handle = null;
    expectedChange.after_handle = null;
    expect(validateRevisionTruth(copied)).toBe(true);
  });

  it("uses the same status and kind vocabularies as the records it is checked against", () => {
    const bad = truth();
    bad.expected_pairs[0].status = "different" as never;
    expect(validateRevisionTruth(bad)).toBe(false);

    const badKind = truth();
    const expectedChange = badKind.expected_pairs[0].expected_changes?.[0];
    if (!expectedChange) throw new Error("fixture lost its expected change");
    expectedChange.kind = "recolored" as never;
    expect(validateRevisionTruth(badKind)).toBe(false);
  });

  it("refuses a clean region that is not a box", () => {
    const bad = truth();
    bad.expected_pairs[0].clean_regions = [[0, 0, 1]] as never;
    expect(validateRevisionTruth(bad)).toBe(false);
  });
});
