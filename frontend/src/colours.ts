import type { Colour } from "./types";

// Dryness colours (PAGASA rain bands, specs/layer2-impact.md), used by the Impact cards and the map.
// Hex because Leaflet needs colour values, not Tailwind class names. The values are Tailwind's standard shades.
export const colourInfo: Record<Colour, { hex: string; label: string }> = {
  green: { hex: "#22c55e", label: "Healthy (above 80% of normal rain)" },
  yellow: { hex: "#facc15", label: "Stressed (40 to 80% of normal rain)" },
  red: { hex: "#dc2626", label: "Severe (40% of normal rain or less)" },
  grey: { hex: "#9ca3af", label: "No rainfall data" },
};
