/**
 * Picks black or white text for a background colour, whichever reads better
 * (WCAG relative luminance). Used for custom accent colours.
 */
export function readableTextOn(hex: string): "#000000" | "#ffffff" {
  const rgb = hex.replace("#", "").match(/.{2}/g)?.map((h) => parseInt(h, 16) / 255);
  if (!rgb || rgb.length !== 3 || rgb.some(Number.isNaN)) return "#ffffff";

  const linear = rgb.map((c) => (c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4));
  const luminance = 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2];

  // Contrast with white vs with black; choose the higher.
  return 1.05 / (luminance + 0.05) >= (luminance + 0.05) / 0.05 ? "#ffffff" : "#000000";
}

/** True for six-digit hex colours like "#3b30ff" (not the short "#fff" form). */
export const isHexColor = (value: string): value is `#${string}` => /^#[0-9a-f]{6}$/i.test(value);
