/**
 * Monotonic request epoch for invalidating stale asynchronous UI operations.
 *
 * Camera permission prompts can resolve after the user selects a photo or the
 * page becomes hidden. Callers must check isCurrent() before adopting results.
 */
export function createRequestEpoch() {
  let current = 0;

  return Object.freeze({
    begin() {
      current += 1;
      return current;
    },
    invalidate() {
      current += 1;
      return current;
    },
    isCurrent(candidate) {
      return Number.isSafeInteger(candidate) && candidate === current;
    },
  });
}
