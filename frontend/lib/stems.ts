/** Nombres de los stems en pantalla. La API y los archivos siguen con los de Demucs. */
const LABELS: Record<string, string> = {
  vocals: "voz",
  bass: "bajo",
  drums: "batería",
  guitar: "guitarra",
  piano: "piano",
  other: "otros",
};

/** Orden fijo de arriba abajo; los stems opcionales van al final. */
const ORDER = ["vocals", "bass", "drums", "guitar", "other", "piano"];

export function stemLabel(name: string): string {
  return LABELS[name] ?? name;
}

/** Los stems de un proyecto en el orden del mezclador, sin el instrumental que no se usa. */
export function stemNames(stems: Record<string, unknown>): string[] {
  return Object.keys(stems)
    .filter((name) => name !== "instrumental")
    .sort((a, b) => orderOf(a) - orderOf(b));
}

function orderOf(name: string): number {
  const index = ORDER.indexOf(name);
  return index === -1 ? ORDER.length : index;
}

/** 4 o 6, según el modelo con el que se separa la canción. */
export function stemCount(model: string | null | undefined): 4 | 6 {
  return model?.includes("6s") ? 6 : 4;
}
