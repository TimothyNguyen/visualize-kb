/** Starting total for a Calculator. */
export const DEFAULT_START = 0;

/** Returns the sum of two numbers. */
export function add(a: number, b: number): number {
  return a + b;
}

/** Something that can add a number to a running total. */
export interface Adder {
  addTo(n: number): number;
}

/** Accumulates a running total. */
export class Calculator implements Adder {
  total: number = DEFAULT_START;

  addTo(n: number): number {
    this.total = add(this.total, n);
    return this.total;
  }
}
