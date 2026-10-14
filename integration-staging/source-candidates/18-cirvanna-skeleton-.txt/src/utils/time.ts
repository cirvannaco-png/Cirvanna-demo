export class TimeUtils {
  static getCurrentSeason(): 'WINTER' | 'SPRING' | 'SUMMER' | 'AUTUMN' {
    const month = new Date().getMonth();
    if (month < 3) return 'WINTER';
    if (month < 6) return 'SPRING';
    if (month < 9) return 'SUMMER';
    return 'AUTUMN';
  }
  
  static getTimeOfDay(): 'MORNING' | 'AFTERNOON' | 'EVENING' | 'NIGHT' {
    const hour = new Date().getHours();
    if (hour < 6) return 'NIGHT';
    if (hour < 12) return 'MORNING';
    if (hour < 17) return 'AFTERNOON';
    return 'EVENING';
  }
  
  static hoursSince(timestamp: number): number {
    return (Date.now() - timestamp) / 3600000;
  }
}
