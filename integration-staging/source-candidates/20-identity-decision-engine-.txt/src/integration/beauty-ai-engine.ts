import { IdentityDecisionEngine } from '../engine/identity-decision-engine';
import { ValidSeason, CriticalRegion } from '../types/core';
import { SEASON_MAP } from '../constants/seasons';

export class BeautyAIEngine {
  private engine = IdentityDecisionEngine.getInstance();
  private featureFlags = new Map<string, boolean>();

  async validateVirtualTryOn(
    userId: string,
    virtualItems: {
      clothing: string[];
      makeup: string;
      accessories?: string[];
      hairStyle?: string;
    },
    userContext: {
      identities?: string[];
      location: string;
      season?: string;
      culturalPreferences?: Array<{ culture: string; criticalRegions: string[]; }>;
    },
    options?: { strictMode?: boolean; includeSuggestions?: boolean; }
  ): Promise<{
    approved: boolean;
    confidence: number;
    decisionId: string;
    culturalNotes: string[];
    suggestions?: string[];
    metadata: { processingTime: number; cacheHit: boolean; };
  }> {
    const startTime = performance.now();
    const allItems = [
      ...virtualItems.clothing,
      `makeup:${virtualItems.makeup}`,
      ...(virtualItems.accessories || []),
      ...(virtualItems.hairStyle ? [`hair:${virtualItems.hairStyle}`] : [])
    ];

    const input = {
      declaredIdentity: userContext.identities,
      clothingItems: allItems,
      location: userContext.location,
      season: userContext.season || this.detectSeason(),
      timestamp: Date.now(),
      culturalRequirements: userContext.culturalPreferences?.map(pref => ({
        culture: pref.culture,
        regions: pref.criticalRegions as CriticalRegion[]
      })),
      correlationId: `beauty-ai-${userId}-${Date.now()}`
    };

    const decision = await this.engine.resolve(input);
    const culturalNotes = this.extractCulturalNotes(decision);
    let suggestions: string[] | undefined;
    if (options?.includeSuggestions && decision.status !== 'APPROVED') {
      suggestions = this.generateSuggestions(decision);
    }

    return {
      approved: decision.status === 'APPROVED',
      confidence: this.extractConfidence(decision),
      decisionId: decision.hash,
      culturalNotes,
      suggestions,
      metadata: {
        processingTime: decision.metadata.processingMs,
        cacheHit: decision.metadata.cacheHit
      }
    };
  }

  async batchValidate(validations: Array<{ userId: string; virtualItems: any; userContext: any; }>): Promise<Array<{ userId: string; result: any; }>> {
    const inputs = validations.map(v => ({
      declaredIdentity: v.userContext.identities,
      clothingItems: v.virtualItems.clothing,
      location: v.userContext.location,
      season: v.userContext.season || this.detectSeason(),
      timestamp: Date.now(),
      culturalRequirements: v.userContext.culturalPreferences?.map((pref: any) => ({
        culture: pref.culture,
        regions: pref.criticalRegions
      })),
      correlationId: `batch-${v.userId}`
    }));
    const decisions = await this.engine.resolveBatch(inputs);
    return decisions.map((d, i) => ({
      userId: validations[i].userId,
      result: {
        approved: d.status === 'APPROVED',
        confidence: this.extractConfidence(d),
        decisionId: d.hash
      }
    }));
  }

  private detectSeason(): ValidSeason {
    const month = new Date().getMonth();
    return SEASON_MAP[month];
  }

  private extractCulturalNotes(decision: any): string[] {
    const notes: string[] = [];
    if (decision.constraints.some((c: string) => c.includes('PARTIAL_IDENTITY_MATCH')))
      notes.push('Some cultural identities were partially recognized');
    if (decision.constraints.some((c: string) => c.includes('TREND_IMPACT')))
      notes.push('Seasonal or location context considered');
    if (decision.source === 'EXPLICIT') notes.push('Based on explicit cultural declaration');
    else if (decision.source === 'WARDROBE') notes.push('Inferred from clothing patterns');
    else if (decision.source === 'HYBRID') notes.push('Combined explicit and wardrobe analysis');
    return notes;
  }

  private generateSuggestions(decision: any): string[] {
    const suggestions: string[] = [];
    if (decision.constraints.some((c: string) => c.startsWith('CMCS_BLOCKED')))
      suggestions.push('Consider adding garments to improve coverage');
    if (decision.constraints.some((c: string) => c.startsWith('TREND_IMPACT')))
      suggestions.push('This outfit may be more appropriate in a different season or location');
    if (decision.status === 'NEEDS_REVIEW')
      suggestions.push('Unable to determine cultural appropriateness - please provide more context');
    return suggestions;
  }

  private extractConfidence(decision: any): number {
    if (typeof decision.identity === 'object' && decision.identity && 'confidence' in decision.identity)
      return decision.identity.confidence;
    if (decision.status === 'APPROVED') return 1.0;
    if (decision.status === 'BLOCKED') return 0.0;
    return 0.5;
  }

  enableFeature(feature: string): void { this.featureFlags.set(feature, true); }
  disableFeature(feature: string): void { this.featureFlags.set(feature, false); }
  isFeatureEnabled(feature: string): boolean { return this.featureFlags.get(feature) || false; }
}
