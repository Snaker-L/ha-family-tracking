/**
 * Converting between what a colour picker shows and what a config stores.
 *
 * The picker works in HSV because that is the shape of the thing on screen: a
 * hue along one slider, then a square where left to right is saturation and
 * top to bottom is value. The card stores hex, because that is what a
 * dashboard config has always held and what anybody would type.
 *
 * Pure arithmetic, no DOM, so the fiddly half can be tested without a browser.
 */

export interface Hsv {
  /** 0–360. */
  h: number;
  /** 0–100. */
  s: number;
  /** 0–100. */
  v: number;
}

const clamp = (value: number, min: number, max: number): number =>
  Math.min(max, Math.max(min, value));

const pad = (value: number): string => value.toString(16).padStart(2, "0");

export function hsvToHex({ h, s, v }: Hsv): string {
  const hue = ((h % 360) + 360) % 360;
  const sat = clamp(s, 0, 100) / 100;
  const val = clamp(v, 0, 100) / 100;

  const c = val * sat;
  const x = c * (1 - Math.abs(((hue / 60) % 2) - 1));
  const m = val - c;

  const [r, g, b] =
    hue < 60
      ? [c, x, 0]
      : hue < 120
        ? [x, c, 0]
        : hue < 180
          ? [0, c, x]
          : hue < 240
            ? [0, x, c]
            : hue < 300
              ? [x, 0, c]
              : [c, 0, x];

  return `#${pad(Math.round((r + m) * 255))}${pad(Math.round((g + m) * 255))}${pad(
    Math.round((b + m) * 255)
  )}`;
}

export function hexToHsv(hex: string): Hsv {
  const raw = hex.trim().replace(/^#/, "");
  const full =
    raw.length === 3 ? raw.split("").map((c) => c + c).join("") : raw.padEnd(6, "0").slice(0, 6);

  const r = parseInt(full.slice(0, 2), 16) / 255;
  const g = parseInt(full.slice(2, 4), 16) / 255;
  const b = parseInt(full.slice(4, 6), 16) / 255;
  if (![r, g, b].every(Number.isFinite)) return { h: 0, s: 0, v: 0 };

  const max = Math.max(r, g, b);
  const min = Math.min(r, g, b);
  const d = max - min;

  let h = 0;
  if (d !== 0) {
    if (max === r) h = ((g - b) / d) % 6;
    else if (max === g) h = (b - r) / d + 2;
    else h = (r - g) / d + 4;
    h *= 60;
    if (h < 0) h += 360;
  }

  return { h, s: max === 0 ? 0 : (d / max) * 100, v: max * 100 };
}

/**
 * Where a click in the saturation/value square lands, as a colour.
 *
 * `x` and `y` are fractions of the square, and they are clamped rather than
 * rejected: a drag that leaves the square should stop at its edge, not stop
 * responding.
 */
export function pickFromSquare(hue: number, x: number, y: number): string {
  return hsvToHex({ h: hue, s: clamp(x, 0, 1) * 100, v: (1 - clamp(y, 0, 1)) * 100 });
}
