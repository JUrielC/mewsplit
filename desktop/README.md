# desktop

Cáscara de Tauri. No contiene lógica de producto: arranca `mewsplit-backend`
como sidecar, lee la línea `MEWSPLIT_READY port=<n> token=<t>` de su stdout
y abre la ventana con esos datos ya inyectados en `window.__MEWSPLIT__`.

**Sin verificar todavía**: en esta máquina no hay Rust instalado, así que
nada de esto se ha compilado. Antes de la primera build:

```bash
curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh
npm install
npx tauri icon ../design/icono.png   # genera src-tauri/icons/
../scripts/build-sidecar.sh          # produce src-tauri/binaries/
npm run dev
```

`tauri.conf.json` va dentro de `src-tauri/`, no en la raíz de `desktop/`:
es donde la CLI de Tauri lo busca.
