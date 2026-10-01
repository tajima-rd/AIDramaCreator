"use strict";
/*
 * <data-viewer-panel> — Tree上のDatasetノードをクリックした際にmain-areaへ
 * mountする読み取り専用のビューア。他のパネルと同じ
 * 規約(light DOM、apiFetch/showApiError/escapeHtml/csvToRowsをグローバル
 * 利用)。CSVは表として、PDF(論文等)はサーバーが返すファイルそのもの
 * (GET .../datasets/{file_id}/file)をブラウザのPDF表示で見せる。Word・Excel(DOCX・XLSX)は
 * ブラウザで表示できないためダウンロードさせる。
 */

customElements.define(
  "data-viewer-panel",
  class extends HTMLElement {
    constructor() {
      super();
      this.projectId = null;
      this.fileId = null;
      this.filename = null;
      this.fileFormat = null; // "csv" | "pdf" | "other"
      this.content = null; // {columns, rows}
      this.loadFailed = false;
    }

    connectedCallback() {
      this.innerHTML = `
        <div class="panel-header" id="dv-header">Data Viewer</div>
        <div class="panel-body" id="dv-body"></div>
      `;
    }

    async run(projectId, fileId, filename, fileFormat) {
      this.projectId = projectId;
      this.fileId = fileId;
      this.filename = filename;
      // 呼び出し側が形式を知らない場合は拡張子から決める(サーバーのcore.project.dataset.file_formatと同じ規則)
      this.fileFormat = fileFormat || datasetFileFormat(filename);
      this.content = null;
      this.loadFailed = false;
      this.render();
      if (this.fileFormat !== "csv") return; // PDFはrenderでファイルそのものを表示する
      try {
        const data = await apiFetch(`/projects/${projectId}/datasets/${encodeURIComponent(fileId)}`);
        this.content = csvToRows(data.csv);
      } catch (e) {
        this.loadFailed = true;
        showApiError(e);
      }
      this.render();
    }

    render() {
      const header = this.querySelector("#dv-header");
      const body = this.querySelector("#dv-body");
      header.textContent = this.filename ? `Data Viewer — ${this.filename}` : "Data Viewer";

      const fileUrl = `${state.serverBaseUrl.replace(/\/$/, "")}/projects/${this.projectId}/datasets/${encodeURIComponent(this.fileId)}/file`;
      if (this.fileFormat === "pdf") {
        body.innerHTML = `<iframe class="pdf-viewer" src="${escapeAttr(fileUrl)}" title="${escapeAttr(this.filename)}"></iframe>`;
        return;
      }
      if (this.fileFormat !== "csv") {
        // Word・Excel等はブラウザの中で表示できないため、ダウンロードして開いてもらう
        body.innerHTML = `
          <p class="placeholder">この形式(${escapeHtml(this.fileFormat.toUpperCase())})はブラウザの中では表示できません。ダウンロードして開いてください。</p>
          <div class="panel-actions"><a class="btn" href="${escapeAttr(fileUrl)}" download="${escapeAttr(this.filename)}">Download</a></div>`;
        return;
      }

      if (this.loadFailed) {
        body.innerHTML = `<p class="placeholder">データの取得に失敗しました。</p>`;
        return;
      }
      if (!this.content) {
        body.innerHTML = `<p class="placeholder">読み込んでいます…</p>`;
        return;
      }
      const { columns, rows } = this.content;
      if (columns.length === 0) {
        body.innerHTML = `<p class="placeholder">データがありません。</p>`;
        return;
      }
      const headerRow = `<tr>${columns.map((c) => `<th>${escapeHtml(c)}</th>`).join("")}</tr>`;
      const bodyRows = rows
        .map((r) => `<tr>${columns.map((c) => `<td>${escapeHtml(r[c])}</td>`).join("")}</tr>`)
        .join("");
      body.innerHTML = `
        <div class="panel-section-title">${escapeHtml(this.filename)} (${rows.length} rows × ${columns.length} columns)</div>
        <div class="data-table-wrap data-table-wrap--fill">
          <table class="data-table">${headerRow}${bodyRows}</table>
        </div>
      `;
    }
  }
);
