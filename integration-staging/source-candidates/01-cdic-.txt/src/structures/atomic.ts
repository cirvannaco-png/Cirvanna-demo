export class AtomicValue<T> {
  private value: T;
  private version: number = 0;

  constructor(initialValue: T) {
    this.value = initialValue;
  }

  get(): { value: T; version: number } {
    return { value: this.value, version: this.version };
  }

  set(newValue: T): boolean {
    this.value = newValue;
    this.version++;
    return true;
  }

  compareAndSwap(expected: T, newValue: T): boolean {
    if (this.value === expected) {
      this.value = newValue;
      this.version++;
      return true;
    }
    return false;
  }
}
