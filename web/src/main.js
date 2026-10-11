import "./styles.css";
import { App } from "./app.js";
import { loadCatalog } from "./catalog.js";

async function boot() {
  const canvas = document.getElementById("viewport");
  await loadCatalog();
  const app = new App(canvas);
  window.__app = app;
  await app.init();
}

boot().catch((err) => {
  console.error(err);
  const t = document.getElementById("toast");
  if (t) {
    t.textContent = "初始化失败：" + err.message;
    t.classList.remove("hidden");
  }
});
