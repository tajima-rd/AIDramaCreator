"use strict";
/*
 * <dramaturgy-editor-panel> — Edit > Dramaturgy Editor(またはTreeの作品)が開く、作品(Dramaturgy)の
 * タブ切り替え式の編集パネル。QIDMのDomain Editorにならう。
 * apiFetch/state/showToast/showApiError/textField/fieldError/escapeHtml/escapeAttr/EditorDraftをグローバル利用する。
 *
 * 正本を変えるのは下書きの確定だけ(docs/architecture.md 7節)なので、このパネルは人物パネルと共有する編集用の下書き
 * (editor_draft.jsのEditorDraft)を通して編集する。ヘッダーのSave Versionが確定(QIDMのSave Schemaにあたる)。
 *
 * タブ: Properties(題・あらすじ・言語)・Proposal(企画書。作品の初期シードで、題・あらすじ・登場人物は作品と共有しない)・
 * Agents(作品作りに参加するエージェント。役割・性格づけ・厳守事項・禁止事項・タスクの文面を書き換える。足りない職能は
 * タブを開いたときにプロジェクトのユーザー既定から読み込む。Reset to Defaultはユーザー既定に戻し、空にした項目はシステム既定になる。
 * Save as User Default・Restore System Defaultでプロジェクトのユーザー既定を書き換える。Actorは出さない)・
 * Casts(配役。人物ごとの役の重さ(主役・脇役・端役)・演じ方・声の条件と、演者(Actor)の声。声の一覧は音声合成の提供元から取る)・
 * Locations(作品で使う場所(Location)と、場所の間の移動(SiteFlow)。場所の実体はプロジェクトにあり、作品は参照で持つ。
 * Import Mapで地図(KML・KMZ・GeoPackage)を取り込み、Generate Scenesで、シーンの無い場所からシーンを機械的に作る)・Acts(幕の一覧と詳細。追加・削除)・
 * Scenes(すべての幕のシーンの一覧と詳細。追加・削除)。幕・シーンのorderは0から連番で、削除したら残りを詰める。
 *
 * 埋め込み(loadEmbedded): Build with AIの右側で、決まったタブだけを出す(ヘッダー・タブは隠し、編集用の下書きは埋め込む側の
 * EditorDraftを共有する)。下書きを読み直したら"dramaturgy-editor-edited"を出す(埋め込む側がSave Versionの表示を直すため)。
 */

// 役の重さ(core.model.drama.cast.CastBilling)と表示名。空は未設定
const CAST_BILLINGS = [
  ["", "(未設定)"],
  ["lead", "主役"],
  ["supporting", "脇役"],
  ["minor", "端役"],
];
// 声を当てるときの性別(core.model.drama.cast.VoiceGender)
const CAST_VOICE_GENDERS = [
  ["", "(未設定)"],
  ["male", "male"],
  ["female", "female"],
  ["neutral", "neutral"],
];

// 移動(SiteFlow)の向き([値, 表示])。値は線を引いた向き(origin→destination)に対する向き。空は未設定
const SITE_FLOW_DIRECTIONS = [
  ["", "(未設定)"],
  ["forward", "forward(origin→destination)"],
  ["backward", "backward(destination→origin)"],
  ["both", "both(双方向)"],
];

// WKTの形の種類(POLYGON等)。無ければnull
function wktKind(wkt) {
  const m = /^\s*([A-Za-z]+)/.exec(wkt || "");
  return m ? m[1].toUpperCase() : null;
}

// Agentsタブに出す職能([モデル定義YAMLのdramaturgy.agentsの区画名, 職能の名前, 表示名])。並びが一覧の順。
// Actor(演者)は配役ごとに置くので出さない(置き場所は保留。docs/future_design.md)
const AGENT_SECTIONS = [
  ["researchers", "researcher", "Researcher"],
  ["casting_directors", "casting_director", "Casting Director"],
  ["scriptwriters", "scriptwriter", "Scriptwriter"],
  ["directors", "director", "Director"],
  ["stage_managers", "stage_manager", "Stage Manager"],
  ["sound_engineers", "sound_engineer", "Sound Engineer"],
];

// 1行に1つ書いた文(厳守事項・禁止事項)を一覧にする
function linesToList(text) {
  return text
    .split("\n")
    .map((s) => s.trim())
    .filter((s) => s.length > 0);
}

customElements.define(
  "dramaturgy-editor-panel",
  class extends HTMLElement {
    constructor() {
      super();
      this.projectId = null;
      this.dramaturgyId = null;
      this.draft = null; // 編集用の下書き(EditorDraft)
      this.content = null; // 下書きの中身(モデル定義YAMLの対応表。人物の名前を引くため)
      this.dramaturgy = null; // 下書きの中の作品(DramaturgySpecの対応表。削除済みならnull)
      this.selectedAgentId = null;
      this.activeTab = "properties";
      this.selectedActId = null;
      this.selectedLocationId = null;
      this.selectedSceneId = null;
      this.selectedCastId = null;
      this.embedded = false; // 他のパネルに埋め込んで、決まったタブだけを出す
      this.voiceLists = {}; // 言語→声の一覧の取得結果(VoiceListResult。失敗なら{error})
    }

    connectedCallback() {
      this.innerHTML = `
        <div class="panel-header" id="de-header"></div>
        <div class="panel-tabs" id="de-tabs"></div>
        <div class="panel-body" id="de-body"><p class="placeholder">読み込んでいます…</p></div>
      `;
    }

    async load(projectId, dramaturgyId) {
      this.projectId = projectId;
      this.dramaturgyId = dramaturgyId;
      this.activeTab = "properties";
      this.selectedActId = null;
      this.selectedAgentId = null;
      this.selectedLocationId = null;
      this.selectedSceneId = null;
      this.agentDefaultsFailed = false;
      this.draft = new EditorDraft(projectId);
      try {
        if (!(await this.draft.ensure())) {
          this.dispatchEvent(new CustomEvent("dramaturgy-editor-closed", { bubbles: true }));
          return;
        }
        await this.reloadContent();
      } catch (e) {
        showApiError(e);
      }
    }

    // Build with AIの右側に、決まったタブ(tab)だけを出す。編集用の下書き(draft)は埋め込む側と共有する
    async loadEmbedded(projectId, dramaturgyId, draft, tab) {
      this.embedded = true;
      this.projectId = projectId;
      this.dramaturgyId = dramaturgyId;
      this.draft = draft;
      this.activeTab = tab;
      try {
        await this.reloadContent();
      } catch (e) {
        showApiError(e);
      }
    }

    async reloadContent() {
      const content = await this.draft.content();
      this.content = content;
      this.dramaturgy = (content.dramaturgies || []).find((d) => d.id === this.dramaturgyId) || null;
      if (this.dramaturgy && this.selectedActId && !this.acts().some((a) => a.id === this.selectedActId)) {
        this.selectedActId = null;
      }
      this.render();
      if (this.embedded) this.dispatchEvent(new CustomEvent("dramaturgy-editor-edited", { bubbles: true }));
    }

    acts() {
      return [...((this.dramaturgy && this.dramaturgy.acts) || [])].sort((a, b) => (a.order ?? 0) - (b.order ?? 0));
    }

    // 部分YAML(この作品の中の変えたい部分)を下書きに重ねて、読み直す。
    async editDramaturgy(patch) {
      await this.draft.edit({ dramaturgies: [{ id: this.dramaturgyId, ...patch }] });
      await this.reloadContent();
    }

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

    render() {
      this.querySelector("#de-header").hidden = this.embedded;
      this.querySelector("#de-tabs").hidden = this.embedded;
      if (!this.embedded) {
        this.renderHeader();
        this.renderTabs();
      }
      this.renderBody();
    }

    // Save Versionは、どのタブで変更しても押し忘れないよう、タブに関係なく常に見えるヘッダーに置く。
    // 変更が無ければグレー、確定していない変更があれば緑。
    renderHeader() {
      const header = this.querySelector("#de-header");
      const title = this.dramaturgy ? this.dramaturgy.title : "(削除済み)";
      header.innerHTML = `
        <div class="panel-header-row">
          <span class="panel-header-title">Dramaturgy Editor — ${escapeHtml(title)}</span>
          <div class="panel-header-actions">
            <span class="panel-header-version">${escapeHtml(this.draft.versionLabel())}</span>
            <button type="button" class="${this.draft.versionButtonClass()}" id="de_save_version">Save Version</button>
          </div>
        </div>
      `;
      header.querySelector("#de_save_version").addEventListener("click", (ev) =>
        this.withButtonBusy(ev.currentTarget, "Saving...", () => this.saveVersion())
      );
    }

    async saveVersion() {
      try {
        const version = await this.draft.confirm();
        if (version === null) {
          showToast(`確定する変更はありません(${this.draft.versionLabel()}のまま)`, "info");
          return;
        }
        showToast(`版 v${version} として確定しました`, "ok");
        this.dispatchEvent(new CustomEvent("dramaturgy-editor-saved", { bubbles: true }));
        await this.reloadContent();
        // 削除を確定した作品は正本からも消えたので、パネルを閉じる
        if (!this.dramaturgy) this.dispatchEvent(new CustomEvent("dramaturgy-editor-closed", { bubbles: true }));
      } catch (e) {
        showApiError(e);
      }
    }

    renderTabs() {
      const tabs = this.querySelector("#de-tabs");
      tabs.innerHTML = "";
      if (!this.dramaturgy) return;
      const defs = [
        ["properties", "Properties"],
        ["proposal", "Proposal"],
        ["agents", "Agents"],
        ["casts", "Casts"],
        ["locations", "Locations"],
        ["acts", "Acts"],
        ["scenes", "Scenes"],
      ];
      for (const [key, label] of defs) {
        const btn = document.createElement("button");
        btn.className = "panel-tab" + (this.activeTab === key ? " active" : "");
        btn.textContent = label;
        btn.addEventListener("click", () => {
          this.activeTab = key;
          this.render();
        });
        tabs.appendChild(btn);
      }
    }

    renderBody() {
      const body = this.querySelector("#de-body");
      if (!this.dramaturgy) {
        body.innerHTML = `<p class="placeholder">この作品は下書きで削除されています。Save Versionで確定すると、正本からも消えます。</p>`;
        return;
      }
      if (this.activeTab === "properties") this.renderPropertiesTab(body);
      else if (this.activeTab === "proposal") this.renderProposalTab(body);
      else if (this.activeTab === "agents") this.renderAgentsTab(body);
      else if (this.activeTab === "casts") this.renderCastsTab(body);
      else if (this.activeTab === "locations") this.renderLocationsTab(body);
      else if (this.activeTab === "acts") this.renderActsTab(body);
      else if (this.activeTab === "scenes") this.renderScenesTab(body);
    }

    // -------------------------------------------------------------------
    // Properties
    // -------------------------------------------------------------------

    renderPropertiesTab(body) {
      const d = this.dramaturgy;
      body.innerHTML = `
        <div class="panel-form">
          <div class="panel-readonly-id">ID: ${escapeHtml(d.id)}</div>
          ${textField("dp_title", "Title", d.title || "")}
          <div class="field">
            <label for="dp_synopsis">Synopsis</label>
            <textarea id="dp_synopsis">${escapeHtml(d.synopsis || "")}</textarea>
            <div class="field-hint">作品全体のあらすじ(メタメタストーリー)。</div>
          </div>
          <div class="panel-form-row">
            ${textField("dp_input_language", "Input Language", d.input_language || "", "制作に使う言語のコード(例: ja)")}
            ${textField("dp_output_language", "Output Language", d.output_language || "", "音声にする言語のコード(例: ja・zh)")}
          </div>
          <div class="panel-actions">
            <button type="button" class="btn btn-primary" id="dp_save">Save</button>
            <button type="button" class="btn btn-danger" id="dp_delete">Delete Dramaturgy</button>
          </div>
        </div>
      `;
      body.querySelector("#dp_save").addEventListener("click", (ev) =>
        this.withButtonBusy(ev.currentTarget, "Saving...", () => this.saveProperties())
      );
      body.querySelector("#dp_delete").addEventListener("click", () => this.deleteDramaturgy());
    }

    async saveProperties() {
      const body = this.querySelector("#de-body");
      const title = body.querySelector("#dp_title").value.trim();
      fieldError(body, "dp_title", "");
      if (!title) {
        fieldError(body, "dp_title", "入力してください");
        return;
      }
      const value = (id) => body.querySelector(`#${id}`).value.trim() || null; // nullはその属性を消す
      try {
        await this.editDramaturgy({
          title,
          synopsis: value("dp_synopsis"),
          input_language: value("dp_input_language"),
          output_language: value("dp_output_language"),
        });
        showToast("下書きに保存しました(Save Versionで確定)", "ok");
      } catch (e) {
        showApiError(e);
      }
    }

    async deleteDramaturgy() {
      if (!confirm(`作品「${this.dramaturgy.title}」を削除します。幕・シーン・配役も削除されます。よろしいですか?(Save Versionで確定するまでは正本に残ります)`)) {
        return;
      }
      try {
        await this.editDramaturgy({ delete: true });
        showToast("下書きから削除しました(Save Versionで確定)", "ok");
      } catch (e) {
        showApiError(e);
      }
    }

    // -------------------------------------------------------------------
    // Proposal(企画書)
    // -------------------------------------------------------------------

    renderProposalTab(body) {
      new ProposalForm(body, {
        withImport: true,
        onSave: async (values) => {
          try {
            await this.editDramaturgy({ proposal: values });
            showToast("下書きに保存しました(Save Versionで確定)", "ok");
          } catch (e) {
            showApiError(e);
          }
        },
      }).render(this.dramaturgy.proposal);
    }

    // -------------------------------------------------------------------
    // Agents
    // -------------------------------------------------------------------

    // 作品のエージェント(Agentsタブに出す職能だけ)を、職能の順に平らな一覧にする({section, roleName, label, agent})
    agentEntries() {
      const groups = (this.dramaturgy && this.dramaturgy.agents) || {};
      return AGENT_SECTIONS.flatMap(([section, roleName, label]) =>
        (groups[section] || []).map((agent) => ({ section, roleName, label, agent }))
      );
    }

    // プロジェクトのユーザー既定(職能の名前→エージェント)
    async fetchAgentDefaults() {
      const result = await apiFetch(`/projects/${this.projectId}/agent-defaults`);
      return result.defaults || {};
    }

    renderAgentsTab(body) {
      const groups = (this.dramaturgy && this.dramaturgy.agents) || {};
      const missing = AGENT_SECTIONS.filter(([section]) => !(groups[section] || []).length);
      if (missing.length && !this.agentDefaultsFailed) {
        body.innerHTML = `<p class="placeholder">足りない職能のエージェントを、プロジェクトの既定から読み込んでいます…</p>`;
        this.loadMissingAgents(missing);
        return;
      }
      body.innerHTML = `
        <div class="panel-master-detail">
          <div class="panel-master" id="de-agent-master"></div>
          <div class="panel-detail" id="de-agent-detail"></div>
        </div>
      `;
      const master = body.querySelector("#de-agent-master");
      const entries = this.agentEntries();
      if (entries.length === 0) master.innerHTML = `<div class="panel-master-empty">(No Agents)</div>`;
      for (const { label, agent } of entries) {
        const item = document.createElement("div");
        item.className = "panel-master-item" + (agent.id === this.selectedAgentId ? " selected" : "");
        item.innerHTML = `<div class="item-alias">${escapeHtml(agent.name)}</div><div class="item-name">${escapeHtml(label)}</div>`;
        item.addEventListener("click", () => {
          this.selectedAgentId = agent.id;
          this.renderBody();
        });
        master.appendChild(item);
      }
      this.renderAgentDetail(body.querySelector("#de-agent-detail"));
    }

    // 作品に無い職能のエージェントを、プロジェクトのユーザー既定から下書きに読み込む(Agentsタブを開いたとき。
    // 未確定の変更になる)。失敗したら、作品を読み直すまで繰り返さない。
    async loadMissingAgents(missing) {
      if (this.loadingAgentDefaults) return;
      this.loadingAgentDefaults = true;
      try {
        const defaults = await this.fetchAgentDefaults();
        const agents = {};
        for (const [section, roleName] of missing) agents[section] = [defaults[roleName]];
        await this.editDramaturgy({ agents });
        showToast("足りない職能のエージェントを、プロジェクトの既定から読み込みました(Save Versionで確定)", "info");
      } catch (e) {
        this.agentDefaultsFailed = true;
        showApiError(e);
        this.renderBody();
      } finally {
        this.loadingAgentDefaults = false;
      }
    }

    renderAgentDetail(detail) {
      const entry = this.agentEntries().find((e) => e.agent.id === this.selectedAgentId);
      if (!entry) {
        detail.innerHTML = `<p class="placeholder">左の一覧からエージェントを選択してください。</p>`;
        return;
      }
      const { section, roleName, label, agent } = entry;
      const linesArea = (id, title, items, hint) => `
        <div class="field">
          <label for="${id}">${title}</label>
          <textarea id="${id}" class="prose">${escapeHtml((items || []).join("\n"))}</textarea>
          <div class="field-hint">${hint}</div>
        </div>`;
      const taskHtml = (agent.tasks || [])
        .map(
          (t, i) => `
        <div class="agent-task" data-code="${escapeAttr(t.code)}">
          <div class="panel-subsection-title">${escapeHtml(t.title || t.code)} <span class="panel-readonly-id">${escapeHtml(t.code)}</span></div>
          ${textField(`at_title_${i}`, "Title", t.title || "")}
          <div class="field">
            <label for="at_description_${i}">Description</label>
            <textarea id="at_description_${i}" class="prose">${escapeHtml(t.description || "")}</textarea>
          </div>
          <div class="panel-form-row">
            ${linesArea(`at_rules_${i}`, "Rules", t.rules, "このタスクで守ること(1行に1つ)")}
            ${linesArea(`at_prohibitions_${i}`, "Prohibitions", t.prohibitions, "このタスクでしてはいけないこと(1行に1つ)")}
          </div>
        </div>`
        )
        .join("");
      detail.innerHTML = `
        <div class="panel-section-title">${escapeHtml(agent.name)} <span class="dataset-badge">${escapeHtml(label)}</span></div>
        <div class="panel-form panel-form--wide">
          <div class="panel-readonly-id">ID: ${escapeHtml(agent.id)}</div>
          <div class="field-hint">生成AIとの対話を始める前に渡す情報です(プロンプトはここから組み立てます)。役割・厳守事項・禁止事項・タスクの文面を空にすると、システム既定になります。</div>
          ${textField("ag_name", "Name", agent.name || "")}
          <div class="field">
            <label for="ag_role">Role</label>
            <textarea id="ag_role" class="prose">${escapeHtml(agent.role || "")}</textarea>
            <div class="field-hint">役割の説明</div>
          </div>
          <div class="field">
            <label for="ag_persona">Persona</label>
            <textarea id="ag_persona" class="prose">${escapeHtml(agent.persona || "")}</textarea>
            <div class="field-hint">性格づけ(任意)</div>
          </div>
          ${linesArea("ag_rules", "Rules", agent.rules, "どのタスクでも守ること(1行に1つ)")}
          ${linesArea("ag_prohibitions", "Prohibitions", agent.prohibitions, "どのタスクでもしてはいけないこと(1行に1つ)")}
          <div class="panel-section-title">Tasks</div>
          ${taskHtml || `<p class="field-hint">(タスクはありません)</p>`}
          <div class="panel-actions">
            <button type="button" class="btn btn-primary" id="ag_save">Save</button>
            <button type="button" class="btn" id="ag_reset">Reset to Default</button>
            <button type="button" class="btn" id="ag_save_default">Save as User Default</button>
            <button type="button" class="btn" id="ag_restore_system">Restore System Default</button>
          </div>
          <div class="field-hint">Reset to Default: この作品のエージェントを、プロジェクトの既定(ユーザー既定)に戻します。Save as User Default: 今の入力を、このプロジェクトの${escapeHtml(label)}の既定にします(以後の新しい作品とReset to Defaultで使います)。Restore System Default: このプロジェクトの${escapeHtml(label)}の既定を、システム既定に戻します(作品のエージェントは変えません)。</div>
        </div>
      `;
      detail.querySelector("#ag_save").addEventListener("click", (ev) =>
        this.withButtonBusy(ev.currentTarget, "Saving...", () => this.saveAgent(section, agent))
      );
      detail.querySelector("#ag_reset").addEventListener("click", () => this.resetAgent(section, roleName, agent));
      detail.querySelector("#ag_save_default").addEventListener("click", (ev) =>
        this.withButtonBusy(ev.currentTarget, "Saving...", () => this.saveAsUserDefault(roleName, label))
      );
      detail.querySelector("#ag_restore_system").addEventListener("click", () => this.restoreSystemDefault(roleName, label));
    }

    // 入力からエージェントの内容を読む。空にした項目はnull(=システム既定)。タスクは書いた項目だけを持つ。名前が空ならnull
    readAgentForm() {
      const detail = this.querySelector("#de-agent-detail");
      const value = (id) => detail.querySelector(`#${id}`).value.trim();
      const name = value("ag_name");
      fieldError(detail, "ag_name", "");
      if (!name) {
        fieldError(detail, "ag_name", "入力してください");
        return null;
      }
      const linesOrNull = (id) => {
        const items = linesToList(detail.querySelector(`#${id}`).value);
        return items.length ? items : null;
      };
      const tasks = [...detail.querySelectorAll(".agent-task")].map((el, i) => {
        const task = { code: el.dataset.code };
        const title = value(`at_title_${i}`);
        const description = value(`at_description_${i}`);
        const rules = linesToList(detail.querySelector(`#at_rules_${i}`).value);
        const prohibitions = linesToList(detail.querySelector(`#at_prohibitions_${i}`).value);
        if (title) task.title = title;
        if (description) task.description = description;
        if (rules.length) task.rules = rules;
        if (prohibitions.length) task.prohibitions = prohibitions;
        return task;
      });
      return {
        name,
        role: value("ag_role") || null,
        persona: value("ag_persona") || null,
        rules: linesOrNull("ag_rules"),
        prohibitions: linesOrNull("ag_prohibitions"),
        tasks,
      };
    }

    async saveAgent(section, agent) {
      const form = this.readAgentForm();
      if (!form) return;
      try {
        await this.editDramaturgy({ agents: { [section]: [{ id: agent.id, ...form }] } });
        showToast("下書きに保存しました(Save Versionで確定)", "ok");
      } catch (e) {
        showApiError(e);
      }
    }

    // この作品のエージェントを、プロジェクトのユーザー既定の内容(名前・性格づけも含めて)で置き換える
    async resetAgent(section, roleName, agent) {
      if (!confirm(`「${agent.name}」を、このプロジェクトの既定に戻します(名前・性格づけも含めて置き換わります)。よろしいですか?`)) {
        return;
      }
      try {
        const spec = (await this.fetchAgentDefaults())[roleName];
        const patch = {
          id: agent.id,
          name: spec.name,
          role: spec.role ?? null,
          persona: spec.persona ?? null,
          rules: spec.rules ?? null,
          prohibitions: spec.prohibitions ?? null,
          tasks: spec.tasks ?? null,
        };
        await this.editDramaturgy({ agents: { [section]: [patch] } });
        showToast("既定に戻しました(Save Versionで確定)", "ok");
      } catch (e) {
        showApiError(e);
      }
    }

    async saveAsUserDefault(roleName, label) {
      const form = this.readAgentForm();
      if (!form) return;
      if (!confirm(`今の入力を、このプロジェクトの${label}の既定にします。よろしいですか?`)) return;
      // 空にした項目(null)は送らない(=システム既定で補う)
      const spec = Object.fromEntries(Object.entries(form).filter(([, v]) => v !== null));
      try {
        await apiFetch(`/projects/${this.projectId}/agent-defaults/${roleName}`, { method: "PUT", bodyObj: spec });
        showToast(`${label}の既定(ユーザー既定)を保存しました`, "ok");
      } catch (e) {
        showApiError(e);
      }
    }

    async restoreSystemDefault(roleName, label) {
      if (!confirm(`このプロジェクトの${label}の既定を、システム既定に戻します。作品のエージェントは変わりません。よろしいですか?`)) return;
      try {
        await apiFetch(`/projects/${this.projectId}/agent-defaults/${roleName}/restore`, { method: "POST" });
        showToast(`${label}の既定をシステム既定に戻しました(作品のエージェントに反映するにはReset to Default)`, "ok");
      } catch (e) {
        showApiError(e);
      }
    }

    // -------------------------------------------------------------------
    // Casts(配役と演者の声)
    // -------------------------------------------------------------------

    characterName(key) {
      const character = (this.content.characters || []).find((c) => c.key === key);
      return character ? character.name : key;
    }

    // 配役を演じる演者(Actor。いなければnull)
    actorOf(cast) {
      const actors = ((this.dramaturgy.agents || {}).actors || []);
      return actors.find((a) => a.cast && a.cast.ref === cast.key) || null;
    }

    // 配役の声を選ぶ言語(配役の言語、無ければ作品の言語)
    castLanguage(cast) {
      return cast.language || this.dramaturgy.output_language || this.dramaturgy.input_language || "";
    }

    // 言語の声の一覧(一度取ったものは覚えておく。失敗なら{error})
    async voiceList(language) {
      if (!this.voiceLists[language]) {
        const query = language ? `?language=${encodeURIComponent(language)}` : "";
        this.voiceLists[language] = apiFetch(`/projects/${this.projectId}/voices${query}`).catch((e) => ({
          error: e && e.message ? e.message : String(e),
        }));
      }
      return this.voiceLists[language];
    }

    renderCastsTab(body) {
      body.innerHTML = `
        <div class="panel-master-detail">
          <div class="panel-master" id="de-cast-master"></div>
          <div class="panel-detail" id="de-cast-detail"></div>
        </div>
      `;
      const master = body.querySelector("#de-cast-master");
      const casts = this.dramaturgy.casts || [];
      if (casts.length === 0) master.innerHTML = `<div class="panel-master-empty">(No Casts)</div>`;
      const billingLabel = Object.fromEntries(CAST_BILLINGS);
      for (const cast of casts) {
        const actor = this.actorOf(cast);
        const item = document.createElement("div");
        item.className = "panel-master-item" + (cast.id === this.selectedCastId ? " selected" : "");
        const facts = [cast.billing ? billingLabel[cast.billing] : null, actor && actor.voice_name ? `声: ${actor.voice_name}` : "声: 未定"];
        item.innerHTML =
          `<div class="item-alias">${escapeHtml(this.characterName(cast.character.ref))}</div>` +
          `<div class="item-name">${escapeHtml(facts.filter(Boolean).join(" · "))}</div>`;
        item.addEventListener("click", () => {
          this.selectedCastId = cast.id;
          this.renderBody();
        });
        master.appendChild(item);
      }
      // 配役の無い登場人物から、配役を足す
      const castKeys = new Set(casts.map((c) => c.character.ref));
      const candidates = (this.dramaturgy.characters || []).map((r) => r.ref).filter((key) => !castKeys.has(key));
      const add = document.createElement("div");
      add.className = "panel-master-add-row";
      add.innerHTML = candidates.length
        ? `<select id="dc_add_character">${candidates
            .map((key) => `<option value="${escapeAttr(key)}">${escapeHtml(this.characterName(key))}</option>`)
            .join("")}</select><button type="button" class="panel-master-add" id="dc_add">+ Add Cast</button>`
        : `<div class="field-hint">登場人物はすべて配役済みです(人物はCharacter EditorかBuild with AIのCharactersで加えます)。</div>`;
      master.appendChild(add);
      const addButton = add.querySelector("#dc_add");
      if (addButton) addButton.addEventListener("click", () => this.addCast(add.querySelector("#dc_add_character").value));
      this.renderCastDetail(body.querySelector("#de-cast-detail"));
    }

    renderCastDetail(detail) {
      const cast = (this.dramaturgy.casts || []).find((c) => c.id === this.selectedCastId);
      if (!cast) {
        detail.innerHTML = `<p class="placeholder">左の一覧から配役を選択するか、配役の無い人物を選んで「+ Add Cast」で追加してください。</p>`;
        return;
      }
      const performance = cast.performance || {};
      const options = (pairs, current) =>
        pairs.map(([value, label]) => `<option value="${value}" ${(current || "") === value ? "selected" : ""}>${escapeHtml(label)}</option>`).join("");
      const name = this.characterName(cast.character.ref);
      detail.innerHTML = `
        <div class="panel-section-title">${escapeHtml(name)}</div>
        <div class="panel-form panel-form--wide">
          <div class="panel-readonly-id">ID: ${escapeHtml(cast.id)}</div>
          <div class="panel-form-row">
            <div class="field"><label for="dc_billing">Billing</label><select id="dc_billing">${options(CAST_BILLINGS, cast.billing)}</select>
              <div class="field-hint">役の重さ(主役・脇役・端役)</div></div>
            <div class="field"><label for="dc_voice_gender">Voice Gender</label><select id="dc_voice_gender">${options(CAST_VOICE_GENDERS, cast.voice_gender)}</select>
              <div class="field-hint">声を当てるときの性別(人物の性別とは別)</div></div>
          </div>
          ${textField("dc_performance_title", "Performance Title", performance.title || "", "演じ方の短い見出し")}
          <div class="field">
            <label for="dc_performance_description">Performance Description</label>
            <textarea id="dc_performance_description" class="prose">${escapeHtml(performance.description || "")}</textarea>
            <div class="field-hint">演じ方の説明(声の印象・話しぶり・感情の出し方)。声を選ぶ条件になります。</div>
          </div>
          <div class="panel-form-row">
            ${textField("dc_pace", "Pace", performance.pace || "", "話す速さ")}
            ${textField("dc_language", "Language", cast.language || "", "話す言語のコード(空なら作品の言語)")}
            ${textField("dc_accent", "Accent", cast.accent || "", "訛り・話しぶり")}
          </div>
          <div class="panel-actions">
            <button type="button" class="btn btn-primary" id="dc_save">Save</button>
            <button type="button" class="btn btn-danger" id="dc_delete">Delete Cast</button>
          </div>
          <div class="panel-section-title">Actor(演者の声)</div>
          <div id="dc_voice"><p class="field-hint">声の一覧を読み込んでいます…</p></div>
        </div>
      `;
      detail.querySelector("#dc_save").addEventListener("click", (ev) =>
        this.withButtonBusy(ev.currentTarget, "Saving...", () => this.saveCast(cast))
      );
      detail.querySelector("#dc_delete").addEventListener("click", () => this.deleteCast(cast));
      this.renderVoiceSection(detail.querySelector("#dc_voice"), cast);
    }

    // 演者の声: 音声合成の提供元の声の一覧(配役の言語)から選ぶ。一覧が取れなければ、声の識別子を直接入れる
    async renderVoiceSection(box, cast) {
      const language = this.castLanguage(cast);
      const result = await this.voiceList(language);
      if (!box.isConnected) return;
      const actor = this.actorOf(cast);
      const current = actor ? actor.voice_name || "" : "";
      const voices = result.voices || [];
      const voiceLabel = (v) => `${v.voice_id}(${[v.gender, v.pitch, v.accent].filter(Boolean).join(" · ")})`;
      const known = voices.some((v) => v.voice_id === current);
      const selector = result.error
        ? `${textField("dc_voice_name", "Voice", current, "声の識別子")}<div class="field-hint">声の一覧を取得できません: ${escapeHtml(result.error)}</div>`
        : `<div class="field"><label for="dc_voice_name">Voice</label><select id="dc_voice_name">
            <option value="">(なし)</option>
            ${!known && current ? `<option value="${escapeAttr(current)}" selected>${escapeHtml(current)}(一覧に無い声)</option>` : ""}
            ${voices.map((v) => `<option value="${escapeAttr(v.voice_id)}" ${v.voice_id === current ? "selected" : ""}>${escapeHtml(voiceLabel(v))}</option>`).join("")}
          </select>
          <div class="field-hint">${escapeHtml(result.provider)} · ${escapeHtml(result.model)} の声(言語: ${escapeHtml(language || "すべて")}、${voices.length}件)</div></div>
          <div class="field-hint" id="dc_voice_description"></div>`;
      box.innerHTML = `
        ${selector}
        <div class="panel-readonly-id">${actor ? `演者: ${escapeHtml(actor.name)}${actor.tts_provider ? ` · ${escapeHtml(actor.tts_provider)} · ${escapeHtml(actor.tts_model || "")}` : ""}` : "演者はまだいません(声を保存すると作ります)"}</div>
        <div class="panel-actions"><button type="button" class="btn" id="dc_save_voice">Save Voice</button></div>
      `;
      const input = box.querySelector("#dc_voice_name");
      const describe = () => {
        const target = box.querySelector("#dc_voice_description");
        const voice = voices.find((v) => v.voice_id === input.value);
        if (target) target.textContent = voice ? [voice.persona, voice.description].filter(Boolean).join(" — ") : "";
      };
      input.addEventListener("change", describe);
      describe();
      box.querySelector("#dc_save_voice").addEventListener("click", (ev) =>
        this.withButtonBusy(ev.currentTarget, "Saving...", () =>
          this.saveVoice(cast, input.value.trim(), result.error ? null : result)
        )
      );
    }

    async addCast(characterKey) {
      if (!characterKey) return;
      try {
        await this.editDramaturgy({ casts: [{ character: { ref: characterKey } }] });
        const added = (this.dramaturgy.casts || []).find((c) => c.character.ref === characterKey);
        this.selectedCastId = added ? added.id : null;
        this.renderBody();
        showToast(`${this.characterName(characterKey)}の配役を追加しました(Save Versionで確定)`, "ok");
      } catch (e) {
        showApiError(e);
      }
    }

    async saveCast(cast) {
      const detail = this.querySelector("#de-cast-detail");
      const value = (id) => detail.querySelector(`#${id}`).value.trim() || null; // nullはその属性を消す
      try {
        await this.editDramaturgy({
          casts: [
            {
              id: cast.id,
              billing: value("dc_billing"),
              voice_gender: value("dc_voice_gender"),
              performance: {
                title: value("dc_performance_title"),
                description: value("dc_performance_description"),
                pace: value("dc_pace"),
              },
              language: value("dc_language"),
              accent: value("dc_accent"),
            },
          ],
        });
        showToast("下書きに保存しました(Save Versionで確定)", "ok");
      } catch (e) {
        showApiError(e);
      }
    }

    // 演者の声を保存する(演者がいなければ作る)。提供元・モデルは、声の一覧を取った音声合成の設定
    async saveVoice(cast, voiceName, list) {
      const actor = this.actorOf(cast);
      const fields = {
        voice_name: voiceName || null,
        ...(list ? { tts_provider: list.provider, tts_model: list.model } : {}),
      };
      const patch = actor
        ? { id: actor.id, ...fields }
        : { name: `${this.characterName(cast.character.ref)}役の演者`, cast: { ref: cast.key }, ...fields };
      try {
        await this.editDramaturgy({ agents: { actors: [patch] } });
        showToast("下書きに保存しました(Save Versionで確定)", "ok");
      } catch (e) {
        showApiError(e);
      }
    }

    // 配役と、その演者を消す(台詞が配役を使っていれば、参照切れとして断られる)
    async deleteCast(cast) {
      const name = this.characterName(cast.character.ref);
      if (!confirm(`${name}の配役と演者を削除します。よろしいですか?(台詞がこの配役を使っていると削除できません)`)) return;
      const actor = this.actorOf(cast);
      try {
        await this.editDramaturgy({
          casts: [{ id: cast.id, delete: true }],
          ...(actor ? { agents: { actors: [{ id: actor.id, delete: true }] } } : {}),
        });
        this.selectedCastId = null;
        this.renderBody();
        showToast(`${name}の配役を削除しました(Save Versionで確定)`, "ok");
      } catch (e) {
        showApiError(e);
      }
    }

    // -------------------------------------------------------------------
    // Locations(場所と移動)
    // -------------------------------------------------------------------

    // 作品が参照する場所・移動(下書きの中身の最上位の一覧から、参照のkeyで引く)
    dramaturgyLocations() {
      const byKey = new Map((this.content.locations || []).map((l) => [l.key, l]));
      return (this.dramaturgy.locations || []).map((r) => byKey.get(r.ref)).filter(Boolean);
    }

    dramaturgySiteFlows() {
      const byKey = new Map((this.content.site_flows || []).map((f) => [f.key, f]));
      return (this.dramaturgy.site_flows || []).map((r) => byKey.get(r.ref)).filter(Boolean);
    }

    // すべての幕のシーンを、幕・シーンの順に({act, scene})
    sceneEntries() {
      return this.acts().flatMap((act) =>
        [...(act.scenes || [])].sort((a, b) => (a.order ?? 0) - (b.order ?? 0)).map((scene) => ({ act, scene }))
      );
    }

    // この作品のシーンが使っている場所のkey
    usedLocationKeys() {
      return new Set(this.sceneEntries().map(({ scene }) => scene.location && scene.location.ref).filter(Boolean));
    }

    // 作品の場所を、移動(SiteFlow)を辿った順に並べる。移動の向き(direction)に従い(未設定はforward)、入ってくる移動が無く
    // 出ていく移動がある場所から深さ優先で辿る(分岐は移動の並びの順)。辿れなかった場所(環の中だけにあるもの)はそこから
    // 辿り直し、どの移動にもつながらない場所は末尾に置く(どちらも場所の並びの順)。
    siteFlowOrder() {
      const locations = this.dramaturgyLocations();
      const keys = new Set(locations.map((l) => l.key));
      const next = new Map(locations.map((l) => [l.key, []]));
      const incoming = new Set();
      const link = (from, to) => {
        if (!keys.has(from) || !keys.has(to)) return;
        next.get(from).push(to);
        incoming.add(to);
      };
      for (const flow of this.dramaturgySiteFlows()) {
        const origin = flow.origin.ref;
        const destination = flow.destination.ref;
        if (flow.direction === "backward") link(destination, origin);
        else if (flow.direction === "both") {
          link(origin, destination);
          link(destination, origin);
        } else link(origin, destination);
      }
      const ordered = [];
      const visited = new Set();
      const visit = (key) => {
        if (visited.has(key)) return;
        visited.add(key);
        ordered.push(key);
        for (const to of next.get(key)) visit(to);
      };
      const linked = (key) => incoming.has(key) || next.get(key).length > 0;
      for (const l of locations) if (!incoming.has(l.key) && linked(l.key)) visit(l.key);
      for (const l of locations) if (linked(l.key)) visit(l.key);
      for (const l of locations) visit(l.key);
      const byKey = new Map(locations.map((l) => [l.key, l]));
      return ordered.map((key) => byKey.get(key));
    }

    renderLocationsTab(body) {
      const acts = this.acts();
      const actOptions = acts
        .map((a) => `<option value="${escapeAttr(a.id)}">Act ${(a.order ?? 0) + 1}${a.title ? ` ${escapeHtml(a.title)}` : ""}</option>`)
        .join("");
      body.innerHTML = `
        <div class="panel-form-row">
          <div class="field">
            <label>Import Map</label>
            <div class="panel-form-row">
              <input type="file" id="dl_map_file" accept=".kml,.kmz,.gpkg,.xml" hidden>
              <button type="button" class="btn" id="dl_import">Import KML / GeoPackage...</button>
            </div>
            <div class="field-hint">LocationとSiteFlowのフォルダ(層)を取り込み、この作品の場所・移動をファイルの内容で置き換えます。それ以外のフォルダ(層)は補助情報として、この作品のDatasetに保存します。</div>
          </div>
          <div class="field">
            <label for="dl_act">Generate Scenes</label>
            <div class="panel-form-row">
              ${acts.length ? `<select id="dl_act" style="flex: 0 0 240px">${actOptions}</select>` : ""}
              <button type="button" class="btn btn-primary" id="dl_generate" ${acts.length ? "" : "disabled"}>Generate Scenes</button>
            </div>
            <div class="field-hint">${
              acts.length
                ? "シーンの無い場所から、選んだ幕にシーンを1つずつ作ります(題=場所の名前、場所=その場所。生成AIは使いません)。並びは移動(SiteFlow)を辿った順です。"
                : "先にActsタブで幕を追加してください。"
            }</div>
          </div>
        </div>
        <div class="panel-master-detail panel-master-detail--fill">
          <div class="panel-master" id="de-location-master"></div>
          <div class="panel-detail" id="de-location-detail"></div>
        </div>
      `;
      const fileInput = body.querySelector("#dl_map_file");
      body.querySelector("#dl_import").addEventListener("click", () => fileInput.click());
      fileInput.addEventListener("change", () => {
        const file = fileInput.files[0];
        fileInput.value = "";
        if (file) this.withButtonBusy(body.querySelector("#dl_import"), "Importing...", () => this.importMap(file));
      });
      if (acts.length) {
        body.querySelector("#dl_generate").addEventListener("click", (ev) =>
          this.withButtonBusy(ev.currentTarget, "Generating...", () => this.generateScenes(body.querySelector("#dl_act").value))
        );
      }
      const master = body.querySelector("#de-location-master");
      const locations = this.dramaturgyLocations();
      const used = this.usedLocationKeys();
      if (locations.length === 0) {
        master.innerHTML = `<div class="panel-master-empty">(No Locations)</div>`;
      }
      for (const location of locations) {
        const item = document.createElement("div");
        item.className = "panel-master-item" + (location.id === this.selectedLocationId ? " selected" : "");
        item.innerHTML =
          `<div class="item-alias">${escapeHtml(location.name)}</div>` +
          `<div class="item-name">${escapeHtml(wktKind(location.geometry) || "形なし")}${used.has(location.key) ? " · シーンあり" : ""}</div>`;
        item.addEventListener("click", () => {
          this.selectedLocationId = location.id;
          this.renderBody();
        });
        master.appendChild(item);
      }
      this.renderLocationDetail(body.querySelector("#de-location-detail"));
    }

    renderLocationDetail(detail) {
      const location = this.dramaturgyLocations().find((l) => l.id === this.selectedLocationId);
      if (!location) {
        const count = this.dramaturgySiteFlows().length;
        detail.innerHTML = `<p class="placeholder">左の一覧から場所を選択してください。${
          this.dramaturgyLocations().length === 0
            ? "この作品はまだ場所を使っていません(Import KML / GeoPackage...で地図を取り込みます)。"
            : `この作品の移動(SiteFlow)は${count}件です。`
        }</p>`;
        return;
      }
      const names = new Map((this.content.locations || []).map((l) => [l.key, l.name]));
      const flows = this.dramaturgySiteFlows().filter(
        (f) => f.origin.ref === location.key || f.destination.ref === location.key
      );
      const flowRows = flows
        .map(
          (f) => `
          <tr data-id="${escapeAttr(f.id)}">
            <td>${escapeHtml(f.name || "")}</td>
            <td>${escapeHtml(names.get(f.origin.ref) || f.origin.ref)} → ${escapeHtml(names.get(f.destination.ref) || f.destination.ref)}</td>
            <td><select class="dl-flow-direction">${SITE_FLOW_DIRECTIONS.map(
              ([value, label]) => `<option value="${value}" ${(f.direction || "") === value ? "selected" : ""}>${escapeHtml(label)}</option>`
            ).join("")}</select></td>
          </tr>`
        )
        .join("");
      detail.innerHTML = `
        <div class="panel-section-title">${escapeHtml(location.name)}</div>
        <div class="panel-form panel-form--wide">
          <div class="panel-readonly-id">ID: ${escapeHtml(location.id)}</div>
          <div class="field-hint">場所はプロジェクト全体で共有されます(ここでの変更は、この場所を使う他の作品にも及びます)。</div>
          ${textField("dl_name", "Name", location.name || "")}
          ${textField("dl_address", "Address", location.address || "")}
          <div class="field">
            <label for="dl_instruction">Instruction</label>
            <textarea id="dl_instruction" class="prose">${escapeHtml(location.instruction || "")}</textarea>
            <div class="field-hint">この場所で案内すること</div>
          </div>
          <div class="field">
            <label for="dl_description">Description</label>
            <textarea id="dl_description" class="prose">${escapeHtml(location.description || "")}</textarea>
            <div class="field-hint">この場所の事実</div>
          </div>
          <div class="field">
            <label>Geometry</label>
            <textarea readonly>${escapeHtml(location.geometry || "")}</textarea>
            <div class="field-hint">形(WKT。WGS84、経度・緯度の順)。形はEdit > Edit Location on Mapで直すか、QGIS・Google マイマップ等で直してImport KML / GeoPackage...で取り込み直します。</div>
          </div>
          <div class="panel-actions">
            <button type="button" class="btn btn-primary" id="dl_save">Save</button>
          </div>
          <div class="panel-section-title">Site Flows</div>
          ${
            flows.length
              ? `<div class="data-table-wrap"><table class="data-table">
                  <thead><tr><th>Name</th><th>Origin → Destination</th><th>Direction</th></tr></thead>
                  <tbody>${flowRows}</tbody>
                </table></div>
                <div class="panel-actions"><button type="button" class="btn" id="dl_save_flows">Save Directions</button></div>`
              : `<p class="field-hint">(この場所に出入りする移動はありません)</p>`
          }
        </div>
      `;
      detail.querySelector("#dl_save").addEventListener("click", (ev) =>
        this.withButtonBusy(ev.currentTarget, "Saving...", () => this.saveLocation(location))
      );
      const saveFlows = detail.querySelector("#dl_save_flows");
      if (saveFlows) {
        saveFlows.addEventListener("click", (ev) => this.withButtonBusy(ev.currentTarget, "Saving...", () => this.saveFlowDirections()));
      }
    }

    // 地図(KML・KMZ・GeoPackage)を、この作品に取り込む(下書きに入る。補助情報のDatasetはすぐに保存される)
    async importMap(file) {
      const content = await new Promise((resolve, reject) => {
        const reader = new FileReader();
        // data:<MIME>;base64,xxxx の base64 部分だけを送る
        reader.onload = () => resolve(String(reader.result).split(",", 2)[1] || "");
        reader.onerror = () => reject(reader.error);
        reader.readAsDataURL(file);
      });
      try {
        const result = await apiFetch(`/projects/${this.projectId}/drama-drafts/${this.draft.draftId}/import-geodata`, {
          method: "POST",
          bodyObj: { dramaturgy_id: this.dramaturgyId, filename: file.name, content_base64: content },
        });
        this.draft.noteChange();
        await this.reloadContent();
        const auxiliary = Object.values(result.auxiliary_layers || {}).reduce((a, b) => a + b, 0);
        showToast(
          `${file.name}を取り込みました(Location 新規${result.locations_created}・更新${result.locations_updated}、` +
            `SiteFlow 新規${result.site_flows_created}・更新${result.site_flows_updated}` +
            (result.auxiliary_filename ? `、補助情報${auxiliary}件をDataset「${result.auxiliary_filename}」に保存` : "") +
            ")。Save Versionで確定してください",
          "ok"
        );
        if (result.auxiliary_file_id) {
          this.dispatchEvent(new CustomEvent("dramaturgy-editor-datasets-changed", { bubbles: true }));
        }
      } catch (e) {
        showApiError(e);
      }
    }

    // 場所はプロジェクトの要素なので、最上位のlocationsに部分YAMLを重ねる
    async saveLocation(location) {
      const detail = this.querySelector("#de-location-detail");
      const name = detail.querySelector("#dl_name").value.trim();
      fieldError(detail, "dl_name", "");
      if (!name) {
        fieldError(detail, "dl_name", "入力してください");
        return;
      }
      const value = (id) => detail.querySelector(`#${id}`).value.trim() || null;
      try {
        await this.draft.edit({
          locations: [
            {
              id: location.id,
              name,
              address: value("dl_address"),
              instruction: value("dl_instruction"),
              description: value("dl_description"),
            },
          ],
        });
        await this.reloadContent();
        showToast("下書きに保存しました(Save Versionで確定)", "ok");
      } catch (e) {
        showApiError(e);
      }
    }

    async saveFlowDirections() {
      const rows = [...this.querySelectorAll("#de-location-detail tr[data-id]")];
      const siteFlows = rows.map((row) => ({
        id: row.dataset.id,
        direction: row.querySelector(".dl-flow-direction").value || null,
      }));
      try {
        await this.draft.edit({ site_flows: siteFlows });
        await this.reloadContent();
        showToast("下書きに保存しました(Save Versionで確定)", "ok");
      } catch (e) {
        showApiError(e);
      }
    }

    // シーンの無い場所から、幕actIdの末尾にシーンを作る(移動を辿った順。題=場所の名前、場所=その場所)
    async generateScenes(actId) {
      const act = this.acts().find((a) => a.id === actId);
      if (!act) return;
      const used = this.usedLocationKeys();
      const targets = this.siteFlowOrder().filter((l) => !used.has(l.key));
      if (targets.length === 0) {
        showToast("シーンの無い場所はありません", "info");
        return;
      }
      const skipped = this.dramaturgyLocations().length - targets.length;
      const actLabel = `Act ${(act.order ?? 0) + 1}`;
      if (
        !confirm(
          `${actLabel}に、場所${targets.length}件からシーンを作ります(移動を辿った順)。` +
            (skipped ? `シーンのある場所${skipped}件は飛ばします。` : "") +
            "よろしいですか?"
        )
      ) {
        return;
      }
      const scenes = act.scenes || [];
      const start = scenes.length === 0 ? 0 : Math.max(...scenes.map((s) => s.order ?? 0)) + 1;
      try {
        await this.editDramaturgy({
          acts: [
            {
              id: act.id,
              scenes: targets.map((l, i) => ({ order: start + i, title: l.name, location: { ref: l.key } })),
            },
          ],
        });
        showToast(`${actLabel}にシーンを${targets.length}件作りました(Save Versionで確定)`, "ok");
      } catch (e) {
        showApiError(e);
      }
    }

    // -------------------------------------------------------------------
    // Scenes
    // -------------------------------------------------------------------

    renderScenesTab(body) {
      body.innerHTML = `
        <div class="panel-master-detail">
          <div class="panel-master" id="de-scene-master"></div>
          <div class="panel-detail" id="de-scene-detail"></div>
        </div>
      `;
      const master = body.querySelector("#de-scene-master");
      const entries = this.sceneEntries();
      if (entries.length === 0) master.innerHTML = `<div class="panel-master-empty">(No Scenes)</div>`;
      const names = new Map((this.content.locations || []).map((l) => [l.key, l.name]));
      for (const { act, scene } of entries) {
        const item = document.createElement("div");
        item.className = "panel-master-item" + (scene.id === this.selectedSceneId ? " selected" : "");
        const place = scene.location ? names.get(scene.location.ref) : null;
        item.innerHTML =
          `<div class="item-alias">${escapeHtml(scene.title || "(無題)")}</div>` +
          `<div class="item-name">Act ${(act.order ?? 0) + 1} · Scene ${(scene.order ?? 0) + 1}${place ? ` · ${escapeHtml(place)}` : ""}</div>`;
        item.addEventListener("click", () => {
          this.selectedSceneId = scene.id;
          this.renderBody();
        });
        master.appendChild(item);
      }
      const addBtn = document.createElement("button");
      addBtn.className = "panel-master-add";
      addBtn.textContent = "+ Add Scene";
      addBtn.addEventListener("click", () => this.addScene());
      master.appendChild(addBtn);
      this.renderSceneDetail(body.querySelector("#de-scene-detail"));
    }

    renderSceneDetail(detail) {
      const entry = this.sceneEntries().find(({ scene }) => scene.id === this.selectedSceneId);
      if (!entry) {
        detail.innerHTML = `<p class="placeholder">左の一覧からシーンを選択するか、「+ Add Scene」で追加してください(選んでいるシーンの幕、無ければ最後の幕に加えます)。</p>`;
        return;
      }
      const { act, scene } = entry;
      const current = scene.location ? scene.location.ref : "";
      const locations = this.dramaturgyLocations();
      // 作品で使っていない場所を参照しているシーンも、その場所を選択肢に残す
      const options = [{ key: "", name: "(なし)" }, ...locations];
      if (current && !locations.some((l) => l.key === current)) {
        const other = (this.content.locations || []).find((l) => l.key === current);
        options.push({ key: current, name: `${other ? other.name : current}(作品で使っていない場所)` });
      }
      detail.innerHTML = `
        <div class="panel-section-title">Act ${(act.order ?? 0) + 1} · Scene ${(scene.order ?? 0) + 1}</div>
        <div class="panel-form">
          <div class="panel-readonly-id">ID: ${escapeHtml(scene.id)}</div>
          ${textField("ds_title", "Title", scene.title || "")}
          <div class="field">
            <label for="ds_synopsis">Synopsis</label>
            <textarea id="ds_synopsis">${escapeHtml(scene.synopsis || "")}</textarea>
            <div class="field-hint">このシーンのあらすじ(プロット)。</div>
          </div>
          <div class="field">
            <label for="ds_location">Location</label>
            <select id="ds_location">${options
              .map((o) => `<option value="${escapeAttr(o.key)}" ${o.key === current ? "selected" : ""}>${escapeHtml(o.name)}</option>`)
              .join("")}</select>
          </div>
          <div class="panel-actions">
            <button type="button" class="btn btn-primary" id="ds_save">Save</button>
            <button type="button" class="btn btn-danger" id="ds_delete">Delete Scene</button>
          </div>
        </div>
      `;
      detail.querySelector("#ds_save").addEventListener("click", (ev) =>
        this.withButtonBusy(ev.currentTarget, "Saving...", () => this.saveScene(act, scene))
      );
      detail.querySelector("#ds_delete").addEventListener("click", () => this.deleteScene(act, scene));
    }

    async saveScene(act, scene) {
      const detail = this.querySelector("#de-scene-detail");
      const value = (id) => detail.querySelector(`#${id}`).value.trim() || null;
      const location = detail.querySelector("#ds_location").value;
      try {
        await this.editDramaturgy({
          acts: [
            {
              id: act.id,
              scenes: [
                {
                  id: scene.id,
                  title: value("ds_title"),
                  synopsis: value("ds_synopsis"),
                  location: location ? { ref: location } : null,
                },
              ],
            },
          ],
        });
        showToast("下書きに保存しました(Save Versionで確定)", "ok");
      } catch (e) {
        showApiError(e);
      }
    }

    // 選んでいるシーンの幕(無ければ最後の幕)の末尾に、空のシーンを足す
    async addScene() {
      const acts = this.acts();
      if (acts.length === 0) {
        showToast("先にActsタブで幕を追加してください", "warn");
        return;
      }
      const selected = this.sceneEntries().find(({ scene }) => scene.id === this.selectedSceneId);
      const act = selected ? selected.act : acts[acts.length - 1];
      const scenes = act.scenes || [];
      const order = scenes.length === 0 ? 0 : Math.max(...scenes.map((s) => s.order ?? 0)) + 1;
      try {
        await this.editDramaturgy({ acts: [{ id: act.id, scenes: [{ order }] }] });
        const added = this.acts()
          .find((a) => a.id === act.id)
          .scenes.find((s) => (s.order ?? 0) === order);
        this.selectedSceneId = added ? added.id : null;
        this.renderBody();
        showToast(`Act ${(act.order ?? 0) + 1}にScene ${order + 1}を追加しました(Save Versionで確定)`, "ok");
      } catch (e) {
        showApiError(e);
      }
    }

    // シーンを消し、同じ幕の残りのシーンのorderを0から詰め直す(1回の直接編集で)。
    async deleteScene(act, scene) {
      const label = `Act ${(act.order ?? 0) + 1} · Scene ${(scene.order ?? 0) + 1}${scene.title ? `「${scene.title}」` : ""}`;
      if (!confirm(`${label}を削除します。台詞・原稿も削除されます。よろしいですか?`)) return;
      const remaining = [...(act.scenes || [])]
        .filter((s) => s.id !== scene.id)
        .sort((a, b) => (a.order ?? 0) - (b.order ?? 0));
      const patchScenes = [{ id: scene.id, delete: true }];
      remaining.forEach((s, i) => {
        if ((s.order ?? 0) !== i) patchScenes.push({ id: s.id, order: i });
      });
      try {
        await this.editDramaturgy({ acts: [{ id: act.id, scenes: patchScenes }] });
        this.selectedSceneId = null;
        this.renderBody();
        showToast(`${label}を削除しました(Save Versionで確定)`, "ok");
      } catch (e) {
        showApiError(e);
      }
    }

    // -------------------------------------------------------------------
    // Acts
    // -------------------------------------------------------------------

    renderActsTab(body) {
      body.innerHTML = `
        <div class="panel-master-detail">
          <div class="panel-master" id="de-act-master"></div>
          <div class="panel-detail" id="de-act-detail"></div>
        </div>
      `;
      const master = body.querySelector("#de-act-master");
      const acts = this.acts();
      if (acts.length === 0) {
        master.innerHTML = `<div class="panel-master-empty">(No Acts)</div>`;
      }
      for (const act of acts) {
        const item = document.createElement("div");
        item.className = "panel-master-item" + (act.id === this.selectedActId ? " selected" : "");
        item.innerHTML =
          `<div class="item-alias">Act ${(act.order ?? 0) + 1}</div>` +
          `<div class="item-name">${escapeHtml(act.title || "(無題)")} · シーン ${(act.scenes || []).length}</div>`;
        item.addEventListener("click", () => {
          this.selectedActId = act.id;
          this.renderBody();
        });
        master.appendChild(item);
      }
      const addBtn = document.createElement("button");
      addBtn.className = "panel-master-add";
      addBtn.textContent = "+ Add Act";
      addBtn.addEventListener("click", () => this.addAct());
      master.appendChild(addBtn);
      this.renderActDetail(body.querySelector("#de-act-detail"));
    }

    renderActDetail(detail) {
      const act = this.acts().find((a) => a.id === this.selectedActId);
      if (!act) {
        detail.innerHTML = `<p class="placeholder">左の一覧から幕を選択するか、「+ Add Act」で追加してください。</p>`;
        return;
      }
      detail.innerHTML = `
        <div class="panel-section-title">Act ${(act.order ?? 0) + 1}</div>
        <div class="panel-form">
          <div class="panel-readonly-id">ID: ${escapeHtml(act.id)} · シーン ${(act.scenes || []).length}</div>
          ${textField("da_title", "Title", act.title || "")}
          <div class="field">
            <label for="da_synopsis">Synopsis</label>
            <textarea id="da_synopsis">${escapeHtml(act.synopsis || "")}</textarea>
            <div class="field-hint">この幕のあらすじ(メタストーリー)。</div>
          </div>
          <div class="panel-actions">
            <button type="button" class="btn btn-primary" id="da_save">Save</button>
            <button type="button" class="btn btn-danger" id="da_delete">Delete Act</button>
          </div>
        </div>
      `;
      detail.querySelector("#da_save").addEventListener("click", (ev) =>
        this.withButtonBusy(ev.currentTarget, "Saving...", () => this.saveAct(act))
      );
      detail.querySelector("#da_delete").addEventListener("click", () => this.deleteAct(act));
    }

    async addAct() {
      const acts = this.acts();
      const order = acts.length === 0 ? 0 : Math.max(...acts.map((a) => a.order ?? 0)) + 1;
      try {
        await this.editDramaturgy({ acts: [{ order }] });
        const added = this.acts().find((a) => (a.order ?? 0) === order);
        this.selectedActId = added ? added.id : null;
        this.renderBody();
        showToast(`Act ${order + 1}を追加しました(Save Versionで確定)`, "ok");
      } catch (e) {
        showApiError(e);
      }
    }

    async saveAct(act) {
      const detail = this.querySelector("#de-act-detail");
      const value = (id) => detail.querySelector(`#${id}`).value.trim() || null;
      try {
        await this.editDramaturgy({ acts: [{ id: act.id, title: value("da_title"), synopsis: value("da_synopsis") }] });
        showToast("下書きに保存しました(Save Versionで確定)", "ok");
      } catch (e) {
        showApiError(e);
      }
    }

    // 幕を消し、残りの幕のorderを0から詰め直す(1回の直接編集で)。
    async deleteAct(act) {
      const sceneCount = (act.scenes || []).length;
      const label = `Act ${(act.order ?? 0) + 1}${act.title ? `「${act.title}」` : ""}`;
      if (!confirm(`${label}を削除します。${sceneCount > 0 ? `シーン${sceneCount}件も削除されます。` : ""}よろしいですか?`)) {
        return;
      }
      const remaining = this.acts().filter((a) => a.id !== act.id);
      const patchActs = [{ id: act.id, delete: true }];
      remaining.forEach((a, i) => {
        if ((a.order ?? 0) !== i) patchActs.push({ id: a.id, order: i });
      });
      try {
        await this.editDramaturgy({ acts: patchActs });
        this.selectedActId = null;
        this.renderBody();
        showToast(`${label}を削除しました(Save Versionで確定)`, "ok");
      } catch (e) {
        showApiError(e);
      }
    }
  }
);
