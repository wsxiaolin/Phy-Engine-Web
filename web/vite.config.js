import { defineConfig } from "vite";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const root = path.dirname(fileURLToPath(import.meta.url));
const build = path.resolve(root, "../build");

const MIME = {
  ".js": "text/javascript",
  ".mjs": "text/javascript",
  ".wasm": "application/wasm",
  ".glb": "model/gltf-binary",
  ".gltf": "model/gltf+json",
  ".json": "application/json",
  ".png": "image/png",
  ".jpg": "image/jpeg",
  ".jpeg": "image/jpeg",
  ".bin": "application/octet-stream",
};

// Serve the shared artefacts under /assets (GLB + catalog) and /wasm (engine)
// straight out of ../build during dev, and copy them for a production build.
function buildArtefacts() {
  const mounts = {
    "/assets": path.join(build, "assets"),
    "/wasm": path.join(build, "wasm"),
  };
  return {
    name: "phy-build-artefacts",
    configureServer(server) {
      server.middlewares.use((req, res, next) => {
        const url = (req.url || "").split("?")[0];
        for (const [prefix, dir] of Object.entries(mounts)) {
          if (url === prefix || url.startsWith(prefix + "/")) {
            const rel = decodeURIComponent(url.slice(prefix.length).replace(/^\/+/, ""));
            const file = path.join(dir, rel);
            if (file.startsWith(dir) && fs.existsSync(file) && fs.statSync(file).isFile()) {
              res.setHeader("Content-Type", MIME[path.extname(file).toLowerCase()] || "application/octet-stream");
              res.setHeader("Cache-Control", "no-cache");
              fs.createReadStream(file).pipe(res);
              return;
            }
          }
        }
        next();
      });
    },
    closeBundle() {
      for (const [prefix, dir] of Object.entries(mounts)) {
        fs.cpSync(dir, path.join(root, "dist", prefix.replace(/^\//, "")), { recursive: true });
      }
    },
  };
}

export default defineConfig({
  base: "./",
  plugins: [buildArtefacts()],
  server: {
    host: true,
    port: 5173,
    allowedHosts: [".monkeycode-ai.online"],
  },
  build: {
    target: "esnext",
    chunkSizeWarningLimit: 4096,
  },
});
