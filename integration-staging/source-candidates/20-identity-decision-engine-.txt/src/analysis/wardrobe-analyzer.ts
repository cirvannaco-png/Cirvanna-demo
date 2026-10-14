import { CriticalRegion, ValidSeason } from '../types/core';
import { WardrobeAnalysis } from '../types/analysis';
import { PATTERN_DATABASE, MATERIAL_MAP } from '../constants/patterns';
import { COVERAGE_MAP } from '../constants/regions';

export class WardrobeAnalyzer {
  static analyze(
    items: readonly string[],
    patterns: readonly string[],
    season: ValidSeason,
    coverage: Readonly<Record<CriticalRegion, boolean>>,
    criticalRegions: readonly CriticalRegion[]
  ): WardrobeAnalysis {
    try {
      const derived = this.analyzePatterns(patterns, items, season, criticalRegions);
      const material = this.analyzeMaterials(items, criticalRegions);
      const coverageLevel = this.analyzeCoverageLevel(coverage);
      const allAttributes = [...derived, ...material, ...coverageLevel];
      const score = this.calculateCompositeScore(allAttributes);
      const descriptor = this.generateWeightedDescriptor(allAttributes, score);
      return {
        active: allAttributes.length > 0,
        patterns: Object.freeze(allAttributes.map(a => ({ type: a.value, confidence: a.confidence, weight: a.weight }))),
        score,
        descriptor
      };
    } catch (error) {
      return {
        active: false,
        patterns: [],
        score: 0,
        descriptor: 'wardrobe:undetermined'
      };
    }
  }

  private static analyzePatterns(
    patterns: readonly string[],
    items: readonly string[],
    season: ValidSeason,
    criticalRegions: readonly CriticalRegion[]
  ): Array<{ type: string; value: string; confidence: number; weight: number }> {
    const result: Array<{ type: string; value: string; confidence: number; weight: number }> = [];
    for (const pattern of patterns) {
      const patternData = PATTERN_DATABASE[pattern as keyof typeof PATTERN_DATABASE];
      if (!patternData) continue;
      const patternItems = items.filter(item =>
        item.toLowerCase().includes(pattern.replace('pattern_', ''))
      );
      if (patternItems.length === 0) continue;
      const weight = this.calculatePatternWeight(patternItems, criticalRegions);
      const seasonalFactor = patternData.seasonalRelevance[season] || 0.5;
      const confidence = patternData.confidence * seasonalFactor;
      result.push({
        type: 'PATTERN',
        value: pattern,
        confidence,
        weight
      });
      patternData.styles.forEach(style => {
        result.push({
          type: 'STYLE_INFERENCE',
          value: style,
          confidence: confidence * 0.8,
          weight
        });
      });
    }
    return result;
  }

  private static calculatePatternWeight(items: string[], criticalRegions: readonly CriticalRegion[]): number {
    if (items.length === 0) return 0;
    let totalWeight = 0;
    for (const item of items) {
      const regions = this.getItemCoverage(item);
      const coveredCritical = regions.filter(r => criticalRegions.includes(r));
      totalWeight += coveredCritical.length / criticalRegions.length;
    }
    return Math.min(1, totalWeight / items.length);
  }

  private static analyzeMaterials(
    items: readonly string[],
    criticalRegions: readonly CriticalRegion[]
  ): Array<{ type: string; value: string; confidence: number; weight: number }> {
    const materialCounts = new Map<string, { count: number; items: string[] }>();
    for (const item of items) {
      const lower = item.toLowerCase();
      for (const [material, keywords] of Object.entries(MATERIAL_MAP)) {
        if (keywords.some(k => lower.includes(k))) {
          const existing = materialCounts.get(material) || { count: 0, items: [] };
          existing.count++;
          existing.items.push(item);
          materialCounts.set(material, existing);
          break;
        }
      }
    }
    const result: Array<{ type: string; value: string; confidence: number; weight: number }> = [];
    for (const [material, data] of materialCounts.entries()) {
      const weight = this.calculatePatternWeight(data.items, criticalRegions);
      result.push({
        type: 'MATERIAL_INFERENCE',
        value: material,
        confidence: 0.7,
        weight
      });
    }
    return result;
  }

  private static analyzeCoverageLevel(coverage: Record<CriticalRegion, boolean>): Array<{ type: string; value: string; confidence: number; weight: number }> {
    const covered = Object.values(coverage).filter(Boolean).length;
    const total = Object.keys(coverage).length;
    if (covered === 0) return [];
    const levels = [
      { threshold: 4, value: 'FULL_COVERAGE', confidence: 0.95 },
      { threshold: 3, value: 'HIGH_COVERAGE', confidence: 0.85 },
      { threshold: 2, value: 'MODERATE_COVERAGE', confidence: 0.75 },
      { threshold: 1, value: 'MINIMAL_COVERAGE', confidence: 0.65 }
    ];
    for (const level of levels) {
      if (covered >= level.threshold) {
        return [{
          type: 'COVERAGE_LEVEL',
          value: level.value,
          confidence: level.confidence,
          weight: covered / total
        }];
      }
    }
    return [];
  }

  private static calculateCompositeScore(attributes: Array<{ confidence: number; weight: number }>): number {
    if (attributes.length === 0) return 0;
    let weightedSum = 0, totalWeight = 0;
    for (const attr of attributes) {
      weightedSum += attr.confidence * attr.weight;
      totalWeight += attr.weight;
    }
    return totalWeight > 0 ? weightedSum / totalWeight : 0;
  }

  private static generateWeightedDescriptor(
    attributes: Array<{ type: string; value: string; confidence: number; weight: number }>,
    compositeScore: number
  ): string {
    if (attributes.length === 0) return 'wardrobe:undetermined';
    const groups = new Map<string, string[]>();
    for (const attr of attributes) {
      const type = attr.type.toLowerCase().replace('_inference', '');
      if (!groups.has(type)) groups.set(type, []);
      groups.get(type)!.push(attr.value);
    }
    const parts: string[] = [];
    for (const [type, values] of groups.entries()) {
      const top = [...new Set(values)].sort().slice(0, 2);
      if (top.length) parts.push(`${type}:${top.join('+')}`);
    }
    const confidencePercent = Math.round(compositeScore * 100);
    return `wardrobe:${parts.sort().join('|')}|confidence:${confidencePercent}%`;
  }

  private static getItemCoverage(item: string): readonly CriticalRegion[] {
    const lowerItem = item.toLowerCase();
    for (const [garment, regions] of Object.entries(COVERAGE_MAP)) {
      if (lowerItem === garment || lowerItem.includes(garment) || garment.includes(lowerItem)) {
        return regions;
      }
    }
    return [];
  }
}
