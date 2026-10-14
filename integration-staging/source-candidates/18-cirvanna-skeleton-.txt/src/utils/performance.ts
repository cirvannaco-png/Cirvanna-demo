export class PerformanceTracker {
  private static readonly isBrowser = typeof window !== 'undefined';
  private static readonly isNode = typeof process !== 'undefined' && process.versions?.node;
  
  static now(): number {
    return typeof performance !== 'undefined' && performance.now 
      ? performance.now() 
      : Date.now();
  }
  
  static memoryUsage(): number {
    if (this.isNode && process.memoryUsage) {
      return process.memoryUsage().heapUsed;
    }
    return 0;
  }
  
  static measure<T>(label: string, operation: () => T): T {
    const start = this.now();
    try {
      return operation();
    } finally {
      const duration = this.now() - start;
      if (duration > 10) {
        console.debug(`[Perf] ${label}: ${duration.toFixed(2)}ms`);
      }
    }
  }
}
