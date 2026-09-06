/**
 * Cliente HTTP del backend.
 *
 * La misma build sirve a escritorio y a web: lo único que cambia es la URL
 * base. En escritorio el backend toma un puerto libre al arrancar y Tauri
 * inyecta puerto y token en `window.__MEWSPLIT__`; en web vienen de las
 * variables de entorno de la build.
 */

import type { components } from "@shared/types";

export type Job = components["schemas"]["JobOut"];
export type Chord = components["schemas"]["ChordOut"];
export type Health = components["schemas"]["HealthOut"];
export type Status = components["schemas"]["Status"];

declare global {
  interface Window {
    __MEWSPLIT__?: { api: string; token: string };
  }
}

export interface Config {
  api: string;
  token: string;
}

export function getConfig(): Config {
  if (typeof window !== "undefined" && window.__MEWSPLIT__) {
    return window.__MEWSPLIT__;
  }
  return {
    api: process.env.NEXT_PUBLIC_MEWSPLIT_API ?? "http://127.0.0.1:8000",
    token: process.env.NEXT_PUBLIC_MEWSPLIT_TOKEN ?? "",
  };
}

export class ApiError extends Error {
  constructor(
    readonly status: number,
    message: string,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const { api, token } = getConfig();
  const response = await fetch(`${api}${path}`, {
    ...init,
    headers: { "X-Mewsplit-Token": token, ...(init?.headers ?? {}) },
  });

  if (!response.ok) {
    throw new ApiError(response.status, await errorMessage(response));
  }
  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

async function errorMessage(response: Response): Promise<string> {
  try {
    const body = await response.json();
    return typeof body?.detail === "string" ? body.detail : response.statusText;
  } catch {
    return response.statusText;
  }
}

export function getHealth(): Promise<Health> {
  return request<Health>("/health");
}

export interface AnalysisOptions {
  sixStems?: boolean;
  withChords?: boolean;
  largeVocabulary?: boolean;
}

export function uploadAudio(file: File, options: AnalysisOptions = {}): Promise<Job> {
  const body = new FormData();
  body.append("file", file);

  const params = new URLSearchParams();
  if (options.sixStems) params.set("model", "htdemucs_6s.yaml");
  if (options.withChords === false) params.set("with_chords", "false");
  if (options.largeVocabulary === false) params.set("large_vocabulary", "false");
  const query = params.toString();

  return request<Job>(`/jobs${query ? `?${query}` : ""}`, { method: "POST", body });
}

export function getJob(id: string): Promise<Job> {
  return request<Job>(`/jobs/${id}`);
}

export function deleteJob(id: string): Promise<void> {
  return request<void>(`/jobs/${id}`, { method: "DELETE" });
}

/**
 * Sondea hasta que el trabajo termina. El backend no empuja estado todavía;
 * si el sondeo se queda corto, el siguiente paso es SSE sobre el mismo /jobs.
 */
export async function waitForJob(
  id: string,
  onUpdate?: (job: Job) => void,
  intervalMs = 500,
  signal?: AbortSignal,
): Promise<Job> {
  for (;;) {
    if (signal?.aborted) throw new DOMException("Cancelado", "AbortError");

    const job = await getJob(id);
    onUpdate?.(job);

    if (job.status === "done") return job;
    if (job.status === "error") {
      throw new ApiError(500, job.error ?? "El análisis falló");
    }
    await new Promise((resolve) => setTimeout(resolve, intervalMs));
  }
}

export async function downloadStem(jobId: string, stem: string): Promise<ArrayBuffer> {
  const { api, token } = getConfig();
  const response = await fetch(`${api}/jobs/${jobId}/stems/${stem}`, {
    headers: { "X-Mewsplit-Token": token },
  });
  if (!response.ok) {
    throw new ApiError(response.status, await errorMessage(response));
  }
  return response.arrayBuffer();
}

/**
 * URL local de un stem, para `<audio src>` o para un enlace de descarga.
 *
 * Pasa por blob en vez de apuntar al backend: el token viaja en cabecera y
 * un `<audio src>` no la manda. Quien la crea es responsable de liberarla
 * con `URL.revokeObjectURL`.
 */
export async function getStemUrl(jobId: string, stem: string): Promise<string> {
  const data = await downloadStem(jobId, stem);
  return URL.createObjectURL(new Blob([data], { type: "audio/wav" }));
}
