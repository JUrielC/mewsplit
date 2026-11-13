import { useSyncExternalStore } from "react";

/**
 * Preferencias guardadas en localStorage que la interfaz lee al pintar.
 *
 * Con useSyncExternalStore y no copiándolas al estado en un useEffect: la
 * build estática prerenderiza sin localStorage (de ahí el null del servidor)
 * y React pasa al valor guardado al hidratar sin que el HTML deje de
 * coincidir. Lo escrito queda también en memoria: sin almacenamiento
 * (ventana privada, datos bloqueados) la elección dura hasta cerrar la app.
 */
const memory = new Map<string, string | null>();
const listeners = new Set<() => void>();

export function readString(key: string): string | null {
  if (memory.has(key)) return memory.get(key) ?? null;
  try {
    return localStorage.getItem(key);
  } catch {
    return null;
  }
}

export function writeString(key: string, value: string | null) {
  memory.set(key, value);
  try {
    if (value === null) localStorage.removeItem(key);
    else localStorage.setItem(key, value);
  } catch {
    // Sin almacenamiento solo se pierde el recuerdo al cerrar la app.
  }
  listeners.forEach((listener) => listener());
}

function subscribe(listener: () => void) {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}

export function useStoredString(key: string): string | null {
  return useSyncExternalStore(
    subscribe,
    () => readString(key),
    () => null,
  );
}
