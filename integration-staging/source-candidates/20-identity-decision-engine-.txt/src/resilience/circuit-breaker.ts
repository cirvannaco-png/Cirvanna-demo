export class CircuitBreaker {
  private state: 'CLOSED' | 'OPEN' | 'HALF_OPEN' = 'CLOSED';
  private failures = 0;
  private halfOpenAttempts = 0;
  private nextAttempt = 0;
  private stats = { successes: 0, failures: 0, trips: 0 };

  constructor(
    private readonly failureThreshold: number = 5,
    private readonly resetTimeout: number = 60000,
    private readonly halfOpenMaxAttempts: number = 3
  ) {}

  async execute<T>(operation: () => Promise<T>, fallback?: () => Promise<T>): Promise<T> {
    if (this.state === 'OPEN') {
      if (Date.now() > this.nextAttempt) {
        this.state = 'HALF_OPEN';
        this.halfOpenAttempts = 0;
      } else {
        if (fallback) return fallback();
        throw new Error('Circuit breaker is OPEN');
      }
    }

    try {
      const result = await operation();
      if (this.state === 'HALF_OPEN') {
        this.halfOpenAttempts++;
        if (this.halfOpenAttempts >= this.halfOpenMaxAttempts) {
          this.failures = 0;
          this.state = 'CLOSED';
        }
      } else {
        this.failures = 0;
      }
      this.stats.successes++;
      return result;
    } catch (error) {
      this.recordFailure();
      if (fallback) return fallback();
      throw error;
    }
  }

  private recordFailure(): void {
    this.failures++;
    this.stats.failures++;
    if (this.state === 'HALF_OPEN') {
      this.state = 'OPEN';
      this.nextAttempt = Date.now() + this.resetTimeout;
      this.stats.trips++;
    } else if (this.state === 'CLOSED' && this.failures >= this.failureThreshold) {
      this.state = 'OPEN';
      this.nextAttempt = Date.now() + this.resetTimeout;
      this.stats.trips++;
    }
  }

  getState(): string { return this.state; }
  getStats() { return { ...this.stats, state: this.state }; }
}
