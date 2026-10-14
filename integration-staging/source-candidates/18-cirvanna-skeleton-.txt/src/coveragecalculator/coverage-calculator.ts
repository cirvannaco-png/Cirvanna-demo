import { UserStateVector, RegionScore, DecisionIntent, BodyRegion } from '../types';

export class CoverageCalculator {
  private readonly baseWeights: Record<BodyRegion, number> = {
    'HEAD': 0.1, 'NECK': 0.15, 'TORSO': 0.3,
    'ARMS': 0.15, 'BACK': 0.15, 'LEGS': 0.15
  };
  
  calculateDeviation(regions: RegionScore[], usv: UserStateVector): { deviation: number; penalty: number } {
    const weights = this.calculateWeights(usv);
    let deviation = 0;
    let totalWeight = 0;
    
    for (const region of regions) {
      const regionWeight = this.calculateRegionWeight(region, weights, usv);
      totalWeight += regionWeight;
      
      if (!region.covered) {
        deviation += regionWeight * (region.required ? 1.5 : 1);
      }
    }
    
    deviation = totalWeight > 0 ? deviation / totalWeight : 0;
    const penalty = this.calculatePenalty(deviation, usv);
    
    return {
      deviation: Math.min(1, deviation),
      penalty
    };
  }
  
  private calculateWeights(usv: UserStateVector): Record<BodyRegion, number> {
    const weights = { ...this.baseWeights };
    
    const multipliers: Record<DecisionIntent, Record<BodyRegion, number>> = {
      'MODESTY_COMPLIANCE': {
        'TORSO': 1.8, 'LEGS': 1.6, 'ARMS': 1.4,
        'BACK': 1.5, 'HEAD': 1.2, 'NECK': 1.3
      },
      'CULTURAL_PRESERVATION': {
        'HEAD': 2.0, 'ARMS': 1.8, 'LEGS': 1.6,
        'TORSO': 1.4, 'BACK': 1.7, 'NECK': 1.5
      },
      'AESTHETIC_OPTIMIZATION': {
        'TORSO': 1.3, 'LEGS': 1.2, 'ARMS': 1.1,
        'BACK': 1.0, 'HEAD': 0.8, 'NECK': 0.9
      },
      'EXPLORATORY_SUGGESTION': {
        'TORSO': 1.0, 'LEGS': 1.0, 'ARMS': 1.0,
        'BACK': 1.0, 'HEAD': 1.0, 'NECK': 1.0
      }
    };
    
    const intentMultiplier = multipliers[usv.intent];
    for (const region of Object.keys(weights) as BodyRegion[]) {
      weights[region] *= intentMultiplier[region];
    }
    
    const total = Object.values(weights).reduce((a, b) => a + b, 0);
    for (const region of Object.keys(weights) as BodyRegion[]) {
      weights[region] /= total;
    }
    
    return weights;
  }
  
  private calculateRegionWeight(
    region: RegionScore,
    dynamicWeights: Record<BodyRegion, number>,
    usv: UserStateVector
  ): number {
    let weight = dynamicWeights[region.region];
    
    if (region.culturalSensitivity > 0) {
      weight *= (1 + region.culturalSensitivity * 0.5);
    }
    
    if (region.required) weight *= 2.0;
    if (region.safetyCritical) weight *= 1.5;
    
    if (usv.overrides.forcedCoverage?.includes(region.region)) {
      weight *= 2.0;
    }
    
    return Math.min(1, weight);
  }
  
  private calculatePenalty(deviation: number, usv: UserStateVector): number {
    let penalty = 0;
    
    if (deviation < 0.1) penalty = deviation * 0.1;
    else if (deviation < 0.3) penalty = 0.01 + (deviation - 0.1) * 0.2;
    else if (deviation < 0.5) penalty = 0.05 + (deviation - 0.3) * 0.4;
    else penalty = 0.13 + (deviation - 0.5) * 0.74;
    
    const scales: Record<DecisionIntent, number> = {
      'MODESTY_COMPLIANCE': 1.5,
      'CULTURAL_PRESERVATION': 1.3,
      'AESTHETIC_OPTIMIZATION': 0.7,
      'EXPLORATORY_SUGGESTION': 0.5
    };
    
    return Math.min(0.5, penalty * scales[usv.intent]);
  }
}
