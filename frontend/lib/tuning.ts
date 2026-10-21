/**
 * Afinación de la grabación respecto a La 440.
 *
 * Los acordes ya se calculan compensándola (ver analyze_chords en el
 * backend); esto es para quien toca encima: con una grabación corrida ~20
 * cents o más, un instrumento afinado a 440 suena desafinado contra ella.
 */

/** A partir de aquí se avisa: el desvío ya se oye al tocar encima. */
export const TUNING_WARNING_CENTS = 20;

export function isDetuned(cents: number | null | undefined): cents is number {
  return cents != null && Math.abs(cents) >= TUNING_WARNING_CENTS;
}

/** El La al que hay que afinar el instrumento para sonar con la grabación. */
export function referencePitch(cents: number): number {
  return 440 * Math.pow(2, cents / 1200);
}

export function formatCents(cents: number): string {
  return `${cents > 0 ? "+" : ""}${Math.round(cents)} cents`;
}
