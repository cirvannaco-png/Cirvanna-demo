import { DecisionIntentContract } from '../dic';
import { InputValidator } from '../validation';
import { UserStateInterpreter } from '../usi';
import { LookGenerator } from '../lookgenerator';
import { CoverageCalculator } from '../coveragecalculator';
import { RegretManager } from '../regretmanager';
import { TrendLedger } from '../trendledger';
import { HumilityResolver } from '../humilityresolver';
import { CircuitBreaker } from '../circuitbreaker';
import { PerformanceTracker, FastHash } from '../utils';
import { EngineConfig, CirvannaInput, DecisionOutput, PerformanceMetrics } from '../types';

export class CirvannaEngine32 {
  private dic: DecisionIntentContract;
  private validator: InputValidator;
  private usi: UserStateInterpreter;
  private lookGenerator: LookGenerator;
  private coverageCalculator: CoverageCalculator;
  private regretManager: RegretManager;
  private trendLedger: TrendLedger;
  private humilityResolver: HumilityResolver;
  private circuitBreaker: CircuitBreaker;
  
  private metrics: PerformanceMetrics = {
    totalDecisions: 0,
    humilityTriggers: 0,
    avgProcessingTime: 0,
    errorCount: 0,
    byIntent: {
      'MODESTY_COMPLIANCE': 0,
      'AESTHETIC_OPTIMIZATION': 0,
      'CULTURAL_PRESERVATION': 0,
      'EXPLORATORY_SUGGESTION': 0
    },
    stageTimings: {}
  };
  
  private config: EngineConfig;
  
  constructor(config: Partial<EngineConfig> = {}) {
    this.config = {
      maxLookCount: 15,
      minLookCount: 3,
      defaultLookCount: 5,
      regretCap: 100,
      trendCap: 200,
      coldStorageLimit: 10000,
      batchDelay: 100,
      humilityThresholdBase: 0.35,
      circuitBreakerThreshold: 5,
      circuitBreakerResetMs: 60000,
      performanceSamplingRate: 0.1,
      ...config
    };
    
    this.dic = new DecisionIntentContract();
    this.validator = new InputValidator();
    this.usi = new UserStateInterpreter();
    this.lookGenerator = new LookGenerator();
    this.coverageCalculator = new CoverageCalculator();
    this.regretManager = new RegretManager(this.config.regretCap, this.config.coldStorageLimit);
    this.trendLedger = new TrendLedger(this.config.trendCap);
    this.humilityResolver = new HumilityResolver();
    this.circuitBreaker = new CircuitBreaker(
      this.config.circuitBreakerThreshold,
      this.config.circuitBreakerResetMs
    );
  }
  
  async processDecision(input: CirvannaInput): Promise<DecisionOutput> {
    const startTime = PerformanceTracker.now();
    const stageTimings: Record<string, number> = {};
    let stageStart: number;
    
    try {
      this.metrics.totalDecisions++;
      this.metrics.byIntent[input.intent]++;
      
      stageStart = PerformanceTracker.now();
      this.validator.validateInput(input);
      stageTimings.validation = PerformanceTracker.now() - stageStart;
      
      stageStart = PerformanceTracker.now();
      const validatedIntent = this.dic.validateIntent(input.intent);
      await this.dic.recordAudit(validatedIntent, input);
      stageTimings.intent = PerformanceTracker.now() - stageStart;
      
      stageStart = PerformanceTracker.now();
      const usv = this.usi.computeUSV(input);
      stageTimings.usv = PerformanceTracker.now() - stageStart;
      
      stageStart = PerformanceTracker.now();
      let outfits = await this.lookGenerator.generateLooks(usv, input.wardrobeItems);
      stageTimings.generation = PerformanceTracker.now() - stageStart;
      
      stageStart = PerformanceTracker.now();
      let coverageScore: number | undefined;
      if (input.regions && input.regions.length > 0) {
        const { deviation, penalty } = this.coverageCalculator.calculateDeviation(input.regions, usv);
        coverageScore = 1 - deviation;
        
        outfits = outfits.map(outfit => ({
          ...outfit,
          confidence: Math.max(0.1, outfit.confidence - penalty),
          metadata: {
            ...outfit.metadata,
            coverageScore,
            confidenceFactors: {
              ...outfit.metadata.confidenceFactors,
              coverage: -penalty
            }
          }
        }));
      }
      stageTimings.coverage = PerformanceTracker.now() - stageStart;
      
      stageStart = PerformanceTracker.now();
      let updatedRegrets: RegretSignal[] = [];
      if (input.regrets && input.regrets.length > 0) {
        const result = this.regretManager.applyRegret(outfits, usv);
        outfits = result.adjustedOutfits;
        updatedRegrets = result.updatedRegrets;
      }
      stageTimings.regret = PerformanceTracker.now() - stageStart;
      
      stageStart = PerformanceTracker.now();
      let appliedTrends = 0;
      if (input.trends && input.trends.length > 0) {
        const result = this.trendLedger.applyTrendInfluence(outfits, usv);
        outfits = result.influencedOutfits;
        appliedTrends = result.appliedTrends;
        this.trendLedger.addTrendEntries(input.trends);
      }
      stageTimings.trend = PerformanceTracker.now() - stageStart;
      
      stageStart = PerformanceTracker.now();
      outfits.sort((a, b) => b.confidence - a.confidence);
      stageTimings.sorting = PerformanceTracker.now() - stageStart;
      
      stageStart = PerformanceTracker.now();
      const topOutfit = outfits[0];
      const { humility, reason, threshold } = this.humilityResolver.checkHumility(
        topOutfit,
        usv,
        coverageScore
      );
      
      if (humility) this.metrics.humilityTriggers++;
      stageTimings.humility = PerformanceTracker.now() - stageStart;
      
      stageStart = PerformanceTracker.now();
      const conflict = this.humilityResolver.resolveConflicts(
        outfits,
        usv,
        input.violations
      );
      stageTimings.conflict = PerformanceTracker.now() - stageStart;
      
      if (humility && input.humilityFeedback && input.humilityFeedback.length > 0) {
        const boostedFeedback = input.humilityFeedback.map(feedback => ({
          ...feedback,
          regretScore: Math.max(feedback.regretScore, 0.8),
          feedbackWeight: Math.max(feedback.feedbackWeight || 1.0, 1.5),
          context: { ...usv }
        }));
        
        this.regretManager.applyRegret([], usv);
      }
      
      const totalTime = PerformanceTracker.now() - startTime;
      this.updateMetrics(totalTime, stageTimings, humility);
      
      return {
        outfits: outfits.slice(0, 5),
        conflict,
        humility,
        humilityReason: reason,
        confidenceThreshold: threshold,
        updatedRegrets,
        metrics: {
          processingTime: totalTime,
          memoryUsage: PerformanceTracker.memoryUsage(),
          regretCount: input.regrets?.length || 0,
          trendCount: appliedTrends,
          lookCount: outfits.length,
          stageTimings
        },
        requestId: input.requestId,
        timestamp: Date.now(),
        deterministicId: await FastHash.hash({
          seed: usv.deterministicSeed,
          timestamp: startTime,
          requestId: input.requestId
        })
      };
      
    } catch (error) {
      this.metrics.errorCount++;
      
      const totalTime = PerformanceTracker.now() - startTime;
      
      return {
        outfits: [],
        conflict: 'CONFLICT',
        humility: true,
        humilityReason: `System error: ${error instanceof Error ? error.message : 'Unknown error'}`,
        confidenceThreshold: 0.5,
        updatedRegrets: [],
        metrics: {
          processingTime: totalTime,
          memoryUsage: PerformanceTracker.memoryUsage(),
          regretCount: 0,
          trendCount: 0,
          lookCount: 0,
          stageTimings
        },
        requestId: input.requestId,
        timestamp: Date.now(),
        deterministicId: await FastHash.hash(Date.now())
      };
    }
  }
  
  private updateMetrics(totalTime: number, stageTimings: Record<string, number>, humility: boolean): void {
    this.metrics.avgProcessingTime = 
      (this.metrics.avgProcessingTime * (this.metrics.totalDecisions - 1) + totalTime) / 
      this.metrics.totalDecisions;
    
    for (const [stage, time] of Object.entries(stageTimings)) {
      if (!this.metrics.stageTimings[stage]) {
        this.metrics.stageTimings[stage] = { total: 0, count: 0, avg: 0 };
      }
      
      const stageMetric = this.metrics.stageTimings[stage];
      stageMetric.total += time;
      stageMetric.count++;
      stageMetric.avg = stageMetric.total / stageMetric.count;
    }
  }
  
  getMetrics(): PerformanceMetrics {
    return { ...this.metrics };
  }
  
  resetMetrics(): void {
    this.metrics = {
      totalDecisions: 0,
      humilityTriggers: 0,
      avgProcessingTime: 0,
      errorCount: 0,
      byIntent: {
        'MODESTY_COMPLIANCE': 0,
        'AESTHETIC_OPTIMIZATION': 0,
        'CULTURAL_PRESERVATION': 0,
        'EXPLORATORY_SUGGESTION': 0
      },
      stageTimings: {}
    };
  }
  
  cleanup(): void {
    this.dic.cleanup();
    this.regretManager.cleanup();
    this.trendLedger.cleanup();
  }
}
