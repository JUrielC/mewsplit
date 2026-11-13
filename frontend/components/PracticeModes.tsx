"use client";

/**
 * Modos de práctica: aíslan combinaciones de stems. Son atajos del mezclador,
 * no un estado aparte — por eso solo mandan la lista de pistas a dejar sonando.
 *
 * Cada modo se calcula sobre las pistas que existen de verdad. Con una lista
 * fija, "sin voz" silenciaba también guitarra y piano al separar en 6 stems.
 */
const MODES: { label: string; pick: (names: string[]) => string[] }[] = [
  { label: "Mezcla completa", pick: () => [] },
  { label: "Aislar bajo", pick: (names) => names.filter((n) => n === "bass") },
  { label: "Sin voz", pick: (names) => names.filter((n) => n !== "vocals") },
  {
    label: "Sección rítmica",
    pick: (names) => names.filter((n) => n === "bass" || n === "drums"),
  },
];

interface Props {
  names: string[];
  active: string[];
  onMode: (tracks: string[]) => void;
}

function sameSet(a: string[], b: string[]): boolean {
  return a.length === b.length && a.every((name) => b.includes(name));
}

export function PracticeModes({ names, active, onMode }: Props) {
  // Sin pistas cargadas todos los modos eligen la lista vacía y saldrían todos marcados.
  const loaded = names.length > 0;

  return (
    <div className="segmented" role="group" aria-label="Modos de práctica">
      {MODES.map((mode) => {
        const tracks = mode.pick(names);
        return (
          <button
            key={mode.label}
            type="button"
            className="button"
            aria-pressed={loaded && sameSet(tracks, active)}
            disabled={!loaded}
            onClick={() => onMode(tracks)}
          >
            {mode.label}
          </button>
        );
      })}
    </div>
  );
}
