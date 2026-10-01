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
 * Save as User Default・Restore System Defaultでプロジェクトのユーザー既定を書き換える。Actorは出さない)・Acts(幕の一覧と詳細。追加・削除)。幕のorderは0から連番で、削除したら残りを詰める。
 */

// 企画書(モデル定義YAMLのproposal。core.schema.formats.dramaturgy_definition.ProposalSpec)の項目
const PROPOSAL_FIELDS = ["title", "catchphrase", "logline", "intent", "target_area", "synopsis", "characters"];
const PROPOSAL_CHARACTER_FIELDS = ["name", "description"];

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

// 企画書のYAMLの文字列から、企画書(proposalの対応表)を取り出す。読める形は、最上位がproposalの文書と、
// モデル定義YAML(dramaturgy.proposal、またはdramaturgiesの一覧の中で企画書を持つ最初の作品)。
// 知らない項目は書き誤りとして断る(モデル定義YAMLと同じく、黙って捨てない)。
function proposalFromYaml(text) {
  const documents = jsyaml.loadAll(text).filter((d) => d !== null && d !== undefined);
  let proposal = null;
  for (const doc of documents) {
    if (typeof doc !== "object" || Array.isArray(doc)) continue;
    const candidates = [doc.proposal, doc.dramaturgy && doc.dramaturgy.proposal, ...(doc.dramaturgies || []).map((d) => d && d.proposal)];
    proposal = candidates.find((p) => p && typeof p === "object") || null;
    if (proposal) break;
  }
  if (!proposal) throw new Error("企画書(proposal)が見つかりません。最上位のproposal:か、dramaturgy:の下のproposal:に書いてください。");
  const unknown = Object.keys(proposal).filter((k) => !PROPOSAL_FIELDS.includes(k));
  if (unknown.length) throw new Error(`企画書に知らない項目があります: ${unknown.join(", ")}`);
  const characters = proposal.characters || [];
  if (!Array.isArray(characters)) throw new Error("charactersは一覧で書いてください");
  characters.forEach((c, i) => {
    if (!c || typeof c !== "object") throw new Error(`characters[${i}]は{name, description}で書いてください`);
    const bad = Object.keys(c).filter((k) => !PROPOSAL_CHARACTER_FIELDS.includes(k));
    if (bad.length) throw new Error(`characters[${i}]に知らない項目があります: ${bad.join(", ")}`);
  });
  const text_ = (v) => (v === null || v === undefined ? "" : String(v));
  return {
    title: text_(proposal.title),
    catchphrase: text_(proposal.catchphrase),
    logline: text_(proposal.logline),
    intent: text_(proposal.intent),
    target_area: text_(proposal.target_area),
    synopsis: text_(proposal.synopsis),
    characters: characters.map((c) => ({ name: text_(c.name), description: text_(c.description) })),
  };
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

    async reloadContent() {
      const content = await this.draft.content();
      this.content = content;
      this.dramaturgy = (content.dramaturgies || []).find((d) => d.id === this.dramaturgyId) || null;
      if (this.dramaturgy && this.selectedActId && !this.acts().some((a) => a.id === this.selectedActId)) {
        this.selectedActId = null;
      }
      this.render();
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
      this.renderHeader();
      this.renderTabs();
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
        ["acts", "Acts"],
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
      else if (this.activeTab === "acts") this.renderActsTab(body);
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
      const p = this.dramaturgy.proposal || {};
      const area = (id, label, value, hint) => `
        <div class="field">
          <label for="${id}">${label}</label>
          <textarea id="${id}" class="prose">${escapeHtml(value || "")}</textarea>
          ${hint ? `<div class="field-hint">${hint}</div>` : ""}
        </div>`;
      body.innerHTML = `
        <div class="panel-form panel-form--wide">
          <div class="field-hint">企画書は作品制作の初期シードです。仮の設定でよく、後から修正できます。題・あらすじ・登場人物は作品(Properties・人物)とは別に持ちます。</div>
          ${textField("pp_title", "Title", p.title || "", "企画の仮の題")}
          ${textField("pp_catchphrase", "Catchphrase", p.catchphrase || "", "キャッチコピー")}
          ${area("pp_logline", "Logline", p.logline, "ログライン(作品を数行で言い表す)")}
          ${area("pp_intent", "Intent", p.intent, "企画意図(なぜ作るか・地域の課題・対象とする人)")}
          ${textField("pp_target_area", "Target Area", p.target_area || "", "対象地域")}
          ${area("pp_synopsis", "Synopsis", p.synopsis, "企画書のあらすじ(作品のSynopsisとは別)")}
          <div class="field">
            <label>Characters</label>
            <div id="pp_characters"></div>
            <div class="field-hint">登場人物(仮の設定)。正式な人物は後で作ります。</div>
            <div><button type="button" class="btn" id="pp_add_character">+ Add Character</button></div>
          </div>
          <div class="panel-actions">
            <button type="button" class="btn" id="pp_import">Import from YAML</button>
            <button type="button" class="btn btn-primary" id="pp_save">Save</button>
            <input type="file" id="pp_import_file" accept=".yaml,.yml" hidden>
          </div>
        </div>
      `;
      this.renderProposalCharacters(body, (p.characters || []).map((c) => ({ ...c })));
      const fileInput = body.querySelector("#pp_import_file");
      body.querySelector("#pp_import").addEventListener("click", () => fileInput.click());
      fileInput.addEventListener("change", async () => {
        const file = fileInput.files[0];
        fileInput.value = ""; // 同じファイルを選び直しても読めるように
        if (file) await this.importProposalFile(body, file);
      });
      body.querySelector("#pp_add_character").addEventListener("click", () => {
        this.renderProposalCharacters(body, [...this.readProposalCharacters(body), { name: "", description: "" }]);
      });
      body.querySelector("#pp_save").addEventListener("click", (ev) =>
        this.withButtonBusy(ev.currentTarget, "Saving...", () => this.saveProposal())
      );
    }

    // 企画書のYAMLを読み、フォームに入れる(下書きにはSaveで保存する)。今の入力は置き換わる。
    async importProposalFile(body, file) {
      let proposal;
      try {
        proposal = proposalFromYaml(await file.text());
      } catch (e) {
        showToast(`${file.name}を読めません: ${e.message}`, "error");
        return;
      }
      for (const key of ["title", "catchphrase", "logline", "intent", "target_area", "synopsis"]) {
        body.querySelector(`#pp_${key}`).value = proposal[key];
      }
      this.renderProposalCharacters(body, proposal.characters);
      showToast(`${file.name}の企画書をフォームに読み込みました。確かめてからSaveしてください`, "warn");
    }

    // 登場人物の行(名前・説明・削除)。入力中の値は、行を足す・消すときにDOMから読み直して保つ。
    renderProposalCharacters(body, characters) {
      const container = body.querySelector("#pp_characters");
      if (characters.length === 0) {
        container.innerHTML = `<p class="field-hint">(登場人物はまだありません)</p>`;
        return;
      }
      container.innerHTML = characters
        .map(
          (c, i) => `
        <div class="panel-form-row proposal-character-row" data-index="${i}">
          <div class="field proposal-character-name">
            <input type="text" class="pc-name" placeholder="名前" value="${escapeAttr(c.name || "")}">
          </div>
          <div class="field">
            <input type="text" class="pc-description" placeholder="説明" value="${escapeAttr(c.description || "")}">
          </div>
          <button type="button" class="btn pc-remove" title="この登場人物を消す">×</button>
        </div>`
        )
        .join("");
      container.querySelectorAll(".pc-remove").forEach((btn) => {
        btn.addEventListener("click", () => {
          const index = Number(btn.closest(".proposal-character-row").dataset.index);
          const current = this.readProposalCharacters(body);
          current.splice(index, 1);
          this.renderProposalCharacters(body, current);
        });
      });
    }

    readProposalCharacters(body) {
      return [...body.querySelectorAll(".proposal-character-row")].map((row) => ({
        name: row.querySelector(".pc-name").value,
        description: row.querySelector(".pc-description").value,
      }));
    }

    async saveProposal() {
      const body = this.querySelector("#de-body");
      const value = (id) => body.querySelector(`#${id}`).value.trim() || null; // nullはその属性を消す
      // 名前も説明も空の行は捨てる。登場人物の一覧は丸ごと置き換わる(識別子の無い仮の設定のため)
      const characters = this.readProposalCharacters(body)
        .map((c) => ({ name: c.name.trim() || null, description: c.description.trim() || null }))
        .filter((c) => c.name || c.description)
        .map((c) => Object.fromEntries(Object.entries(c).filter(([, v]) => v !== null)));
      try {
        await this.editDramaturgy({
          proposal: {
            title: value("pp_title"),
            catchphrase: value("pp_catchphrase"),
            logline: value("pp_logline"),
            intent: value("pp_intent"),
            target_area: value("pp_target_area"),
            synopsis: value("pp_synopsis"),
            characters,
          },
        });
        showToast("下書きに保存しました(Save Versionで確定)", "ok");
      } catch (e) {
        showApiError(e);
      }
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
