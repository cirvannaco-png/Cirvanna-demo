import {
  DecisionInput,
  CoverageAnalysis,
  IdentityAnalysis,
  WardrobeAnalysis,
  TrendAnalysis,
  HybridIdentity,
  FinalDecision,
  DecisionStatus,
  IdentitySource,
  ProcessingStage
} from '../types';

export class DecisionComposer {
  static compose(
    input: DecisionInput,
    coverage: CoverageAnalysis,
    identity: IdentityAnalysis,
    wardrobe: WardrobeAnalysis,
    trend: TrendAnalysis,
    hybrid: HybridIdentity | null,
    stageTimings: Partial<Record<ProcessingStage, number>>,
    cacheHit: boolean,
    startTime: number
  ): FinalDecision {
    let status: DecisionStatus = 'APPROVED';
    if (coverage.blocked) {
      status = 'BLOCKED';
    } else if (!hybrid && !identity.active && !wardrobe.active) {
      status = 'NEEDS_REVIEW';
    }

    let finalIdentity: FinalDecision['identity'] = null;
    let source: IdentitySource = 'UNDETERMINED';

    if (hybrid) {
      source = hybrid.source;
      finalIdentity = hybrid;
    } else if (identity.active) {
      source = 'EXPLICIT';
      finalIdentity = identity.identities.length === 1
        ? identity.identities[0]
        : identity.identities;
    } else if (wardrobe.active) {
      source = 'WARDROBE';
      finalIdentity = wardrobe.descriptor;
    }

    const constraints: string[] = [];
    if (coverage.blocked) {
      constraints.push(`CMCS_BLOCKED:${coverage.uncovered.join(',')}`);
    }
    if (trend.maxImpact > 0) {
      constraints.push(`TREND_IMPACT:${trend.maxImpact.toFixed(2)}`);
    }
    if (identity.active) {
      constraints.push(`IDENTITY_VERSION:${identity.version}`);
      if (identity.isPartial) {
        constraints.push('PARTIAL_IDENTITY_MATCH');
      }
    }
    if (wardrobe.active) {
      constraints.push(`WARDROBE_CONFIDENCE:${wardrobe.score.toFixed(2)}`);
    }
    if (coverage.covered.length > 0) {
      constraints.push(`COVERED_REGIONS:${coverage.covered.join(',')}`);
    }

    const timestamp = Math.floor(Date.now() / 1000) * 1000;
    const hash = this.generateHash({
      inputHash: this.generateInputHash(input),
      identity: finalIdentity,
      source,
      constraints: constraints.sort(),
      timestamp: Math.floor(timestamp / 1000)
    });

    return {
      status,
      identity: finalIdentity,
      source,
      constraints: Object.freeze(constraints.sort()),
      timestamp,
      hash,
      metadata: {
        processingMs: performance.now() - startTime,
        cacheHit,
        correlationId: input.correlationId,
        stageTimings
      }
    };
  }

  private static generateInputHash(input: DecisionInput): string {
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

  private static generateHash(data: any): string {
    const normalized = JSON.stringify(data, (key, value) => {
      if (Array.isArray(value)) {
        return [...value].sort();
      }
      if (value && typeof value === 'object') {
        const sorted = Object.keys(value).sort();
        const result: Record<string, any> = {};
        for (const k of sorted) {
          result[k] = value[k];
        }
        return result;
      }
      return value;
    });
    let hash = 0;
    for (let i = 0; i < normalized.length; i++) {
      hash = ((hash << 5) - hash) + normalized.charCodeAt(i);
      hash |= 0;
    }
    return Math.abs(hash).toString(36).padStart(13, '0');
  }
}
