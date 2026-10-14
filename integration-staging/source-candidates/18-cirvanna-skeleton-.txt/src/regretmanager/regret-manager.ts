import { TimeUtils } from '../utils';
import { OutfitOption, UserStateVector, RegretSignal, DecisionIntent, RegretLayer } from '../types';

export class RegretManager {
  private realTimeRegrets = new Map<string, RegretSignal[]>();
  private coldStorage: RegretSignal[] = [];
  private regretHashes = new Set<string>();
  private lookupCache = new Map<string, RegretSignal[]>();
  private cacheTimestamp = 0;
  private readonly CACHE_TTL = 1000;
  
  constructor(
    private realTimeCap = 100,
    private coldStorageLimit = 10000
  ) {}
  
  applyRegret(outfits: OutfitOption[], usv: UserStateVector): {
    adjustedOutfits: OutfitOption[];
    updatedRegrets: RegretSignal[];
  } {
    const now = Date.now();
    const updatedRegrets: RegretSignal[] = [];
    
    if (now - this.cacheTimestamp > this.CACHE_TTL) {
      this.lookupCache.clear();
      this.cacheTimestamp = now;
    }
    
    const adjustedOutfits = outfits.map(outfit => {
      const regrets = this.getRelevantRegrets(outfit.id, usv);
      let confidence = outfit.confidence;
      let totalImpact = 0;
      
      for (const regret of regrets) {
        const decayed = this.applyDecay(regret);
        const impact = this.calculateImpact(decayed, usv);
        
        confidence *= (1 - Math.min(0.5, impact));
        totalImpact += impact;
        updatedRegrets.push(decayed);
      }
      
      return {
        ...outfit,
        confidence: Math.max(0.1, confidence),
        metadata: {
          ...outfit.metadata,
          confidenceFactors: {
            ...outfit.metadata.confidenceFactors,
            regret: -Math.min(0.5, totalImpact)
          }
        }
      };
    });
    
    this.updateStorage(updatedRegrets);
    return { adjustedOutfits, updatedRegrets };
  }
  
  private getRelevantRegrets(outfitId: string, usv: UserStateVector): RegretSignal[] {
    const cacheKey = `${outfitId}_${usv.intent}`;
    
    if (this.lookupCache.has(cacheKey)) {
      return this.lookupCache.get(cacheKey)!;
    }
    
    const allRegrets = this.realTimeRegrets.get(outfitId) || [];
    const relevant = allRegrets
      .filter(regret => this.isRelevant(regret, usv))
      .slice(-this.realTimeCap);
    
    this.lookupCache.set(cacheKey, relevant);
    return relevant;
  }
  
  private isRelevant(regret: RegretSignal, usv: UserStateVector): boolean {
    if (regret.layer === 'USER_OVERRIDE') return true;
    
    const hours = TimeUtils.hoursSince(regret.timestamp);
    if (hours > 24) return false;
    
    if (regret.context.intent && regret.context.intent !== usv.intent) {
      return false;
    }
    
    return true;
  }
  
  private applyDecay(regret: RegretSignal): RegretSignal {
    const hours = TimeUtils.hoursSince(regret.timestamp);
    const decayFactor = Math.exp(-(regret.decayRate || 0.01) * hours);
    const decayedScore = regret.regretScore * decayFactor * (regret.feedbackWeight || 1.0);
    
    return {
      ...regret,
      regretScore: Math.max(0.01, decayedScore)
    };
  }
  
  private calculateImpact(regret: RegretSignal, usv: UserStateVector): number {
    const suppressionMatrix: Record<RegretLayer, Record<DecisionIntent, number>> = {
      'CULTURAL': {
        'MODESTY_COMPLIANCE': 1.0, 'CULTURAL_PRESERVATION': 1.2,
        'AESTHETIC_OPTIMIZATION': 0.6, 'EXPLORATORY_SUGGESTION': 0.4
      },
      'AESTHETIC': {
        'MODESTY_COMPLIANCE': 0.3, 'CULTURAL_PRESERVATION': 0.4,
        'AESTHETIC_OPTIMIZATION': 1.0, 'EXPLORATORY_SUGGESTION': 0.8
      },
      'USER_OVERRIDE': {
        'MODESTY_COMPLIANCE': 1.0, 'CULTURAL_PRESERVATION': 1.0,
        'AESTHETIC_OPTIMIZATION': 1.0, 'EXPLORATORY_SUGGESTION': 0.9
      },
      'COVERAGE': {
        'MODESTY_COMPLIANCE': 1.2, 'CULTURAL_PRESERVATION': 1.1,
        'AESTHETIC_OPTIMIZATION': 0.5, 'EXPLORATORY_SUGGESTION': 0.3
      },
      'SAFETY': {
        'MODESTY_COMPLIANCE': 1.5, 'CULTURAL_PRESERVATION': 1.3,
        'AESTHETIC_OPTIMIZATION': 0.8, 'EXPLORATORY_SUGGESTION': 0.6
      }
    };
    
    const multiplier = suppressionMatrix[regret.layer]?.[usv.intent] || 1.0;
    return regret.regretScore * multiplier;
  }
  
  private updateStorage(regrets: RegretSignal[]): void {
    for (const regret of regrets) {
      const hash = `${regret.outfitHash}_${regret.layer}_${regret.timestamp}`;
      
      if (this.regretHashes.has(hash)) continue;
      
      this.regretHashes.add(hash);
      
      if (!this.realTimeRegrets.has(regret.outfitHash)) {
        this.realTimeRegrets.set(regret.outfitHash, []);
      }
      
      const list = this.realTimeRegrets.get(regret.outfitHash)!;
      list.push(regret);
      
      if (list.length > this.realTimeCap) {
        const removed = list.splice(0, list.length - this.realTimeCap);
        for (const oldRegret of removed) {
          const oldHash = `${oldRegret.outfitHash}_${oldRegret.layer}_${oldRegret.timestamp}`;
          this.regretHashes.delete(oldHash);
        }
      }
      
      this.coldStorage.push(regret);
      if (this.coldStorage.length > this.coldStorageLimit) {
        const toRemove = this.coldStorage.splice(0, this.coldStorage.length - this.coldStorageLimit);
        for (const oldRegret of toRemove) {
          const oldHash = `${oldRegret.outfitHash}_${oldRegret.layer}_${oldRegret.timestamp}`;
          this.regretHashes.delete(oldHash);
        }
      }
    }
    
    this.lookupCache.clear();
  }
  
  cleanup(): void {
    this.realTimeRegrets.clear();
    this.coldStorage.length = 0;
    this.regretHashes.clear();
    this.lookupCache.clear();
  }
}
