import { describe, expect, it } from "vitest";
import { isIntentionalPaintDrag, PAINT_DRAG_THRESHOLD_PX } from "./presenzeSelection";

describe("selezione multipla Presenze", () => {
  it("tratta i piccoli spostamenti del clic come una sola cella", () => {
    expect(isIntentionalPaintDrag({ x: 100, y: 100 }, { x: 103, y: 102 })).toBe(false);
  });

  it("attiva il rettangolo soltanto dopo un trascinamento reale", () => {
    expect(isIntentionalPaintDrag(
      { x: 100, y: 100 },
      { x: 100 + PAINT_DRAG_THRESHOLD_PX, y: 100 },
    )).toBe(true);
  });
});

