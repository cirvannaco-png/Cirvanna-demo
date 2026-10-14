import { FinalDecision } from '../types/decisions';
import { MAX_CACHE_SIZE, CACHE_TTL_MS } from '../constants/patterns';

export class OptimizedCache {
  private cache = new Map<string, { value: FinalDecision; expiry: number }>();
  private accessTimes = new Map<string, number>();
  private hits = 0;
  private misses = 0;
  private size = 0;

  get(key: string): FinalDecision | null {
    const item = this.cache.get(key);
    if (!item) {
      this.misses++;
      return null;
    }
    if (Date.now() > item.expiry) {
      this.delete(key);
      this.misses++;
      return null;
    }
    this.accessTimes.set(key, Date.now());
    this.hits++;
    return item.value;
  }

  set(key: string, value: FinalDecision, ttl: number = CACHE_TTL_MS): void {
    if (this.size >= MAX_CACHE_SIZE) this.evictOldest();
    this.cache.set(key, { value, expiry: Date.now() + ttl });
    this.accessTimes.set(key, Date.now());
    this.size++;
  }

  delete(key: string): void {
    if (this.cache.delete(key)) {
      this.accessTimes.delete(key);
      this.size--;
    }
  }

  clear(): void { this.cache.clear(); this.accessTimes.clear(); this.size = 0; this.hits = 0; this.misses = 0; }

  private evictOldest(): void {
    let oldestKey: string | null = null;
    let oldestTime = Date.now();
    for (const [key, time] of this.accessTimes.entries()) {
      if (time < oldestTime) { oldestTime = time; oldestKey = key; }
    }
    if (oldestKey) this.delete(oldestKey);
  }

  stats(): { size: number; hitRate: number; hits: number; misses: number } {
    const total = this.hits + this.misses;
    return {
      size: this.size,
      hits: this.hits,
      misses: this.misses,
      hitRate: total > 0 ? this.hits / total : 0
    };
  }
}
