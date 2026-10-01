"use strict";
/*
 * <project-overview-panel> — TreeのProject・Datasetsノードをクリックした際にmain-areaへmountする、
 * プロジェクト全体を扱うタブ式パネル(panel-tabs/panel-body、Datasetタブはpanel-master-detail)。
 * selectHtml/textField/fieldError/apiFetch/showApiError/showToast/escapeHtml/escapeAttr/csvToRows/
 * ApiError/testServerHealth/setCurrentProject/mountDataViewerPanelをグローバル利用する。
 *
 * タブ構成:
 * - Overview: project.yamlのname/server_base_urlの編集フォームのみ
 * - Summary: Datasetの数と、project.yamlの読み取り専用の情報(protocol_version等)
 * - Generative AI: 生成AIの接続先の設定(project.yamlのgenaiセクション)とAPIキー。
 *   中身はproject_genai_tab.jsのProjectGenaiTab。Project > Preferences... もこのタブを開く
 * - Dataset: プロジェクト内の全Datasetの一覧+メタデータの閲覧・編集+新規Dataset追加
 *
 * Datasetとして追加できるのは参考資料のファイル(PDF・DOCX・XLSX)だけ(POST .../datasets/files)。
 * Datasetとドラマの結び付けは未決定(docs/future_design.md)なので、割り当ての操作は置かない。
 */

// CSVのDatasetのColumns行(列名(読み取り専用)+型セレクト+説明入力)で選べる型。
// SQLiteの型親和性(type affinity)の5分類。データメタデータYAML側の
// columns[].typeは自由記述の文字列のため、ここで選んだ値がそのまま
// 文字列として保存される。
const SQLITE_COLUMN_TYPES = ["TEXT", "NUMERIC", "INTEGER", "REAL", "BLOB"];

// DatasetSummary.file_format(データ本体の形式、拡張子から決まる)の表示名
const DATASET_FORMAT_LABELS = { csv: "CSV", pdf: "PDF", docx: "Word (DOCX)", xlsx: "Excel (XLSX)", other: "Other" };
// Datasetとして追加できる形式(POST .../datasets/files)
const DATASET_FILE_FORMATS = ["pdf", "docx", "xlsx"];

function datasetFileFormat(filename) {
  const m = /\.([a-z0-9]+)$/i.exec(filename || "");
  const ext = m ? m[1].toLowerCase() : "";
  return ext === "csv" || DATASET_FILE_FORMATS.includes(ext) ? ext : "other";
}

// provenance.parameters(dict)の表示用の文字列
function formatParameters(parameters) {
  const entries = Object.entries(parameters || {});
  if (entries.length === 0) return "(none)";
  return entries.map(([k, v]) => `${k}: ${v}`).join(", ");
}

// 既存データの自由記述な型名(string/integer等、旧テキスト欄時代に入力
// された値や他ツール由来の値)をSQLITE_COLUMN_TYPESの値へ丸め込む。
// 該当しなければ既定でTEXTとする。
function normalizeSqliteType(type) {
  if (!type) return "TEXT";
  const upper = String(type).trim().toUpperCase();
  if (SQLITE_COLUMN_TYPES.includes(upper)) return upper;
  const map = {
    STRING: "TEXT",
    STR: "TEXT",
    VARCHAR: "TEXT",
    DATE: "TEXT",
    DATETIME: "TEXT",
    INT: "INTEGER",
    BOOL: "INTEGER",
    BOOLEAN: "INTEGER",
    FLOAT: "REAL",
    DOUBLE: "REAL",
  };
  return map[upper] || "TEXT";
}

// Columns行群のHTML(既存のCSVのDatasetの編集フォーム)。
// 列名は読み取り専用(CSVヘッダーから決まるため)、型はSQLITE_COLUMN_TYPES
// のセレクト、説明のみ自由入力。
function renderColumnsRowsHtml(columns, idPrefix) {
  if (columns.length === 0) {
    return `<p class="field-hint">(列情報がありません)</p>`;
  }
  return columns
    .map(
      (c, i) => `
    <div class="panel-form-row columns-row">
      <div class="columns-row-name">${escapeHtml(c.name)}</div>
      <div class="columns-row-type">${selectHtml(`${idPrefix}_type_${i}`, SQLITE_COLUMN_TYPES, normalizeSqliteType(c.type), null)}</div>
      <div class="columns-row-desc"><input type="text" id="${idPrefix}_desc_${i}" value="${escapeAttr(c.description || "")}" placeholder="説明(任意)"></div>
    </div>`
    )
    .join("");
}

// Columns行群のイベント配線。columnsは呼び出し元が保持する配列への参照を
// そのまま受け取り、行の変更をその場でcolumns[i]へ書き戻す(保存時は
// columnsをそのまま送るだけでよい)。
function wireColumnsRows(container, columns, idPrefix) {
  columns.forEach((c, i) => {
    const typeSelect = container.querySelector(`#${idPrefix}_type_${i}`);
    if (typeSelect) {
      typeSelect.addEventListener("change", (ev) => {
        c.type = ev.target.value;
      });
    }
    const descInput = container.querySelector(`#${idPrefix}_desc_${i}`);
    if (descInput) {
      descInput.addEventListener("input", (ev) => {
        c.description = ev.target.value;
      });
    }
  });
}

customElements.define(
  "project-overview-panel",
  class extends HTMLElement {
    constructor() {
      super();
      this.projectId = null;
      this.project = null; // ProjectInfo
      this.datasets = null; // DatasetSummary[]
      this.activeTab = "overview";
      this.selectedDatasetFileId = null;
      this.creatingDataset = false;
      this.newDatasetForm = null; // {filename, filenameEditedByUser, fileFormat, fileBase64, datasetCategory, description, source, collectedAt, tags, notes}
      this.datasetMetadataCache = {}; // file_id -> DatasetMetadata | null(未保存) | "loading" | "failed"
      this.datasetColumnsOverride = {}; // file_id -> [{name,type,description}](「カラム情報を更新」ボタンでCSVヘッダーから取得した値。保存されるまではmetadata.columnsより優先して表示する)
      this.loadFailed = false;
    }

    connectedCallback() {
      this.innerHTML = `
        <div class="panel-header" id="po-header">Project Overview</div>
        <div class="panel-tabs" id="po-tabs"></div>
        <div class="panel-body" id="po-body"></div>
      `;
    }

    async run(projectId) {
      this.projectId = projectId;
      this.project = null;
      this.datasets = null;
      this.activeTab = "overview";
      this.selectedDatasetFileId = null;
      this.creatingDataset = false;
      this.newDatasetForm = null;
      this.datasetMetadataCache = {};
      this.datasetColumnsOverride = {};
      this.genaiTab = new ProjectGenaiTab(projectId); // 入力中の内容はタブを切り替えても保つ
      this.loadFailed = false;
      this.render();
      await this.reloadAll();
    }

    selectTab(tab) {
      this.activeTab = tab;
      this.render();
    }

    async reloadAll() {
      try {
        const [project, datasetsResult] = await Promise.all([
          apiFetch(`/projects/${this.projectId}`),
          apiFetch(`/projects/${this.projectId}/datasets`),
        ]);
        this.project = project;
        this.datasets = datasetsResult.datasets || [];
      } catch (e) {
        this.loadFailed = true;
        showApiError(e);
      }
      this.render();
    }

    async reloadDatasetsOnly() {
      try {
        const result = await apiFetch(`/projects/${this.projectId}/datasets`);
        this.datasets = result.datasets || [];
      } catch (e) {
        showApiError(e);
      }
    }

    render() {
      this.renderTabs();
      const body = this.querySelector("#po-body");
      if (this.loadFailed) {
        body.innerHTML = `<p class="placeholder">プロジェクト情報の取得に失敗しました。</p>`;
        return;
      }
      if (!this.project) {
        body.innerHTML = `<p class="placeholder">読み込んでいます…</p>`;
        return;
      }
      if (this.activeTab === "overview") this.renderOverviewTab(body);
      else if (this.activeTab === "summary") this.renderSummaryTab(body);
      else if (this.activeTab === "genai") this.genaiTab.mount(body);
      else if (this.activeTab === "dataset") this.renderDatasetTab(body);
    }

    renderTabs() {
      const tabs = this.querySelector("#po-tabs");
      tabs.innerHTML = "";
      const defs = [
        ["overview", "Overview"],
        ["summary", "Summary"],
        ["genai", "Generative AI"],
        ["dataset", "Dataset"],
      ];
      for (const [key, label] of defs) {
        const btn = document.createElement("button");
        btn.className = "panel-tab" + (this.activeTab === key ? " active" : "");
        btn.textContent = label;
        btn.addEventListener("click", () => this.selectTab(key));
        tabs.appendChild(btn);
      }
    }

    // -------------------------------------------------------------------
    // Overview tab
    // -------------------------------------------------------------------

    renderOverviewTab(body) {
      const p = this.project;
      body.innerHTML = `
        <div class="panel-section-title">Project</div>
        <div class="panel-form">
          ${textField("po_name", "Name", p.name)}
          ${textField("po_server_base_url", "Server Base URL", p.server_base_url, "保存時に接続テストを行い、接続できない場合は保存しません。")}
          <div class="panel-actions">
            <button type="button" class="btn btn-primary" id="po_save">Save</button>
          </div>
        </div>
      `;
      body.querySelector("#po_save").addEventListener("click", () => this.saveProperties());
    }

    async saveProperties() {
      const body = this.querySelector("#po-body");
      const name = body.querySelector("#po_name").value.trim();
      const serverBaseUrl = body.querySelector("#po_server_base_url").value.trim();
      fieldError(body, "po_name", "");
      fieldError(body, "po_server_base_url", "");
      if (!name) {
        fieldError(body, "po_name", "入力してください");
        return;
      }
      if (!serverBaseUrl) {
        fieldError(body, "po_server_base_url", "入力してください");
        return;
      }

      const saveBtn = body.querySelector("#po_save");
      const originalLabel = saveBtn.textContent;
      saveBtn.disabled = true;
      saveBtn.textContent = "Testing Connection...";
      const healthy = await testServerHealth(serverBaseUrl);
      if (!healthy) {
        saveBtn.disabled = false;
        saveBtn.textContent = originalLabel;
        fieldError(body, "po_server_base_url", "このURLに接続できませんでした(保存を中止しました)");
        return;
      }

      saveBtn.textContent = "Saving...";
      try {
        const info = await apiFetch(`/projects/${this.projectId}`, {
          method: "PUT",
          bodyObj: { name, server_base_url: serverBaseUrl },
        });
        this.project = info;
        setCurrentProject(info);
        showToast("プロジェクトを更新しました", "ok");
        this.render();
      } catch (e) {
        showApiError(e);
      } finally {
        saveBtn.disabled = false;
        saveBtn.textContent = originalLabel;
      }
    }

    // -------------------------------------------------------------------
    // Summary tab
    // -------------------------------------------------------------------

    renderSummaryTab(body) {
      const p = this.project;
      body.innerHTML = `
        <div class="panel-section-title">Overview</div>
        <div class="overview-stats-grid">
          ${this.statCard(this.datasets.length, "Datasets")}
        </div>

        <div class="panel-section-title">project.yaml (Read-only)</div>
        <div class="overview-meta-list">
          ${this.metaRow("Project ID", p.project_id)}
          ${this.metaRow("Path", p.path)}
          ${this.metaRow("Protocol Version", p.protocol_version)}
          ${this.metaRow("Created At", p.created_at)}
          ${this.metaRow("Modified At", p.modified_at)}
        </div>

      `;
    }

    statCard(value, label, sub) {
      return `
        <div class="overview-stat-card">
          <div class="overview-stat-value">${escapeHtml(String(value))}</div>
          <div class="overview-stat-label">${escapeHtml(label)}</div>
          ${sub ? `<div class="overview-stat-sub">${escapeHtml(sub)}</div>` : ""}
        </div>
      `;
    }

    metaRow(key, value) {
      return `<div class="overview-meta-row"><div class="k">${escapeHtml(key)}</div><div class="v">${escapeHtml(String(value))}</div></div>`;
    }

    // -------------------------------------------------------------------
    // Dataset tab
    // -------------------------------------------------------------------

    renderDatasetTab(body) {
      body.innerHTML = `
        <div class="panel-master-detail">
          <div class="panel-master" id="ds-master"></div>
          <div class="panel-detail" id="ds-detail"></div>
        </div>
      `;
      this.renderDatasetMaster();
      this.renderDatasetDetail();
    }

    renderDatasetMaster() {
      const master = this.querySelector("#ds-master");
      master.innerHTML = "";
      if (this.datasets.length === 0) {
        const empty = document.createElement("div");
        empty.className = "panel-master-empty";
        empty.textContent = "(No Datasets)";
        master.appendChild(empty);
      }
      for (const d of this.datasets) {
        const item = document.createElement("div");
        const selected = !this.creatingDataset && this.selectedDatasetFileId === d.file_id;
        item.className = "panel-master-item" + (selected ? " selected" : "");
        const categoryBadge =
          d.dataset_category && d.dataset_category !== "unspecified"
            ? `<span class="dataset-badge">${escapeHtml(d.dataset_category)}</span>`
            : "";
        const formatBadge = d.file_format
          ? `<span class="dataset-badge">${escapeHtml(d.file_format.toUpperCase())}</span>`
          : "";
        item.innerHTML =
          `<div class="item-alias">${escapeHtml(d.filename)}</div>` +
          `<div class="item-name">${categoryBadge}${formatBadge}</div>`;
        item.addEventListener("click", () => this.selectDataset(d.file_id));
        master.appendChild(item);
      }
      const addBtn = document.createElement("button");
      addBtn.className = "panel-master-add";
      addBtn.textContent = "+ Add Dataset";
      addBtn.addEventListener("click", () => {
        this.selectedDatasetFileId = null;
        this.creatingDataset = true;
        this.newDatasetForm = {
          filename: "",
          filenameEditedByUser: false,
          fileFormat: "", // "pdf" | "docx" | "xlsx"(選んだファイルの拡張子から決める)
          fileBase64: "", // ファイルの中身(base64)
          datasetCategory: "reference",
          description: "",
          source: "",
          collectedAt: "",
          tags: "",
          notes: "",
        };
        this.render();
      });
      master.appendChild(addBtn);
    }

    selectDataset(fileId) {
      this.selectedDatasetFileId = fileId;
      this.creatingDataset = false;
      this.render();
      if (this.datasetMetadataCache[fileId] === undefined) {
        this.loadDatasetMetadata(fileId);
      }
    }

    async loadDatasetMetadata(fileId) {
      this.datasetMetadataCache[fileId] = "loading";
      if (this.selectedDatasetFileId === fileId) this.renderDatasetDetail();
      try {
        const metadata = await apiFetch(`/projects/${this.projectId}/datasets/${encodeURIComponent(fileId)}/metadata`);
        this.datasetMetadataCache[fileId] = metadata;
      } catch (e) {
        if (e instanceof ApiError && e.status === 404) {
          this.datasetMetadataCache[fileId] = null; // メタデータ未保存(エラーではない)
        } else {
          this.datasetMetadataCache[fileId] = "failed";
          showApiError(e);
        }
      }
      if (this.selectedDatasetFileId === fileId) this.renderDatasetDetail();
    }

    renderDatasetDetail() {
      const detail = this.querySelector("#ds-detail");
      if (!detail) return;
      if (this.creatingDataset) {
        this.renderCreateDatasetForm(detail);
        return;
      }
      if (!this.selectedDatasetFileId) {
        detail.innerHTML = `<p class="placeholder">左の一覧からDatasetを選択するか、「+ Add Dataset」で新規追加してください。</p>`;
        return;
      }
      const fileId = this.selectedDatasetFileId;
      const summary = this.datasets.find((d) => d.file_id === fileId);
      const filename = summary ? summary.filename : "?";
      const cache = this.datasetMetadataCache[fileId];

      if (cache === "loading" || cache === undefined) {
        detail.innerHTML = `<p class="placeholder">読み込んでいます…</p>`;
        return;
      }
      if (cache === "failed") {
        detail.innerHTML = `<p class="placeholder">メタデータの取得に失敗しました。</p>`;
        return;
      }
      const metadata = cache; // DatasetMetadata | null(未保存)
      const d = metadata ? metadata.dataset : null;
      const lastHistory = d && d.history.length > 0 ? d.history[d.history.length - 1] : null;
      const provenance = metadata ? metadata.provenance : null;
      const fileFormat = summary ? summary.file_format : "other";
      const isCsv = fileFormat === "csv";
      const storedColumns = metadata ? metadata.columns : [];
      const columns = this.datasetColumnsOverride[fileId] || storedColumns;
      this._currentEditColumns = columns; // wireColumnsRowsが行の変更をここへ書き戻す
      const showUpdateColumnsBtn = isCsv && columns.length === 0;
      detail.innerHTML = `
        <div class="panel-readonly-id">Filename: ${escapeHtml(filename)}</div>
        <dl class="properties mb-md">
          <dt>Size</dt><dd>${summary ? summary.size_bytes : "?"} bytes</dd>
          <dt>Format</dt><dd>${escapeHtml(DATASET_FORMAT_LABELS[fileFormat] || "Unknown")}</dd>
          <dt>Dataset Category</dt><dd>${escapeHtml((d && d.dataset_category) || "unspecified")}</dd>
          <dt>Created At</dt><dd>${escapeHtml(d && d.created_at ? d.created_at : "(none)")}</dd>
          <dt>Last Updated</dt><dd>${escapeHtml(lastHistory ? lastHistory.updated_at : "(none)")}</dd>
        </dl>
        ${
          provenance
            ? `
        <div class="panel-section-title mt-0">Provenance</div>
        <dl class="properties mb-md">
          <dt>Process</dt><dd>${escapeHtml(provenance.process)}</dd>
          <dt>Parameters</dt><dd>${escapeHtml(formatParameters(provenance.parameters))}</dd>
          <dt>Source Refs</dt><dd>${
            provenance.source_refs.length > 0
              ? escapeHtml(provenance.source_refs.map((r) => `${r.kind}: ${r.id}`).join(", "))
              : "(none)"
          }</dd>
        </dl>`
            : ""
        }
        <div class="panel-actions mb-lg">
          <button type="button" class="btn" id="ds_view_data">${fileFormat === "pdf" ? "View PDF" : fileFormat === "csv" ? "View Data" : "Open"}</button>
        </div>
        ${metadata === null ? `<p class="field-hint">このDatasetにはまだメタデータYAMLがありません。保存すると新規作成されます。</p>` : ""}
        <div class="panel-form">
          ${textField("dm_description", "Description", (d && d.description) || "")}
          ${textField("dm_source", "Source", (d && d.source) || "")}
          ${textField("dm_collected_at", "Collected At", (d && d.collected_at) || "", "自由記述の日付文字列")}
          ${textField("dm_tags", "Tags", d && d.tags ? d.tags.join(", ") : "", "カンマ区切り")}
          <div class="field">
            <label for="dm_notes">Notes</label>
            <textarea id="dm_notes">${escapeHtml((d && d.notes) || "")}</textarea>
          </div>
          ${
            isCsv
              ? `<div class="field">
            <label>Columns (type specified by SQLite type affinity)</label>
            <div id="dm_columns_rows">${renderColumnsRowsHtml(columns, "dm_col")}</div>
          </div>`
              : ""
          }
          <div class="panel-actions">
            <button type="button" class="btn btn-primary" id="dm_save">Save Metadata</button>
            ${showUpdateColumnsBtn ? `<button type="button" class="btn" id="dm_update_columns">Update Columns</button>` : ""}
            <button type="button" class="btn btn-danger" id="dm_remove">Remove Dataset</button>
          </div>
        </div>
      `;
      wireColumnsRows(detail, columns, "dm_col");
      detail.querySelector("#ds_view_data").addEventListener("click", () => {
        mountDataViewerPanel(this.projectId, fileId, filename, fileFormat);
      });
      detail.querySelector("#dm_save").addEventListener("click", () => this.saveDatasetMetadata(fileId));
      if (showUpdateColumnsBtn) {
        detail.querySelector("#dm_update_columns").addEventListener("click", () => this.updateColumnsFromCsv(fileId));
      }
      detail.querySelector("#dm_remove").addEventListener("click", () => this.deleteDataset(fileId));
    }

    // CSVのヘッダーから列名を検出し、Columnsのdescription/typeを編集できる
    // 状態にする(「Add Dataset」フォームと同じ体験)。保存はしない(通常通り
    // 「Save Metadata」を押すまで確定しない)。metadata.columnsが空のCSV
    // Datasetでのみボタンが表示される(renderDatasetDetail参照)。
    async updateColumnsFromCsv(fileId) {
      const detail = this.querySelector("#ds-detail");
      const btn = detail.querySelector("#dm_update_columns");
      const originalLabel = btn.textContent;
      btn.disabled = true;
      btn.textContent = "Detecting...";
      try {
        const content = await apiFetch(`/projects/${this.projectId}/datasets/${encodeURIComponent(fileId)}`);
        const { columns } = csvToRows(content.csv);
        this.datasetColumnsOverride[fileId] = columns.map((name) => ({ name, type: "TEXT", description: "" }));
        this.renderDatasetDetail();
      } catch (e) {
        showApiError(e);
        btn.disabled = false;
        btn.textContent = originalLabel;
      }
    }

    async deleteDataset(fileId) {
      const summary = this.datasets.find((d) => d.file_id === fileId);
      const filename = summary ? summary.filename : fileId;
      const ok = confirm(
        `Dataset "${filename}" を削除します。ファイル本体・メタデータYAMLとも削除され、元に戻せません。よろしいですか?`
      );
      if (!ok) return;
      try {
        await apiFetch(`/projects/${this.projectId}/datasets/${encodeURIComponent(fileId)}`, { method: "DELETE" });
        showToast("Datasetを削除しました", "ok");
        delete this.datasetMetadataCache[fileId];
        if (this.selectedDatasetFileId === fileId) this.selectedDatasetFileId = null;
        await this.reloadDatasetsOnly();
        this.dispatchEvent(new CustomEvent("project-overview-changed", { bubbles: true }));
        this.render();
      } catch (e) {
        showApiError(e);
      }
    }

    async saveDatasetMetadata(fileId) {
      const detail = this.querySelector("#ds-detail");
      const description = detail.querySelector("#dm_description").value.trim() || null;
      const source = detail.querySelector("#dm_source").value.trim() || null;
      const collectedAt = detail.querySelector("#dm_collected_at").value.trim() || null;
      const tags = detail
        .querySelector("#dm_tags")
        .value.split(",")
        .map((s) => s.trim())
        .filter((s) => s.length > 0);
      const notes = detail.querySelector("#dm_notes").value.trim() || null;
      // this._currentEditColumns はrenderDatasetDetailが直近描画した配列への
      // 参照で、wireColumnsRowsが行の変更(型セレクト/説明)をその場で
      // 書き戻し済み(「カラム情報を更新」ボタンで取得した値も含む)。
      const columns = (this._currentEditColumns || []).map((c) => ({
        name: c.name,
        type: c.type,
        description: c.description ? c.description.trim() || null : null,
      }));

      const saveBtn = detail.querySelector("#dm_save");
      const originalLabel = saveBtn.textContent;
      saveBtn.disabled = true;
      saveBtn.textContent = "Saving...";
      try {
        const metadata = await apiFetch(`/projects/${this.projectId}/datasets/${encodeURIComponent(fileId)}/metadata`, {
          method: "PUT",
          bodyObj: { description, source, collected_at: collectedAt, tags, notes, columns, message: "" },
        });
        this.datasetMetadataCache[fileId] = metadata;
        delete this.datasetColumnsOverride[fileId];
        showToast("メタデータを保存しました", "ok");
        this.renderDatasetDetail();
      } catch (e) {
        showApiError(e);
      } finally {
        saveBtn.disabled = false;
        saveBtn.textContent = originalLabel;
      }
    }

    renderCreateDatasetForm(detail) {
      const form = this.newDatasetForm;
      detail.innerHTML = `
        <div class="panel-section-title">Add New Dataset</div>
        <div class="panel-form">
          <div class="field">
            <label for="nd_file">File</label>
            <div class="field-file-row"><input type="file" id="nd_file" accept=".pdf,.docx,.xlsx"></div>
            <div class="field-hint">参考資料(PDF・Word(DOCX)・Excel(XLSX))を選びます。</div>
            <div class="field-error" id="err_nd_file"></div>
          </div>
          ${textField("nd_filename", "Filename", form.filename, "例: paper.pdf(ファイル選択時、未編集ならファイル名を自動セット)")}
          <div class="field">
            <label for="nd_dataset_category">Dataset Category</label>
            ${selectHtml("nd_dataset_category", ["reference", "unspecified"], form.datasetCategory, (v) =>
              v === "reference" ? "Reference (生成AIに渡す参考資料)" : "Unspecified"
            )}
          </div>
          <div class="panel-section-title">Metadata (Optional)</div>
          ${textField("nd_description", "Description", form.description)}
          ${textField("nd_source", "Source", form.source, "書誌情報・URL等")}
          ${textField("nd_collected_at", "Collected At", form.collectedAt, "自由記述の日付文字列")}
          ${textField("nd_tags", "Tags", form.tags, "カンマ区切り")}
          <div class="field">
            <label for="nd_notes">Notes</label>
            <textarea id="nd_notes">${escapeHtml(form.notes)}</textarea>
          </div>
          <div class="panel-actions">
            <button type="button" class="btn btn-primary" id="nd_create">Create</button>
            <button type="button" class="btn" id="nd_cancel">Cancel</button>
          </div>
        </div>
      `;
      this.wireCreateDatasetForm(detail);
    }

    wireCreateDatasetForm(detail) {
      const form = this.newDatasetForm;
      const filenameInput = detail.querySelector("#nd_filename");
      filenameInput.addEventListener("input", () => {
        form.filename = filenameInput.value;
        form.filenameEditedByUser = true;
      });
      detail.querySelector("#nd_dataset_category").addEventListener("change", (ev) => {
        form.datasetCategory = ev.target.value;
      });
      detail.querySelector("#nd_description").addEventListener("input", (ev) => {
        form.description = ev.target.value;
      });
      detail.querySelector("#nd_source").addEventListener("input", (ev) => {
        form.source = ev.target.value;
      });
      detail.querySelector("#nd_collected_at").addEventListener("input", (ev) => {
        form.collectedAt = ev.target.value;
      });
      detail.querySelector("#nd_tags").addEventListener("input", (ev) => {
        form.tags = ev.target.value;
      });
      detail.querySelector("#nd_notes").addEventListener("input", (ev) => {
        form.notes = ev.target.value;
      });

      const fileInput = detail.querySelector("#nd_file");
      fileInput.addEventListener("change", () => {
        const file = fileInput.files[0];
        if (!file) return;
        const chosenFormat = datasetFileFormat(file.name);
        if (!DATASET_FILE_FORMATS.includes(chosenFormat)) {
          fieldError(detail, "nd_file", "PDF・DOCX・XLSXのファイルを選択してください");
          return;
        }
        const reader = new FileReader();
        reader.onload = () => {
          if (!form.filenameEditedByUser) {
            form.filename = file.name;
          }
          form.fileFormat = chosenFormat;
          // data:<MIME>;base64,xxxx の base64 部分だけを送る
          form.fileBase64 = String(reader.result).split(",", 2)[1] || "";
          this.renderCreateDatasetForm(detail);
        };
        reader.readAsDataURL(file);
      });

      detail.querySelector("#nd_create").addEventListener("click", () => this.createDataset());
      detail.querySelector("#nd_cancel").addEventListener("click", () => {
        this.creatingDataset = false;
        this.newDatasetForm = null;
        this.render();
      });
    }

    async createDataset() {
      const detail = this.querySelector("#ds-detail");
      const form = this.newDatasetForm;
      fieldError(detail, "nd_filename", "");
      fieldError(detail, "nd_file", "");
      let ok = true;
      if (!form.filename.trim()) {
        fieldError(detail, "nd_filename", "入力してください");
        ok = false;
      }
      if (!form.fileBase64) {
        fieldError(detail, "nd_file", "PDF・DOCX・XLSXのファイルを選択してください");
        ok = false;
      }
      if (!ok) return;

      const createBtn = detail.querySelector("#nd_create");
      createBtn.disabled = true;
      try {
        const saved = await apiFetch(`/projects/${this.projectId}/datasets/files`, {
          method: "POST",
          bodyObj: {
            filename: form.filename.trim(),
            content_base64: form.fileBase64,
            dataset_category: form.datasetCategory,
          },
        });
        const tags = form.tags
          .split(",")
          .map((s) => s.trim())
          .filter((s) => s.length > 0);
        await apiFetch(`/projects/${this.projectId}/datasets/${encodeURIComponent(saved.file_id)}/metadata`, {
          method: "PUT",
          bodyObj: {
            description: form.description.trim() || null,
            source: form.source.trim() || null,
            collected_at: form.collectedAt.trim() || null,
            tags,
            notes: form.notes.trim() || null,
            columns: [],
            message: "",
          },
        });
        showToast("Datasetを追加しました", "ok");
        this.creatingDataset = false;
        this.newDatasetForm = null;
        await this.reloadDatasetsOnly();
        this.dispatchEvent(new CustomEvent("project-overview-changed", { bubbles: true }));
        this.selectDataset(saved.file_id);
      } catch (e) {
        showApiError(e);
      } finally {
        createBtn.disabled = false;
      }
    }
  }
);
