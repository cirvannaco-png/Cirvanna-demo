import { ValidSeason } from '../types/core';

export const PATTERN_DATABASE: Readonly<Record<string, {
  styles: readonly string[];
  confidence: number;
  seasonalRelevance: Readonly<Record<ValidSeason, number>>;
}>> = Object.freeze({
  pattern_stripes: {
    styles: ['casual', 'formal', 'nautical', 'preppy'],
    confidence: 0.95,
    seasonalRelevance: { spring: 0.7, summer: 0.9, fall: 0.6, winter: 0.5 }
  },
  pattern_solid: {
    styles: ['versatile', 'formal', 'minimal', 'basic'],
    confidence: 0.90,
    seasonalRelevance: { spring: 0.8, summer: 0.7, fall: 0.8, winter: 0.9 }
  },
  pattern_floral: {
    styles: ['casual', 'feminine', 'seasonal', 'bohemian'],
    confidence: 0.85,
    seasonalRelevance: { spring: 1.0, summer: 0.9, fall: 0.3, winter: 0.1 }
  },
  pattern_checkered: {
    styles: ['casual', 'country', 'preppy', 'rustic'],
    confidence: 0.88,
    seasonalRelevance: { spring: 0.6, summer: 0.5, fall: 0.9, winter: 0.8 }
  },
  pattern_polka_dot: {
    styles: ['casual', 'feminine', 'retro', 'playful'],
    confidence: 0.82,
    seasonalRelevance: { spring: 0.8, summer: 0.7, fall: 0.5, winter: 0.4 }
  },
  pattern_abstract: {
    styles: ['artistic', 'modern', 'contemporary', 'casual'],
    confidence: 0.75,
    seasonalRelevance: { spring: 0.7, summer: 0.6, fall: 0.7, winter: 0.5 }
  },
  pattern_geometric: {
    styles: ['modern', 'minimal', 'contemporary', 'architectural'],
    confidence: 0.80,
    seasonalRelevance: { spring: 0.6, summer: 0.5, fall: 0.8, winter: 0.7 }
  },
  pattern_animal_print: {
    styles: ['bold', 'trendy', 'casual', 'exotic'],
    confidence: 0.70,
    seasonalRelevance: { spring: 0.5, summer: 0.4, fall: 0.7, winter: 0.6 }
  },
  pattern_camo: {
    styles: ['casual', 'utilitarian', 'streetwear', 'military'],
    confidence: 0.78,
    seasonalRelevance: { spring: 0.6, summer: 0.5, fall: 0.8, winter: 0.7 }
  },
  pattern_paisley: {
    styles: ['bohemian', 'ethnic', 'casual', 'artistic'],
    confidence: 0.72,
    seasonalRelevance: { spring: 0.7, summer: 0.6, fall: 0.5, winter: 0.4 }
  },
});

export const MATERIAL_MAP: Readonly<Record<string, readonly string[]>> = Object.freeze({
  wool: ['wool', 'merino', 'cashmere', 'tweed', 'tartan', 'shearling'],
  cotton: ['cotton', 'denim', 'canvas', 'chambray', 'poplin', 'oxford'],
  synthetic: ['polyester', 'nylon', 'spandex', 'lycra', 'acrylic', 'rayon', 'viscose'],
  leather: ['leather', 'suede', 'pleather', 'faux leather'],
  silk: ['silk', 'satin', 'chiffon', 'organza', 'dupioni'],
  linen: ['linen'],
  velvet: ['velvet', 'velour', 'corduroy'],
  knit: ['knit', 'sweater', 'cardigan', 'jersey', 'ribbed'],
  fleece: ['fleece', 'polar', 'microfleece'],
  down: ['down', 'feather', 'quilted'],
});

export const MAX_CACHE_SIZE = 10000;
export const CACHE_TTL_MS = 300000;
export const MAX_CONCURRENT_PROCESSING = 1000;
export const BATCH_SIZE = 50;
