import { VALID_SEASONS, SEASON_MAP } from '../constants/seasons';
import { ValidSeason, CriticalRegion, CulturalRequirement, DecisionInput } from '../types';

export class InputValidator {
  static validate(input: unknown):
    | { valid: true; data: DecisionInput; hash: string }
    | { valid: false; error: string; details?: unknown } {
    try {
      if (!input || typeof input !== 'object') {
        return { valid: false, error: 'Input must be an object' };
      }

      const typedInput = input as Record<string, unknown>;
      const items = this.validateClothingItems(typedInput.clothingItems);
      if (!items.valid) return items;

      const season = this.validateSeason(typedInput.season, typedInput.timestamp);
      if (!season.valid) return season;

      const location = this.validateLocation(typedInput.location);
      if (!location.valid) return location;

      const timestamp = this.validateTimestamp(typedInput.timestamp);
      if (!timestamp.valid) return timestamp;

      const patterns = this.validatePatterns(typedInput.clothingPatterns);
      const identity = this.validateIdentity(typedInput.declaredIdentity);
      const cultural = this.validateCultural(typedInput.culturalRequirements);
      const correlationId = typeof typedInput.correlationId === 'string'
        ? typedInput.correlationId
        : undefined;

      const validatedInput: DecisionInput = {
        declaredIdentity: identity.data,
        clothingItems: items.data,
        clothingPatterns: patterns.data,
        location: location.data,
        season: season.data,
        timestamp: timestamp.data,
        culturalRequirements: cultural.data,
        correlationId
      };

      const hash = this.generateHash(validatedInput);
      return { valid: true, data: validatedInput, hash };
    } catch (error) {
      return {
        valid: false,
        error: 'Validation processing error',
        details: error instanceof Error ? error.message : 'Unknown'
      };
    }
  }

  private static validateClothingItems(items: unknown):
    | { valid: true; data: readonly string[] }
    | { valid: false; error: string } {
    if (!Array.isArray(items)) {
      return { valid: false, error: 'clothingItems must be an array' };
    }
    if (items.length === 0) {
      return { valid: false, error: 'clothingItems cannot be empty' };
    }
    if (items.length > 100) {
      return { valid: false, error: 'Too many clothing items (max 100)' };
    }

    const validated: string[] = [];
    for (const item of items) {
      if (typeof item !== 'string') {
        return { valid: false, error: 'All clothing items must be strings' };
      }
      const trimmed = item.trim();
      if (trimmed.length === 0) {
        return { valid: false, error: 'Clothing item cannot be empty string' };
      }
      if (trimmed.length > 200) {
        return { valid: false, error: 'Clothing item too long (max 200 chars)' };
      }
      validated.push(trimmed.toLowerCase());
    }
    return { valid: true, data: Object.freeze(validated) };
  }

  private static validateSeason(season: unknown, timestamp: unknown):
    | { valid: true; data: ValidSeason }
    | { valid: false; error: string } {
    if (typeof season === 'string') {
      const normalized = season.trim().toLowerCase() as ValidSeason;
      if (VALID_SEASONS.includes(normalized)) {
        return { valid: true, data: normalized };
      }
    }
    if (typeof timestamp === 'number' && timestamp > 0) {
      const date = new Date(timestamp);
      return { valid: true, data: SEASON_MAP[date.getMonth()] };
    }
    return { valid: true, data: SEASON_MAP[new Date().getMonth()] };
  }

  private static validateLocation(location: unknown):
    | { valid: true; data: string }
    | { valid: false; error: string } {
    if (typeof location !== 'string') {
      return { valid: false, error: 'location must be a string' };
    }
    const trimmed = location.trim();
    if (trimmed.length === 0) {
      return { valid: false, error: 'location cannot be empty' };
    }
    if (trimmed.length > 200) {
      return { valid: false, error: 'location too long (max 200 chars)' };
    }
    return { valid: true, data: trimmed.toLowerCase() };
  }

  private static validateTimestamp(timestamp: unknown):
    | { valid: true; data: number }
    | { valid: false; error: string } {
    if (typeof timestamp !== 'number') {
      return { valid: false, error: 'timestamp must be a number' };
    }
    if (timestamp <= 0) {
      return { valid: false, error: 'timestamp must be positive' };
    }
    const normalized = Math.floor(timestamp / 1000) * 1000;
    if (normalized > Date.now() + 86400000) {
      return { valid: false, error: 'timestamp cannot be more than 24 hours in future' };
    }
    return { valid: true, data: normalized };
  }

  private static validatePatterns(patterns: unknown):
    | { valid: true; data: readonly string[] }
    | { valid: false; data: readonly string[] } {
    if (!Array.isArray(patterns)) {
      return { valid: false, data: Object.freeze([]) };
    }
    const validated: string[] = [];
    for (const pattern of patterns) {
      if (typeof pattern === 'string') {
        const trimmed = pattern.trim().toLowerCase();
        if (trimmed.length > 0 && trimmed.length <= 50) validated.push(trimmed);
      }
    }
    return { valid: true, data: Object.freeze([...new Set(validated)]) };
  }

  private static validateIdentity(identity: unknown):
    | { valid: true; data: string | readonly string[] | null }
    | { valid: false; data: null } {
    if (identity === null || identity === undefined) return { valid: false, data: null };
    if (typeof identity === 'string') {
      const trimmed = identity.trim().toLowerCase();
      return trimmed.length > 0
        ? { valid: true, data: trimmed }
        : { valid: false, data: null };
    }
    if (Array.isArray(identity)) {
      const validated: string[] = [];
      for (const id of identity) {
        if (typeof id === 'string') {
          const trimmed = id.trim().toLowerCase();
          if (trimmed.length > 0) validated.push(trimmed);
        }
      }
      if (validated.length === 0) return { valid: false, data: null };
      return { valid: true, data: Object.freeze([...new Set(validated)].sort()) };
    }
    return { valid: false, data: null };
  }

  private static validateCultural(requirements: unknown):
    | { valid: true; data: readonly CulturalRequirement[] }
    | { valid: false; data: undefined } {
    if (!Array.isArray(requirements)) return { valid: false, data: undefined };

    const validated: CulturalRequirement[] = [];
    for (const req of requirements) {
      if (req && typeof req === 'object' && 'culture' in req && 'regions' in req) {
        const value = req as { culture: unknown; regions: unknown };
        const culture = String(value.culture).trim().toLowerCase();
        if (culture.length === 0 || !Array.isArray(value.regions)) continue;
        const regions: CriticalRegion[] = [];
        for (const region of value.regions) {
          if (typeof region === 'string' && ['head', 'torso', 'arms', 'legs'].includes(region)) {
            regions.push(region as CriticalRegion);
          }
        }
        if (regions.length > 0) {
          validated.push({ culture, regions: Object.freeze([...new Set(regions)].sort()) });
        }
      }
    }
    if (validated.length === 0) return { valid: false, data: undefined };
    return { valid: true, data: Object.freeze(validated) };
  }

  private static generateHash(input: DecisionInput): string {
    const normalized = {
      identity: Array.isArray(input.declaredIdentity)
        ? [...input.declaredIdentity].sort()
        : input.declaredIdentity,
      items: [...input.clothingItems].sort(),
      patterns: input.clothingPatterns ? [...input.clothingPatterns].sort() : [],
      location: input.location,
      season: input.season,
      timestamp: Math.floor(input.timestamp / 1000),
      cultural: input.culturalRequirements
        ? input.culturalRequirements.map(r => ({
            culture: r.culture,
            regions: [...r.regions].sort()
          })).sort((a, b) => a.culture.localeCompare(b.culture))
        : []
    };
    const json = JSON.stringify(normalized);
    let hash = 0;
    for (let i = 0; i < json.length; i++) {
      hash = ((hash << 5) - hash) + json.charCodeAt(i);
      hash |= 0;
    }
    return Math.abs(hash).toString(36).padStart(13, '0');
  }
}
