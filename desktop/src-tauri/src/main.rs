// La cáscara y nada más: arranca el backend de Python como sidecar, espera a
// que anuncie puerto y token, y abre la ventana con esos datos ya inyectados.
//
// La comunicación es HTTP sobre loopback, igual que en web. Mantener además
// un camino de IPC nativo para la misma funcionalidad no compensa: el overhead
// de HTTP local es irrelevante frente a una separación de 30 segundos.

#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use tauri::{WebviewUrl, WebviewWindowBuilder};
use tauri_plugin_shell::process::CommandEvent;
use tauri_plugin_shell::ShellExt;

/// Contrato con `backend/mewsplit/api.py`: la primera línea de stdout es
/// `MEWSPLIT_READY port=<n> token=<t>`.
const READY_PREFIX: &str = "MEWSPLIT_READY";

struct Backend {
    port: u16,
    token: String,
}

fn parse_ready_line(line: &str) -> Option<Backend> {
    let rest = line.trim().strip_prefix(READY_PREFIX)?;

    let mut port = None;
    let mut token = None;
    for field in rest.split_whitespace() {
        match field.split_once('=') {
            Some(("port", value)) => port = value.parse().ok(),
            Some(("token", value)) => token = Some(value.to_string()),
            _ => {}
        }
    }

    Some(Backend {
        port: port?,
        token: token?,
    })
}

/// El frontend lee `window.__MEWSPLIT__` (ver `frontend/lib/api.ts`). Se
/// inyecta como script de inicialización para que exista antes de que corra
/// cualquier JS de la página; por eso la ventana se crea después del arranque.
fn config_script(backend: &Backend) -> String {
    format!(
        r#"window.__MEWSPLIT__ = {{ api: "http://127.0.0.1:{}", token: "{}" }};"#,
        backend.port, backend.token
    )
}

fn open_window(app: &tauri::AppHandle, backend: &Backend) -> tauri::Result<()> {
    WebviewWindowBuilder::new(app, "main", WebviewUrl::default())
        .title("mewsplit")
        .inner_size(1280.0, 800.0)
        .min_inner_size(960.0, 600.0)
        .initialization_script(&config_script(backend))
        .build()?;
    Ok(())
}

fn main() {
    tauri::Builder::default()
        .plugin(tauri_plugin_shell::init())
        .setup(|app| {
            let handle = app.handle().clone();

            // El nombre real lleva el target triple de Rust (así lo exige Tauri).
            let (mut events, _child) = app.shell().sidecar("mewsplit-backend")?.spawn()?;

            tauri::async_runtime::spawn(async move {
                let mut window_opened = false;

                while let Some(event) = events.recv().await {
                    match event {
                        CommandEvent::Stdout(bytes) => {
                            if window_opened {
                                continue;
                            }
                            let line = String::from_utf8_lossy(&bytes);
                            if let Some(backend) = parse_ready_line(&line) {
                                if let Err(e) = open_window(&handle, &backend) {
                                    eprintln!("no se pudo abrir la ventana: {e}");
                                }
                                window_opened = true;
                            }
                        }
                        CommandEvent::Stderr(bytes) => {
                            eprint!("[backend] {}", String::from_utf8_lossy(&bytes));
                        }
                        CommandEvent::Terminated(status) => {
                            eprintln!("el backend terminó: {status:?}");
                            handle.exit(1);
                        }
                        _ => {}
                    }
                }
            });

            Ok(())
        })
        .run(tauri::generate_context!())
        .expect("fallo al arrancar mewsplit");
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn parses_the_ready_line() {
        let backend = parse_ready_line("MEWSPLIT_READY port=52341 token=abc-123\n").unwrap();
        assert_eq!(backend.port, 52341);
        assert_eq!(backend.token, "abc-123");
    }

    #[test]
    fn ignores_log_lines() {
        assert!(parse_ready_line("INFO: Uvicorn running").is_none());
    }

    #[test]
    fn requires_both_fields() {
        assert!(parse_ready_line("MEWSPLIT_READY port=52341").is_none());
    }
}
