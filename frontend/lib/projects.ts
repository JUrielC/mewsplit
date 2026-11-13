import type { ProjectSummary, Status } from "@/lib/api";

const UNFINISHED: Status[] = ["downloading", "queued", "processing"];

export function isUnfinished(project: ProjectSummary): boolean {
  return UNFINISHED.includes(project.status);
}

/** En qué va un proyecto que todavía no está listo. */
export function stageText(project: ProjectSummary): string {
  const percent = `${Math.round(project.progress * 100)}%`;
  switch (project.status) {
    case "downloading":
      // Sin avance todavía, yt-dlp está resolviendo el video y su título.
      return project.progress > 0 ? `Descargando de YouTube ${percent}` : "Buscando el video en YouTube…";
    case "queued":
      return "En cola";
    case "processing":
      // El avance mide la separación; al llegar al 100% aún se guardan los stems.
      return project.progress >= 1 ? "Guardando las pistas…" : `Separando ${percent}`;
    default:
      return "";
  }
}

/** "4:57": minutos y segundos, sin décimas. */
export function formatDuration(seconds: number): string {
  const whole = Math.round(seconds);
  return `${Math.floor(whole / 60)}:${String(whole % 60).padStart(2, "0")}`;
}
