import { CriticalRegion, ValidSeason, IdentitySource } from './core';

export interface CulturalRequirement {
  readonly culture: string;
  readonly regions: readonly CriticalRegion[];
}

export interface DecisionInput {
  readonly declaredIdentity?: string | readonly string[] | null;
  readonly clothingItems: readonly string[];
  readonly clothingPatterns?: readonly string[];
  readonly location: string;
  readonly season: string;
  readonly timestamp: number;
  readonly culturalRequirements?: readonly CulturalRequirement[];
  readonly correlationId?: string;
}

export interface CoverageAnalysis {
  readonly covered: readonly CriticalRegion[];
  readonly uncovered: readonly CriticalRegion[];
  readonly blocked: boolean;
  readonly coverageMap: Readonly<Record<CriticalRegion, boolean>>;
}

export interface IdentityAnalysis {
  readonly active: boolean;
  readonly identities: readonly string[];
  readonly isPartial: boolean;
  readonly version: string;
}

export interface WardrobeAnalysis {
  readonly active: boolean;
  readonly patterns: readonly {
    readonly type: string;
    readonly confidence: number;
    readonly weight: number;
  }[];
  readonly score: number;
  readonly descriptor: string;
}

export interface TrendAnalysis {
  readonly adjustments: readonly {
    readonly type: string;
    readonly reason: string;
    readonly impact: number;
  }[];
  readonly maxImpact: number;
}
