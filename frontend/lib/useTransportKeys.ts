"use client";

import { useEffect, useRef } from "react";

/** Desplazamiento por pulsación. Con Shift, el salto largo. */
const NUDGE = 1;
const NUDGE_LARGE = 5;

/** Campos que necesitan sus propias teclas y no deben perderlas. */
const EDITABLE = new Set(["INPUT", "TEXTAREA", "SELECT"]);

export type Shortcut = { action: "toggle" } | { action: "nudge"; seconds: number };

interface KeyLike {
  key: string;
  shiftKey?: boolean;
  metaKey?: boolean;
  ctrlKey?: boolean;
  altKey?: boolean;
  target?: { tagName?: string; isContentEditable?: boolean } | null;
}

/**
 * Decide qué hace una pulsación. Pura y exportada a propósito: es donde viven
 * los casos raros (fader enfocado, atajos del sistema) y así se puede probar
 * sin navegador.
 */
export function resolveShortcut(event: KeyLike): Shortcut | null {
  const target = event.target;
  // Con un fader enfocado las flechas ajustan el volumen, y en un campo de
  // texto el espacio escribe un espacio. Ahí mandan ellos.
  if (target && (target.isContentEditable || EDITABLE.has(target.tagName ?? ""))) return null;
  // Cmd+flecha, Ctrl+espacio y compañía son del sistema o del navegador.
  if (event.metaKey || event.ctrlKey || event.altKey) return null;

  const seconds = event.shiftKey ? NUDGE_LARGE : NUDGE;

  switch (event.key) {
    case " ":
      return { action: "toggle" };
    case "ArrowLeft":
      return { action: "nudge", seconds: -seconds };
    case "ArrowRight":
      return { action: "nudge", seconds };
    default:
      return null;
  }
}

interface Options {
  onToggle: () => void;
  onNudge: (seconds: number) => void;
}

/**
 * Atajos de transporte: espacio reproduce/pausa, flechas mueven el playhead.
 *
 * Se registra UN solo listener y los callbacks viajan por ref: `Studio` se
 * repinta en cada frame mientras suena, así que depender de ellos en el
 * useEffect suscribiría y desuscribiría 60 veces por segundo.
 */
export function useTransportKeys({ onToggle, onNudge }: Options) {
  const handlers = useRef({ onToggle, onNudge });
  handlers.current = { onToggle, onNudge };

  useEffect(() => {
    function handleKey(event: KeyboardEvent) {
      const shortcut = resolveShortcut(event as unknown as KeyLike);
      if (!shortcut) return;

      // preventDefault hace dos cosas: evita que la página haga scroll con el
      // espacio y las flechas, y evita que un botón con el foco se active,
      // que alternaría la reproducción dos veces.
      event.preventDefault();

      if (shortcut.action === "toggle") handlers.current.onToggle();
      else handlers.current.onNudge(shortcut.seconds);
    }

    window.addEventListener("keydown", handleKey);
    return () => window.removeEventListener("keydown", handleKey);
  }, []);
}
