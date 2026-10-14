import { DeterministicRandom, FastHash } from '../utils';
import { UserStateVector, OutfitOption, DecisionIntent } from '../types';

export class LookGenerator {
  private readonly mockItems = [
    'shirt', 'pants', 'dress', 'jacket', 'skirt',
    'blouse', 'coat', 'scarf', 'hat', 'shoes'
  ];
  
  async generateLooks(usv: UserStateVector, wardrobeItems: string[] = []): Promise<OutfitOption[]> {
    const count = this.calculateCount(usv);
    const baseConfidence = this.calculateConfidence(usv);
    const deterministic = new DeterministicRandom(usv.deterministicSeed);
    
    const promises: Promise<OutfitOption>[] = [];
    
    for (let i = 0; i < count; i++) {
      promises.push(this.generateOutfit(usv, i, baseConfidence, deterministic, wardrobeItems));
    }
    
    return Promise.all(promises);
  }
  
  private calculateCount(usv: UserStateVector): number {
    const baseCounts: Record<DecisionIntent, number> = {
      'MODESTY_COMPLIANCE': 3,
      'CULTURAL_PRESERVATION': 3,
      'AESTHETIC_OPTIMIZATION': 4,
      'EXPLORATORY_SUGGESTION': 8
    };
    
    let count = baseCounts[usv.intent];
    
    if (usv.variance > 0.7) count = Math.min(count + 2, 10);
    if (usv.overrides.mandatoryItems?.length) count = Math.min(count, 4);
    
    return Math.max(2, Math.min(15, count));
  }
  
  private calculateConfidence(usv: UserStateVector): number {
    let confidence = usv.moodScore * 0.6 + 0.4;
    
    const multipliers: Record<DecisionIntent, number> = {
      'MODESTY_COMPLIANCE': 0.9,
      'CULTURAL_PRESERVATION': 0.85,
      'AESTHETIC_OPTIMIZATION': 1.0,
      'EXPLORATORY_SUGGESTION': 0.7
    };
    
    confidence *= multipliers[usv.intent];
    confidence += usv.confidenceBias * 0.2;
    confidence *= (1 - usv.variance * 0.3);
    
    return Math.max(0.1, Math.min(0.95, confidence));
  }
  
  private async generateOutfit(
    usv: UserStateVector,
    index: number,
    baseConfidence: number,
    deterministic: DeterministicRandom,
    wardrobeItems: string[]
  ): Promise<OutfitOption> {
    const id = `outfit_${usv.deterministicSeed}_${index}_${await FastHash.hash(Date.now())}`;
    const coverage = this.simulateCoverage(usv, index, deterministic);
    const culturalCompliance = this.simulateCulturalCompliance(usv, deterministic);
    const items = this.selectItems(wardrobeItems, index, deterministic);
    
    return {
      id,
      confidence: baseConfidence,
      metadata: {
        generatedAt: Date.now(),
        USV: usv,
        itemIds: items,
        coverageScore: coverage,
        culturalCompliance,
        auditTrace: await this.generateTrace(usv.intent, id),
        confidenceFactors: {
          base: baseConfidence,
          coverage: 0,
          regret: 0,
          trend: 0,
          final: baseConfidence
        },
        violationFlags: []
      }
    };
  }
  
  private simulateCoverage(usv: UserStateVector, index: number, deterministic: DeterministicRandom): number {
    const coverageRanges: Record<DecisionIntent, [number, number]> = {
      'MODESTY_COMPLIANCE': [0.9, 1.0],
      'CULTURAL_PRESERVATION': [0.8, 1.0],
      'AESTHETIC_OPTIMIZATION': [0.6, 0.9],
      'EXPLORATORY_SUGGESTION': [0.5, 1.0]
    };
    
    const [min, max] = coverageRanges[usv.intent];
    return min + (deterministic.next() * (max - min));
  }
  
  private simulateCulturalCompliance(usv: UserStateVector, deterministic: DeterministicRandom): Record<string, number> {
    const compliance: Record<string, number> = {};
    
    for (const [region, weight] of Object.entries(usv.LCS.culturalNorms)) {
      compliance[region] = 0.9 - (weight * 0.3) + (deterministic.next() * 0.1 * (1 - weight));
    }
    
    return compliance;
  }
  
  private selectItems(wardrobeItems: string[], index: number, deterministic: DeterministicRandom): string[] {
    if (wardrobeItems.length === 0) {
      const item1 = this.mockItems[index % this.mockItems.length];
      const item2 = this.mockItems[(index + 1) % this.mockItems.length];
      return [`${item1}_${index}`, `${item2}_${index}`];
    }
    
    const count = Math.min(3, Math.max(1, Math.floor(wardrobeItems.length / 4)));
    const selected: string[] = [];
    
    for (let i = 0; i < count; i++) {
      const itemIndex = Math.floor(deterministic.next() * wardrobeItems.length);
      selected.push(wardrobeItems[itemIndex]);
    }
    
    return selected;
  }
  
  private async generateTrace(intent: DecisionIntent, outfitId: string): Promise<string> {
    return `GEN:${intent}:${outfitId}:${await FastHash.hash(Date.now())}`;
  }
}
