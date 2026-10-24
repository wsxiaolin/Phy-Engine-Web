import { categories, itemsIn, isSupported, WIRE_COLORS } from "./catalog.js";
import { thumbnail } from "./components.js";

export class UI {
  constructor() {
    this.palette = document.getElementById("palette");
    this.tabsEl = document.getElementById("palette-tabs");
    this.cardsEl = document.getElementById("palette-cards");
    this.inspector = document.getElementById("inspector");
    this.inspTitle = document.getElementById("insp-title");
    this.inspRows = document.getElementById("insp-rows");
    this.wirebar = document.getElementById("wirebar");
    this.swatches = document.getElementById("wire-swatches");
    this.toastEl = document.getElementById("toast");
    this.labelsEl = document.getElementById("labels");
    this.fpsEl = document.getElementById("fps");
    this.perfEl = document.getElementById("perf");
    this._toastTimer = null;
    this.labels = new Map();
    this._paletteOpen = true;
    this.bindDrawerGesture(); // 移动端：元件抽屉上下滑动开合（Unity 平板同款）
  }

  // 抽屉滑动手势：在 tab 栏（把手区）上下滑动 >30px 切换开合；
  // 绑在 tabs 而非整个 sheet，避免与卡片列表纵向滚动冲突。
  bindDrawerGesture() {
    const bar = this.tabsEl;
    let startY = null, fired = false;
    bar.addEventListener(
      "touchstart",
      (e) => {
        if (e.touches.length === 1) {
          startY = e.touches[0].clientY;
          fired = false;
        } else startY = null;
      },
      { passive: true },
    );
    bar.addEventListener(
      "touchmove",
      (e) => {
        if (startY === null || fired || e.touches.length !== 1) return;
        const dy = e.touches[0].clientY - startY;
        if (Math.abs(dy) > 30) {
          this.setPaletteOpen(dy < 0); // 上滑展开 / 下滑收起
          fired = true;
        }
      },
      { passive: true },
    );
    const end = () => (startY = null);
    bar.addEventListener("touchend", end, { passive: true });
    bar.addEventListener("touchcancel", end, { passive: true });
  }

  buildPalette(onPick) {
    const cats = categories();
    this.tabsEl.innerHTML = "";
    let active = cats[0];
    const render = () => {
      const token = Symbol();
      this._renderToken = token;
      this.cardsEl.innerHTML = "";
      for (const item of itemsIn(active)) {
        const card = document.createElement("div");
        card.className = "pcard" + (isSupported(item.ModelID) ? "" : " unsupported");
        card.title = item.ModelID + (isSupported(item.ModelID) ? "" : "（引擎暂不支持，仅摆放）");
        const img = document.createElement("img");
        img.className = "thumb";
        img.alt = item.FriendlyName || item.ModelID;
        const name = document.createElement("div");
        name.className = "pname";
        name.textContent = item.FriendlyName || item.ModelID;
        card.append(img, name);
        card.addEventListener("click", () => onPick(item));
        this.cardsEl.appendChild(card);
        thumbnail(item.ModelID)
          .then((url) => {
            if (this._renderToken === token) img.src = url;
          })
          .catch(() => {});
      }
      this.cardsEl.scrollLeft = 0;
    };
    for (const c of cats) {
      const t = document.createElement("div");
      t.className = "tab" + (c === active ? " active" : "");
      t.textContent = c;
      t.addEventListener("click", () => {
        active = c;
        [...this.tabsEl.children].forEach((x) => x.classList.toggle("active", x.textContent === c));
        render();
      });
      this.tabsEl.appendChild(t);
    }
    render();
  }

  setPaletteOpen(open) {
    this._paletteOpen = open;
    this.palette.classList.toggle("collapsed", !open);
  }
  togglePalette() {
    this.setPaletteOpen(!this._paletteOpen);
  }

  buildWireBar(onColor, activeName) {
    this.swatches.innerHTML = "";
    for (const c of WIRE_COLORS) {
      const s = document.createElement("div");
      s.className = "swatch" + (c.name === activeName ? " active" : "");
      s.style.background = "#" + c.hex.toString(16).padStart(6, "0");
      s.title = c.name;
      s.addEventListener("click", () => {
        [...this.swatches.children].forEach((x) => x.classList.remove("active"));
        s.classList.add("active");
        onColor(c.name);
      });
      this.swatches.appendChild(s);
    }
  }

  toggleWireBar() {
    this.wirebar.classList.toggle("hidden");
  }
  showWireBar() {
    this.wirebar.classList.remove("hidden");
  }
  hideWireBar() {
    this.wirebar.classList.add("hidden");
  }

  showInspector(title, rows, onRotate, onDelete, onRepair) {
    this.inspTitle.textContent = title;
    this.inspRows.innerHTML = "";
    for (const row of rows) {
      const r = document.createElement("div");
      r.className = "row";
      const label = document.createElement("span");
      label.textContent = row.label;
      if (row.type === "stat") {
        const v = document.createElement("span");
        v.className = "stat";
        v.textContent = row.value;
        r.append(label, v);
      } else if (row.type === "select") {
        const sel = document.createElement("select");
        for (const [val, text] of row.options) {
          const o = document.createElement("option");
          o.value = String(val);
          o.textContent = text;
          sel.appendChild(o);
        }
        sel.value = String(row.value);
        sel.addEventListener("change", () => row.onChange(sel.value));
        r.append(label, sel);
      } else {
        const input = document.createElement("input");
        input.value = row.value;
        input.addEventListener("change", () => row.onChange(input.value));
        r.append(label, input);
      }
      this.inspRows.appendChild(r);
    }
    const actions = this.inspector.querySelector(".insp-actions");
    actions.innerHTML = "";
    if (onRepair) {
      // Unity CircuitComponent 元数据操作区首位：Button-Repair（仅 IsBroken 时出现）
      const b = document.createElement("button");
      b.className = "btn";
      b.textContent = "维修";
      b.onclick = onRepair;
      actions.appendChild(b);
    }
    if (onRotate) {
      const b = document.createElement("button");
      b.className = "btn";
      b.textContent = "旋转";
      b.onclick = onRotate;
      actions.appendChild(b);
    }
    if (onDelete) {
      const b = document.createElement("button");
      b.className = "btn danger";
      b.textContent = "删除";
      b.onclick = onDelete;
      actions.appendChild(b);
    }
    this.inspector.classList.remove("hidden");
  }

  hideInspector() {
    this.inspector.classList.add("hidden");
  }

  toast(msg) {
    this.toastEl.textContent = msg;
    this.toastEl.classList.remove("hidden");
    clearTimeout(this._toastTimer);
    this._toastTimer = setTimeout(() => this.toastEl.classList.add("hidden"), 2600);
  }

  setFps(fps) {
    // <10 fps 保留 1 位小数：headless/低端机 0.3fps 不会误显为 0
    this.fpsEl.textContent = `${fps >= 10 ? Math.round(fps) : fps.toFixed(1)} fps`;
  }

  setPerf(text) {
    this.perfEl.textContent = text;
  }

  updateLabels(entries, camera, renderer) {
    const seen = new Set();
    const w = renderer.domElement.clientWidth;
    const h = renderer.domElement.clientHeight;
    const v = new (camera.position.constructor)();
    for (const { id, world, text } of entries) {
      seen.add(id);
      let el = this.labels.get(id);
      if (!el) {
        el = document.createElement("div");
        el.className = "label";
        this.labelsEl.appendChild(el);
        this.labels.set(id, el);
      }
      el.textContent = text;
      v.copy(world).project(camera);
      const visible = v.z < 1;
      el.style.display = visible ? "" : "none";
      el.style.left = `${((v.x + 1) / 2) * w}px`;
      el.style.top = `${((-v.y + 1) / 2) * h}px`;
    }
    for (const [id, el] of this.labels) {
      if (!seen.has(id)) {
        el.remove();
        this.labels.delete(id);
      }
    }
  }
}
