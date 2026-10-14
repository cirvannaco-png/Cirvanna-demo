import { DecisionIntent, BodyRegion, RegretLayer, HybridResolution, TrendSignal } from './index';

export interface RegionScore {
  region: BodyRegion;
  weight: number;
  covered: boolean;
  required: boolean;
  culturalSensitivity: number;
  safetyCritical: boolean;
}

export interface OverrideRules {
  forcedCoverage?: BodyRegion[];
  bannedItems?: string[];
  mandatoryItems?: string[];
  maxExposure?: number;
}

export interface SocialTemporalContext {
  occasion: 'FORMAL' | 'CASUAL' | 'CEREMONIAL' | 'WORK' | 'SPORT' | 'INTIMATE';
  timeOfDay: 'MORNING' | 'AFTERNOON' | 'EVENING' | 'NIGHT';
  season: 'WINTER' | 'SPRING' | 'SUMMER' | 'AUTUMN';
  socialSetting: 'PUBLIC' | 'PRIVATE' | 'INTIMATE' | 'PROFESSIONAL';
  urgency: number;
}

export interface LocationContextSignals {
  culturalNorms: Record<string, number>;
  weather: {
    temperature: number;
    precipitation: number;
    humidity: number;
    uvIndex: number;
  };
  venueType: 'INDOOR' | 'OUTDOOR' | 'MIXED';
  visibility: 'HIGH' | 'MEDIUM' | 'LOW';
  safetyLevel: number;
}

export interface UserStateVector {
  moodScore: number;
  overrides: OverrideRules;
  STC: SocialTemporalContext;
  LCS: LocationContextSignals;
  intent: DecisionIntent;
  confidenceBias: number;
  variance: number;
  timestamp: number;
  deterministicSeed: number;
}

export interface OutfitMetadata {
  generatedAt: number;
  USV: UserStateVector;
  itemIds: string[];
  coverageScore: number;
  culturalCompliance: Record<string, number>;
  auditTrace: string;
  confidenceFactors: {
    base: number;
    coverage: number;
    regret: number;
    trend: number;
    final: number;
  };
  violationFlags: string[];
}

export interface OutfitOption {
  id: string;
  confidence: number;
  metadata: OutfitMetadata;
}

export interface RegretSignal {
  outfitHash: string;
  regretScore: number;
  layer: RegretLayer;
  timestamp: number;
  context: Partial<UserStateVector>;
  decayRate: number;
  feedbackWeight: number;
  deterministicId: string;
}

export interface TrendLedgerEntry {
  signal: TrendSignal;
  impact: number;
  sourceDataHash: string;
  timestamp: number;
  confidence: number;
  expiration: number;
  region?: string;
}

export interface CirvannaInput {
  intent: DecisionIntent;
  mood?: number;
  overrides?: OverrideRules;
  STC?: Partial<SocialTemporalContext>;
  LCS?: Partial<LocationContextSignals>;
  regions?: RegionScore[];
  regrets?: RegretSignal[];
  trends?: TrendLedgerEntry[];
  violations?: HybridResolution[];
  humilityFeedback?: RegretSignal[];
  wardrobeItems?: string[];
  userId?: string;
  sessionId?: string;
  requestId?: string;
  deterministicSeed?: number;
}
