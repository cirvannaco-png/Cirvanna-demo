import { IdentityAnalysis, WardrobeAnalysis, HybridIdentity, IdentitySource } from '../types/analysis';

export class IdentityComposer {
  static compose(
    identityAnalysis: IdentityAnalysis,
    wardrobeAnalysis: WardrobeAnalysis,
    trendImpact: number
  ): HybridIdentity | null {
    if (identityAnalysis.active && !wardrobeAnalysis.active) {
      return {
        explicit: identityAnalysis.identities,
        wardrobe: 'none',
        confidence: 1.0,
        source: 'EXPLICIT'
      };
    }
    if (!identityAnalysis.active && wardrobeAnalysis.active) {
      const confidence = Math.max(0.1, wardrobeAnalysis.score * (1 - trendImpact));
      return {
        explicit: Object.freeze([]),
        wardrobe: wardrobeAnalysis.descriptor,
        confidence,
        source: 'WARDROBE'
      };
    }
    if (identityAnalysis.active && wardrobeAnalysis.active) {
      const explicitWeight = 0.7;
      const wardrobeWeight = 0.3;
      const wardrobeConfidence = wardrobeAnalysis.score * (1 - trendImpact);
      const confidence = (1.0 * explicitWeight) + (wardrobeConfidence * wardrobeWeight);
      return {
        explicit: identityAnalysis.identities,
        wardrobe: wardrobeAnalysis.descriptor,
        confidence: Math.min(0.99, confidence),
        source: 'HYBRID'
      };
    }
    return null;
  }
}
