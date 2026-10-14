import { FastHash } from '../utils';
import { DecisionIntent, CirvannaInput } from '../types';

export class DecisionIntentContract {
  private auditLog: Array<{
    intent: DecisionIntent;
    inputHash: string;
    timestamp: number;
    requestId?: string;
  }> = [];
  
  private batchQueue: Array<typeof this.auditLog[0]> = [];
  private batchTimer: any = null;
  private isProcessing = false;
  
  validateIntent(intent: string): DecisionIntent {
    const validIntents: DecisionIntent[] = [
      'MODESTY_COMPLIANCE', 'AESTHETIC_OPTIMIZATION',
      'CULTURAL_PRESERVATION', 'EXPLORATORY_SUGGESTION'
    ];
    
    if (!validIntents.includes(intent as DecisionIntent)) {
      throw new Error(`Invalid intent: ${intent}`);
    }
    
    return intent as DecisionIntent;
  }
  
  async recordAudit(intent: DecisionIntent, input: CirvannaInput): Promise<void> {
    const entry = {
      intent,
      inputHash: FastHash.hashSync(input),
      timestamp: Date.now(),
      requestId: input.requestId
    };
    
    this.batchQueue.push(entry);
    
    if (!this.batchTimer && !this.isProcessing) {
      this.batchTimer = setTimeout(() => this.processBatch(), 100);
    }
  }
  
  private async processBatch(): Promise<void> {
    if (this.isProcessing || this.batchQueue.length === 0) return;
    
    this.isProcessing = true;
    this.batchTimer = null;
    
    const batch = this.batchQueue.splice(0, 50);
    
    try {
      await new Promise(resolve => setTimeout(resolve, 0));
      this.auditLog.push(...batch);
      
      if (this.auditLog.length > 1000) {
        this.auditLog = this.auditLog.slice(-1000);
      }
    } catch (error) {
      console.error('Audit batch failed:', error);
    } finally {
      this.isProcessing = false;
      
      if (this.batchQueue.length > 0) {
        this.batchTimer = setTimeout(() => this.processBatch(), 100);
      }
    }
  }
  
  cleanup(): void {
    if (this.batchTimer) {
      clearTimeout(this.batchTimer);
      this.batchTimer = null;
    }
    this.batchQueue.length = 0;
  }
}
