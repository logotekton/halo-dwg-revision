import { describe, expect, it } from "vitest";

import { formatErrors, validateLayerStats } from "../src/validate";
import { clone, loadExample, readExampleText } from "./helpers";

type Aggregate = {
  entity_count: number;
  count_by_type: Record<string, number>;
  length_sum_mm: number;
  hatch_area_sum_mm2: number;
  text_count: number;
  text_hash: string;
  insert_by_block: Record<string, number>;
};
type StatsDoc = {
  buckets: { layer: string; space: string; aggregate: Aggregate }[];
  totals: Aggregate;
};
type NdjDoc = { entities: Record<string, unknown>[] };

function sum(values: number[]): number {
  return values.reduce((a, b) => a + b, 0);
}

describe("layer statistics", () => {
  const stats = loadExample("layer-stats.f06.json") as StatsDoc;

  it("validates", () => {
    if (!validateLayerStats(stats)) {
      throw new Error(JSON.stringify(formatErrors(validateLayerStats.errors), null, 2));
    }
  });

  it("survives a serialise / parse round trip byte for byte", () => {
    const text = readExampleText("layer-stats.f06.json");
    const parsed: unknown = JSON.parse(text);
    expect(validateLayerStats(parsed)).toBe(true);

    const reserialised = JSON.stringify(parsed);
    const reparsed: unknown = JSON.parse(reserialised);
    expect(validateLayerStats(reparsed)).toBe(true);
    expect(reparsed).toEqual(parsed);
    // A second pass must be byte-identical, which is what lets the crosscheck
    // compare a viewer document against an engine document by value.
    expect(JSON.stringify(reparsed)).toBe(reserialised);
  });

  it("totals agree with the sum over the buckets", () => {
    const buckets = stats.buckets.map((bucket) => bucket.aggregate);
    expect(stats.totals.entity_count).toBe(sum(buckets.map((a) => a.entity_count)));
    expect(stats.totals.length_sum_mm).toBe(sum(buckets.map((a) => a.length_sum_mm)));
    expect(stats.totals.hatch_area_sum_mm2).toBe(sum(buckets.map((a) => a.hatch_area_sum_mm2)));
    expect(stats.totals.text_count).toBe(sum(buckets.map((a) => a.text_count)));

    const totalByType: Record<string, number> = {};
    for (const aggregate of buckets) {
      for (const [type, count] of Object.entries(aggregate.count_by_type)) {
        totalByType[type] = (totalByType[type] ?? 0) + count;
      }
    }
    expect(totalByType).toEqual(stats.totals.count_by_type);
  });

  it("describes the same drawing as the NDJ example", () => {
    const ndj = loadExample("f06.ndj.json") as NdjDoc;
    expect(stats.totals.entity_count).toBe(ndj.entities.length);

    const observed: Record<string, number> = {};
    for (const entity of ndj.entities) {
      const type = entity.type as string;
      observed[type] = (observed[type] ?? 0) + 1;
    }
    expect(observed).toEqual(stats.totals.count_by_type);
  });

  it("rejects a count_by_type key that is not a DXF record name", () => {
    const broken = clone(stats);
    broken.buckets[0]!.aggregate.count_by_type = { line: 1 };
    expect(validateLayerStats(broken)).toBe(false);
  });

  it("accepts raw DXF record names such as MULTILEADER (stats contract)", () => {
    const ok = clone(stats);
    ok.buckets[0]!.aggregate.count_by_type = { MULTILEADER: 1 };
    ok.buckets[0]!.aggregate.entity_count = 1;
    expect(validateLayerStats(ok)).toBe(true);
  });

  it("rejects a text hash that is not the documented 16 hex characters", () => {
    const broken = clone(stats);
    broken.totals.text_hash = "not-a-hash";
    expect(validateLayerStats(broken)).toBe(false);
  });

  it("rejects negative counts", () => {
    const broken = clone(stats);
    broken.totals.entity_count = -1;
    expect(validateLayerStats(broken)).toBe(false);
  });
});
