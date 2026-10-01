"use strict";
/*
 * AIDC Console — 上部のメニューバー・左のTree・右のパネルの入れ物(main-area)から成る、
 * 常駐ワークスペース型のGUIの枠。QIDM Console(QIDMの apps/QIDM/static/app.js)の共通部分を
 * 持ち込んだもの(docs/qidm_reuse.md)。
 *
 * - APIクライアント(apiFetch)・トースト・モーダル・フォーム部品・メニューバーの描画は、
 *   各パネル(*_panel.js)からもグローバルに使う。
 * - main-areaには一度に1つのパネル(Custom Element)を置く。
 */

const SERVER_STORAGE_KEY = "aidc_server_base_url";
const DEFAULT_SERVER_BASE_URL = "http://127.0.0.1:8100";

const state = {
  serverBaseUrl: localStorage.getItem(SERVER_STORAGE_KEY) || "",
  project: null, // ProjectInfo | null
  treeRoots: [],
  selectedNodeId: null,
  selectedDramaturgyId: null, // Treeで選んだ作品(Edit > Dramaturgy Editorの対象)
};

// ---------------------------------------------------------------------------
// API client
// ---------------------------------------------------------------------------

class ApiError extends Error {
  constructor(status, detail) {
    super(`API error (status ${status}): ${detail}`);
    this.status = status;
    this.detail = detail;
  }
}

async function apiFetch(path, { method = "GET", bodyObj = null } = {}) {
  if (!state.serverBaseUrl) {
    throw new ApiError(0, "サーバーに接続していません。Connection > Connect to Server... を先に実行してください。");
  }
  const hasBody = bodyObj !== null;
  const requestText = hasBody ? jsyaml.dump(bodyObj, { sortKeys: false }) : undefined;
  let res;
  try {
    res = await fetch(state.serverBaseUrl.replace(/\/$/, "") + path, {
      method,
      headers: hasBody ? { "Content-Type": "application/yaml" } : {},
      body: requestText,
    });
  } catch (e) {
    throw new ApiError(0, `サーバーに接続できません: ${e.message}`);
  }
  const text = await res.text();
  let parsed = null;
  try {
    parsed = JSON.parse(text);
  } catch (e1) {
    try {
      parsed = text ? jsyaml.load(text) : null;
    } catch (e2) {
      parsed = null;
    }
  }
  if (!res.ok) {
    const detail = parsed && parsed.detail ? parsed.detail : text || res.statusText;
    throw new ApiError(res.status, detail);
  }
  return parsed;
}

// ---------------------------------------------------------------------------
// Toast
// ---------------------------------------------------------------------------

// 種類(kind)と色: error=失敗(赤、操作が完了しなかった)・warn=注意(黄、完了したが利用者が確かめること)・
// info=報告(青)・ok=成功(緑)。表示時間は文の長さに応じて延ばし、失敗・注意は読み切れるよう長めにとる。
// トーストはクリックを透過させる(.toastのpointer-events: none)ため、クリックで閉じる操作は設けない。
const TOAST_KINDS = ["error", "warn", "info", "ok"];
let toastTimer = null;
function toastDuration(message, kind) {
  const reading = 3500 + 50 * String(message).length;
  return kind === "error" || kind === "warn" ? Math.min(20000, Math.max(6000, reading)) : Math.min(10000, reading);
}

function showToast(message, kind = "info") {
  const el = document.getElementById("toast");
  el.textContent = message;
  el.className = "toast " + (TOAST_KINDS.includes(kind) ? kind : "info");
  el.hidden = false;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => {
    el.hidden = true;
  }, toastDuration(message, kind));
}

function showApiError(e) {
  if (e instanceof ApiError) {
    showToast(e.detail, "error");
  } else {
    showToast(String(e.message || e), "error");
  }
}

// ---------------------------------------------------------------------------
// Modal
// ---------------------------------------------------------------------------

function closeModal() {
  document.getElementById("modal-backdrop").hidden = true;
  document.getElementById("modal-box").innerHTML = "";
}

function openModal({ title, bodyHtml, onMount, buttons }) {
  const backdrop = document.getElementById("modal-backdrop");
  const box = document.getElementById("modal-box");
  const buttonsHtml = buttons
    .map((b, i) => `<button type="button" class="btn ${b.primary ? "btn-primary" : ""}" data-btn-index="${i}">${b.label}</button>`)
    .join("");
  box.innerHTML = `
    <div class="modal-header">${title}</div>
    <div class="modal-body">${bodyHtml}</div>
    <div class="modal-footer">${buttonsHtml}</div>
  `;
  backdrop.hidden = false;
  buttons.forEach((b, i) => {
    box.querySelector(`[data-btn-index="${i}"]`).addEventListener("click", () => b.onClick());
  });
  backdrop.onclick = (ev) => {
    if (ev.target === backdrop) closeModal();
  };
  if (onMount) onMount(box);
}

// blobをファイルとして保存する。File System Access API(showSaveFilePicker)が使えるブラウザでは、
// ユーザーが保存先を任意に選べるネイティブダイアログを出す。未対応ブラウザでは、<a download>による
// ブラウザの既定ダウンロード先への保存にフォールバックする。pickerTypeはshowSaveFilePickerの
// types要素({description, accept})。noteを渡すと、保存後のトーストに添える(例: 次に何をするか)。
async function saveBlobToFile(blob, filename, pickerType, note = "") {
  const suffix = note ? `。${note}` : "";
  if (window.showSaveFilePicker) {
    try {
      const handle = await window.showSaveFilePicker({ suggestedName: filename, types: [pickerType] });
      const writable = await handle.createWritable();
      await writable.write(blob);
      await writable.close();
      showToast(`保存しました${suffix}`, "ok");
      return;
    } catch (e) {
      if (e && e.name === "AbortError") return; // ユーザーによるキャンセル
      // VSCode組み込みブラウザ等、showSaveFilePickerが存在はするものの
      // 実際には使えない(SecurityError等になる)環境があるため、失敗時は
      // エラー表示で終わらせず通常のダウンロードにフォールバックする。
      console.warn("showSaveFilePicker failed, falling back to download:", e);
    }
  }

  try {
    downloadBlob(blob, filename);
    showToast(`ダウンロードフォルダに保存しました${suffix}`, "ok");
  } catch (e) {
    showApiError(e);
  }
}

// <a download>による、ブラウザの既定のダウンロード先への保存。
function downloadBlob(blob, filename) {
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}

// ---------------------------------------------------------------------------
// CSV
// ---------------------------------------------------------------------------

// CSVテキストを{columns, rows}へ変換する(簡易パーサ。セル内改行までは想定しない)。
function csvToRows(csvText) {
  const lines = csvText.replace(/\r\n/g, "\n").split("\n").filter((l) => l.length > 0);
  if (lines.length === 0) return { columns: [], rows: [] };
  const parseLine = (line) => {
    const cells = [];
    let cur = "";
    let inQuotes = false;
    for (let i = 0; i < line.length; i++) {
      const ch = line[i];
      if (inQuotes) {
        if (ch === '"') {
          if (line[i + 1] === '"') {
            cur += '"';
            i++;
          } else {
            inQuotes = false;
          }
        } else {
          cur += ch;
        }
      } else if (ch === '"') {
        inQuotes = true;
      } else if (ch === ",") {
        cells.push(cur);
        cur = "";
      } else {
        cur += ch;
      }
    }
    cells.push(cur);
    return cells;
  };
  const columns = parseLine(lines[0]);
  const rows = lines.slice(1).map((line) => {
    const cells = parseLine(line);
    const obj = {};
    columns.forEach((c, i) => (obj[c] = cells[i]));
    return obj;
  });
  return { columns, rows };
}

// ---------------------------------------------------------------------------
// Field builders (モーダル・パネル内で使う簡易フォーム部品)
// ---------------------------------------------------------------------------

function textField(id, label, value = "", hint = "") {
  return `
    <div class="field">
      <label for="${id}">${label}</label>
      <input type="text" id="${id}" value="${escapeAttr(value)}">
      ${hint ? `<div class="field-hint">${hint}</div>` : ""}
      <div class="field-error" id="err_${id}"></div>
    </div>`;
}

function selectHtml(id, options, current, labelFn) {
  const opts = options
    .map((opt) => {
      const label = labelFn ? labelFn(opt) : opt;
      return `<option value="${escapeAttr(opt)}" ${opt === current ? "selected" : ""}>${escapeHtml(label)}</option>`;
    })
    .join("");
  return `<select id="${id}">${opts}</select>`;
}

function fieldError(box, fieldId, message) {
  const el = box.querySelector(`#err_${fieldId}`);
  if (el) el.textContent = message || "";
}

function escapeAttr(str) {
  return String(str).replace(/&/g, "&amp;").replace(/"/g, "&quot;");
}

function escapeHtml(str) {
  return String(str).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

// ---------------------------------------------------------------------------
// Connection
// ---------------------------------------------------------------------------

function renderBadges() {
  const serverBadge = document.getElementById("server-badge");
  if (state.serverBaseUrl) {
    serverBadge.textContent = `Server: ${state.serverBaseUrl}`;
    serverBadge.classList.add("set");
  } else {
    serverBadge.textContent = "Server: not connected";
    serverBadge.classList.remove("set");
  }

  const projectBadge = document.getElementById("project-badge");
  if (state.project) {
    projectBadge.textContent = `Project: ${state.project.name}`;
    projectBadge.classList.add("set");
  } else {
    projectBadge.textContent = "Project: none";
    projectBadge.classList.remove("set");
  }
}

function actionConnectToServer() {
  openModal({
    title: "Connect to Server",
    bodyHtml: textField("f_base_url", "Server base URL", state.serverBaseUrl || DEFAULT_SERVER_BASE_URL),
    buttons: [
      { label: "Cancel", onClick: closeModal },
      {
        label: "Connect",
        primary: true,
        onClick: async () => {
          const box = document.getElementById("modal-box");
          const value = box.querySelector("#f_base_url").value.trim();
          if (!value) {
            fieldError(box, "f_base_url", "入力してください");
            return;
          }
          state.serverBaseUrl = value.replace(/\/$/, "");
          localStorage.setItem(SERVER_STORAGE_KEY, state.serverBaseUrl);
          renderBadges();
          closeModal();
          await actionTestConnection();
        },
      },
    ],
  });
}

async function actionTestConnection() {
  try {
    const result = await apiFetch("/health");
    if (result && result.status === "ok") {
      showToast("接続成功", "ok");
    } else {
      showToast("サーバーから予期しない応答がありました", "error");
    }
  } catch (e) {
    showApiError(e);
  }
}

// state.serverBaseUrl(現在接続中のセッション)を経由せず、任意のURLへ
// 直接/healthを叩く。Project Overviewパネルでserver_base_urlをproject.yaml
// へ保存する前の接続テストに使う(apiFetchは常にstate.serverBaseUrl宛のため
// 使えない)。
async function testServerHealth(baseUrl) {
  try {
    const res = await fetch(baseUrl.replace(/\/$/, "") + "/health");
    if (!res.ok) return false;
    const data = jsyaml.load(await res.text());
    return !!(data && data.status === "ok");
  } catch (e) {
    return false;
  }
}

function actionUpdateProjectPath() {
  if (!state.project) {
    showToast("先にプロジェクトを開いてください", "error");
    return;
  }
  openModal({
    title: "Update Project Path",
    bodyHtml: textField("f_path", "New Path", state.project.path, "project.yamlが実際に置かれているディレクトリの絶対パスを指定してください。"),
    buttons: [
      { label: "Cancel", onClick: closeModal },
      {
        label: "Update",
        primary: true,
        onClick: async () => {
          const box = document.getElementById("modal-box");
          const value = box.querySelector("#f_path").value.trim();
          if (!value) {
            fieldError(box, "f_path", "入力してください");
            return;
          }
          try {
            const info = await apiFetch(`/projects/${state.project.project_id}/path`, {
              method: "PUT",
              bodyObj: { path: value },
            });
            setCurrentProject(info);
            closeModal();
            showToast("パスを更新しました", "ok");
          } catch (e) {
            showApiError(e);
          }
        },
      },
    ],
  });
}

function actionDisconnect() {
  state.serverBaseUrl = "";
  localStorage.removeItem(SERVER_STORAGE_KEY);
  setCurrentProject(null);
  renderBadges();
  showToast("切断しました", "info");
}

// ---------------------------------------------------------------------------
// Project
// ---------------------------------------------------------------------------

// 開いているプロジェクトを切り替える(nullで閉じる)。別のプロジェクトに切り替わったら、
// Treeとmain-areaを作り直す(同じプロジェクトの情報の更新なら、そのまま残す)。
function setCurrentProject(info) {
  const switched = !info || !state.project || state.project.project_id !== info.project_id;
  state.project = info;
  if (switched) {
    state.treeRoots = [];
    state.selectedNodeId = null;
    state.selectedDramaturgyId = null;
    document.getElementById("main-area").innerHTML = "";
  }
  renderBadges();
  renderTreeRoot();
}

function actionCreateNewProject() {
  openModal({
    title: "Create New Project",
    bodyHtml:
      textField(
        "f_path",
        "Directory Path",
        "Project/TEST_PROJECT_",
        "存在しない、または空のディレクトリを指定してください。相対パスはサーバーを起動したディレクトリ(リポジトリ直下)から。実験用はProject/TEST_PROJECT_##(01からの連番)に作る(CLAUDE.md)。"
      ) + textField("f_name", "Project Name", ""),
    buttons: [
      { label: "Cancel", onClick: closeModal },
      {
        label: "Create",
        primary: true,
        onClick: async () => {
          const box = document.getElementById("modal-box");
          const path = box.querySelector("#f_path").value.trim();
          const name = box.querySelector("#f_name").value.trim();
          let ok = true;
          if (!path) { fieldError(box, "f_path", "入力してください"); ok = false; } else { fieldError(box, "f_path", ""); }
          if (!name) { fieldError(box, "f_name", "入力してください"); ok = false; } else { fieldError(box, "f_name", ""); }
          if (!ok) return;
          try {
            const info = await apiFetch("/projects", { method: "POST", bodyObj: { path, name } });
            setCurrentProject(info);
            closeModal();
            showToast(`プロジェクト「${info.name}」を作成しました`, "ok");
          } catch (e) {
            showApiError(e);
          }
        },
      },
    ],
  });
}

async function actionOpenProject() {
  let recentProjects = [];
  try {
    const result = await apiFetch("/projects");
    recentProjects = result.projects || [];
  } catch (e) {
    // 一覧取得に失敗しても、パス直接入力での起動は継続できるようにする
  }

  const recentHtml = recentProjects.length
    ? recentProjects.map((p) => `<li data-path="${escapeAttr(p.path)}">${escapeHtml(p.name)} <span class="field-hint">${escapeHtml(p.path)}</span></li>`).join("")
    : `<li class="recent-empty">(登録済みプロジェクトはありません)</li>`;

  openModal({
    title: "Open Project",
    bodyHtml: `
      ${textField("f_path", "Directory Path", "", "project.yaml が置かれているディレクトリの絶対パス")}
      <div class="field">
        <label>Open Recent</label>
        <ul class="recent-list" id="recent-list">${recentHtml}</ul>
      </div>
    `,
    onMount: (box) => {
      box.querySelectorAll("#recent-list li[data-path]").forEach((li) => {
        li.addEventListener("click", () => {
          box.querySelector("#f_path").value = li.dataset.path;
        });
      });
    },
    buttons: [
      { label: "Cancel", onClick: closeModal },
      {
        label: "Open",
        primary: true,
        onClick: async () => {
          const box = document.getElementById("modal-box");
          const path = box.querySelector("#f_path").value.trim();
          if (!path) {
            fieldError(box, "f_path", "入力してください");
            return;
          }
          try {
            const info = await apiFetch("/projects/open", { method: "POST", bodyObj: { path } });
            setCurrentProject(info);
            closeModal();
            showToast(`プロジェクト「${info.name}」を開きました`, "ok");
          } catch (e) {
            showApiError(e);
          }
        },
      },
    ],
  });
}

async function actionSave() {
  if (!state.project) {
    showToast("開いているプロジェクトがありません", "error");
    return;
  }
  try {
    const info = await apiFetch(`/projects/${state.project.project_id}/save`, { method: "POST" });
    setCurrentProject(info);
    showToast("保存しました", "ok");
  } catch (e) {
    showApiError(e);
  }
}

function actionSaveAs() {
  if (!state.project) {
    showToast("開いているプロジェクトがありません", "error");
    return;
  }
  openModal({
    title: "Save As",
    bodyHtml: textField("f_path", "Destination Directory Path", "", "存在しない、または空のディレクトリを指定してください。") + textField("f_name", "New Project Name (leave blank to keep current name)"),
    buttons: [
      { label: "Cancel", onClick: closeModal },
      {
        label: "Save As",
        primary: true,
        onClick: async () => {
          const box = document.getElementById("modal-box");
          const path = box.querySelector("#f_path").value.trim();
          const name = box.querySelector("#f_name").value.trim();
          if (!path) {
            fieldError(box, "f_path", "入力してください");
            return;
          }
          try {
            const info = await apiFetch(`/projects/${state.project.project_id}/save-as`, {
              method: "POST",
              bodyObj: name ? { path, name } : { path },
            });
            setCurrentProject(info);
            closeModal();
            showToast(`「${info.name}」として保存し、切り替えました`, "ok");
          } catch (e) {
            showApiError(e);
          }
        },
      },
    ],
  });
}

function actionCloseProject() {
  if (!state.project) {
    showToast("開いているプロジェクトがありません", "error");
    return;
  }
  setCurrentProject(null);
  showToast("プロジェクトを閉じました", "info");
}

// Project > Preferences...: Project OverviewパネルのGenerative AIタブ(生成AIの接続先・APIキー、
// project_genai_tab.js)を開く。
function actionOpenPreferences() {
  if (!state.project) {
    showToast("開いているプロジェクトがありません", "error");
    return;
  }
  openProjectOverview(state.project.project_id, "genai");
}

function actionExit() {
  openModal({
    title: "Exit",
    bodyHtml: `<p>Web版のため、アプリケーションを直接終了することはできません。このタブを閉じてください。</p>`,
    buttons: [{ label: "OK", primary: true, onClick: closeModal }],
  });
}

// ---------------------------------------------------------------------------
// Tree
// ---------------------------------------------------------------------------

// Treeの最上位は「Project」(Project Overviewを開く)・「Dramaturgies」(子に正本の作品の一覧。選ぶと
// Dramaturgy Editor)・「Datasets」(子にDatasetの一覧)。作品の中(Act→Scene・人物等)の並びはまだ置かない。
const EXPANDABLE_TREE_KINDS = ["group"];

function makeTreeRoots() {
  return [
    { id: "project", label: "Project", kind: "project" },
    { id: "dramaturgies", label: "Dramaturgies", kind: "group", expanded: false, children: null },
    { id: "datasets", label: "Datasets", kind: "group", expanded: false, children: null },
  ];
}

// グループ(idで指定)を開いた状態で読み直す。Datasetの追加・削除、作品の確定の後に呼ぶ。
async function reloadGroupNode(groupId) {
  const node = state.treeRoots.find((n) => n.id === groupId);
  if (!node) return;
  node.children = null;
  node.expanded = true;
  await loadGroupChildren(node);
  renderTreeRoot();
}

function renderTreeRoot() {
  const container = document.getElementById("tree-root");
  container.innerHTML = "";
  if (!state.project) {
    container.innerHTML = '<p class="placeholder">プロジェクトを開くと構造が表示されます。</p>';
    return;
  }
  if (state.treeRoots.length === 0) {
    state.treeRoots = makeTreeRoots();
  }
  for (const node of state.treeRoots) {
    container.appendChild(renderTreeNode(node));
  }
}

function renderTreeNode(node) {
  const wrapper = document.createElement("div");
  wrapper.className = "tree-node";

  const row = document.createElement("div");
  row.className = "tree-node-row" + (state.selectedNodeId === node.id ? " selected" : "");
  const caret = document.createElement("span");
  caret.className = "tree-caret";
  if (EXPANDABLE_TREE_KINDS.includes(node.kind)) {
    caret.textContent = node.expanded ? "▾" : "▸";
  }
  const label = document.createElement("span");
  label.textContent = node.label;
  row.appendChild(caret);
  row.appendChild(label);
  wrapper.appendChild(row);

  const childrenContainer = document.createElement("div");
  childrenContainer.className = "tree-node-children";
  wrapper.appendChild(childrenContainer);

  row.addEventListener("click", async () => {
    state.selectedNodeId = node.id;
    selectTreeNode(node);
    if (EXPANDABLE_TREE_KINDS.includes(node.kind)) {
      node.expanded = !node.expanded;
      if (node.expanded && node.children === null) {
        await loadGroupChildren(node);
      }
    }
    renderTreeRoot();
  });

  if (EXPANDABLE_TREE_KINDS.includes(node.kind) && node.expanded && node.children) {
    for (const child of node.children) {
      childrenContainer.appendChild(renderTreeNode(child));
    }
  }

  return wrapper;
}

async function loadGroupChildren(node) {
  try {
    if (node.id === "dramaturgies") {
      const model = await apiFetch(`/projects/${state.project.project_id}/drama-model`);
      node.children = ((model && model.dramaturgies) || []).map((d) => ({
        id: `dramaturgy:${d.id}`,
        label: d.title,
        kind: "dramaturgy",
        dramaturgyId: d.id,
      }));
    } else if (node.id === "datasets") {
      const result = await apiFetch(`/projects/${state.project.project_id}/datasets`);
      node.children = (result.datasets || []).map((d) => ({
        id: `dataset:${d.file_id}`,
        label: d.filename,
        kind: "dataset",
        fileId: d.file_id,
        filename: d.filename,
        fileFormat: d.file_format,
      }));
    }
    if (node.children.length === 0) {
      node.children = [{ id: `${node.id}:empty`, label: "(空)", kind: "empty" }];
    }
  } catch (e) {
    showApiError(e);
    node.children = [{ id: `${node.id}:error`, label: "(読み込みに失敗しました)", kind: "empty" }];
  }
}

async function selectTreeNode(node) {
  if (node.kind === "dramaturgy") {
    state.selectedDramaturgyId = node.dramaturgyId;
    await mountOrUpdateDramaturgyEditor(state.project.project_id, node.dramaturgyId);
  } else if (node.kind === "project") {
    await openProjectOverview(state.project.project_id, "overview");
  } else if (node.kind === "group" && node.id === "datasets") {
    await openProjectOverview(state.project.project_id, "dataset");
  } else if (node.kind === "dataset") {
    mountDataViewerPanel(state.project.project_id, node.fileId, node.filename, node.fileFormat);
  }
}

// ---------------------------------------------------------------------------
// main-areaのパネル
// ---------------------------------------------------------------------------

// 既にmount済みの<project-overview-panel>があればタブ切り替えのみ行い
// (データ再取得はしない)、無ければ新規mountしてデータを読み込む。
async function openProjectOverview(projectId, tab) {
  const mainArea = document.getElementById("main-area");
  let panel = mainArea.querySelector("project-overview-panel");
  if (!panel || panel.projectId !== projectId) {
    mainArea.innerHTML = "";
    panel = document.createElement("project-overview-panel");
    panel.addEventListener("project-overview-changed", () => reloadGroupNode("datasets"));
    mainArea.appendChild(panel);
    await panel.run(projectId);
  }
  panel.selectTab(tab);
}

// CSVは表として、PDFはブラウザのPDF表示でmain-areaに表示する(fileFormatはDatasetSummary.file_format)。
function mountDataViewerPanel(projectId, fileId, filename, fileFormat) {
  const mainArea = document.getElementById("main-area");
  mainArea.innerHTML = "";
  const panel = document.createElement("data-viewer-panel");
  mainArea.appendChild(panel);
  panel.run(projectId, fileId, filename, fileFormat);
}

// 既に同じ作品のDramaturgy Editorが開いていれば、そのまま(入力中のタブ等を保つ)。
// 別の作品なら同じパネルでload()し直し、無ければ新しくmountする。
async function mountOrUpdateDramaturgyEditor(projectId, dramaturgyId) {
  const mainArea = document.getElementById("main-area");
  let panel = mainArea.querySelector("dramaturgy-editor-panel");
  if (panel && panel.projectId === projectId) {
    if (panel.dramaturgyId !== dramaturgyId) await panel.load(projectId, dramaturgyId);
    return;
  }
  mainArea.innerHTML = "";
  panel = document.createElement("dramaturgy-editor-panel");
  panel.addEventListener("dramaturgy-editor-saved", () => reloadGroupNode("dramaturgies"));
  panel.addEventListener("dramaturgy-editor-closed", () => {
    if (state.selectedDramaturgyId === panel.dramaturgyId) state.selectedDramaturgyId = null;
    mainArea.innerHTML = "";
  });
  mainArea.appendChild(panel);
  await panel.load(projectId, dramaturgyId);
}

// 人物パネル(プロジェクト全体。作品を選ばなくても開ける)。既に開いていればそのまま(入力中のタブ等を保つ)。
async function mountCharacterEditor(projectId) {
  const mainArea = document.getElementById("main-area");
  let panel = mainArea.querySelector("character-editor-panel");
  if (panel && panel.projectId === projectId) return;
  mainArea.innerHTML = "";
  panel = document.createElement("character-editor-panel");
  panel.addEventListener("character-editor-closed", () => {
    mainArea.innerHTML = "";
  });
  mainArea.appendChild(panel);
  await panel.load(projectId);
}

// ---------------------------------------------------------------------------
// Edit
// ---------------------------------------------------------------------------

// Edit > New Dramaturgy...: 題・幕数・言語から、空の幕を持つ作品を作り、すぐに確定する(Treeに出る)。エージェントは
// プロジェクトのユーザー既定(職能ごと)を必ず入れる。
// 作品の追加専用の下書きを作って確定するため、Dramaturgy Editorの下書きに確定していない変更があると、
// その下書きが確定できなくなる。そのため、変更があれば先にSave Versionを求める(変更が無ければ、
// 次にDramaturgy Editorを開くときに作り直される)。
function actionNewDramaturgy() {
  if (!state.project) {
    showToast("先にプロジェクトを開いてください", "error");
    return;
  }
  openModal({
    title: "New Dramaturgy",
    bodyHtml:
      textField("f_title", "Title") +
      textField("f_act_count", "Number of Acts", "1", "空の幕をこの数だけ作ります(後からDramaturgy EditorのActsタブで追加・削除できます)") +
      textField("f_input_language", "Input Language", "ja", "制作に使う言語のコード(例: ja)") +
      textField("f_output_language", "Output Language", "ja", "音声にする言語のコード(例: ja・zh)"),
    buttons: [
      { label: "Cancel", onClick: closeModal },
      {
        label: "Create",
        primary: true,
        onClick: async () => {
          const box = document.getElementById("modal-box");
          const title = box.querySelector("#f_title").value.trim();
          const actCountText = box.querySelector("#f_act_count").value.trim();
          const actCount = Number(actCountText);
          let ok = true;
          fieldError(box, "f_title", "");
          fieldError(box, "f_act_count", "");
          if (!title) { fieldError(box, "f_title", "入力してください"); ok = false; }
          if (!/^\d+$/.test(actCountText) || actCount < 1) { fieldError(box, "f_act_count", "1以上の整数を入力してください"); ok = false; }
          if (!ok) return;
          const projectId = state.project.project_id;
          try {
            const editor = await findEditorDraft(projectId);
            if (editor.changeCount > 0) {
              showToast("Dramaturgy Editor・Character Editorに確定していない変更があります。先にSave Versionで確定してください", "error");
              return;
            }
            const draft = await apiFetch(`/projects/${projectId}/drama-drafts`, {
              method: "POST",
              bodyObj: { title: "New Dramaturgy" },
            });
            const base = `/projects/${projectId}/drama-drafts/${draft.draft_id}`;
            const language = (id) => box.querySelector(`#${id}`).value.trim() || null;
            const defaults = (await apiFetch(`/projects/${projectId}/agent-defaults`)).defaults || {};
            const agents = {};
            for (const [roleName, spec] of Object.entries(defaults)) agents[`${roleName}s`] = [spec];
            const dramaturgy = {
              title,
              acts: Array.from({ length: actCount }, (_, i) => ({ order: i })),
              agents,
            };
            if (language("f_input_language")) dramaturgy.input_language = language("f_input_language");
            if (language("f_output_language")) dramaturgy.output_language = language("f_output_language");
            try {
              await apiFetch(`${base}/edit`, { method: "POST", bodyObj: { dramaturgies: [dramaturgy] } });
              await apiFetch(`${base}/confirm`, { method: "POST", bodyObj: { note: `New Dramaturgy: ${title}` } });
            } catch (e) {
              await apiFetch(`${base}/discard`, { method: "POST" }).catch(() => {});
              throw e;
            }
            if (editor.draft) {
              await apiFetch(`/projects/${projectId}/drama-drafts/${editor.draft.draft_id}/discard`, { method: "POST" });
            }
            closeModal();
            showToast(`作品「${title}」を作成しました`, "ok");
            await reloadGroupNode("dramaturgies");
            // 開いているDramaturgy Editor・人物パネルは古い版の下書きを持っているので、新しい版から開き直す
            const mainArea = document.getElementById("main-area");
            const panel = mainArea.querySelector("dramaturgy-editor-panel");
            if (panel) await panel.load(projectId, panel.dramaturgyId);
            const characterPanel = mainArea.querySelector("character-editor-panel");
            if (characterPanel) await characterPanel.load(projectId);
          } catch (e) {
            showApiError(e);
          }
        },
      },
    ],
  });
}

// Edit > Character Editor: プロジェクトの人物・まとまり・人物関係を編集する(作品の選択は要らない)。
function actionOpenCharacterEditor() {
  if (!state.project) {
    showToast("先にプロジェクトを開いてください", "error");
    return;
  }
  mountCharacterEditor(state.project.project_id);
}

// Edit > Dramaturgy Editor: Treeで選んだ作品を開く。
function actionOpenDramaturgyEditor() {
  if (!state.project) {
    showToast("先にプロジェクトを開いてください", "error");
    return;
  }
  if (!state.selectedDramaturgyId) {
    showToast("先にTreeのDramaturgiesで作品を選択してください", "error");
    return;
  }
  mountOrUpdateDramaturgyEditor(state.project.project_id, state.selectedDramaturgyId);
}

// ---------------------------------------------------------------------------
// Menu bar
// ---------------------------------------------------------------------------

// メニュー定義。アクションの関数はapp.js以外のファイル(app.jsより後に読み込む)にも
// 置けるよう、全スクリプトの読み込み後(init→renderMenuBar)に組み立てる。
function buildMenus() {
  return [
    {
      id: "project",
      label: "Project",
      enabled: true,
      items: [
        { label: "Create New Project...", action: actionCreateNewProject },
        { label: "Open Project...", action: actionOpenProject },
        { separator: true },
        { label: "Save", action: actionSave },
        { label: "Save As...", action: actionSaveAs },
        { label: "Close Project", action: actionCloseProject },
        { separator: true },
        { label: "Preferences...", action: actionOpenPreferences },
        { separator: true },
        { label: "Exit", action: actionExit },
      ],
    },
    {
      id: "edit",
      label: "Edit",
      enabled: true,
      items: [
        { label: "New Dramaturgy...", action: actionNewDramaturgy },
        { label: "Dramaturgy Editor", action: actionOpenDramaturgyEditor },
        { label: "Character Editor", action: actionOpenCharacterEditor },
      ],
    },
    {
      id: "connection",
      label: "Connection",
      enabled: true,
      items: [
        { label: "Connect to Server...", action: actionConnectToServer },
        { label: "Test Connection", action: actionTestConnection },
        { separator: true },
        { label: "Update Project Path...", action: actionUpdateProjectPath },
        { separator: true },
        { label: "Disconnect", action: actionDisconnect },
      ],
    },
  ];
}

function closeAllMenus() {
  document.querySelectorAll(".menu-top").forEach((top) => {
    top.classList.remove("open");
    const dropdown = top.querySelector(".menu-dropdown");
    if (dropdown) dropdown.hidden = true;
  });
}

function renderMenuBar() {
  const container = document.getElementById("menubar-left");
  container.innerHTML = "";
  for (const menu of buildMenus()) {
    const top = document.createElement("div");
    top.className = "menu-top";

    const btn = document.createElement("button");
    btn.className = "menu-top-btn";
    btn.textContent = menu.label;
    btn.disabled = !menu.enabled;
    top.appendChild(btn);

    if (menu.enabled) {
      const dropdown = document.createElement("div");
      dropdown.className = "menu-dropdown";
      dropdown.hidden = true;
      for (const item of menu.items) {
        if (item.separator) {
          const sep = document.createElement("div");
          sep.className = "menu-separator";
          dropdown.appendChild(sep);
        } else if (item.groupLabel) {
          const gl = document.createElement("div");
          gl.className = "menu-submenu-label";
          gl.textContent = item.groupLabel;
          dropdown.appendChild(gl);
        } else {
          const mi = document.createElement("button");
          mi.className = "menu-item";
          mi.textContent = item.label;
          mi.addEventListener("click", () => {
            closeAllMenus();
            item.action();
          });
          dropdown.appendChild(mi);
        }
      }
      top.appendChild(dropdown);

      btn.addEventListener("click", (ev) => {
        ev.stopPropagation();
        const isOpen = top.classList.contains("open");
        closeAllMenus();
        if (!isOpen) {
          top.classList.add("open");
          dropdown.hidden = false;
        }
      });
    }

    container.appendChild(top);
  }

  document.addEventListener("click", closeAllMenus);
}

// ---------------------------------------------------------------------------
// 初期化
// ---------------------------------------------------------------------------

function init() {
  renderMenuBar();
  renderBadges();
  renderTreeRoot();
}

document.addEventListener("DOMContentLoaded", init);
