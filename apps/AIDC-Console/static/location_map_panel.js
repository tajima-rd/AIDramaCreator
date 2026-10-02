"use strict";
/*
 * <location-map-panel> — Edit > Edit Location on Map が開く、作品の場所(Location)と移動(SiteFlow)を地図の上で編集するパネル
 * (2026-10-02ユーザー決定。docs/architecture.md 8節)。Leaflet(static/vendor/leaflet)とLeaflet-Geoman(static/vendor/leaflet-geoman)を使う。
 * apiFetch/state/showToast/showApiError/escapeHtml/escapeAttr/EditorDraftをグローバル利用する。
 *
 * - 面を描くとLocation、線を描くとSiteFlow(頂点をクリックして描く)。形の編集・移動・削除はGeomanの道具で行う。
 *   選んだ地物の属性は右の欄で書き換える。
 * - Saveで、地図の状態(形のある場所・移動のすべて)を編集用の下書き(Dramaturgy Editorと共有するEditorDraft)に入れる
 *   (POST .../map。地図の取り込みと同じ規則)。移動のorigin・destinationは、線の始点・終点を含む場所の面からサーバーが決め、
 *   どの面にも入らない端点があれば保存全体を断る。Save Versionで確定する(地図に保存していない変更があれば、先にSaveする)。
 * - 地図から消した場所・移動は、作品の参照から外れる(プロジェクトの実体は消えない)。形の無い場所は地図に出ないが、
 *   一覧のDraw Shapeで形を描ける。
 * - 補助情報(作品に割り当てたGeoPackageのDataset)は表示だけ(Geomanの編集の対象にしない)。
 * - 形はGeoJSONでやり取りする(座標は経度・緯度の順。Leafletの緯度・経度との変換はL.geoJSON・toGeoJSONに任せる)。
 */

const MAP_BASE_LAYERS = [
  {
    label: "地理院タイル(標準)",
    url: "https://cyberjapandata.gsi.go.jp/xyz/std/{z}/{x}/{y}.png",
    options: { maxNativeZoom: 18 },
    attribution: '<a href="https://maps.gsi.go.jp/development/ichiran.html" target="_blank">地理院タイル</a>',
  },
  {
    label: "地理院タイル(淡色)",
    url: "https://cyberjapandata.gsi.go.jp/xyz/pale/{z}/{x}/{y}.png",
    options: { maxNativeZoom: 18 },
    attribution: '<a href="https://maps.gsi.go.jp/development/ichiran.html" target="_blank">地理院タイル</a>',
  },
  {
    label: "地理院タイル(写真)",
    url: "https://cyberjapandata.gsi.go.jp/xyz/seamlessphoto/{z}/{x}/{y}.jpg",
    options: { maxNativeZoom: 18 },
    attribution: '<a href="https://maps.gsi.go.jp/development/ichiran.html" target="_blank">地理院タイル</a>',
  },
  {
    label: "OpenStreetMap",
    url: "https://tile.openstreetmap.org/{z}/{x}/{y}.png",
    options: { maxNativeZoom: 19 },
    attribution: '&copy; <a href="https://www.openstreetmap.org/copyright" target="_blank">OpenStreetMap</a> contributors',
  },
];

const MAP_STYLES = {
  location: { color: "#2f5fa8", weight: 2, fillOpacity: 0.15 },
  locationSelected: { color: "#d9480f", weight: 3, fillOpacity: 0.3 },
  siteFlow: { color: "#e8590c", weight: 3, opacity: 0.9 },
  siteFlowSelected: { color: "#c92a2a", weight: 5, opacity: 1 },
  auxiliary: { color: "#666", weight: 1.5, fillOpacity: 0.08, dashArray: "4 3" },
};

const MAP_INITIAL_VIEW = { center: [36.0, 138.0], zoom: 5 }; // 地物が無いとき(日本全体)

customElements.define(
  "location-map-panel",
  class extends HTMLElement {
    constructor() {
      super();
      this.projectId = null;
      this.dramaturgyId = null;
      this.dramaturgyTitle = "";
      this.draft = null; // 編集用の下書き(EditorDraft)
      this.map = null;
      this.items = []; // {uid, kind: "location"|"site_flow", data, layer(形が無ければnull), shapeChanged}
      this.nextUid = 1;
      this.selectedUid = null;
      this.dirty = false; // 地図に、下書きへ保存していない変更がある
      this.pendingShapeUid = null; // Draw Shapeで形を描いている、形の無い場所
      this.resizeObserver = null;
    }

    connectedCallback() {
      this.innerHTML = `
        <div class="panel-header" id="lm-header"></div>
        <div class="lm-body">
          <div class="lm-map" id="lm-map"></div>
          <aside class="lm-side">
            <div id="lm-detail"></div>
            <div class="panel-section-title">Locations</div>
            <div class="lm-list" id="lm-list-locations"></div>
            <div class="panel-section-title">Site Flows</div>
            <div class="lm-list" id="lm-list-flows"></div>
          </aside>
        </div>
      `;
    }

    disconnectedCallback() {
      if (this.resizeObserver) this.resizeObserver.disconnect();
      if (this.map) this.map.remove();
      this.map = null;
    }

    async load(projectId, dramaturgyId) {
      this.projectId = projectId;
      this.dramaturgyId = dramaturgyId;
      this.draft = new EditorDraft(projectId);
      try {
        if (!(await this.draft.ensure())) {
          this.dispatchEvent(new CustomEvent("location-map-closed", { bubbles: true }));
          return;
        }
        await this.reloadMap(true);
      } catch (e) {
        showApiError(e);
      }
    }

    // 下書きの作品の地図を読み直す(fitならすべての地物が見えるように表示を合わせる)
    async reloadMap(fit) {
      const result = await apiFetch(
        `/projects/${this.projectId}/drama-drafts/${this.draft.draftId}/map?dramaturgy_id=${encodeURIComponent(this.dramaturgyId)}`
      );
      this.dramaturgyTitle = result.dramaturgy_title || "";
      this.ensureMap();
      this.clearFeatures();
      for (const location of result.locations || []) this.addItem("location", location, location.geometry);
      for (const flow of result.site_flows || []) this.addItem("site_flow", flow, flow.geometry);
      this.renderAuxiliary(result.auxiliary_layers || []);
      this.dirty = false;
      this.selectedUid = null;
      this.pendingShapeUid = null;
      this.refreshArrows();
      this.renderHeader();
      this.renderSide();
      if (fit) this.fitAll();
      for (const warning of result.warnings || []) showToast(warning, "warn");
    }

    // ---------------------------------------------------------------- 地図の用意

    ensureMap() {
      if (this.map) return;
      const container = this.querySelector("#lm-map");
      const map = L.map(container, { center: MAP_INITIAL_VIEW.center, zoom: MAP_INITIAL_VIEW.zoom });
      const baseLayers = {};
      MAP_BASE_LAYERS.forEach((base, i) => {
        const layer = L.tileLayer(base.url, { maxZoom: 20, attribution: base.attribution, ...base.options });
        baseLayers[base.label] = layer;
        if (i === 0) layer.addTo(map);
      });
      this.locationGroup = L.featureGroup().addTo(map);
      this.flowGroup = L.featureGroup().addTo(map);
      this.arrowGroup = L.layerGroup().addTo(map);
      this.auxiliaryGroups = [];
      this.layerControl = L.control
        .layers(baseLayers, { Locations: this.locationGroup, "Site Flows": this.flowGroup, Directions: this.arrowGroup }, { collapsed: true })
        .addTo(map);
      L.control.scale({ imperial: false }).addTo(map);

      map.pm.setLang("ja");
      map.pm.addControls({
        position: "topleft",
        drawMarker: false,
        drawCircleMarker: false,
        drawPolyline: true,
        drawRectangle: false,
        drawPolygon: true,
        drawCircle: false,
        drawText: false,
        editMode: true,
        dragMode: true,
        cutPolygon: false,
        removalMode: true,
        rotateMode: false,
      });
      map.pm.setGlobalOptions({ snappable: true, snapDistance: 15, allowSelfIntersection: false });
      map.on("pm:create", (e) => this.onCreate(e));
      map.on("pm:remove", (e) => this.onRemove(e.layer));
      map.on("pm:drawend", () => {
        this.pendingShapeUid = null;
      });
      map.on("zoomend", () => this.refreshArrows());
      this.map = map;

      // パネルの大きさが変わったら(初回の表示を含む)、地図の大きさを測り直す
      this.resizeObserver = new ResizeObserver(() => map.invalidateSize());
      this.resizeObserver.observe(container);
    }

    clearFeatures() {
      this.locationGroup.clearLayers();
      this.flowGroup.clearLayers();
      this.arrowGroup.clearLayers();
      for (const group of this.auxiliaryGroups) {
        this.layerControl.removeLayer(group);
        this.map.removeLayer(group);
      }
      this.auxiliaryGroups = [];
      this.items = [];
    }

    // GeoJSONの形から、編集できる1つの層を作る
    makeLayer(kind, geometry) {
      const style = kind === "location" ? MAP_STYLES.location : MAP_STYLES.siteFlow;
      const group = L.geoJSON(geometry, { style, pointToLayer: (_f, latlng) => L.marker(latlng) });
      return group.getLayers()[0] || null;
    }

    addItem(kind, data, geometry) {
      const item = { uid: this.nextUid++, kind, data: { ...data }, layer: null, shapeChanged: false };
      delete item.data.geometry;
      this.items.push(item);
      if (geometry) this.attachLayer(item, this.makeLayer(kind, geometry));
      return item;
    }

    attachLayer(item, layer) {
      if (!layer) return;
      item.layer = layer;
      layer._lmUid = item.uid;
      (item.kind === "location" ? this.locationGroup : this.flowGroup).addLayer(layer);
      layer.on("click", () => this.select(item.uid));
      const changed = () => {
        item.shapeChanged = true;
        this.markDirty();
        this.refreshArrows();
      };
      layer.on("pm:edit", changed);
      layer.on("pm:dragend", changed);
      this.applyStyle(item);
    }

    renderAuxiliary(layers) {
      for (const layer of layers) {
        const group = L.geoJSON(
          {
            type: "FeatureCollection",
            features: layer.features
              .filter((f) => f.geometry)
              .map((f) => ({ type: "Feature", geometry: f.geometry, properties: f.properties || {} })),
          },
          {
            pmIgnore: true, // 補助情報は表示だけ(Geomanの編集の対象にしない)
            style: MAP_STYLES.auxiliary,
            pointToLayer: (_f, latlng) =>
              L.circleMarker(latlng, { ...MAP_STYLES.auxiliary, radius: 4, fillOpacity: 0.6, pmIgnore: true }),
            onEachFeature: (feature, l) => l.bindPopup(this.propertiesHtml(layer.layer, feature.properties)),
          }
        ).addTo(this.map);
        group.bringToBack();
        this.auxiliaryGroups.push(group);
        this.layerControl.addOverlay(group, `補助情報: ${escapeHtml(layer.layer)}`);
      }
    }

    propertiesHtml(title, properties) {
      const rows = Object.entries(properties || {})
        .filter(([, v]) => v !== null && v !== "")
        .map(([k, v]) => `<tr><th>${escapeHtml(k)}</th><td>${escapeHtml(String(v))}</td></tr>`)
        .join("");
      return `<div class="lm-popup"><div class="lm-popup-title">${escapeHtml(title)}</div><table>${rows}</table></div>`;
    }

    fitAll() {
      const bounds = L.latLngBounds([]);
      for (const group of [this.locationGroup, this.flowGroup]) {
        if (group.getLayers().length) bounds.extend(group.getBounds());
      }
      if (!bounds.isValid()) {
        for (const group of this.auxiliaryGroups) if (group.getLayers().length) bounds.extend(group.getBounds());
      }
      if (bounds.isValid()) this.map.fitBounds(bounds, { padding: [24, 24], maxZoom: 18 });
    }

    // ---------------------------------------------------------------- Geomanの操作

    onCreate(e) {
      const layer = e.layer;
      this.map.removeLayer(layer); // 描いた層は地図に直接入るので、Location・SiteFlowの層に入れ直す
      if (e.shape === "Polygon") {
        const pending = this.items.find((i) => i.uid === this.pendingShapeUid && !i.layer);
        this.pendingShapeUid = null;
        let item = pending;
        if (!item) {
          const count = this.items.filter((i) => i.kind === "location").length + 1;
          item = this.addItem("location", { name: `新しい場所 ${count}` }, null);
        }
        item.shapeChanged = true;
        this.attachLayer(item, layer);
        this.select(item.uid);
      } else if (e.shape === "Line") {
        const item = this.addItem("site_flow", { name: null, direction: null }, null);
        item.shapeChanged = true;
        this.attachLayer(item, layer);
        this.select(item.uid);
      } else {
        return;
      }
      this.markDirty();
      this.refreshArrows();
      this.renderSide();
    }

    onRemove(layer) {
      const item = this.items.find((i) => i.uid === layer._lmUid);
      if (!item) return;
      const group = item.kind === "location" ? this.locationGroup : this.flowGroup;
      group.removeLayer(layer); // Geomanの削除は地図から外すだけのことがあるので、層のまとまりからも外す
      if (
        item.kind === "location" &&
        item.data.used_in_scenes &&
        !confirm(`「${item.data.name}」はこの作品のシーンが使っています。地図から消しますか?(作品の場所の一覧から外れます)`)
      ) {
        group.addLayer(layer);
        return;
      }
      this.items = this.items.filter((i) => i !== item);
      if (this.selectedUid === item.uid) this.selectedUid = null;
      this.markDirty();
      this.refreshArrows();
      this.renderSide();
    }

    removeItem(item) {
      if (item.layer) this.onRemove(item.layer);
    }

    // 形の無い場所に、面を描く
    drawShapeFor(item) {
      this.pendingShapeUid = item.uid;
      this.map.pm.enableDraw("Polygon");
      showToast(`「${item.data.name}」の面を、頂点をクリックして描いてください(最初の頂点をクリックで閉じます)`, "info");
    }

    markDirty() {
      if (!this.dirty) {
        this.dirty = true;
        this.renderHeader();
      }
    }

    // ---------------------------------------------------------------- 表示

    applyStyle(item) {
      if (!item.layer || typeof item.layer.setStyle !== "function") return;
      const selected = item.uid === this.selectedUid;
      if (item.kind === "location") item.layer.setStyle(selected ? MAP_STYLES.locationSelected : MAP_STYLES.location);
      else item.layer.setStyle(selected ? MAP_STYLES.siteFlowSelected : MAP_STYLES.siteFlow);
    }

    select(uid) {
      this.selectedUid = uid;
      for (const item of this.items) this.applyStyle(item);
      this.renderSide();
    }

    focus(item) {
      if (!item.layer) return;
      if (typeof item.layer.getBounds === "function") this.map.fitBounds(item.layer.getBounds(), { padding: [40, 40], maxZoom: 18 });
      else this.map.setView(item.layer.getLatLng(), Math.max(this.map.getZoom(), 16));
    }

    // 移動の向きの矢印(線の途中に置く。画面の座標で向きを計るので、拡大・縮小のたびに置き直す)
    refreshArrows() {
      if (!this.arrowGroup) return;
      this.arrowGroup.clearLayers();
      for (const item of this.items) {
        if (item.kind !== "site_flow" || !item.layer || !item.data.direction) continue;
        const latlngs = item.layer.getLatLngs().flat(Infinity);
        if (latlngs.length < 2) continue;
        const marks =
          item.data.direction === "both"
            ? [[1 / 3, 0], [2 / 3, 180]]
            : [[0.5, item.data.direction === "backward" ? 180 : 0]];
        for (const [fraction, turn] of marks) {
          const at = this.pointAlong(latlngs, fraction);
          if (!at) continue;
          L.marker(at.latlng, {
            pmIgnore: true,
            interactive: false,
            keyboard: false,
            icon: L.divIcon({
              className: "lm-arrow",
              html: `<div style="transform: rotate(${at.angle + turn}deg)">➤</div>`,
              iconSize: [22, 22],
              iconAnchor: [11, 11],
            }),
          }).addTo(this.arrowGroup);
        }
      }
    }

    // 線の長さのfractionの位置と、そこでの向き(画面の座標で、東を0度とする時計回りの角度)
    pointAlong(latlngs, fraction) {
      const points = latlngs.map((ll) => this.map.latLngToLayerPoint(ll));
      const lengths = points.slice(1).map((p, i) => p.distanceTo(points[i]));
      const total = lengths.reduce((a, b) => a + b, 0);
      if (total === 0) return null;
      let rest = total * fraction;
      for (let i = 0; i < lengths.length; i++) {
        if (rest <= lengths[i] || i === lengths.length - 1) {
          const a = points[i];
          const b = points[i + 1];
          const t = lengths[i] === 0 ? 0 : Math.min(1, rest / lengths[i]);
          const p = L.point(a.x + (b.x - a.x) * t, a.y + (b.y - a.y) * t);
          return { latlng: this.map.layerPointToLatLng(p), angle: (Math.atan2(b.y - a.y, b.x - a.x) * 180) / Math.PI };
        }
        rest -= lengths[i];
      }
      return null;
    }

    renderHeader() {
      const header = this.querySelector("#lm-header");
      header.innerHTML = `
        <div class="panel-header-row">
          <span class="panel-header-title">Location Map — ${escapeHtml(this.dramaturgyTitle)}</span>
          <div class="panel-header-actions">
            <span class="panel-header-version">${escapeHtml(this.draft.versionLabel())}${this.dirty ? " · 地図に未保存の変更あり" : ""}</span>
            <button type="button" class="btn ${this.dirty ? "btn-primary" : ""}" id="lm_save" ${this.dirty ? "" : "disabled"}>Save</button>
            <button type="button" class="${this.draft.versionButtonClass()}" id="lm_save_version">Save Version</button>
          </div>
        </div>
      `;
      header.querySelector("#lm_save").addEventListener("click", (ev) =>
        this.withButtonBusy(ev.currentTarget, "Saving...", () => this.saveMap())
      );
      header.querySelector("#lm_save_version").addEventListener("click", (ev) =>
        this.withButtonBusy(ev.currentTarget, "Saving...", () => this.saveVersion())
      );
    }

    renderSide() {
      this.renderDetail();
      const names = new Map(this.items.filter((i) => i.kind === "location").map((i) => [i.data.id, i.data.name]));
      const list = (kind, label) => {
        const box = this.querySelector(kind === "location" ? "#lm-list-locations" : "#lm-list-flows");
        const items = this.items.filter((i) => i.kind === kind);
        box.innerHTML = items.length ? "" : `<div class="panel-master-empty">(No ${label})</div>`;
        for (const item of items) {
          const row = document.createElement("div");
          row.className = "panel-master-item" + (item.uid === this.selectedUid ? " selected" : "");
          let sub;
          if (kind === "location") {
            sub = item.layer ? (item.data.used_in_scenes ? "シーンあり" : "") : "形なし(地図に出ません)";
          } else if (item.shapeChanged || !item.data.origin_id) {
            sub = "Saveで、端点を含む場所から決まります";
          } else {
            sub = `${names.get(item.data.origin_id) || "?"} → ${names.get(item.data.destination_id) || "?"}`;
          }
          row.innerHTML =
            `<div class="item-alias">${escapeHtml(item.data.name || "(名前なし)")}</div>` +
            (sub ? `<div class="item-name">${escapeHtml(sub)}</div>` : "");
          row.addEventListener("click", () => {
            this.select(item.uid);
            this.focus(item);
          });
          box.appendChild(row);
        }
      };
      list("location", "Locations");
      list("site_flow", "Site Flows");
    }

    renderDetail() {
      const detail = this.querySelector("#lm-detail");
      const item = this.items.find((i) => i.uid === this.selectedUid);
      if (!item) {
        detail.innerHTML = `
          <div class="field-hint lm-help">
            左上の道具で、<b>面を描くとLocation</b>、<b>線を描くとSiteFlow</b>になります(頂点をクリックして描き、面は最初の頂点、線は最後の頂点をもう一度クリックで終わります)。
            地物をクリックすると、ここで属性を書き換えられます。SiteFlowの線は、始点と終点をそれぞれLocationの面の中に置いてください。
            変更は<b>Save</b>で下書きに入り、<b>Save Version</b>で確定します。補助情報は表示だけです(右上の層の切り替えで隠せます)。
          </div>`;
        return;
      }
      const value = (key) => escapeAttr(item.data[key] || "");
      if (item.kind === "location") {
        detail.innerHTML = `
          <div class="panel-section-title">Location</div>
          <div class="panel-form">
            ${item.data.id ? `<div class="panel-readonly-id">ID: ${escapeHtml(item.data.id)}</div>` : `<div class="field-hint">新しい場所(Saveで作られます)</div>`}
            <div class="field"><label for="lm_name">Name</label><input type="text" id="lm_name" data-key="name" value="${value("name")}"></div>
            <div class="field"><label for="lm_address">Address</label><input type="text" id="lm_address" data-key="address" value="${value("address")}"></div>
            <div class="field"><label for="lm_instruction">Instruction</label><textarea id="lm_instruction" class="prose" data-key="instruction">${escapeHtml(item.data.instruction || "")}</textarea><div class="field-hint">この場所で案内すること</div></div>
            <div class="field"><label for="lm_description">Description</label><textarea id="lm_description" class="prose" data-key="description">${escapeHtml(item.data.description || "")}</textarea><div class="field-hint">この場所の事実</div></div>
            <div class="field-hint">場所はプロジェクト全体で共有されます(この場所を使う他の作品にも及びます)。</div>
            <div class="panel-actions">
              ${item.layer ? `<button type="button" class="btn" id="lm_remove">Remove from Map</button>` : `<button type="button" class="btn btn-primary" id="lm_draw_shape">Draw Shape</button>`}
            </div>
          </div>`;
      } else {
        const names = new Map(this.items.filter((i) => i.kind === "location").map((i) => [i.data.id, i.data.name]));
        const ends =
          item.shapeChanged || !item.data.origin_id
            ? "Saveで、線の始点・終点を含む場所から決まります"
            : `${names.get(item.data.origin_id) || "?"} → ${names.get(item.data.destination_id) || "?"}`;
        detail.innerHTML = `
          <div class="panel-section-title">Site Flow</div>
          <div class="panel-form">
            ${item.data.id ? `<div class="panel-readonly-id">ID: ${escapeHtml(item.data.id)}</div>` : `<div class="field-hint">新しい移動(Saveで作られます)</div>`}
            <div class="field"><label>Origin → Destination</label><div>${escapeHtml(ends)}</div></div>
            <div class="field"><label for="lm_name">Name</label><input type="text" id="lm_name" data-key="name" value="${value("name")}"></div>
            <div class="field">
              <label for="lm_direction">Direction</label>
              <select id="lm_direction" data-key="direction">${SITE_FLOW_DIRECTIONS.map(
                ([v, label]) => `<option value="${v}" ${(item.data.direction || "") === v ? "selected" : ""}>${escapeHtml(label)}</option>`
              ).join("")}</select>
              <div class="field-hint">線を引いた向き(始点→終点)に対する移動の向き。地図に矢印で出ます。</div>
            </div>
            <div class="panel-actions"><button type="button" class="btn" id="lm_remove">Remove from Map</button></div>
          </div>`;
      }
      for (const input of detail.querySelectorAll("[data-key]")) {
        const update = () => {
          item.data[input.dataset.key] = input.value.trim() === "" ? null : input.value;
          this.markDirty();
          if (input.dataset.key === "direction") this.refreshArrows();
        };
        input.addEventListener("input", update);
        input.addEventListener("change", () => {
          update();
          this.renderSide(); // 一覧の名前を直す(入力中に描き直すと入力欄が置き換わるので、確定時だけ)
        });
      }
      const remove = detail.querySelector("#lm_remove");
      if (remove) remove.addEventListener("click", () => this.removeItem(item));
      const draw = detail.querySelector("#lm_draw_shape");
      if (draw) draw.addEventListener("click", () => this.drawShapeFor(item));
    }

    // ---------------------------------------------------------------- 保存

    async withButtonBusy(button, label, fn) {
      const original = button.textContent;
      button.disabled = true;
      button.textContent = label;
      try {
        await fn();
      } finally {
        if (button.isConnected) {
          button.disabled = false;
          button.textContent = original;
        }
      }
    }

    // 地図の状態を下書きに入れる。成功すればtrue
    async saveMap() {
      const shaped = this.items.filter((i) => i.layer);
      const unnamed = shaped.find((i) => i.kind === "location" && !(i.data.name || "").trim());
      if (unnamed) {
        this.select(unnamed.uid);
        this.focus(unnamed);
        showToast("名前の無い場所があります。Nameを入力してください", "error");
        return false;
      }
      const geometry = (item) => item.layer.toGeoJSON().geometry;
      const body = {
        dramaturgy_id: this.dramaturgyId,
        locations: shaped
          .filter((i) => i.kind === "location")
          .map((i) => ({
            id: i.data.id || null,
            name: i.data.name.trim(),
            address: i.data.address || null,
            instruction: i.data.instruction || null,
            description: i.data.description || null,
            geometry: geometry(i),
          })),
        site_flows: shaped
          .filter((i) => i.kind === "site_flow")
          .map((i) => ({
            id: i.data.id || null,
            name: i.data.name || null,
            direction: i.data.direction || null,
            geometry: geometry(i),
          })),
      };
      try {
        const result = await apiFetch(`/projects/${this.projectId}/drama-drafts/${this.draft.draftId}/map`, {
          method: "POST",
          bodyObj: body,
        });
        this.draft.noteChange();
        await this.reloadMap(false);
        showToast(
          `下書きに保存しました(Location 新規${result.locations_created}・更新${result.locations_updated}、` +
            `SiteFlow 新規${result.site_flows_created}・更新${result.site_flows_updated})。Save Versionで確定してください`,
          "ok"
        );
        return true;
      } catch (e) {
        showApiError(e);
        return false;
      }
    }

    async saveVersion() {
      if (this.dirty && !(await this.saveMap())) return;
      try {
        const version = await this.draft.confirm();
        if (version === null) {
          showToast(`確定する変更はありません(${this.draft.versionLabel()}のまま)`, "info");
          return;
        }
        showToast(`版 v${version} として確定しました`, "ok");
        this.dispatchEvent(new CustomEvent("location-map-saved", { bubbles: true }));
        await this.reloadMap(false);
      } catch (e) {
        showApiError(e);
      }
    }
  }
);
