export const PAINT_DRAG_THRESHOLD_PX = 6;

export function isIntentionalPaintDrag(start, current, threshold = PAINT_DRAG_THRESHOLD_PX) {
  if (!start || !current) return false;
  return Math.hypot(current.x - start.x, current.y - start.y) >= threshold;
}

