import { CriticalRegion, WardrobeAnalysis } from '../types';

export class WardrobeAnalyzer {
  private static readonly PATTERN_CONFIDENCE: Readonly<Record<string, number>> = {
    'stripes': 0.95,
    'solid': 0.90,
    'floral': 0.85,
    'checkered': 0.88,
    'abstract': 0.75,
    'geometric': 0.80
  };

  private static readonly MATERIAL_KEYWORDS: Readonly<Record<string, readonly string[]>> = {
    'cotton': ['cotton'],
    'wool': ['wool', 'merino', 'cashmere'],
    'silk': ['silk'],
    'leather': ['leather', 'suede'],
    'denim': ['denim', 'jean']
  };

  static analyze(
    items: readonly string[],
    patterns: readonly string[],
    coverage: Readonly<Record<CriticalRegion, boolean>>
  ): WardrobeAnalysis {
    if (items.length === 0) {
      return {
        active: false,
        patterns: Object.freeze([]),
        score: 0,
        descriptor: 'wardrobe:undetermined'
      };
    }

    const patternAnalysis = this.analyzePatterns(patterns, items);
    const materialAnalysis = this.analyzeMaterials(items);
    const coverageAnalysis = this.analyzeCoverage(coverage);

    const allPatterns = [
      ...patternAnalysis,
      ...materialAnalysis,
      ...coverageAnalysis
    ];

    const score = this.calculateScore(allPatterns);
    const descriptor = this.generateDescriptor(allPatterns, score);

    return {
      active: allPatterns.length > 0,
      patterns: Object.freeze(allPatterns),
      score,
      descriptor
    };
  }

  private static analyzePatterns(
    patterns: readonly string[],
    items: readonly string[]
  ): Array<{ type: string; confidence: number; weight: number }> {
    const result: Array<{ type: string; confidence: number; weight: number }> = [];
    for (const pattern of patterns) {
      const confidence = this.PATTERN_CONFIDENCE[pattern] || 0.5;
      const matchingItems = items.filter(item =>
        item.toLowerCase().includes(pattern.toLowerCase())
      ).length;
      const weight = matchingItems / Math.max(1, items.length);

      if (weight > 0) {
        result.push({
          type: `pattern_${pattern}`,
          confidence,
          weight
        });
      }
    }
    return result;
  }

  private static analyzeMaterials(
    items: readonly string[]
  ): Array<{ type: string; confidence: number; weight: number }> {
    const result: Array<{ type: string; confidence: number; weight: number }> = [];
    const materialCounts = new Map<string, number>();

    for (const item of items) {
      const lowerItem = item.toLowerCase();
      for (const [material, keywords] of Object.entries(this.MATERIAL_KEYWORDS)) {
        if (keywords.some(keyword => lowerItem.includes(keyword))) {
          materialCounts.set(material, (materialCounts.get(material) || 0) + 1);
          break;
        }
      }
    }

    for (const [material, count] of materialCounts.entries()) {
      result.push({
        type: `material_${material}`,
        confidence: 0.7,
        weight: count / items.length
      });
    }
    return result;
  }

  private static analyzeCoverage(
    coverage: Readonly<Record<CriticalRegion, boolean>>
  ): Array<{ type: string; confidence: number; weight: number }> {
    const covered = Object.values(coverage).filter(Boolean).length;
    const total = Object.keys(coverage).length;

    if (covered === 0) {
      return [];
    }

    return [{
      type: 'coverage_level',
      confidence: 0.9,
      weight: covered / total
    }];
  }

  private static calculateScore(
    patterns: Array<{ confidence: number; weight: number }>
  ): number {
    if (patterns.length === 0) return 0;

    let weightedSum = 0;
    let totalWeight = 0;

    for (const pattern of patterns) {
      weightedSum += pattern.confidence * pattern.weight;
      totalWeight += pattern.weight;
    }

    return totalWeight > 0 ? weightedSum / totalWeight : 0;
  }

  private static generateDescriptor(
    patterns: Array<{ type: string; confidence: number; weight: number }>,
    score: number
  ): string {
    if (patterns.length === 0) {
      return 'wardrobe:undetermined';
    }

    const groups = new Map<string, string[]>();
    for (const pattern of patterns) {
      const [prefix, value] = pattern.type.split('_', 2);
      if (!groups.has(prefix)) {
        groups.set(prefix, []);
      }
      if (value && !groups.get(prefix)!.includes(value)) {
        groups.get(prefix)!.push(value);
      }
    }

    const parts: string[] = [];
    for (const [prefix, values] of groups.entries()) {
      if (values.length > 0) {
        parts.push(`${prefix}:${values.sort().join('+')}`);
      }
    }

    const confidencePercent = Math.round(score * 100);
    return `wardrobe:${parts.sort().join('|')}|confidence:${confidencePercent}%`;
  }
}
