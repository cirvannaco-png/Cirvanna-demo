import { ValidationError } from './errors';
import { CirvannaInput, DecisionIntent, BodyRegion } from '../types';

export class InputValidator {
  static validateInput(input: any): asserts input is CirvannaInput {
    if (!input) throw new ValidationError('Input required', 'input');
    if (!input.intent) throw new ValidationError('Intent required', 'intent');
    
    const validIntents: DecisionIntent[] = [
      'MODESTY_COMPLIANCE', 'AESTHETIC_OPTIMIZATION',
      'CULTURAL_PRESERVATION', 'EXPLORATORY_SUGGESTION'
    ];
    
    if (!validIntents.includes(input.intent)) {
      throw new ValidationError(`Invalid intent: ${input.intent}`, 'intent');
    }
    
    if (input.mood !== undefined) {
      if (typeof input.mood !== 'number' || input.mood < 0 || input.mood > 1) {
        throw new ValidationError('Mood must be 0-1', 'mood');
      }
    }
    
    if (input.regions) {
      if (!Array.isArray(input.regions)) {
        throw new ValidationError('Regions must be array', 'regions');
      }
      
      const validRegions: BodyRegion[] = ['HEAD', 'NECK', 'TORSO', 'ARMS', 'BACK', 'LEGS'];
      input.regions.forEach((region: any, i: number) => {
        if (!validRegions.includes(region.region)) {
          throw new ValidationError(`Invalid region at ${i}: ${region.region}`, `regions[${i}].region`);
        }
      });
    }
  }
}
