import { CirvannaEngine32 } from '../engine';
import { CirvannaInput } from '../types';
import { PerformanceTracker } from '../utils';

export class CirvannaTester {
  static async runPerformanceTest(iterations = 1000): Promise<void> {
    console.log(`🚀 Running performance test (${iterations} iterations)...`);
    
    const engine = new CirvannaEngine32();
    const times: number[] = [];
    
    for (let i = 0; i < iterations; i++) {
      const input: CirvannaInput = {
        intent: ['MODESTY_COMPLIANCE', 'AESTHETIC_OPTIMIZATION', 
                'CULTURAL_PRESERVATION', 'EXPLORATORY_SUGGESTION'][i % 4] as any,
        mood: Math.random(),
        wardrobeItems: Array.from({ length: 10 }, (_, j) => `item_${j}`),
        requestId: `test_${i}`,
        deterministicSeed: i
      };
      
      const start = performance.now();
      await engine.processDecision(input);
      times.push(performance.now() - start);
      
      if (i % 100 === 0) {
        console.log(`  Completed ${i}/${iterations}...`);
      }
    }
    
    const avg = times.reduce((a, b) => a + b, 0) / times.length;
    const max = Math.max(...times);
    const p95 = times.sort((a, b) => a - b)[Math.floor(times.length * 0.95)];
    const p99 = times.sort((a, b) => a - b)[Math.floor(times.length * 0.99)];
    
    console.log('\n📊 Performance Results:');
    console.log(`  Average: ${avg.toFixed(2)}ms`);
    console.log(`  Maximum: ${max.toFixed(2)}ms`);
    console.log(`  95th %ile: ${p95.toFixed(2)}ms`);
    console.log(`  99th %ile: ${p99.toFixed(2)}ms`);
    console.log(`  Target (<100ms): ${avg < 100 ? '✅ PASS' : '❌ FAIL'}`);
    
    engine.cleanup();
  }
  
  static async runDeterminismTest(): Promise<boolean> {
    console.log('🧪 Running determinism test...');
    
    const engine = new CirvannaEngine32();
    const input: CirvannaInput = {
      intent: 'AESTHETIC_OPTIMIZATION',
      mood: 0.5,
      wardrobeItems: ['item1', 'item2', 'item3'],
      requestId: 'determinism_test',
      deterministicSeed: 12345
    };
    
    const results = await Promise.all([
      engine.processDecision(input),
      engine.processDecision(input),
      engine.processDecision(input)
    ]);
    
    const allEqual = results.every((result, i) => {
      if (i === 0) return true;
      const prev = results[i - 1];
      
      if (result.outfits.length !== prev.outfits.length) return false;
      
      return result.outfits.every((outfit, j) => {
        const prevOutfit = prev.outfits[j];
        return outfit.id === prevOutfit.id && 
               Math.abs(outfit.confidence - prevOutfit.confidence) < 0.001;
      });
    });
    
    console.log(`  Determinism: ${allEqual ? '✅ PASS' : '❌ FAIL'}`);
    
    engine.cleanup();
    return allEqual;
  }
  
  static async runMemoryTest(iterations = 100): Promise<void> {
    console.log('💾 Running memory leak test...');
    
    const engines: CirvannaEngine32[] = [];
    const initialMemory = PerformanceTracker.memoryUsage();
    
    for (let i = 0; i < iterations; i++) {
      const engine = new CirvannaEngine32();
      engines.push(engine);
      
      for (let j = 0; j < 10; j++) {
        const input: CirvannaInput = {
          intent: 'EXPLORATORY_SUGGESTION',
          mood: Math.random(),
          requestId: `memory_test_${i}_${j}`,
          trends: Array.from({ length: 10 }, (_, k) => ({
            signal: 'SEASON',
            impact: Math.random() * 2 - 1,
            sourceDataHash: `trend_${k}`,
            timestamp: Date.now(),
            confidence: Math.random(),
            expiration: Date.now() + 3600000
          })) as any,
          regrets: Array.from({ length: 5 }, (_, k) => ({
            outfitHash: `outfit_${k}`,
            regretScore: Math.random(),
            layer: 'AESTHETIC',
            timestamp: Date.now(),
            context: {},
            decayRate: 0.01,
            feedbackWeight: 1.0,
            deterministicId: `regret_${k}`
          })) as any
        };
        
        await engine.processDecision(input);
      }
      
      engine.cleanup();
    }
    
    const finalMemory = PerformanceTracker.memoryUsage();
    const memoryGrowth = finalMemory - initialMemory;
    
    console.log(`  Memory growth: ${(memoryGrowth / 1024 / 1024).toFixed(2)}MB`);
    console.log(`  Leak check: ${memoryGrowth < 1024 * 1024 ? '✅ PASS' : '❌ FAIL'}`);
  }
  
  static async runAllTests(): Promise<boolean> {
    console.log('🧪 Running comprehensive test suite...\n');
    
    const tests = [
      () => this.runDeterminismTest(),
      () => this.runPerformanceTest(100),
      () => this.runMemoryTest(10)
    ];
    
    const results = await Promise.allSettled(tests.map(test => test()));
    
    console.log('\n📋 Test Summary:');
    
    let passed = 0;
    let failed = 0;
    
    results.forEach((result, i) => {
      if (result.status === 'fulfilled') {
        if (typeof result.value === 'boolean') {
          if (result.value) passed++;
          else failed++;
        } else {
          passed++;
        }
        console.log(`  Test ${i + 1}: ✅ PASSED`);
      } else {
        failed++;
        console.log(`  Test ${i + 1}: ❌ FAILED - ${result.reason}`);
      }
    });
    
    console.log(`\n  Total: ${passed} passed, ${failed} failed`);
    return failed === 0;
  }
}
