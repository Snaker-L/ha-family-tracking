import { strictEqual } from "node:assert/strict";
import { describe, it } from "node:test";

import { hexToHsv, hsvToHex, pickFromSquare } from "../../src/color.ts";

describe("Farbumrechnung", () => {
  it("trifft die Eckfälle", () => {
    strictEqual(hsvToHex({ h: 0, s: 0, v: 100 }), "#ffffff");
    strictEqual(hsvToHex({ h: 0, s: 0, v: 0 }), "#000000");
    strictEqual(hsvToHex({ h: 0, s: 100, v: 100 }), "#ff0000");
    strictEqual(hsvToHex({ h: 120, s: 100, v: 100 }), "#00ff00");
    strictEqual(hsvToHex({ h: 240, s: 100, v: 100 }), "#0000ff");
  });

  it("kommt hin und zurück beim selben Wert an", () => {
    for (const hex of ["#7c4dff", "#00b894", "#2d7ff9", "#ff7043", "#8d6e63", "#fbc02d"]) {
      strictEqual(hsvToHex(hexToHsv(hex)), hex);
    }
  });

  it("liest die Kurzform", () => {
    strictEqual(hsvToHex(hexToHsv("#f00")), "#ff0000");
  });

  it("hat bei Grau keinen Farbton", () => {
    const grau = hexToHsv("#808080");
    strictEqual(grau.h, 0);
    strictEqual(grau.s, 0);
  });

  it("dreht den Farbton über 360 hinaus weiter", () => {
    strictEqual(hsvToHex({ h: 360, s: 100, v: 100 }), hsvToHex({ h: 0, s: 100, v: 100 }));
    strictEqual(hsvToHex({ h: -120, s: 100, v: 100 }), hsvToHex({ h: 240, s: 100, v: 100 }));
  });
});

describe("Auswahl im Farbfeld", () => {
  it("links oben ist weiß, rechts oben die reine Farbe", () => {
    strictEqual(pickFromSquare(210, 0, 0), "#ffffff");
    strictEqual(pickFromSquare(0, 1, 0), "#ff0000");
  });

  it("unten ist es schwarz, unabhängig vom Farbton", () => {
    for (const ton of [0, 90, 200, 330]) strictEqual(pickFromSquare(ton, 0.5, 1), "#000000");
  });

  it("bleibt am Rand stehen statt aufzuhören", () => {
    // Beim Ziehen verlässt der Zeiger das Feld regelmäßig.
    strictEqual(pickFromSquare(0, 2, -1), pickFromSquare(0, 1, 0));
    strictEqual(pickFromSquare(0, -5, 9), pickFromSquare(0, 0, 1));
  });
});
