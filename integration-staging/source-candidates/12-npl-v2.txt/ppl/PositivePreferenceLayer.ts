export class PositivePreferenceLayer {
  // No ML – uses explicit user likes stored in DB (simplified)
  async getScore(userId: string, itemId: string): Promise<number> {
    // In reality, fetch from a 'user_likes' table
    // For demo, return 0.5
    return 0.5;
  }
}
