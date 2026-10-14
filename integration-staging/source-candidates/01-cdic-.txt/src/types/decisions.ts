import { IdentitySource, DecisionStatus } from './core';

export interface HybridIdentity {
  readonly explicit: readonly string[];
  readonly wardrobe: string;
  readonly confidence: number;
  readonly source: IdentitySource;
}

export interface FinalDecision {
  readonly status: DecisionStatus;
  readonly identity: string | readonly string[] | HybridIdentity | null;
  readonly source: IdentitySource;
  readonly constraints: readonly string[];
  readonly timestamp: number;
  readonly hash: string;
  readonly metadata: {
    readonly processingMs: number;
    readonly cacheHit: boolean;
    readonly correlationId?: string;
    readonly stageTimings: Partial<Record<ProcessingStage, number>>;
  };
}
