import { deepStrictEqual, ok, strictEqual } from "node:assert/strict";
import { describe, it } from "node:test";

import {
  dayRole,
  firstDayOfWeek,
  isoDate,
  monthGrid,
  monthLabel,
  nextSelection,
  weekdayLabels,
} from "../../src/calendar.ts";

describe("Wochenbeginn", () => {
  it("beginnt in Europa am Montag", () => {
    strictEqual(firstDayOfWeek("de-AT"), 1);
    strictEqual(firstDayOfWeek("de-DE"), 1);
  });

  it("beginnt in den USA am Sonntag", () => {
    // Der Standard zählt Sonntag als 7, JavaScript als 0 -- die eine Stelle,
    // an der die beiden sich widersprechen.
    strictEqual(firstDayOfWeek("en-US"), 0);
  });

  it("weicht bei unbrauchbarer Sprache auf Montag aus", () => {
    strictEqual(firstDayOfWeek("nicht-echt!!"), 1);
  });
});

describe("Monatsraster", () => {
  it("hat immer sechs Wochen", () => {
    // Sonst springen die Knöpfe darunter beim Blättern.
    for (const [j, m] of [[2026, 8], [2026, 1], [2024, 1], [2026, 10]] as const) {
      strictEqual(monthGrid(j, m, 1).length, 42);
    }
  });

  it("beginnt auf dem gewählten Wochentag", () => {
    for (const first of [0, 1]) {
      strictEqual(monthGrid(2026, 8, first)[0].date.getDay(), first);
    }
  });

  it("umschließt den ganzen Monat", () => {
    const raster = monthGrid(2026, 8, 1);
    const drin = raster.filter((t) => t.inMonth);
    strictEqual(drin.length, 30);
    strictEqual(drin[0].iso, "2026-09-01");
    strictEqual(drin[drin.length - 1].iso, "2026-09-30");
  });

  it("füllt die Ränder mit den Nachbarmonaten", () => {
    const raster = monthGrid(2026, 8, 1);
    ok(raster.some((t) => !t.inMonth && t.iso.startsWith("2026-08")));
    ok(raster.some((t) => !t.inMonth && t.iso.startsWith("2026-10")));
  });

  it("überspringt keinen Tag", () => {
    const raster = monthGrid(2026, 1, 1);
    for (let i = 1; i < raster.length; i++) {
      const abstand = raster[i].date.getTime() - raster[i - 1].date.getTime();
      // Sommerzeit macht einen Tag 23 Stunden lang; entscheidend ist, dass es
      // genau ein Kalendertag bleibt.
      ok(abstand >= 23 * 3600e3 && abstand <= 25 * 3600e3, String(abstand));
    }
  });

  it("schreibt Daten lokal, nicht in UTC", () => {
    strictEqual(isoDate(new Date(2026, 8, 22, 0, 30)), "2026-09-22");
    strictEqual(isoDate(new Date(2026, 8, 22, 23, 30)), "2026-09-22");
  });
});

describe("Beschriftungen", () => {
  it("nennt sieben Wochentage", () => {
    strictEqual(weekdayLabels("de-AT").length, 7);
    strictEqual(weekdayLabels("en-US")[0], weekdayLabels("en-US", 0)[0]);
  });

  it("nennt Monat und Jahr in der Sprache", () => {
    ok(monthLabel("de-AT", 2026, 8).includes("2026"));
    ok(monthLabel("de-AT", 2026, 8).toLowerCase().includes("september"));
  });
});

describe("Auswahl mit zwei Klicks", () => {
  it("wählt beim ersten Klick einen Tag", () => {
    deepStrictEqual(nextSelection({ from: "", to: "" }, "2026-09-22"),
      { from: "2026-09-22", to: "" });
  });

  it("macht daraus beim zweiten Klick eine Spanne", () => {
    deepStrictEqual(nextSelection({ from: "2026-09-19", to: "" }, "2026-09-22"),
      { from: "2026-09-19", to: "2026-09-22" });
  });

  it("beginnt beim dritten Klick von vorne", () => {
    deepStrictEqual(nextSelection({ from: "2026-09-19", to: "2026-09-22" }, "2026-09-25"),
      { from: "2026-09-25", to: "" });
  });

  it("nimmt auch die rückwärts gewählte Spanne", () => {
    deepStrictEqual(nextSelection({ from: "2026-09-22", to: "" }, "2026-09-19"),
      { from: "2026-09-22", to: "2026-09-19" });
  });
});

describe("Hervorhebung", () => {
  it("kennt Anfang, Ende und die Tage dazwischen", () => {
    const f = "2026-09-19", t = "2026-09-22";
    strictEqual(dayRole(f, f, t), "start");
    strictEqual(dayRole(t, f, t), "end");
    strictEqual(dayRole("2026-09-20", f, t), "between");
    strictEqual(dayRole("2026-09-18", f, t), "none");
    strictEqual(dayRole("2026-09-23", f, t), "none");
  });

  it("markiert einen einzelnen Tag als solchen", () => {
    strictEqual(dayRole("2026-09-22", "2026-09-22", ""), "single");
    strictEqual(dayRole("2026-09-22", "2026-09-22", "2026-09-22"), "single");
  });

  it("stimmt auch bei rückwärts gewählter Spanne", () => {
    const f = "2026-09-22", t = "2026-09-19";
    strictEqual(dayRole("2026-09-19", f, t), "start");
    strictEqual(dayRole("2026-09-22", f, t), "end");
    strictEqual(dayRole("2026-09-20", f, t), "between");
  });

  it("hebt ohne Auswahl nichts hervor", () => {
    strictEqual(dayRole("2026-09-22", "", ""), "none");
  });
});
