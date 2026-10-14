import { DecisionIntent, BodyRegion, RegretLayer, HybridResolution, TrendSignal } from './index';

export interface EngineConfig {
  maxLookCount: number;
  minLookCount: number;
  defaultLookCount: number;
  regretCap: number;
  trendCap: number;
  coldStorageLimit: number;
  batchDelay: number;
  humilityThresholdBase: number;
  circuitBreakerThreshold: number;
  circuitBreakerResetMs: number;
  performanceSamplingRate: number;
}
