import { IdentityDecisionEngine } from './engine/identity-decision-engine';
import { BeautyAIEngine } from './integration/beauty-ai-engine';
import { VERSION } from './constants';

const engineInstance = IdentityDecisionEngine.getInstance();

export const resolveIdentityDecision = engineInstance.resolve.bind(engineInstance);
export const resolveIdentityBatch = engineInstance.resolveBatch.bind(engineInstance);
export const clearDecisionCache = engineInstance.clearCache.bind(engineInstance);
export const getEngineMetrics = engineInstance.getMetrics.bind(engineInstance);
export const beautyAIEngine = new BeautyAIEngine();

export * from './types';
export * from './constants';

export async function healthCheck(): Promise<{ status: 'healthy' | 'degraded' | 'unhealthy'; details: any }> {
  try {
    const testInput = {
      clothingItems: ['test-shirt', 'test-pants'],
      location: 'test',
      season: 'summer',
      timestamp: Date.now()
    };
    const result = await resolveIdentityDecision(testInput);
    return {
      status: result.status === 'APPROVED' ? 'healthy' : 'degraded',
      details: {
        version: VERSION,
        testDecision: result.status,
        processingTime: result.metadata.processingMs,
        cacheStats: engineInstance.getMetrics().cacheStats
      }
    };
  } catch (error) {
    return {
      status: 'unhealthy',
      details: { error: error instanceof Error ? error.message : 'Unknown', timestamp: Date.now() }
    };
  }
}

setInterval(() => {
  const metrics = engineInstance.getMetrics();
  if (metrics.totalRequests > 0) {
    console.log(`Engine metrics: ${JSON.stringify(metrics, null, 2)}`);
  }
}, 60000);

if (process.env.NODE_ENV === 'development') {
  engineInstance.runSelfTest().catch(console.error);
}
