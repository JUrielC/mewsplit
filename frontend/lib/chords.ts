/**
 * Notación Harte ("G:min") al cifrado de siempre ("Gm").
 *
 * De momento SOLO mayores y menores, con y sin séptima. El vocabulario del
 * modelo son 170 clases (sus, disminuidos, sextas, dominantes); lo que no
 * está en la tabla sale crudo a propósito, en vez de inventarle una notación
 * que luego haya que deshacer.
 *
 * El backend sigue devolviendo Harte: esto es formato de pantalla, no dato.
 */
const SUFFIXES: Record<string, string> = {
  maj: "",
  min: "m",
  maj7: "maj7",
  min7: "m7",
};

export function formatChord(chord: string): string {
  const separator = chord.indexOf(":");
  if (separator === -1) return chord;

  const suffix = SUFFIXES[chord.slice(separator + 1)];
  if (suffix === undefined) return chord;

  return chord.slice(0, separator) + suffix;
}
