import { CriticalRegion, CulturalRequirement } from '../types';
import { DEFAULT_CRITICAL } from '../constants/regions';

export class CoverageAnalyzer {
  private static readonly COVERAGE_MAP = new Map<string, readonly CriticalRegion[]>([
    ['hijab', ['head']],
    ['turban', ['head']],
    ['khanzu', ['torso', 'legs', 'arms']],
    ['kimono', ['torso', 'arms']],
    ['robe', ['torso', 'legs', 'arms']],
    ['jacket', ['torso', 'arms']],
    ['pants', ['legs']],
    ['dress', ['torso', 'legs']],
    ['shirt', ['torso', 'arms']],
    ['scarf', ['head', 'torso']]
  ]);

  private static readonly KEYWORD_MAP: Readonly<Record<string, readonly CriticalRegion[]>> = {
    head: ['head'],
    scarf: ['head'],
    hat: ['head'],
    shirt: ['torso', 'arms'],
    top: ['torso'],
    jacket: ['torso', 'arms'],
    coat: ['torso', 'arms'],
    pants: ['legs'],
    trousers: ['legs'],
    skirt: ['legs'],
    dress: ['torso', 'legs']
  };

  static analyze(
    items: readonly string[],
    culturalRequirements?: readonly CulturalRequirement[]
  ): {
    covered: readonly CriticalRegion[];
    uncovered: readonly CriticalRegion[];
    blocked: boolean;
    coverageMap: Readonly<Record<CriticalRegion, boolean>>;
  } {
    const criticalRegions = this.determineCriticalRegions(culturalRequirements);
    const coverage: Record<CriticalRegion, boolean> = {
      head: false,
      torso: false,
      arms: false,
      legs: false
    };

    for (const region of criticalRegions) coverage[region] = false;
    for (const item of items) {
      const regions = this.getItemCoverage(item);
      for (const region of regions) {
        if (criticalRegions.includes(region)) coverage[region] = true;
      }
      if (criticalRegions.every(r => coverage[r])) break;
    }

    const covered: CriticalRegion[] = [];
    const uncovered: CriticalRegion[] = [];
    for (const region of criticalRegions) {
      if (coverage[region]) covered.push(region);
      else uncovered.push(region);
    }

    return {
      covered: Object.freeze(covered),
      uncovered: Object.freeze(uncovered),
      blocked: uncovered.length > 0,
      coverageMap: Object.freeze({ ...coverage })
    };
  }

  private static determineCriticalRegions(
    requirements?: readonly CulturalRequirement[]
  ): readonly CriticalRegion[] {
    if (!requirements || requirements.length === 0) return DEFAULT_CRITICAL;
    const regionSet = new Set<CriticalRegion>();
    for (const req of requirements) for (const region of req.regions) regionSet.add(region);
    return Object.freeze([...regionSet].sort());
  }

  private static getItemCoverage(item: string): readonly CriticalRegion[] {
    const lowerItem = item.toLowerCase();
    for (const [garment, regions] of this.COVERAGE_MAP) {
      if (lowerItem === garment) return regions;
    }
    for (const [garment, regions] of this.COVERAGE_MAP) {
      if (lowerItem.includes(garment) || garment.includes(lowerItem)) return regions;
    }

    const regions: CriticalRegion[] = [];
    for (const [keyword, keywordRegions] of Object.entries(this.KEYWORD_MAP)) {
      if (lowerItem.includes(keyword)) {
        for (const region of keywordRegions) if (!regions.includes(region)) regions.push(region);
      }
    }
    return Object.freeze(regions.sort());
  }
}
