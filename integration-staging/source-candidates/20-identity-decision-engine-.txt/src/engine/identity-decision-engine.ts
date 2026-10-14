import { RingBuffer } from '../structures/ring-buffer';
import { InputValidator } from '../validation/input-validator';
import { CoverageAnalyzer } from '../analysis/coverage-analyzer';
import { analyzeDeclaredIdentity } from '../core/identity';
import { WardrobeAnalyzer } from '../analysis/wardrobe-analyzer';
import { TrendAnalyzer } from '../analysis/trend-analyzer';
import { createHybridIdentity } from '../core/hybrid';
import { DeterministicHasher } from '../core/hashing';
import { OptimizedCache } from '../caching/optimized-cache';
import { CircuitBreaker } from '../resilience/circuit-breaker';
import { DecisionInput, FinalDecision, ProcessingStage, DecisionStatus, IdentitySource, HybridIdentity, CriticalRegion } from '../types';
import { BATCH_SIZE, VERSION } from '../constants';

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

  private constructor() {}

  static getInstance(): IdentityDecisionEngine {
    if (!this.instance) this.instance = new IdentityDecisionEngine();
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
      if (existingPromise) return await existingPromise;

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
        if (decision.status === 'APPROVED' || decision.status === 'BLOCKED') {
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
      const batchResults = await Promise.all(batch.map(inp => this.resolve(inp)));
      results.push(...batchResults);
    }
    return results;
  }

  private async processDecision(input: DecisionInput, startTime: number): Promise<FinalDecision> {
    const stageTimings: Partial<Record<ProcessingStage, number>> = {};

    // CMCS
    const cmcsStart = performance.now();
    const coverage = CoverageAnalyzer.analyze(input.clothingItems, input.culturalRequirements);
    stageTimings.CMCS = performance.now() - cmcsStart;
    if (coverage.blocked) {
      return this.composeFinalDecision(input, coverage, null, null, null, null, stageTimings, false, startTime);
    }

    // CDIL
    const cdilStart = performance.now();
    const identity = await analyzeDeclaredIdentity(input.declaredIdentity);
    stageTimings.CDIL = performance.now() - cdilStart;

    // WDLS – pass critical regions
    const criticalRegions = [...Object.keys(coverage.coverageMap)] as CriticalRegion[];
    const wdlsStart = performance.now();
    const wardrobe = WardrobeAnalyzer.analyze(
      input.clothingItems,
      input.clothingPatterns || [],
      input.season as any,
      coverage.coverageMap,
      criticalRegions
    );
    stageTimings.WDLS = performance.now() - wdlsStart;

    // CTIF
    const ctifStart = performance.now();
    const trend = TrendAnalyzer.analyze(
      input.season as any,
      input.location,
      input.timestamp,
      wardrobe.score,
      identity.active
    );
    stageTimings.CTIF = performance.now() - ctifStart;

    // Hybrid
    const hybridStart = performance.now();
    const hybrid = createHybridIdentity(identity, wardrobe, trend.maxImpact);
    stageTimings.COMPOSITION = performance.now() - hybridStart;

    return this.composeFinalDecision(input, coverage, identity, wardrobe, trend, hybrid, stageTimings, false, startTime);
  }

  private composeFinalDecision(
    input: DecisionInput,
    coverage: { covered: readonly string[]; uncovered: readonly string[]; blocked: boolean; coverageMap: Record<CriticalRegion, boolean> },
    identity: { active: boolean; identities: readonly string[]; isPartial: boolean; version: string } | null,
    wardrobe: { active: boolean; descriptor: string; score: number } | null,
    trend: { maxImpact: number } | null,
    hybrid: HybridIdentity | null,
    stageTimings: Partial<Record<ProcessingStage, number>>,
    cacheHit: boolean,
    startTime: number
  ): FinalDecision {
    let status: DecisionStatus = 'APPROVED';
    if (coverage.blocked) status = 'BLOCKED';
    else if (!hybrid && !identity?.active && !wardrobe?.active) status = 'NEEDS_REVIEW';

    let finalIdentity: FinalDecision['identity'] = null;
    let source: IdentitySource = 'UNDETERMINED';

    if (hybrid) {
      source = hybrid.source;
      finalIdentity = hybrid;
    } else if (identity?.active) {
      source = 'EXPLICIT';
      finalIdentity = identity.identities.length === 1 ? identity.identities[0] : identity.identities;
    } else if (wardrobe?.active) {
      source = 'WARDROBE';
      finalIdentity = wardrobe.descriptor;
    }

    const constraints: string[] = [];
    if (coverage.blocked) constraints.push(`CMCS_BLOCKED:${coverage.uncovered.join(',')}`);
    if (trend?.maxImpact) constraints.push(`TREND_IMPACT:${trend.maxImpact.toFixed(2)}`);
    if (identity?.active) {
      constraints.push(`IDENTITY_VERSION:${identity.version}`);
      if (identity.isPartial) constraints.push('PARTIAL_IDENTITY_MATCH');
    }
    if (wardrobe?.active) constraints.push(`WARDROBE_CONFIDENCE:${wardrobe.score.toFixed(2)}`);
    if (coverage.covered.length) constraints.push(`COVERED_REGIONS:${coverage.covered.join(',')}`);
    constraints.sort();

    const timestamp = Math.floor(Date.now() / 1000) * 1000;
    const hash = DeterministicHasher.hashObject({
      type: 'FINAL_DECISION',
      inputHash: DeterministicHasher.generateInputHash(input as any),
      identity: finalIdentity ? (typeof finalIdentity === 'object' ? JSON.stringify(finalIdentity) : finalIdentity) : null,
      source,
      constraints,
      timestamp: Math.floor(timestamp / 1000)
    });

    return {
      status,
      identity: finalIdentity,
      source,
      constraints: Object.freeze(constraints),
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

  private createErrorDecision(errorType: string, metadata: { error: string; details?: unknown; processingMs: number }): FinalDecision {
    const timestamp = Math.floor(Date.now() / 1000) * 1000;
    const hash = DeterministicHasher.hashObject({
      type: 'ERROR',
      errorType,
      error: metadata.error,
      timestamp: Math.floor(timestamp / 1000)
    });
    return {
      status: 'NEEDS_REVIEW',
      identity: null,
      source: 'UNDETERMINED',
      constraints: Object.freeze([`ERROR:${errorType}`]),
      timestamp,
      hash,
      metadata: { processingMs: metadata.processingMs, cacheHit: false, stageTimings: {} },
      errorDetails: metadata.error,
      partialData: { coverage: { head: false, torso: false, arms: false, legs: false } }
    };
  }

  private recordError(error: unknown): void {
    const key = error instanceof Error ? error.constructor.name : 'UnknownError';
    this.metrics.errorCounts.set(key, (this.metrics.errorCounts.get(key) || 0) + 1);
  }

  clearCache(): void { this.cache.clear(); }

  getMetrics() {
    const times = this.metrics.processingTimes.toArray();
    const avg = times.length ? times.reduce((a,b) => a+b, 0) / times.length : 0;
    const sorted = [...times].sort((a,b) => a-b);
    const p95 = times.length ? sorted[Math.floor(0.95 * times.length)] : 0;
    const hitRate = this.metrics.totalRequests ? (this.metrics.cacheHits / this.metrics.totalRequests) * 100 : 0;
    return {
      totalRequests: this.metrics.totalRequests,
      cacheHitRate: `${hitRate.toFixed(2)}%`,
      avgProcessingTime: `${avg.toFixed(2)}ms`,
      p95ProcessingTime: `${p95.toFixed(2)}ms`,
      errorDistribution: Object.fromEntries(this.metrics.errorCounts),
      cacheStats: this.cache.stats(),
      circuitBreakerState: this.circuitBreaker.getState()
    };
  }

  async runSelfTest(): Promise<void> {
    if (process.env.NODE_ENV !== 'development') return;
    const testInput = {
      declaredIdentity: ['muslim', 'indian'],
      clothingItems: ['hijab', 'khanzu', 'leather shoes'],
      clothingPatterns: ['pattern_solid'],
      location: 'london',
      season: 'winter',
      timestamp: Date.now(),
      culturalRequirements: [
        { culture: 'muslim', criticalRegions: ['head', 'torso', 'arms', 'legs'] }
      ]
    };
    const decision1 = await this.resolve(testInput);
    const decision2 = await this.resolve(testInput);
    if (decision1.hash !== decision2.hash) {
      throw new Error('Self‑test failed: determinism violation');
    }
    console.log('Self‑test passed: determinism verified');
  }
}
