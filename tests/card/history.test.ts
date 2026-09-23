import { strict as assert } from "node:assert";
import { describe, it } from "node:test";

import { fetchPersonHistory, mergeTracks, toTrackPoints } from "../../src/history.ts";

describe("toTrackPoints", () => {
  it("carries state and attributes forward across compressed entries", () => {
    const points = toTrackPoints([
      { s: "home", a: { latitude: 48.2, longitude: 16.3, gps_accuracy: 12 }, lu: 1_700_000_000 },
      // Neither state nor attributes changed, only the timestamp.
      { lu: 1_700_000_060 },
      { s: "not_home", lu: 1_700_000_120 },
      { a: { latitude: 48.21, longitude: 16.31, gps_accuracy: 8 }, lu: 1_700_000_180 },
    ]);

    assert.equal(points.length, 4);
    assert.deepEqual(
      points.map((p) => p.zone),
      ["home", "home", "not_home", "not_home"]
    );
    assert.deepEqual(
      points.map((p) => p.lat),
      [48.2, 48.2, 48.2, 48.21]
    );
    assert.equal(points[3].accuracy, 8);
  });

  it("converts epoch seconds to milliseconds", () => {
    const points = toTrackPoints([
      { s: "home", a: { latitude: 48.2, longitude: 16.3 }, lu: 1_700_000_000.5 },
    ]);
    assert.equal(points[0].t, 1_700_000_000_500);
  });

  it("skips entries without usable coordinates", () => {
    const points = toTrackPoints([
      { s: "unknown", a: {}, lu: 1_700_000_000 },
      { s: "home", a: { latitude: 48.2, longitude: 16.3 }, lu: 1_700_000_060 },
      { s: "not_home", a: { latitude: "n/a", longitude: 16.3 }, lu: 1_700_000_120 },
    ]);
    assert.equal(points.length, 1);
    assert.equal(points[0].zone, "home");
  });

  it("falls back to last_changed when last_updated is absent", () => {
    const points = toTrackPoints([
      { s: "home", a: { latitude: 48.2, longitude: 16.3 }, lc: 1_700_000_000 },
    ]);
    assert.equal(points[0].t, 1_700_000_000_000);
  });

  it("returns nothing for an empty history", () => {
    assert.deepEqual(toTrackPoints([]), []);
  });
});

const at = (t: number, lat = 48.2) => ({ t, lat, lon: 16.3, zone: "not_home" });

describe("mergeTracks", () => {
  it("fügt beide Quellen zeitlich geordnet zusammen und zählt jeden Moment einmal", () => {
    const merged = mergeTracks([at(2000), at(3000)], [at(1000), at(2000, 99), at(4000)]);
    assert.deepEqual(
      merged.map((p) => p.t),
      [1000, 2000, 3000, 4000]
    );
    // Bei Gleichstand gilt der Recorder.
    assert.equal(merged[1].lat, 48.2);
  });
});

describe("fetchPersonHistory", () => {
  const entry = (lu: number) => ({
    s: "not_home",
    a: { latitude: 48.2, longitude: 16.3 },
    lu,
  });
  const hassWith = (recorder: () => unknown, store: () => unknown) =>
    ({
      callWS: async (msg: { type: string }) =>
        msg.type === "family_tracking/history" ? store() : recorder(),
    }) as any;
  const range = [new Date(0), new Date(10_000_000)] as const;

  it("nimmt ältere Tage aus dem Speicher der Integration dazu", async () => {
    const hass = hassWith(
      () => ({ "person.a": [entry(2000)] }),
      () => [entry(1000), entry(2000)]
    );
    const points = await fetchPersonHistory(hass, "person.a", ...range);
    assert.deepEqual(
      points.map((p) => p.t),
      [1_000_000, 2_000_000]
    );
  });

  it("kommt ohne Integration mit dem Recorder allein aus", async () => {
    const hass = hassWith(
      () => ({ "person.a": [entry(2000)] }),
      () => {
        throw new Error("unknown_command");
      }
    );
    const points = await fetchPersonHistory(hass, "person.a", ...range);
    assert.equal(points.length, 1);
  });

  it("meldet einen Fehler erst, wenn keine Quelle antwortet", async () => {
    const fail = () => {
      throw new Error("down");
    };
    await assert.rejects(fetchPersonHistory(hassWith(fail, fail), "person.a", ...range));
  });
});
