# desktop

> **Superado.** La ventana propia de mewsplit es ahora nativa
> (`native/macos/main.swift`) y se distribuye dentro del paquete que instala
> uv, sin firma de Apple ni Rust. Esta cáscara de Tauri ya no se usa; se
> conserva solo como referencia. Ver "Distribución" en el README de la raíz.

Cáscara de Tauri. No contiene lógica de producto: arranca `mewsplit-backend`
como sidecar, lee la línea `MEWSPLIT_READY port=<n> token=<t>` de su stdout
y abre la ventana con esos datos ya inyectados en `window.__MEWSPLIT__`.

**Sin verificar todavía**: en esta máquina no hay Rust instalado, así que
nada de esto se ha compilado. Antes de la primera build:

```bash
curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh
npm install
npx tauri icon ../design/icono.png   # genera src-tauri/icons/
# falta el sidecar en src-tauri/binaries/: ver el aviso de arriba
npm run dev
```

`tauri.conf.json` va dentro de `src-tauri/`, no en la raíz de `desktop/`:
es donde la CLI de Tauri lo busca.
