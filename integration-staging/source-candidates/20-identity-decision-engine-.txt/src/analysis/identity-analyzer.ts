import { IdentityAnalysis } from '../types/analysis';

export class IdentityAnalyzer {
  private static readonly REGISTRY = new Set<string>([
    'muslim', 'indian', 'chinese', 'japanese', 'korean',
    'western', 'african', 'latin', 'middle_eastern'
  ]);
  private static readonly VERSION = '7.0.0';

  static analyze(
    declaredIdentity: string | readonly string[] | null | undefined
  ): IdentityAnalysis {
    if (!declaredIdentity) {
      return {
        active: false,
        identities: Object.freeze([]),
        isPartial: false,
        version: this.VERSION
      };
    }
    const identities = Array.isArray(declaredIdentity)
      ? declaredIdentity
      : [declaredIdentity];
    const valid: string[] = [];
    for (const identity of identities) {
      if (this.REGISTRY.has(identity.toLowerCase())) {
        valid.push(identity);
      }
    }
    return {
      active: valid.length > 0,
      identities: Object.freeze(valid),
      isPartial: valid.length > 0 && valid.length < identities.length,
      version: this.VERSION
    };
  }
}
