export class FastHash {
  private static readonly encoder = new TextEncoder();
  
  static async hash(data: any): Promise<string> {
    const str = JSON.stringify(data);
    let hash = 5381;
    
    for (let i = 0; i < str.length; i++) {
      hash = ((hash << 5) + hash) + str.charCodeAt(i);
      hash = hash & hash;
    }
    
    return Math.abs(hash).toString(36).slice(0, 16);
  }
  
  static hashSync(data: any): string {
    const str = JSON.stringify(data);
    let hash = 5381;
    
    for (let i = 0; i < str.length; i++) {
      hash = ((hash << 5) + hash) + str.charCodeAt(i);
    }
    
    return Math.abs(hash).toString(36).slice(0, 16);
  }
}
