import { TrendLedgerEntry, OutfitOption, UserStateVector, DecisionIntent, TrendSignal } from '../types';

export class TrendLedger {
  private ledger: TrendLedgerEntry[] = [];
  private batchQueue: TrendLedgerEntry[] = [];
  private batchTimer: any = null;
  private expirationTimer: any = null;
  private isProcessing = false;
  private readonly ledgerCap: number;
  
  private readonly gatingMatrix: Record<TrendSignal, Record<DecisionIntent, number>> = {
    'SEASON': {
      'MODESTY_COMPLIANCE': 0.0, 'AESTHETIC_OPTIMIZATION': 0.3,
      'CULTURAL_PRESERVATION': 0.1, 'EXPLORATORY_SUGGESTION': 0.6
    },
    'REGION': {
      'MODESTY_COMPLIANCE': 0.0, 'AESTHETIC_OPTIMIZATION': 0.2,
      'CULTURAL_PRESERVATION': 0.5, 'EXPLORATORY_SUGGESTION': 0.7
    },
    'TEMPORAL': {
      'MODESTY_COMPLIANCE': 0.0, 'AESTHETIC_OPTIMIZATION': 0.1,
      'CULTURAL_PRESERVATION': 0.3, 'EXPLORATORY_SUGGESTION': 0.5
    },
    'SOCIAL': {
      'MODESTY_COMPLIANCE': 0.0, 'AESTHETIC_OPTIMIZATION': 0.5,
      'CULTURAL_PRESERVATION': 0.2, 'EXPLORATORY_SUGGESTION': 0.8
    },
    'EVENT': {
      'MODESTY_COMPLIANCE': 0.1, 'AESTHETIC_OPTIMIZATION': 0.4,
      'CULTURAL_PRESERVATION': 0.6, 'EXPLORATORY_SUGGESTION': 0.9
    },
    'TECH': {
      'MODESTY_COMPLIANCE': 0.0, 'AESTHETIC_OPTIMIZATION': 0.3,
      'CULTURAL_PRESERVATION': 0.2, 'EXPLORATORY_SUGGESTION': 0.7
    }
  };
  
  constructor(cap = 200) {
    this.ledgerCap = cap;
    this.startExpirationCleaner();
  }
  
  applyTrendInfluence(outfits: OutfitOption[], usv: UserStateVector): {
    influencedOutfits: OutfitOption[];
    appliedTrends: number;
  } {
    const activeTrends = this.getActiveTrends();
    let appliedTrends = 0;
    
    const influencedOutfits = outfits.map(outfit => {
      let trendBonus = 0;
      let trendCount = 0;
      
      for (const trend of activeTrends) {
        const gatedImpact = this.gatingMatrix[trend.signal][usv.intent];
        if (gatedImpact === 0) continue;
        
        trendBonus += trend.impact * gatedImpact * trend.confidence;
        trendCount++;
        appliedTrends++;
      }
      
      if (trendCount > 0) {
        trendBonus /= trendCount;
      }
      
      const maxInfluence: Record<DecisionIntent, number> = {
        'MODESTY_COMPLIANCE': 0.1,
        'CULTURAL_PRESERVATION': 0.2,
        'AESTHETIC_OPTIMIZATION': 0.3,
        'EXPLORATORY_SUGGESTION': 0.4
      };
      
      trendBonus = Math.max(-maxInfluence[usv.intent], Math.min(maxInfluence[usv.intent], trendBonus));
      
      return {
        ...outfit,
        confidence: Math.max(0.1, Math.min(1, outfit.confidence + trendBonus)),
        metadata: {
          ...outfit.metadata,
          confidenceFactors: {
            ...outfit.metadata.confidenceFactors,
            trend: trendBonus
          }
        }
      };
    });
    
    return { influencedOutfits, appliedTrends };
  }
  
  private getActiveTrends(): TrendLedgerEntry[] {
    const now = Date.now();
    return this.ledger.filter(trend => 
      trend.expiration > now && trend.confidence > 0.3
    );
  }
  
  addTrendEntries(entries: TrendLedgerEntry[]): void {
    this.batchQueue.push(...entries);
    
    if (!this.batchTimer && !this.isProcessing) {
      this.batchTimer = setTimeout(() => this.processBatch(), 50);
    }
  }
  
  private async processBatch(): Promise<void> {
    if (this.isProcessing || this.batchQueue.length === 0) return;
    
    this.isProcessing = true;
    this.batchTimer = null;
    
    const now = Date.now();
    const batch = this.batchQueue.splice(0, 20).filter(entry => entry.expiration > now);
    
    try {
      for (const entry of batch) {
        const index = this.findInsertionIndex(entry.timestamp);
        this.ledger.splice(index, 0, entry);
      }
      
      if (this.ledger.length > this.ledgerCap) {
        this.ledger = this.ledger.slice(-this.ledgerCap);
      }
    } catch (error) {
      console.error('Trend batch processing failed:', error);
    } finally {
      this.isProcessing = false;
      
      if (this.batchQueue.length > 0) {
        this.batchTimer = setTimeout(() => this.processBatch(), 50);
      }
    }
  }
  
  private findInsertionIndex(timestamp: number): number {
    let low = 0;
    let high = this.ledger.length;
    
    while (low < high) {
      const mid = (low + high) >> 1;
      if (this.ledger[mid].timestamp > timestamp) {
        low = mid + 1;
      } else {
        high = mid;
      }
    }
    
    return low;
  }
  
  private startExpirationCleaner(): void {
    const checkExpired = () => {
      const now = Date.now();
      const before = this.ledger.length;
      this.ledger = this.ledger.filter(trend => trend.expiration > now);
      
      if (this.ledger.length < before) {
        console.debug(`Cleaned ${before - this.ledger.length} expired trends`);
      }
      
      this.expirationTimer = setTimeout(checkExpired, 300000);
    };
    
    this.expirationTimer = setTimeout(checkExpired, 300000);
  }
  
  cleanup(): void {
    if (this.batchTimer) {
      clearTimeout(this.batchTimer);
      this.batchTimer = null;
    }
    
    if (this.expirationTimer) {
      clearTimeout(this.expirationTimer);
      this.expirationTimer = null;
    }
    
    this.batchQueue.length = 0;
    this.ledger.length = 0;
  }
}
