/**
 * Notación Harte ("G:min") al cifrado de siempre ("Gm").
 *
 * La tabla cubre las 14 calidades que puede devolver el modelo; lo que no
 * esté en ella sale crudo a propósito, en vez de inventarle una notación que
 * luego haya que deshacer. Todo en ASCII: "b" y no "♭", "dim" y no "°", para
 * no depender de que la fuente de datos tenga esos glifos.
 *
 * El backend sigue devolviendo Harte: esto es formato de pantalla, no dato.
 */
const SUFFIXES: Record<string, string> = {
  maj: "",
  min: "m",
  dim: "dim",
  aug: "aug",
  maj6: "6",
  min6: "m6",
  "7": "7",
  maj7: "maj7",
  min7: "m7",
  minmaj7: "m(maj7)",
  dim7: "dim7",
  hdim7: "m7b5",
  sus2: "sus2",
  sus4: "sus4",
};

export function formatChord(chord: string): string {
  const separator = chord.indexOf(":");
  if (separator === -1) return chord;

  const suffix = SUFFIXES[chord.slice(separator + 1)];
  if (suffix === undefined) return chord;

  return chord.slice(0, separator) + suffix;
}

/** Nivel de detalle con el que se muestran los acordes. */
export type ChordDetail = "simple" | "full";

/**
 * Calidades con tercera menor. Es la misma regla que usa el backend para
 * agrupar por familia (`MINOR_THIRD` en chords.py): teoría musical, no un
 * parámetro del algoritmo, así que no se desincroniza.
 */
const MINOR_THIRD = new Set(["min", "dim", "min6", "min7", "minmaj7", "dim7", "hdim7"]);

/** "G:7" → "G", "A:hdim7" → "A:min". Raíz y tercera; lo demás se descarta. */
export function toTriad(chord: string): string {
  const separator = chord.indexOf(":");
  if (separator === -1) return chord;

  const root = chord.slice(0, separator);
  return MINOR_THIRD.has(chord.slice(separator + 1)) ? `${root}:min` : root;
}

interface Segment {
  start: number;
  end: number;
  chord: string;
}

/**
 * La progresión reducida a mayores y menores (el modo "simples").
 *
 * Funde los vecinos que quedan iguales ("C" seguido de "C:maj7" pasa a ser
 * un solo "C"): un bloque partido sin cambio de acorde sería un fantasma
 * fabricado aquí, en la pantalla.
 */
export function simplifyChords<T extends Segment>(chords: T[]): T[] {
  const output: T[] = [];
  for (const segment of chords) {
    const chord = toTriad(segment.chord);
    const previous = output[output.length - 1];
    if (previous && previous.chord === chord && previous.end === segment.start) {
      output[output.length - 1] = { ...previous, end: segment.end };
    } else {
      output.push({ ...segment, chord });
    }
  }
  return output;
}
