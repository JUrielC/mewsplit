# desktop

> **En pausa.** mewsplit se distribuye con un comando de instalación
> (`scripts/install.sh`), no con un `.dmg`: sin la firma y notarización de
> Apple, un binario descargado es justo lo que macOS bloquea. Si algún día se
> firma, esta cáscara sirve lanzando el comando `mewsplit` en lugar de un
> binario de PyInstaller, que se descartó y se borró (1–2 GB y se descomprime
> en cada arranque). Ver "Distribución" en el README de la raíz.

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
