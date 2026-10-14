export class DeterministicRandom {
  private static readonly A = 1664525;
  private static readonly C = 1013904223;
  private static readonly M = 2 ** 32;

  static seeded(seed: string): number {
    let hash = 0;
    for (let i = 0; i < seed.length; i++) {
      hash = ((hash << 5) - hash) + seed.charCodeAt(i);
      hash |= 0;
    }
    hash = Math.abs(hash);
    hash = (DeterministicRandom.A * hash + DeterministicRandom.C) % DeterministicRandom.M;
    return hash / DeterministicRandom.M;
  }
}
