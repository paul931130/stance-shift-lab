/** A small stable hash suitable for reproducible demo IDs and values. */
export function stableHash(input: string): string {
  let hash = 0x811c9dc5;
  for (let index = 0; index < input.length; index += 1) {
    hash ^= input.charCodeAt(index);
    hash = Math.imul(hash, 0x01000193);
  }
  return (hash >>> 0).toString(16).padStart(8, "0");
}

export function stableUnit(input: string): number {
  return Number.parseInt(stableHash(input), 16) / 0xffffffff;
}

export function stableNumber(
  input: string,
  minimum: number,
  maximum: number,
  precision = 4,
): number {
  const value = minimum + stableUnit(input) * (maximum - minimum);
  return Number(value.toFixed(precision));
}

export function clamp(value: number, minimum: number, maximum: number): number {
  return Math.min(maximum, Math.max(minimum, value));
}
