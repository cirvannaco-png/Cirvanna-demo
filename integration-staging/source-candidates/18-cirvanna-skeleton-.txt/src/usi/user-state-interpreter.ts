import { TimeUtils, FastHash } from '../utils';
import { CirvannaInput, UserStateVector, DecisionIntent, SocialTemporalContext, LocationContextSignals } from '../types';

export class UserStateInterpreter {
  private static readonly MOOD_MAP = new Float32Array([0.1, 0.15, 0.2, 0.25, 0.3, 0.5, 0.65, 0.75, 0.85, 0.9, 0.95]);
  
  computeUSV(input: CirvannaInput): UserStateVector {
    const mood = Math.max(0, Math.min(1, input.mood ?? 0.5));
    const moodIndex = Math.min(10, Math.floor(mood * 10));
    const moodScore = UserStateInterpreter.MOOD_MAP[moodIndex];
    
    const deterministicSeed = input.deterministicSeed ?? 
      (input.requestId ? FastHash.hashSync(input.requestId) : Date.now());
    
    const defaultSTC: SocialTemporalContext = {
      occasion: 'CASUAL',
      timeOfDay: TimeUtils.getTimeOfDay(),
      season: TimeUtils.getCurrentSeason(),
      socialSetting: 'PUBLIC',
      urgency: 0.5
    };
    
    const defaultLCS: LocationContextSignals = {
      culturalNorms: { 'GLOBAL': 0.5 },
      weather: { temperature: 20, precipitation: 0, humidity: 0.5, uvIndex: 5 },
      venueType: 'MIXED',
      visibility: 'MEDIUM',
      safetyLevel: 0.7
    };
    
    return {
      moodScore,
      overrides: input.overrides ?? {},
      STC: { ...defaultSTC, ...input.STC },
      LCS: { ...defaultLCS, ...input.LCS },
      intent: input.intent,
      confidenceBias: this.calculateBias(input.intent, mood),
      variance: this.calculateVariance(input),
      timestamp: Date.now(),
      deterministicSeed
    };
  }
  
  private calculateBias(intent: DecisionIntent, mood: number): number {
    const biases: Record<DecisionIntent, number> = {
      'MODESTY_COMPLIANCE': -0.1,
      'AESTHETIC_OPTIMIZATION': 0.1,
      'CULTURAL_PRESERVATION': -0.05,
      'EXPLORATORY_SUGGESTION': 0.2
    };
    
    return biases[intent] * (0.5 + mood * 0.5);
  }
  
  private calculateVariance(input: CirvannaInput): number {
    let completeness = 0;
    if (input.mood !== undefined) completeness += 0.25;
    if (input.overrides && Object.keys(input.overrides).length > 0) completeness += 0.25;
    if (input.STC && Object.keys(input.STC).length > 0) completeness += 0.25;
    if (input.LCS && Object.keys(input.LCS).length > 0) completeness += 0.25;
    
    return Math.max(0.1, Math.min(0.9, 1 - completeness));
  }
}
