import { RingBuffer } from '../structures/ring-buffer';
import { InputValidator } from '../validation/input-validator';
import { CoverageAnalyzer } from '../analysis/coverage-analyzer';
import { IdentityAnalyzer } from '../analysis/identity-analyzer';
import { WardrobeAnalyzer } from '../analysis/wardrobe-analyzer';
import { TrendAnalyzer } from '../analysis/trend-analyzer';
import { IdentityComposer } from '../composition/identity-composer';
import { DecisionComposer } from '../composition/decision-composer';
import { OptimizedCache } from '../caching/optimized-cache';
import { CircuitBreaker } from '../resilience/circuit-breaker';
import {
  DecisionInput,
  FinalDecision,
  ProcessingStage,
  BATCH_SIZE
} from '../types';

export class IdentityDecisionEngine {
  private static instance: IdentityDecisionEngine;
  private cache = new OptimizedCache();
  private processingLocks = new Map<string, Promise<FinalDecision>>();
  private metrics = {
    totalRequests: 0,
    cacheHits: 0,
    processingTimes: new RingBuffer<number>(1000),
    errorCounts: new Map<string, number>()
  };
  private circuitBreaker = new CircuitBreaker();

  private constructor() { }

  static getInstance(): IdentityDecisionEngine {
    if (!this.instance) {
      this.instance = new IdentityDecisionEngine();
    }
    return this.instance;
  }

  async resolve(input: any): Promise<FinalDecision> {
    const startTime = performance.now();
    this.metrics.totalRequests++;

    try {
      const validation = InputValidator.validate(input);
      if (!validation.valid) {
        return this.createErrorDecision('VALIDATION_FAILED', {
          error: validation.error,
          details: validation.details,
          processingMs: performance.now() - startTime
        });
      }

      const validatedInput = validation.data;
      const cacheKey = validation.hash;

      const cached = this.cache.get(cacheKey);
      if (cached) {
        this.metrics.cacheHits++;
        return cached;
      }

      const existingPromise = this.processingLocks.get(cacheKey);
      if (existingPromise) {
        return await existingPromise;
      }

      const processingPromise = this.circuitBreaker.execute(
        () => this.processDecision(validatedInput, startTime),
        () => Promise.resolve(this.createErrorDecision('CIRCUIT_BREAKER_OPEN', {
          error: 'Service temporarily unavailable',
          processingMs: performance.now() - startTime
        }))
      );

      this.processingLocks.set(cacheKey, processingPromise);

      try {
        const decision = await processingPromise;
        if (decision.status === 'APPROVED') {
          this.cache.set(cacheKey, decision);
        }
        return decision;
      } finally {
        this.processingLocks.delete(cacheKey);
      }
    } catch (error) {
      this.recordError(error);
      return this.createErrorDecision('PROCESSING_ERROR', {
        error: error instanceof Error ? error.message : 'Unknown error',
        processingMs: performance.now() - startTime
      });
    } finally {
      const processingTime = performance.now() - startTime;
      this.metrics.processingTimes.push(processingTime);
    }
  }

  async resolveBatch(inputs: any[]): Promise<FinalDecision[]> {
    const batches: any[][] = [];
    for (let i = 0; i < inputs.length; i += BATCH_SIZE) {
      batches.push(inputs.slice(i, i + BATCH_SIZE));
    }

    const results: FinalDecision[] = [];
    for (const batch of batches) {
      const batchResults = await Promise.all(
        batch.map(input => this.resolve(input))
      );
      results.push(...batchResults);
    }

    return results;
  }

  private async processDecision(
    input: DecisionInput,
    startTime: number
  ): Promise<FinalDecision> {
    const stageTimings: Partial<Record<ProcessingStage, number>> = {};

    const coverageStart = performance.now();
    const coverage = CoverageAnalyzer.analyze(
      input.clothingItems,
      input.culturalRequirements
    );
    stageTimings.CMCS = performance.now() - coverageStart;

    if (coverage.blocked) {
      return DecisionComposer.compose(
        input,
        coverage,
        { active: false, identities: [], isPartial: false, version: 'none' },
        { active: false, patterns: [], score: 0, descriptor: '' },
        { adjustments: [], maxImpact: 0 },
        null,
        stageTimings,
        false
      );
    }

    const identityStart = performance.now();
    const identity = IdentityAnalyzer.analyze(input.declaredIdentity);
    stageTimings.CDIL = performance.now() - identityStart;

    const wardrobeStart = performance.now();
    const wardrobe = WardrobeAnalyzer.analyze(
      input.clothingItems,
      input.clothingPatterns || [],
      coverage.coverageMap
    );
    stageTimings.WDLS = performance.now() - wardrobeStart;

    const trendStart = performance.now();
    const trend = TrendAnalyzer.analyze(
      input.season as any,
      input.location,
      input.timestamp,
      wardrobe.score,
      identity.active
    );
    stageTimings.CTIF = performance.now() - trendStart;

    const compositionStart = performance.now();
    const hybrid = IdentityComposer.compose(identity, wardrobe, trend.maxImpact);
    stageTimings.COMPOSITION = performance.now() - compositionStart;

    const decision = DecisionComposer.compose(
      input,
      coverage,
      identity,
      wardrobe,
      trend,
      hybrid,
      stageTimings,
      false
    );

    return decision;
  }

  private createErrorDecision(
    errorType: string,
    metadata: { error: string; details?: unknown; processingMs: number }
  ): FinalDecision {
    const timestamp = Math.floor(Date.now() / 1000) * 1000;

    return {
      status: 'NEEDS_REVIEW',
      identity: null,
      source: 'UNDETERMINED',
      constraints: Object.freeze([`ERROR:${errorType}`]),
      timestamp,
      hash: this.generateErrorHash(errorType, metadata),
      metadata: {
        processingMs: metadata.processingMs,
        cacheHit: false,
        correlationId: undefined,
        stageTimings: {}
      }
    };
  }

  private generateErrorHash(errorType: string, metadata: any): string {
    const data = {
      type: 'ERROR',
      errorType,
      error: metadata.error,
      timestamp: Math.floor(Date.now() / 1000)
    };

    let hash = 0;
    const str = JSON.stringify(data);
    for (let i = 0; i < str.length; i++) {
      hash = ((hash << 5) - hash) + str.charCodeAt(i);
      hash |= 0;
    }

    return Math.abs(hash).toString(36).padStart(13, '0');
  }

  private recordError(error: unknown): void {
    const errorKey = error instanceof Error ? error.constructor.name : 'UnknownError';
    const count = this.metrics.errorCounts.get(errorKey) || 0;
    this.metrics.errorCounts.set(errorKey, count + 1);
  }

  clearCache(): void {
    this.cache.clear();
  }

  getMetrics() {
    const processingTimes = this.metrics.processingTimes.toArray();
    const avgProcessingTime = processingTimes.length > 0
      ? processingTimes.reduce((a, b) => a + b, 0) / processingTimes.length
      : 0;

    const cacheHitRate = this.metrics.totalRequests > 0
      ? (this.metrics.cacheHits / this.metrics.totalRequests) * 100
      : 0;

    return {
      totalRequests: this.metrics.totalRequests,
      cacheHitRate: `${cacheHitRate.toFixed(2)}%`,
      avgProcessingTime: `${avgProcessingTime.toFixed(2)}ms`,
      p95ProcessingTime: this.calculatePercentile(processingTimes, 95),
      errorDistribution: Object.fromEntries(this.metrics.errorCounts),
      cacheStats: this.cache.stats(),
      circuitBreakerState: this.circuitBreaker.getState()
    };
  }

  private calculatePercentile(values: number[], percentile: number): string {
    if (values.length === 0) return '0ms';
    const sorted = [...values].sort((a, b) => a - b);
    const index = Math.ceil((percentile / 100) * sorted.length) - 1;
    return `${sorted[Math.max(0, index)].toFixed(2)}ms`;
  }
}
