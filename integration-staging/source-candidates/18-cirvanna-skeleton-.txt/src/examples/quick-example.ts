import { CirvannaEngine32 } from '../engine';
import { CirvannaInput } from '../types';

export async function quickExample() {
  console.log('👚 Cirvanna 3.2 - Quick Example\n');
  
  const engine = new CirvannaEngine32();
  
  const input: CirvannaInput = {
    intent: 'MODESTY_COMPLIANCE',
    mood: 0.7,
    STC: {
      occasion: 'FORMAL',
      timeOfDay: 'EVENING',
      socialSetting: 'PUBLIC'
    } as any,
    LCS: {
      culturalNorms: { 'MIDDLE_EAST': 0.9 },
      weather: { temperature: 22, precipitation: 0, humidity: 0.4, uvIndex: 3 },
      venueType: 'INDOOR',
      visibility: 'HIGH',
      safetyLevel: 0.6
    } as any,
    regions: [
      {
        region: 'TORSO',
        weight: 0.3,
        covered: true,
        required: true,
        culturalSensitivity: 0.9,
        safetyCritical: true
      },
      {
        region: 'LEGS',
        weight: 0.2,
        covered: true,
        required: true,
        culturalSensitivity: 0.7,
        safetyCritical: false
      }
    ] as any,
    wardrobeItems: ['dress_1', 'jacket_1', 'scarf_1', 'pants_1'],
    requestId: 'quick_example_1'
  };
  
  try {
    const result = await engine.processDecision(input);
    
    console.log('✅ Decision completed');
    console.log(`   Humility: ${result.humility ? 'Yes' : 'No'} ${result.humilityReason ? `(${result.humilityReason})` : ''}`);
    console.log(`   Conflict: ${result.conflict}`);
    console.log(`   Processing: ${result.metrics.processingTime.toFixed(2)}ms`);
    console.log(`   Outfits: ${result.outfits.length}`);
    
    result.outfits.slice(0, 3).forEach((outfit, i) => {
      console.log(`   ${i + 1}. ${outfit.id.slice(0, 12)}... - Confidence: ${outfit.confidence.toFixed(3)}`);
    });
    
    return result;
  } finally {
    engine.cleanup();
  }
}
