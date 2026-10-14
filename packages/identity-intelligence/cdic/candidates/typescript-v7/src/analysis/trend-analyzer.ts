import { ValidSeason, TrendAnalysis } from '../types';

export class TrendAnalyzer {
  static analyze(
    season: ValidSeason,
    location: string,
    timestamp: number,
    wardrobeScore: number,
    hasCulturalIdentity: boolean
  ): TrendAnalysis {
    const adjustments: Array<{ type: string; reason: string; impact: number }> = [];
    const seasonalImpact = this.analyzeSeasonal(season, timestamp);
    if (seasonalImpact > 0) adjustments.push({ type: 'seasonal', reason: `Season ${season} trend factor`, impact: seasonalImpact });
    const locationImpact = this.analyzeLocation(location);
    if (locationImpact > 0) adjustments.push({ type: 'location', reason: `Location ${location} context`, impact: locationImpact });
    const temporalImpact = this.analyzeTemporal(timestamp);
    if (temporalImpact > 0) adjustments.push({ type: 'temporal', reason: 'Time-based trend adjustment', impact: temporalImpact });
    if (hasCulturalIdentity) {
      const culturalImpact = this.analyzeCulturalCoherence(season);
      if (culturalImpact > 0) adjustments.push({ type: 'cultural_seasonal', reason: `Cultural-seasonal coherence for ${season}`, impact: culturalImpact });
    }
    const maxImpact = adjustments.length > 0 ? Math.max(...adjustments.map(a => a.impact)) : 0;
    return { adjustments: Object.freeze(adjustments.sort((a, b) => a.type.localeCompare(b.type))), maxImpact };
  }

  private static analyzeSeasonal(season: ValidSeason, timestamp: number): number {
    const month = new Date(timestamp).getMonth();
    const expectedMonths: Record<ValidSeason, readonly number[]> = {
      spring: [2, 3, 4], summer: [5, 6, 7], fall: [8, 9, 10], winter: [11, 0, 1]
    };
    return expectedMonths[season].includes(month) ? 0 : 0.3;
  }

  private static analyzeLocation(location: string): number {
    const lower = location.toLowerCase();
    if (lower.includes('beach') || lower.includes('pool')) return 0.2;
    if (lower.includes('office') || lower.includes('work')) return 0.3;
    if (lower.includes('wedding') || lower.includes('ceremony')) return 0.4;
    return 0;
  }

  private static analyzeTemporal(timestamp: number): number {
    const hour = new Date(timestamp).getHours();
    return hour >= 22 || hour < 6 ? 0.1 : 0;
  }

  private static analyzeCulturalCoherence(season: ValidSeason): number {
    return season === 'summer' ? 0.2 : 0;
  }
}
