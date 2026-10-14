import { ValidSeason } from '../types/core';
import { TrendAnalysis } from '../types/analysis';

export class TrendAnalyzer {
  static analyze(
    season: ValidSeason,
    location: string,
    timestamp: number,
    wardrobeScore: number,
    hasCulturalIdentity: boolean
  ): TrendAnalysis {
    const adjustments: Array<{ type: string; reason: string; impact: number }> = [];

    const seasonal = this.analyzeSeasonal(season, timestamp);
    if (seasonal.impact > 0) adjustments.push({ type: 'seasonal', reason: seasonal.reason, impact: seasonal.impact });

    const locationImpact = this.analyzeLocation(location);
    if (locationImpact.impact > 0) adjustments.push({ type: 'location', reason: locationImpact.reason, impact: locationImpact.impact });

    const temporal = this.analyzeTemporal(timestamp);
    if (temporal.impact > 0) adjustments.push({ type: 'temporal', reason: temporal.reason, impact: temporal.impact });

    if (hasCulturalIdentity) {
      const cultural = this.analyzeCulturalCoherence(season);
      if (cultural.impact > 0) adjustments.push({ type: 'cultural_seasonal', reason: cultural.reason, impact: cultural.impact });
    }

    const maxImpact = adjustments.length ? Math.max(...adjustments.map(a => a.impact)) : 0;
    return {
      adjustments: Object.freeze(adjustments.sort((a, b) => a.type.localeCompare(b.type))),
      maxImpact
    };
  }

  private static analyzeSeasonal(season: ValidSeason, timestamp: number): { impact: number; reason: string } {
    const date = new Date(timestamp);
    const month = date.getMonth();
    const expected: Record<ValidSeason, number[]> = {
      spring: [2, 3, 4],
      summer: [5, 6, 7],
      fall: [8, 9, 10],
      winter: [11, 0, 1]
    };
    if (!expected[season].includes(month)) {
      return { impact: 0.3, reason: `Season ${season} doesn't match current month ${month}` };
    }
    return { impact: 0, reason: '' };
  }

  private static analyzeLocation(location: string): { impact: number; reason: string } {
    const lower = location.toLowerCase();
    if (lower.includes('wedding') || lower.includes('gala') || lower.includes('ceremony')) {
      return { impact: 0.4, reason: `Formal venue: ${location}` };
    }
    if (lower.includes('beach') || lower.includes('park') || lower.includes('gym')) {
      return { impact: 0.2, reason: `Casual venue: ${location}` };
    }
    return { impact: 0, reason: '' };
  }

  private static analyzeTemporal(timestamp: number): { impact: number; reason: string } {
    const hour = new Date(timestamp).getHours();
    if (hour >= 22 || hour < 6) {
      return { impact: 0.1, reason: `Night hours (${hour}:00)` };
    }
    return { impact: 0, reason: '' };
  }

  private static analyzeCulturalCoherence(season: ValidSeason): { impact: number; reason: string } {
    if (season === 'summer') {
      return { impact: 0.2, reason: 'Cultural garments may be heavy in summer' };
    }
    return { impact: 0, reason: '' };
  }
}
