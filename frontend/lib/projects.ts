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
      return project.progress > 0 ? `descargando de youtube ${percent}` : "buscando el video en youtube…";
    case "queued":
      return "en cola";
    case "processing":
      // El avance mide la separación; al llegar al 100% aún se guardan los stems.
      return project.progress >= 1 ? "guardando el proyecto…" : `separando ${percent}`;
    default:
      return "";
  }
}
