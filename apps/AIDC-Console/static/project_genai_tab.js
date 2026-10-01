"use strict";
/*
 * ProjectGenaiTab — Project Overviewパネル(project_overview_panel.js)のGenerative AIタブの中身。
 * Project > Preferences... もこのタブを開く。Overviewが渡す要素(タブの本体)に描画し、
 * タブを離れて要素が外れた後の非同期の結果は描画しない。
 * textField/selectHtml/fieldError/apiFetch/showApiError/showToast/escapeHtml/escapeAttr/ApiError
 * をグローバル利用する。
 *
 * - 文章生成(LLM。作品作り用のCreativeと作業補助用のAssistiveの2つ)・音声合成(TTS)・資料の検索の埋め込み
 *   (Embedding)に使う生成AIの接続先(project.yamlのgenaiセクション)。タスクごとにどちらの文章生成を使うかは
 *   サーバー側(core/service/process/genai/llm_role.py)が決める。手入力を減らすため、
 *   - API URL: Providerを選ぶと接続先の候補(環境変数・手元の既定のURL)を問い合わせ、応答した
 *     ものを自動で入れる(候補は入力欄の候補一覧にも出す)
 *   - Model: 提供元に問い合わせたモデル名の一覧から選ぶ(一覧に無い名前は「手入力」で入れる)
 *   - APIキー: 提供元と接続先で決まるキー(名前はシステムが決める。例: AIDC_GEMINI_API_KEY)の
 *     状態(伏せ字)を表示し、未設定なら入力を促す。入力したキーは~/.aidc/secrets.envに保存され、
 *     AIDCはそこからだけキーを読む(シェルの環境変数は使わない。project.yamlにも書かない)
 */

const PREFERENCE_NO_CLIENT = "";
const PREFERENCE_MANUAL_MODEL = "__manual__";
// 設定の欄(project.yamlのgenai.creative_llm/assistive_llm/tts/embedding。以下ではkindと呼ぶ)ごとの、
// モデルの種類(提供元の一覧・モデル名の一覧の問い合わせに使う)と接続テストの種類(無ければnull)
const PREFERENCE_KIND_SPECS = {
  creative_llm: { modelKind: "llm", testKind: "llm" },
  assistive_llm: { modelKind: "llm", testKind: "llm" },
  tts: { modelKind: "tts", testKind: null },
  embedding: { modelKind: "embedding", testKind: "embedding" },
};
const PREFERENCE_KINDS = Object.keys(PREFERENCE_KIND_SPECS);
const PREFERENCE_TESTABLE_KINDS = PREFERENCE_KINDS.filter((kind) => PREFERENCE_KIND_SPECS[kind].testKind);

class ProjectGenaiTab {
    constructor(projectId) {
      this.projectId = projectId;
      this.container = null; // 描画先(OverviewのタブのDOM)
      this.loading = false;
      this.info = null; // PreferenceInfo
      this.form = null; // {creative_llm: {client, model, api_url}, assistive_llm: {...}, tts: {...}, embedding: {...}}(未保存の入力)
      this.loadFailed = false;
      this.assist = {}; // {creative_llm: 入力補助の状態, ...}(newAssist参照)
      for (const kind of PREFERENCE_KINDS) this.assist[kind] = this.newAssist();
      this.testResults = {}; // {creative_llm: LlmConnectionTestResult, embedding: EmbeddingConnectionTestResult, ...}
      this.testing = {};
      for (const kind of PREFERENCE_TESTABLE_KINDS) {
        this.testResults[kind] = null;
        this.testing[kind] = false;
      }
    }

    // Overviewがタブを描画するたびに呼ぶ。初回は設定を読み込む(以後は入力中の内容を保つ)。
    mount(container) {
      this.container = container;
      if (!this.info && !this.loading && !this.loadFailed) this.load();
      this.render();
    }

    querySelector(selector) {
      return this.container ? this.container.querySelector(selector) : null;
    }

    newAssist() {
      return {
        models: [], // 提供元に問い合わせたモデル名
        modelsState: "idle", // idle / loading / ok / error
        modelsError: "",
        manualModel: false, // 一覧に無いモデル名を手入力する
        urlCandidates: [], // ApiUrlCandidateInfo[]
        urlState: "idle", // idle / loading / ok
        keyInfo: null, // ApiKeyInfo(提供元と接続先で決まるキーの名前・状態)
        keyInput: "", // 入力中のAPIキー(保存するまで画面の中だけに持つ)
        keyEditing: false, // 設定済みのキーを入れ直す
        keySaving: false,
      };
    }

    async load() {
      this.loading = true;
      try {
        this.setInfo(await apiFetch(`/projects/${this.projectId}/preferences`));
      } catch (e) {
        this.loadFailed = true;
        showApiError(e);
      }
      this.loading = false;
      this.render();
      if (this.info) {
        for (const kind of PREFERENCE_KINDS) {
          if (this.form[kind].client !== PREFERENCE_NO_CLIENT) this.refreshAssist(kind, { autoFillUrl: false });
        }
      }
    }

    setInfo(info) {
      this.info = info;
      const toForm = (s) => ({
        client: s ? s.client : PREFERENCE_NO_CLIENT,
        model: s ? s.model : "",
        api_url: (s && s.api_url) || "",
      });
      this.form = {};
      for (const kind of PREFERENCE_KINDS) this.form[kind] = toForm(info[kind]);
    }

    render() {
      // タブを離れた(描画先が外れた)後に届いた非同期の結果は描画しない
      if (!this.container || !this.container.isConnected) return;
      const body = this.container;
      if (this.loadFailed) {
        body.innerHTML = `<p class="placeholder">設定の取得に失敗しました。</p>`;
        return;
      }
      if (!this.info) {
        body.innerHTML = `<p class="placeholder">読み込んでいます…</p>`;
        return;
      }
      // 再描画でスクロール位置が先頭に戻らないようにする
      const scrollTop = body.scrollTop;
      this.renderGenaiTab(body);
      body.scrollTop = scrollTop;
    }

    renderGenaiTab(body) {
      body.innerHTML = `
        <div class="panel-section-title">Text Generation for Creation (Creative LLM)</div>
        <div class="panel-form">
          <div class="field-hint">台詞・演出など、作品の品質に関わる生成に使います。</div>
          ${this.settingFieldsHtml("creative_llm")}
          ${this.connectionTestHtml("creative_llm")}
        </div>
        <div class="panel-section-title">Text Generation for Assistance (Assistive LLM)</div>
        <div class="panel-form">
          <div class="field-hint">骨組みの作成などの作業補助に使います。課金の無い生成AI(Google AI StudioのGemma・手元のllama.cpp等)を想定しています。未設定の場合、作業補助の機能は使えません(Creative LLMで代わりに動かすことはしません)。</div>
          ${this.settingFieldsHtml("assistive_llm")}
          ${this.connectionTestHtml("assistive_llm")}
        </div>
        <div class="panel-section-title">Speech Synthesis (TTS)</div>
        <div class="panel-form">
          ${this.settingFieldsHtml("tts")}
        </div>
        <div class="panel-section-title">Document Search (Embedding)</div>
        <div class="panel-form">
          <div class="field-hint">参考資料の検索で、文章の意味の近さを測るモデルです。使わない場合は語の一致だけで検索します(問いと資料の言語が違うと見つけにくくなります)。</div>
          ${this.settingFieldsHtml("embedding")}
          ${this.connectionTestHtml("embedding")}
        </div>
        <div class="panel-actions">
          <button type="button" class="btn btn-primary" id="pf_save">Save</button>
        </div>
      `;
      for (const kind of PREFERENCE_KINDS) this.wireSettingFields(body, kind);
      for (const kind of PREFERENCE_TESTABLE_KINDS) {
        const testBtn = body.querySelector(`#pf_${kind}_test`);
        if (testBtn) testBtn.addEventListener("click", () => this.testConnection(kind));
      }
      body.querySelector("#pf_save").addEventListener("click", () => this.save());
    }

    clientInfo(kind, name) {
      return this.clients(kind).find((c) => c.name === name) || null;
    }

    // その欄で選べる提供元(PreferenceInfoのllm_clients/tts_clients/embedding_clients)
    clients(kind) {
      return this.info[`${PREFERENCE_KIND_SPECS[kind].modelKind}_clients`];
    }

    settingFieldsHtml(kind) {
      const f = this.form[kind];
      const clients = this.clients(kind);
      const names = [PREFERENCE_NO_CLIENT, ...clients.map((c) => c.name)];
      const clientSelect = `
        <div class="field">
          <label for="pf_${kind}_client">Provider</label>
          ${selectHtml(`pf_${kind}_client`, names, f.client, (n) => (n === PREFERENCE_NO_CLIENT ? "(使わない)" : n))}
          <div class="field-error" id="err_pf_${kind}_client"></div>
        </div>`;
      const client = this.clientInfo(kind, f.client);
      if (!client) return clientSelect;
      return `
        ${clientSelect}
        ${client.requires_api_url ? this.apiUrlFieldHtml(kind) : ""}
        ${this.apiKeyFieldsHtml(kind, client)}
        ${this.modelFieldHtml(kind)}
      `;
    }

    apiUrlFieldHtml(kind) {
      const f = this.form[kind];
      const a = this.assist[kind];
      const options = a.urlCandidates
        .map((c) => `<option value="${escapeAttr(c.url)}">${escapeHtml(this.urlCandidateLabel(c))}</option>`)
        .join("");
      let hint = "サーバーのURL(パスは提供元に応じて自動で付けます)。候補は入力欄の一覧から選べます。";
      if (a.urlState === "loading") hint = "接続先を探しています…";
      else if (a.urlState === "ok" && a.urlCandidates.length && !a.urlCandidates.some((c) => c.reachable)) {
        hint = "応答するサーバーが見つかりませんでした。サーバーが起動しているか確認し、URLを入力してください。";
      }
      return `
        <div class="field">
          <label for="pf_${kind}_api_url">API URL</label>
          <div class="panel-form-row">
            <input type="text" id="pf_${kind}_api_url" list="pf_${kind}_api_url_list" value="${escapeAttr(f.api_url)}" placeholder="http://localhost:8080">
            <button type="button" class="btn" id="pf_${kind}_detect_url" ${a.urlState === "loading" ? "disabled" : ""}>Detect</button>
          </div>
          <datalist id="pf_${kind}_api_url_list">${options}</datalist>
          <div class="field-hint">${hint}</div>
          <div class="field-error" id="err_pf_${kind}_api_url"></div>
        </div>`;
    }

    urlCandidateLabel(c) {
      const source = c.source === "default" ? "手元の既定" : `環境変数 ${c.source}`;
      return `${source}・${c.reachable ? "応答あり" : "応答なし"}`;
    }

    apiKeyFieldsHtml(kind, client) {
      const a = this.assist[kind];
      const info = a.keyInfo;
      if (client.requires_api_url && !this.form[kind].api_url.trim()) {
        return `
          <div class="field">
            <label>API Key</label>
            <div class="field-hint">APIキーは接続先ごとに保存します。先にAPI URLを入力してください。</div>
          </div>`;
      }
      if (!info) {
        return `<div class="field"><label>API Key</label><div class="field-hint">確認しています…</div></div>`;
      }
      const need = info.required ? "必須" : "任意";
      const name = `<code>${escapeHtml(info.name)}</code>`;
      let statusHtml;
      if (info.available && !a.keyEditing) {
        statusHtml = `
          <div class="panel-form-row">
            <div class="field-hint">設定済み ${escapeHtml(info.masked || "")}(${need})</div>
            <button type="button" class="btn" id="pf_${kind}_key_change">Change Key</button>
          </div>`;
      } else if (!info.available && !info.required && !a.keyEditing) {
        statusHtml = `
          <div class="panel-form-row">
            <div class="field-hint">未設定(${need})。サーバーがAPIキーを求める場合だけ設定します。</div>
            <button type="button" class="btn" id="pf_${kind}_key_change">Set Key</button>
          </div>`;
      } else {
        const prompt = info.available
          ? "新しいAPIキーを入力してください。"
          : info.required
            ? "APIキーが設定されていません。入力してください。"
            : "APIキーを入力してください。";
        statusHtml = `
          <div class="${info.available || !info.required ? "field-hint" : "field-error"}">${prompt}</div>
          <div class="panel-form-row">
            <input type="password" id="pf_${kind}_key_value" value="${escapeAttr(a.keyInput)}" placeholder="APIキー" autocomplete="off">
            <button type="button" class="btn btn-primary" id="pf_${kind}_key_save" ${a.keySaving ? "disabled" : ""}>
              ${a.keySaving ? "Saving..." : "Save Key"}
            </button>
            ${info.available || !info.required ? `<button type="button" class="btn" id="pf_${kind}_key_cancel">Cancel</button>` : ""}
          </div>`;
      }
      return `
        <div class="field">
          <label>API Key</label>
          ${statusHtml}
          <div class="field-hint">${name}として~/.aidc/secrets.env(リポジトリ・プロジェクトの外)に保存します。名前は提供元と接続先で決まります。</div>
        </div>`;
    }

    modelFieldHtml(kind) {
      const f = this.form[kind];
      const a = this.assist[kind];
      const reload = `<button type="button" class="btn" id="pf_${kind}_models_reload" ${a.modelsState === "loading" ? "disabled" : ""}>Reload</button>`;
      let control;
      let hint;
      if (a.modelsState === "ok" && a.models.length && !a.manualModel) {
        const list = [...a.models];
        if (f.model && !list.includes(f.model)) list.unshift(f.model);
        const options = [
          ...(f.model ? [] : [`<option value="" selected>(選んでください)</option>`]),
          ...list.map(
            (m) =>
              `<option value="${escapeAttr(m)}" ${m === f.model ? "selected" : ""}>${escapeHtml(m)}${a.models.includes(m) ? "" : "(一覧に無い)"}</option>`
          ),
          `<option value="${PREFERENCE_MANUAL_MODEL}">手入力…</option>`,
        ].join("");
        control = `<select id="pf_${kind}_model">${options}</select>`;
        hint = `提供元で使えるモデル(${a.models.length}件)。一覧に無い名前は「手入力…」で入れます。`;
      } else {
        control = `<input type="text" id="pf_${kind}_model" value="${escapeAttr(f.model)}" placeholder="モデル名">`;
        if (a.modelsState === "loading") hint = "モデルの一覧を取得しています…";
        else if (a.modelsState === "error") hint = escapeHtml(a.modelsError); // サーバーが理由の前置きを付ける
        else if (a.manualModel) hint = "モデル名を入力してください。";
        else hint = "接続先とAPIキーが揃うと、使えるモデルを一覧から選べます。";
      }
      return `
        <div class="field">
          <label for="pf_${kind}_model">Model</label>
          <div class="panel-form-row">${control}${reload}</div>
          <div class="${a.modelsState === "error" ? "field-error" : "field-hint"}">${hint}</div>
          <div class="field-error" id="err_pf_${kind}_model"></div>
        </div>`;
    }

    wireSettingFields(body, kind) {
      const f = this.form[kind];
      const a = this.assist[kind];
      const on = (id, event, handler) => {
        const el = body.querySelector(`#pf_${kind}_${id}`);
        if (el) el.addEventListener(event, handler);
      };

      on("client", "change", (ev) => {
        f.client = ev.target.value;
        f.model = "";
        f.api_url = "";
        this.assist[kind] = this.newAssist();
        if (kind in this.testResults) this.testResults[kind] = null;
        this.render();
        if (f.client !== PREFERENCE_NO_CLIENT) this.refreshAssist(kind, { autoFillUrl: true });
      });

      on("api_url", "input", (ev) => {
        f.api_url = ev.target.value;
      });
      // URLを確定したら(候補の選択を含む)、その接続先のAPIキーの状態とモデル一覧を取り直す
      on("api_url", "change", async () => {
        await this.loadKeyInfo(kind);
        this.loadModels(kind);
      });
      on("detect_url", "click", () => this.refreshAssist(kind, { autoFillUrl: true, forceUrl: true }));

      on("key_change", "click", () => {
        a.keyEditing = true;
        this.render();
      });
      on("key_cancel", "click", () => {
        a.keyEditing = false;
        a.keyInput = "";
        this.render();
      });
      on("key_value", "input", (ev) => {
        a.keyInput = ev.target.value;
      });
      on("key_save", "click", () => this.saveApiKey(kind));

      on("model", "change", (ev) => {
        if (ev.target.value === PREFERENCE_MANUAL_MODEL) {
          a.manualModel = true;
          this.render();
          const input = this.querySelector(`#pf_${kind}_model`);
          if (input) input.focus();
          return;
        }
        f.model = ev.target.value;
      });
      on("model", "input", (ev) => {
        if (ev.target.tagName === "INPUT") f.model = ev.target.value;
      });
      on("models_reload", "click", () => {
        a.manualModel = false;
        this.loadModels(kind);
      });
    }

    // Providerを選んだ直後・開いた直後: 接続先の候補を集め(必要なら自動で入れ)、モデル一覧を取る
    async refreshAssist(kind, { autoFillUrl, forceUrl = false }) {
      const f = this.form[kind];
      const client = this.clientInfo(kind, f.client);
      if (!client) return;
      if (client.requires_api_url) {
        const a = this.assist[kind];
        a.urlState = "loading";
        this.render();
        try {
          const result = await apiFetch(`/preferences/api-url-candidates?client=${encodeURIComponent(f.client)}`);
          if (this.form[kind].client !== client.name) return; // 待つ間にProviderが変わった
          a.urlCandidates = result.candidates;
          const reachable = result.candidates.find((c) => c.reachable);
          if (autoFillUrl && reachable && (forceUrl || !f.api_url.trim())) f.api_url = reachable.url;
        } catch (e) {
          showApiError(e);
        }
        a.urlState = "ok";
        this.render();
      }
      await this.loadKeyInfo(kind);
      await this.loadModels(kind);
    }

    // 提供元と接続先で決まるAPIキーの名前・状態を問い合わせる
    async loadKeyInfo(kind) {
      const f = this.form[kind];
      const a = this.assist[kind];
      const client = this.clientInfo(kind, f.client);
      a.keyInfo = null;
      if (!client || (client.requires_api_url && !f.api_url.trim())) {
        this.render();
        return;
      }
      try {
        const params = new URLSearchParams({ client: f.client });
        if (client.requires_api_url) params.set("api_url", f.api_url.trim());
        const info = await apiFetch(`/preferences/api-key?${params}`);
        if (this.form[kind].client === client.name) a.keyInfo = info;
      } catch (e) {
        showApiError(e);
      }
      this.render();
    }

    async loadModels(kind) {
      const f = this.form[kind];
      const a = this.assist[kind];
      const client = this.clientInfo(kind, f.client);
      if (!client) return;
      if (client.requires_api_url && !f.api_url.trim()) {
        a.modelsState = "idle";
        this.render();
        return;
      }
      if (client.api_key_required && !(a.keyInfo && a.keyInfo.available)) {
        // キーが無いと問い合わせられない(キーの入力を促す表示が出ている)
        a.modelsState = "idle";
        this.render();
        return;
      }
      a.modelsState = "loading";
      this.render();
      try {
        const result = await apiFetch("/preferences/models", {
          method: "POST",
          bodyObj: { kind: PREFERENCE_KIND_SPECS[kind].modelKind, setting: { ...this.settingBody(kind), model: "" } },
        });
        if (this.form[kind].client !== client.name) return;
        a.models = result.models;
        a.modelsState = "ok";
        a.manualModel = false;
      } catch (e) {
        a.models = [];
        a.modelsState = "error";
        a.modelsError = e instanceof ApiError ? e.detail : String(e.message || e);
      }
      this.render();
    }

    async saveApiKey(kind) {
      const f = this.form[kind];
      const a = this.assist[kind];
      const client = this.clientInfo(kind, f.client);
      if (!a.keyInput.trim()) {
        showToast("APIキーを入力してください", "error");
        return;
      }
      a.keySaving = true;
      this.render();
      try {
        a.keyInfo = await apiFetch("/preferences/api-key", {
          method: "PUT",
          bodyObj: {
            client: f.client,
            api_url: client && client.requires_api_url ? f.api_url.trim() : null,
            value: a.keyInput,
          },
        });
        a.keyInput = "";
        a.keyEditing = false;
        showToast("APIキーを保存しました", "ok");
      } catch (e) {
        showApiError(e);
      } finally {
        a.keySaving = false;
        this.render();
      }
      if (a.keyInfo && a.keyInfo.available) this.loadModels(kind);
    }

    // 未入力の検査(提供元との整合はサーバー側でも検査する)。問題があればfalse。
    validateForm(body, kinds) {
      let ok = true;
      for (const kind of kinds) {
        const f = this.form[kind];
        const client = this.clientInfo(kind, f.client);
        if (!client) continue;
        fieldError(body, `pf_${kind}_model`, "");
        if (!f.model.trim()) {
          fieldError(body, `pf_${kind}_model`, "選ぶか入力してください");
          ok = false;
        }
        if (client.requires_api_url) {
          fieldError(body, `pf_${kind}_api_url`, "");
          if (!f.api_url.trim()) {
            fieldError(body, `pf_${kind}_api_url`, "入力してください");
            ok = false;
          }
        }
      }
      return ok;
    }

    settingBody(kind) {
      const f = this.form[kind];
      if (f.client === PREFERENCE_NO_CLIENT) return null;
      const client = this.clientInfo(kind, f.client);
      return {
        client: f.client,
        model: f.model.trim(),
        api_url: client && client.requires_api_url ? f.api_url.trim() || null : null,
      };
    }

    connectionTestHtml(kind) {
      if (this.form[kind].client === PREFERENCE_NO_CLIENT) return "";
      const testing = this.testing[kind];
      return `
        <div class="panel-actions">
          <button type="button" class="btn" id="pf_${kind}_test" ${testing ? "disabled" : ""}>
            ${testing ? "Testing..." : "Test Connection"}
          </button>
        </div>
        ${this.testResultHtml(kind)}`;
    }

    testResultHtml(kind) {
      const r = this.testResults[kind];
      if (!r) return "";
      const seconds = `${Number(r.elapsed_seconds).toFixed(1)} 秒`;
      if (r.ok) {
        const detail = PREFERENCE_KIND_SPECS[kind].testKind === "embedding" ? `ベクトルの次元: ${r.dimensions}` : `応答: ${escapeHtml(r.response_text || "")}`;
        return `<p class="field-hint" id="pf_${kind}_test_result">接続できました(${seconds})。${detail}</p>`;
      }
      return `<p class="field-error" id="pf_${kind}_test_result">接続できませんでした(${seconds})。${escapeHtml(r.message)}</p>`;
    }

    // 保存前のフォームの値で、実際に生成(埋め込み)できるかを試す
    async testConnection(kind) {
      const body = this.container;
      const setting = this.settingBody(kind);
      if (!setting) {
        showToast("Providerを選んでください", "error");
        return;
      }
      if (!this.validateForm(body, [kind])) return;
      this.testing[kind] = true;
      this.testResults[kind] = null;
      this.render();
      try {
        const testKind = PREFERENCE_KIND_SPECS[kind].testKind;
        this.testResults[kind] = await apiFetch(`/projects/${this.projectId}/preferences/${testKind}-test`, {
          method: "POST",
          bodyObj: { [testKind]: setting },
        });
      } catch (e) {
        showApiError(e);
      } finally {
        this.testing[kind] = false;
        this.render();
      }
    }

    async save() {
      const body = this.container;
      if (!this.validateForm(body, PREFERENCE_KINDS)) return;
      const saveBtn = body.querySelector("#pf_save");
      saveBtn.disabled = true;
      saveBtn.textContent = "Saving...";
      try {
        const info = await apiFetch(`/projects/${this.projectId}/preferences`, {
          method: "PUT",
          bodyObj: Object.fromEntries(PREFERENCE_KINDS.map((kind) => [kind, this.settingBody(kind)])),
        });
        const assist = this.assist;
        this.setInfo(info);
        this.assist = assist; // 取得済みのモデル一覧・URLの候補はそのまま使う
        showToast("設定を保存しました", "ok");
        this.render();
      } catch (e) {
        showApiError(e);
        saveBtn.disabled = false;
        saveBtn.textContent = "Save";
      }
    }
}
