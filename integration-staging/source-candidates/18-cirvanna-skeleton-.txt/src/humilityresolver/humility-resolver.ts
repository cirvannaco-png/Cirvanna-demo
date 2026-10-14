import { OutfitOption, UserStateVector, HybridResolution, DecisionIntent } from '../types';

export class HumilityResolver {
  checkHumility(
    topOutfit: OutfitOption | undefined,
    usv: UserStateVector,
    coverageScore?: number
  ): { humility: boolean; reason?: string; threshold: number } {
    if (!topOutfit) {
      return { humility: true, reason: 'NO_OUTFITS', threshold: 0 };
    }
    
    const threshold = this.calculateThreshold(usv, coverageScore);
    
    if (topOutfit.confidence < threshold) {
      return {
        humility: true,
        reason: this.getReason(topOutfit.confidence, threshold, usv, coverageScore),
        threshold
      };
    }
    
    if (this.hasCriticalViolations(topOutfit, usv)) {
      return { humility: true, reason: 'CRITICAL_VIOLATION', threshold };
    }
    
    return { humility: false, threshold };
  }
  
  private calculateThreshold(usv: UserStateVector, coverageScore?: number): number {
    const baseThresholds: Record<DecisionIntent, number> = {
      'MODESTY_COMPLIANCE': 0.5,
      'CULTURAL_PRESERVATION': 0.45,
      'AESTHETIC_OPTIMIZATION': 0.3,
      'EXPLORATORY_SUGGESTION': 0.25
    };
    
    let threshold = baseThresholds[usv.intent];
    threshold += usv.variance * 0.2;
    
    if (usv.LCS.safetyLevel < 0.4) threshold += 0.15;
    if (coverageScore !== undefined && coverageScore < 0.7) threshold += 0.1;
    
    return Math.max(0.1, Math.min(0.9, threshold));
  }
  
  private getReason(
    confidence: number,
    threshold: number,
    usv: UserStateVector,
    coverageScore?: number
  ): string {
    if (confidence < threshold * 0.5) return 'CONFIDENCE_VERY_LOW';
    if (usv.variance > 0.7) return 'HIGH_VARIANCE';
    if (usv.intent === 'MODESTY_COMPLIANCE' && confidence < threshold) return 'MODESTY_SAFETY';
    if (coverageScore !== undefined && coverageScore < 0.7) return 'INSUFFICIENT_COVERAGE';
    return 'BELOW_THRESHOLD';
  }
  
  private hasCriticalViolations(outfit: OutfitOption, usv: UserStateVector): boolean {
    if (outfit.metadata.violationFlags.includes('SAFETY_VIOLATION')) return true;
    
    if (usv.LCS.safetyLevel < 0.4 && outfit.metadata.coverageScore < 0.8) {
      return true;
    }
    
    for (const [region, weight] of Object.entries(usv.LCS.culturalNorms)) {
      if (weight > 0.8 && (outfit.metadata.culturalCompliance[region] || 0.5) < 0.7) {
        return true;
      }
    }
    
    return false;
  }
  
  resolveConflicts(
    outfits: OutfitOption[],
    usv: UserStateVector,
    explicitViolations: HybridResolution[] = []
  ): HybridResolution {
    if (explicitViolations.includes('CONFLICT') || outfits.length === 0) {
      return 'CONFLICT';
    }
    
    const topOutfit = outfits[0];
    if (this.hasCriticalViolations(topOutfit, usv)) return 'CONFLICT';
    
    const coverageThresholds: Record<DecisionIntent, number> = {
      'MODESTY_COMPLIANCE': 0.8,
      'CULTURAL_PRESERVATION': 0.7,
      'AESTHETIC_OPTIMIZATION': 0.5,
      'EXPLORATORY_SUGGESTION': 0.4
    };
    
    if (topOutfit.metadata.coverageScore < coverageThresholds[usv.intent] * 0.7) {
      return 'CONFLICT';
    }
    
    const tensionScore = this.calculateTensionScore(topOutfit, usv);
    
    if (tensionScore > 0.6) return 'CONFLICT';
    if (tensionScore > 0.3 || explicitViolations.includes('TENSION')) {
      return 'TENSION';
    }
    
    return 'COMPATIBLE';
  }
  
  private calculateTensionScore(outfit: OutfitOption, usv: UserStateVector): number {
    let score = 0;
    
    if (outfit.confidence < 0.5) {
      score += (0.5 - outfit.confidence) * 2;
    }
    
    const coverageThresholds: Record<DecisionIntent, number> = {
      'MODESTY_COMPLIANCE': 0.8,
      'CULTURAL_PRESERVATION': 0.7,
      'AESTHETIC_OPTIMIZATION': 0.5,
      'EXPLORATORY_SUGGESTION': 0.4
    };
    
    const threshold = coverageThresholds[usv.intent];
    if (outfit.metadata.coverageScore < threshold) {
      score += (threshold - outfit.metadata.coverageScore) * 1.5;
    }
    
    const regretImpact = Math.abs(outfit.metadata.confidenceFactors.regret || 0);
    if (regretImpact > 0.1) score += regretImpact * 0.8;
    
    score += outfit.metadata.violationFlags.length * 0.1;
    
    return Math.min(1, score);
  }
}
