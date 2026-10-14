import { DecisionIntent } from './index';

export interface DecisionOutput {
  outfits: OutfitOption[];
  conflict: HybridResolution;
  humility: boolean;
  humilityReason?: string;
  confidenceThreshold: number;
  updatedRegrets: RegretSignal[];
  metrics: {
    processingTime: number;
    memoryUsage: number;
    regretCount: number;
    trendCount: number;
    lookCount: number;
    stageTimings: Record<string, number>;
  };
  requestId?: string;
  timestamp: number;
  deterministicId: string;
}

export interface PerformanceMetrics {
  totalDecisions: number;
  humilityTriggers: number;
  avgProcessingTime: number;
  errorCount: number;
  byIntent: Record<DecisionIntent, number>;
  stageTimings: Record<string, { total: number; count: number; avg: number }>;
}
