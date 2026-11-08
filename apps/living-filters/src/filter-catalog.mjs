/**
 * Curated metadata for local-only visual effects.
 * This catalogue deliberately excludes face landmarks, skin inference,
 * product claims, and rendering providers. Those require separate validation.
 */
export const FILTERS = Object.freeze([
  Object.freeze({ id: "original", name: "Original", category: "Natural", description: "A clear view, exactly as captured.", cssFilter: "none", effect: "none" }),
  Object.freeze({ id: "golden-hour", name: "Golden Hour", category: "Light & tone", description: "A warm, sunset-inspired colour grade.", cssFilter: "sepia(0.16) saturate(1.16) brightness(1.04)", effect: "none" }),
  Object.freeze({ id: "dewy-light", name: "Dewy Light", category: "Beauty mood", description: "A soft, brightened colour treatment; not a skin assessment.", cssFilter: "saturate(1.08) brightness(1.07) contrast(0.97)", effect: "soft-glow" }),
  Object.freeze({ id: "rose-tint", name: "Rose Tint", category: "Beauty mood", description: "A rosy colour wash for a romantic editorial feel.", cssFilter: "saturate(1.09) hue-rotate(-5deg)", effect: "rose-haze" }),
  Object.freeze({ id: "editorial", name: "Editorial", category: "Studio", description: "A deeper, contrast-led studio grade.", cssFilter: "contrast(1.12) saturate(0.88)", effect: "none" }),
  Object.freeze({ id: "aurora", name: "Aurora", category: "Creative", description: "Iridescent colour light inspired by the northern sky.", cssFilter: "saturate(1.12) hue-rotate(8deg)", effect: "aurora" }),
  Object.freeze({ id: "starlight", name: "Starlight", category: "Creative", description: "A few quiet points of light over your image.", cssFilter: "saturate(1.05) brightness(1.03)", effect: "starlight" }),
  Object.freeze({ id: "film", name: "Soft Film", category: "Studio", description: "A muted film-inspired grade with gentle contrast.", cssFilter: "sepia(0.12) saturate(0.85) contrast(0.96) brightness(1.02)", effect: "none" }),
]);

export const FILTER_BY_ID = Object.freeze(Object.fromEntries(FILTERS.map((filter) => [filter.id, filter])));

export function getFilterById(id) {
  return FILTER_BY_ID[id] ?? FILTER_BY_ID.original;
}