import { CriticalRegion, CulturalRequirement } from '../types/analysis';
import { DEFAULT_CRITICAL, COVERAGE_MAP } from '../constants/regions';

export class CoverageAnalyzer {
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
    const coverage = this.analyzeCoverage(items, criticalRegions);
    const covered = criticalRegions.filter(r => coverage[r]);
    const uncovered = criticalRegions.filter(r => !coverage[r]);
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
    if (!requirements || requirements.length === 0) {
      return DEFAULT_CRITICAL;
    }
    const regionSet = new Set<CriticalRegion>();
    for (const req of requirements) {
      for (const region of req.regions) {
        regionSet.add(region);
      }
    }
    return Object.freeze([...regionSet].sort());
  }

  private static analyzeCoverage(
    items: readonly string[],
    criticalRegions: readonly CriticalRegion[]
  ): Record<CriticalRegion, boolean> {
    const coverage: Record<CriticalRegion, boolean> = {
      head: false,
      torso: false,
      arms: false,
      legs: false
    };
    // Reset only critical regions
    for (const region of criticalRegions) {
      coverage[region] = false;
    }

    for (const item of items) {
      const regions = this.getItemCoverage(item);
      for (const region of regions) {
        if (criticalRegions.includes(region)) {
          coverage[region] = true;
        }
      }
      if (criticalRegions.every(r => coverage[r])) break;
    }
    return coverage;
  }

  private static getItemCoverage(item: string): readonly CriticalRegion[] {
    const lowerItem = item.toLowerCase();
    // Exact match first
    for (const [garment, regions] of Object.entries(COVERAGE_MAP)) {
      if (lowerItem === garment) {
        return regions;
      }
    }
    // Partial match
    for (const [garment, regions] of Object.entries(COVERAGE_MAP)) {
      if (lowerItem.includes(garment) || garment.includes(lowerItem)) {
        return regions;
      }
    }
    // Keyword fallback
    const regions: CriticalRegion[] = [];
    if (lowerItem.includes('head') || lowerItem.includes('scarf') || lowerItem.includes('hat')) {
      regions.push('head');
    }
    if (lowerItem.includes('shirt') || lowerItem.includes('top') || lowerItem.includes('blouse') ||
        lowerItem.includes('jacket') || lowerItem.includes('coat') || lowerItem.includes('vest')) {
      regions.push('torso');
    }
    if (lowerItem.includes('sleeve') || lowerItem.includes('arm') || lowerItem.includes('glove')) {
      regions.push('arms');
    }
    if (lowerItem.includes('pant') || lowerItem.includes('leg') || lowerItem.includes('skirt') ||
        lowerItem.includes('jean') || lowerItem.includes('short')) {
      regions.push('legs');
    }
    return Object.freeze([...new Set(regions)].sort());
  }
}
