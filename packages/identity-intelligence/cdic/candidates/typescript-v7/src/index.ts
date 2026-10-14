import { IdentityDecisionEngine } from './engine/identity-decision-engine';
import { BeautyAIEngine } from './integration/beauty-ai-engine';

const engineInstance = IdentityDecisionEngine.getInstance();

export const resolveIdentityDecision = engineInstance.resolve.bind(engineInstance);
export const resolveIdentityBatch = engineInstance.resolveBatch.bind(engineInstance);
export const clearDecisionCache = engineInstance.clearCache.bind(engineInstance);
export const getEngineMetrics = engineInstance.getMetrics.bind(engineInstance);
export const beautyAIEngine = new BeautyAIEngine();

export * from './types';
export * from './constants';

export async function healthCheck(): Promise<{
  status: 'healthy' | 'degraded' | 'unhealthy';
  details: Record<string, unknown>;
}> {
  try {
    const result = await resolveIdentityDecision({
      clothingItems: ['test-shirt', 'test-pants'],
      location: 'test',
      season: 'summer',
      timestamp: Date.now()
    });
    return {
      status: result.status === 'APPROVED' ? 'healthy' : 'degraded',
      details: {
        version: '7.0.0-candidate',
        testDecision: result.status,
        processingTime: result.metadata.processingMs,
        cacheStats: engineInstance.getMetrics().cacheStats
      }
    };
  } catch (error) {
    return {
      status: 'unhealthy',
      details: {
        error: error instanceof Error ? error.message : 'Unknown',
        timestamp: Date.now()
      }
    };
  }
}
