# KB Core UI

Interactive React UI for a graph produced by [KB Core](../kb-core/README.md).
It reads `kb-core-out/graph.json` directly; it does not run or depend on a
separate graph server.

## Run

1. Build a graph with KB Core:

   ```powershell
   kb-core extract <repo> --code-only
   ```

2. Make graph available to Vite at `public/kb-core-out/graph.json`:

   ```powershell
   New-Item -ItemType Directory -Force .\public\kb-core-out
   Copy-Item <repo>\kb-core-out\graph.json .\public\kb-core-out\graph.json
   ```

   Or set `VITE_KB_CORE_GRAPH_URL` to another served graph URL.

3. Install and start UI:

   ```powershell
   npm install
   npm run dev
   ```

`npm run build` creates production assets in `dist/`.
