"use strict";
/*
 * <ai-build-panel> — Edit > Build with AI... が開く、生成AIと相談しながら作品を作るパネル(docs/architecture.md 10節。
 * QIDMのBuild Domain from Referencesと同じ構成)。Treeで選んだ作品が対象。
 * - 左側: 参照する資料(Dataset)と、チャット。チャットは右側で開いている工程(タブ)に結び付き、相談相手のエージェントと
 *   タスクは工程で決まる(サーバーの対応表 GET .../ai-build/steps)。モードは「対話」と「ワンショット下書き」
 * - 右側: 工程のタブ(まだ用意していない工程は選べない)と、その工程の内容(Proposalは企画書のフォーム、Characters・Groups・
 *   Relationshipsは人物パネルの該当タブ、Casting・AuditionはDramaturgy EditorのCastsタブを埋め込む。どれも直接直してSaveできる)
 * - 生成AIの提案は会話の中に出し、Applyで編集用の下書きに重ねる(Undoで戻す)。確定はヘッダーのSave Version
 * 編集用の下書きは、Dramaturgy Editor・人物パネルと共通(editor_draft.jsのEditorDraft)。
 * apiFetch/showToast/showApiError/escapeHtml/escapeAttr/EditorDraft/ProposalForm/PROPOSAL_FIELD_LABELSをグローバル利用する。
 */

const AI_BUILD_MODES = [
  ["dialogue", "Dialogue", "相談しながら、必要なときだけ変える項目を提案します"],
  ["one_shot", "One-shot Draft", "要望・資料・今の内容から、工程の内容を丸ごと提案します(Applyすると丸ごと置き換わります)"],
];
// 人物パネル(character_editor_panel.js)のタブをそのまま右側に埋め込む工程(工程のkey=人物パネルのタブ)
const AI_BUILD_WORLD_STEPS = ["characters", "groups", "relationships"];
// Dramaturgy EditorのCastsタブを右側に埋め込む工程
const AI_BUILD_CAST_STEPS = ["casting", "audition"];
const AI_BUILD_STATUS_LABELS = { pending: "未反映", applied: "反映済み", undone: "取り消し済み" };

customElements.define(
  "ai-build-panel",
  class extends HTMLElement {
    constructor() {
      super();
      this.projectId = null;
      this.dramaturgyId = null;
      this.draft = null; // 編集用の下書き(EditorDraft)
      this.dramaturgy = null; // 下書きの中の作品(DramaturgySpecの対応表)
      this.steps = []; // AiBuildStepInfo[]
      this.activeStep = "proposal";
      this.mode = "dialogue";
      this.datasets = []; // DatasetSummary[](参照できる資料の候補)
      this.selectedRefs = new Set(); // 選んだ資料のfile_id
      this.messages = []; // 今の工程の会話(AiBuildMessageInfo[])
      this.busy = null; // 生成AIの応答待ち等の説明(null=待っていない)
      this.chatInput = "";
    }

    connectedCallback() {
      this.innerHTML = `
        <div class="panel-header" id="ab-header"></div>
        <div class="panel-body ab-body" id="ab-body"><p class="placeholder">読み込んでいます…</p></div>
      `;
    }

    async load(projectId, dramaturgyId) {
      this.projectId = projectId;
      this.dramaturgyId = dramaturgyId;
      this.draft = new EditorDraft(projectId);
      try {
        if (!(await this.draft.ensure())) {
          this.dispatchEvent(new CustomEvent("ai-build-closed", { bubbles: true }));
          return;
        }
        const [steps, datasets] = await Promise.all([
          apiFetch(`/projects/${projectId}/ai-build/steps`),
          apiFetch(`/projects/${projectId}/datasets`),
        ]);
        this.steps = steps.steps || [];
        this.datasets = datasets.datasets || [];
        const first = this.steps.find((s) => s.available);
        this.activeStep = first ? first.key : null;
        await this.reloadContent();
        await this.reloadMessages();
      } catch (e) {
        showApiError(e);
      }
      this.render();
    }

    async reloadContent() {
      const content = await this.draft.content();
      this.dramaturgy = (content.dramaturgies || []).find((d) => d.id === this.dramaturgyId) || null;
    }

    async reloadMessages() {
      if (!this.activeStep) return;
      const params = new URLSearchParams({ dramaturgy_id: this.dramaturgyId });
      const result = await apiFetch(`/projects/${this.projectId}/ai-build/${this.activeStep}/messages?${params}`);
      this.messages = result.messages || [];
    }

    step() {
      return this.steps.find((s) => s.key === this.activeStep) || null;
    }

    // 相談相手(作品のエージェントの名前。いなければ職能の名前。サーバーはプロジェクトの既定を使う)
    partnerLabel(step) {
      const agents = ((this.dramaturgy && this.dramaturgy.agents) || {})[`${step.role_name}s`] || [];
      return agents.length ? `${agents[0].name}(${step.role_name})` : `${step.role_name}(プロジェクトの既定)`;
    }

    // パネル全体を描く(作品の内容が変わったとき・工程を切り替えたとき)。右側のフォームも描き直すので、Saveしていない入力は消える
    render() {
      this.renderHeader();
      const body = this.querySelector("#ab-body");
      if (!this.dramaturgy) {
        body.innerHTML = `<p class="placeholder">作品が見つかりません(下書きで削除された可能性があります)。</p>`;
        return;
      }
      body.innerHTML = `
        <div class="ab-layout">
          <div class="ab-left" id="ab-left"></div>
          <div class="ab-right">
            <div class="panel-tabs" id="ab-tabs"></div>
            <div class="ab-view" id="ab-view"></div>
          </div>
        </div>`;
      this.renderView(body.querySelector("#ab-view"));
      this.refreshChat();
    }

    // 左側(資料・チャット)とヘッダー・タブだけを描き直す(右側のフォームの入力は保つ)
    refreshChat() {
      this.renderHeader();
      const left = this.querySelector("#ab-left");
      if (!left) return;
      const busy = !!this.busy;
      const step = this.step();
      this.querySelector("#ab-tabs").innerHTML = this.steps
        .map(
          (s) =>
            `<button type="button" class="panel-tab${s.key === this.activeStep ? " active" : ""}" data-step="${escapeAttr(s.key)}"
              ${s.available && !busy ? "" : "disabled"} title="${s.available ? "" : "準備中"}">${escapeHtml(s.label)}</button>`
        )
        .join("");
      const modes = AI_BUILD_MODES.map(
        ([key, label]) =>
          `<label class="ab-mode"><input type="radio" name="ab_mode" value="${key}" ${this.mode === key ? "checked" : ""} ${busy ? "disabled" : ""}> ${label}</label>`
      ).join("");
      const modeHint =
        this.mode === "one_shot" && [...AI_BUILD_WORLD_STEPS, ...AI_BUILD_CAST_STEPS].includes(this.activeStep)
          ? "要望・資料・今の内容から、この工程の内容を1回で提案します(追加と更新だけで、削除はしません)"
          : (AI_BUILD_MODES.find(([key]) => key === this.mode) || [])[2] || "";
      const placeholder =
        this.mode === "one_shot" ? "要望(任意。空でも、今の内容と資料から作ります)" : "相談・質問・指示(Ctrl+Enterで送信)";
      left.innerHTML = `
        <div class="ab-refs">
          <div class="panel-section-title mt-0">References</div>
          <div class="ab-ref-list">${this.referenceListHtml()}</div>
        </div>
        <div class="ab-chat">
          <div class="panel-section-title mt-0">Chat</div>
          <div class="ab-modes">${modes}</div>
          <div class="field-hint">${escapeHtml(modeHint)}</div>
          ${step ? `<div class="field-hint">相談相手: <b>${escapeHtml(this.partnerLabel(step))}</b> · タスク: ${escapeHtml(step.task_code)} · 工程: ${escapeHtml(step.label)}</div>` : ""}
          <div class="ab-messages" id="ab-messages">${this.messagesHtml()}</div>
          ${busy ? `<div class="field-hint ab-busy">${escapeHtml(this.busy)}</div>` : ""}
          <textarea id="ab_input" rows="3" placeholder="${escapeAttr(placeholder)}" ${busy || !step ? "disabled" : ""}>${escapeHtml(this.chatInput)}</textarea>
          <div class="panel-actions">
            <button type="button" class="btn" id="ab_clear" ${busy || !step ? "disabled" : ""}>Clear</button>
            <button type="button" class="btn btn-primary" id="ab_send" ${busy || !step ? "disabled" : ""}>Send</button>
          </div>
        </div>`;
      this.wire(this);
      const list = left.querySelector("#ab-messages");
      list.scrollTop = list.scrollHeight;
    }

    renderHeader() {
      const header = this.querySelector("#ab-header");
      const title = this.dramaturgy ? this.dramaturgy.title : "";
      header.innerHTML = `
        <div class="panel-header-row">
          <span class="panel-header-title">Build with AI — ${escapeHtml(title)}</span>
          <div class="panel-header-actions">
            <span class="panel-header-version">${escapeHtml(this.draft ? this.draft.versionLabel() : "")}</span>
            <button type="button" class="${this.draft ? this.draft.versionButtonClass() : "btn"}" id="ab_save_version" ${this.busy ? "disabled" : ""}>Save Version</button>
          </div>
        </div>
      `;
      header.querySelector("#ab_save_version").addEventListener("click", () => this.saveVersion());
    }

    referenceListHtml() {
      if (!this.datasets.length) {
        return `<p class="field-hint">資料がありません(Project OverviewのDatasetタブで追加できます)。</p>`;
      }
      return this.datasets
        .map(
          (d) => `
        <label class="ab-ref">
          <input type="checkbox" data-ref="${escapeAttr(d.file_id)}" ${this.selectedRefs.has(d.file_id) ? "checked" : ""} ${this.busy ? "disabled" : ""}>
          <span>${escapeHtml(d.filename)}</span>
        </label>`
        )
        .join("");
    }

    // 右側: 今の工程の内容(Proposalは企画書のフォーム、人物の工程は人物パネルの該当タブを埋め込む)
    renderView(view) {
      view.classList.toggle("ab-view--embed", [...AI_BUILD_WORLD_STEPS, ...AI_BUILD_CAST_STEPS].includes(this.activeStep));
      if (AI_BUILD_CAST_STEPS.includes(this.activeStep)) {
        const panel = document.createElement("dramaturgy-editor-panel");
        panel.addEventListener("dramaturgy-editor-edited", () => this.renderHeader()); // 未確定の変更の数
        view.appendChild(panel);
        panel.loadEmbedded(this.projectId, this.dramaturgyId, this.draft, "casts");
        return;
      }
      if (AI_BUILD_WORLD_STEPS.includes(this.activeStep)) {
        const panel = document.createElement("character-editor-panel");
        panel.addEventListener("character-editor-edited", async () => {
          this.renderHeader(); // 未確定の変更の数
          try {
            await this.reloadContent(); // 相談相手等の表示に使う作品の中身
          } catch (e) {
            showApiError(e);
          }
        });
        view.appendChild(panel);
        panel.loadEmbedded(this.projectId, this.draft, this.activeStep);
        return;
      }
      if (this.activeStep === "proposal") {
        new ProposalForm(view, {
          onSave: async (values) => {
            try {
              await this.draft.edit({ dramaturgies: [{ id: this.dramaturgyId, proposal: values }] });
              await this.reloadContent();
              showToast("下書きに保存しました(Save Versionで確定)", "ok");
              this.render();
            } catch (e) {
              showApiError(e);
            }
          },
        }).render(this.dramaturgy.proposal);
        return;
      }
      view.innerHTML = `<p class="placeholder">この工程はまだ用意していません。</p>`;
    }

    messagesHtml() {
      const items = this.messages.map((m) => {
        const text = escapeHtml(m.text || "").replace(/\n/g, "<br>");
        const modeLabel = m.mode === "one_shot" ? "One-shot" : "Dialogue";
        if (m.role === "user") {
          return `<div class="ab-msg ab-msg--user"><span class="ab-badge">${modeLabel}</span>${text || `<span class="field-hint">(要望なし)</span>`}</div>`;
        }
        const list = (title, arr) =>
          arr && arr.length ? `<div class="ab-msg-list"><b>${title}</b><ul>${arr.map((x) => `<li>${escapeHtml(x)}</li>`).join("")}</ul></div>` : "";
        const evidence =
          m.evidence && m.evidence.length
            ? `<details><summary>Evidence (${m.evidence.length})</summary>${m.evidence
                .map(
                  (e) => `<div class="ab-evidence"><span class="ab-evidence-target">${escapeHtml(e.target || "")}</span> ${escapeHtml(e.source || "")}
                    ${e.quote ? `<div class="ab-evidence-quote">“${escapeHtml(e.quote)}”</div>` : ""}</div>`
                )
                .join("")}</details>`
            : "";
        return `<div class="ab-msg ab-msg--assistant">
            ${text}
            ${this.proposalHtml(m)}${list("確認したいこと", m.questions)}${list("注意", m.warnings)}${evidence}
          </div>`;
      });
      return (
        items.join("") ||
        `<p class="field-hint">この工程の会話はまだありません。「Dialogue」で相談するか、「One-shot Draft」で下書きを作らせてください。</p>`
      );
    }

    // 提案(変わる項目だけを表示する)と、Apply・Undo
    proposalHtml(m) {
      if (!m.proposal) return "";
      const busy = this.busy ? "disabled" : "";
      const isProposal = m.step === "proposal";
      const fields = !isProposal
        ? (m.changed_fields || []).map((c) => `<li>${escapeHtml(c)}</li>`).join("") + this.worldDetailsHtml(m.proposal)
        : (m.changed_fields || [])
        .map((field) => {
          const label = PROPOSAL_FIELD_LABELS[field] || field;
          const value = m.proposal[field];
          if (field === "characters") {
            const rows = (value || []).map((c) => `<li>${escapeHtml(c.name || "(名前なし)")}: ${escapeHtml(c.description || "")}</li>`).join("");
            return `<li><b>${label}</b>${rows ? `<ul>${rows}</ul>` : ` <span class="field-hint">(空にする)</span>`}</li>`;
          }
          return `<li><b>${label}</b>: ${value ? escapeHtml(value).replace(/\n/g, "<br>") : `<span class="field-hint">(空にする)</span>`}</li>`;
        })
        .join("");
      const button =
        m.proposal_status === "pending"
          ? `<button type="button" class="btn btn-primary" data-apply="${m.id}" ${busy}>Apply</button>`
          : m.proposal_status === "applied"
            ? `<button type="button" class="btn" data-undo="${m.id}" ${busy}>Undo</button>`
            : "";
      return `<div class="ab-proposal">
          <div class="ab-proposal-head">Proposal <span class="dataset-badge">${AI_BUILD_STATUS_LABELS[m.proposal_status] || ""}</span>
            ${m.mode === "one_shot" && isProposal ? `<span class="field-hint">丸ごと置き換え</span>` : ""} ${button}</div>
          <ul>${fields}</ul>
        </div>`;
    }

    // 人物の工程の提案の中身(折りたたみ)
    worldDetailsHtml(proposal) {
      const rows = [];
      for (const c of proposal.characters || []) {
        const facts = [c.gender, c.age, c.first_person && `一人称: ${c.first_person}`, c.tone && `口調: ${c.tone}`].filter(Boolean);
        const traits = (c.characteristics || [])
          .map((ch) => `${ch.item}: ${(ch.features || []).map((f) => (f.value ? `${f.item}=${f.value}` : f.item)).join("、")}`)
          .join(" / ");
        rows.push(`<li><b>${escapeHtml(c.name)}</b> ${escapeHtml(facts.join("・"))}${traits ? `<div class="field-hint">${escapeHtml(traits)}</div>` : ""}</li>`);
      }
      for (const g of proposal.groups || []) {
        rows.push(`<li><b>${escapeHtml(g.name)}</b>${g.kind ? `(${escapeHtml(g.kind)})` : ""}: ${escapeHtml((g.members || []).join("、"))}</li>`);
      }
      for (const r of proposal.relationships || []) {
        const extra = [r.form_of_address && `呼び方: ${r.form_of_address}`, r.tone && `口調: ${r.tone}`].filter(Boolean).join("・");
        rows.push(`<li>${escapeHtml(r.source)} → ${escapeHtml(r.target)}: <b>${escapeHtml(r.label)}</b> ${escapeHtml(extra)}</li>`);
      }
      const billing = { lead: "主役", supporting: "脇役", minor: "端役" };
      for (const c of proposal.casts || []) {
        const facts = [billing[c.billing] || c.billing, c.performance_title, c.voice_gender, c.language, c.accent, c.pace && `速さ: ${c.pace}`].filter(Boolean);
        rows.push(`<li><b>${escapeHtml(c.character)}</b> ${escapeHtml(facts.join("・"))}${c.performance_description ? `<div class="field-hint">${escapeHtml(c.performance_description)}</div>` : ""}</li>`);
      }
      for (const a of proposal.auditions || []) {
        rows.push(`<li><b>${escapeHtml(a.character)}</b>: ${escapeHtml(a.voice_id)}${a.reason ? `<div class="field-hint">${escapeHtml(a.reason)}</div>` : ""}</li>`);
      }
      return rows.length ? `<details><summary>提案の中身</summary><ul>${rows.join("")}</ul></details>` : "";
    }

    wire(body) {
      body.querySelectorAll(".panel-tab[data-step]").forEach((btn) =>
        btn.addEventListener("click", async () => {
          this.activeStep = btn.dataset.step;
          try {
            await this.reloadMessages();
          } catch (e) {
            showApiError(e);
          }
          this.render();
        })
      );
      body.querySelectorAll("input[name=ab_mode]").forEach((radio) =>
        radio.addEventListener("change", () => {
          this.chatInput = body.querySelector("#ab_input").value;
          this.mode = radio.value;
          this.refreshChat();
        })
      );
      body.querySelectorAll("input[data-ref]").forEach((box) =>
        box.addEventListener("change", () => {
          if (box.checked) this.selectedRefs.add(box.dataset.ref);
          else this.selectedRefs.delete(box.dataset.ref);
        })
      );
      const input = body.querySelector("#ab_input");
      input.addEventListener("input", () => (this.chatInput = input.value));
      input.addEventListener("keydown", (ev) => {
        if (ev.key === "Enter" && ev.ctrlKey) this.send();
      });
      body.querySelector("#ab_send").addEventListener("click", () => this.send());
      body.querySelector("#ab_clear").addEventListener("click", () => this.clear());
      body.querySelectorAll("[data-apply]").forEach((btn) =>
        btn.addEventListener("click", () => this.proposalAction(Number(btn.dataset.apply), "apply"))
      );
      body.querySelectorAll("[data-undo]").forEach((btn) =>
        btn.addEventListener("click", () => this.proposalAction(Number(btn.dataset.undo), "undo"))
      );
    }

    async send() {
      if (this.busy) return;
      const text = this.chatInput.trim();
      if (this.mode === "dialogue" && !text) {
        showToast("発言を入力してください", "error");
        return;
      }
      this.busy = "生成AIが考えています…(手元の生成AIでは数分かかることがあります)";
      this.refreshChat();
      try {
        await apiFetch(`/projects/${this.projectId}/ai-build/${this.activeStep}/messages`, {
          method: "POST",
          bodyObj: {
            draft_id: this.draft.draftId,
            dramaturgy_id: this.dramaturgyId,
            mode: this.mode,
            text,
            reference_file_ids: [...this.selectedRefs],
          },
        });
        this.chatInput = "";
        await this.reloadMessages();
      } catch (e) {
        showApiError(e); // 失敗した発言は記録されないので、入力はそのまま残す
      } finally {
        this.busy = null;
        this.refreshChat();
      }
    }

    async clear() {
      const step = this.step();
      if (!confirm(`${step ? step.label : ""}の会話を消します。よろしいですか?(作品の内容は変わりません)`)) return;
      try {
        const params = new URLSearchParams({ dramaturgy_id: this.dramaturgyId });
        await apiFetch(`/projects/${this.projectId}/ai-build/${this.activeStep}/messages?${params}`, { method: "DELETE" });
        await this.reloadMessages();
        this.refreshChat();
      } catch (e) {
        showApiError(e);
      }
    }

    async proposalAction(messageId, action) {
      if (this.busy) return;
      this.busy = action === "apply" ? "提案を下書きに反映しています…" : "提案を取り消しています…";
      this.refreshChat();
      try {
        await apiFetch(`/projects/${this.projectId}/ai-build/messages/${messageId}/${action}`, {
          method: "POST",
          bodyObj: { draft_id: this.draft.draftId },
        });
        this.draft.noteChange();
        await this.reloadContent();
        await this.reloadMessages();
        showToast(
          action === "apply" ? "提案を下書きに反映しました(Save Versionで確定)" : "提案を取り消しました",
          "ok"
        );
      } catch (e) {
        showApiError(e);
      } finally {
        this.busy = null;
        this.render();
      }
    }

    async saveVersion() {
      try {
        const version = await this.draft.confirm();
        if (version === null) {
          showToast(`確定する変更はありません(${this.draft.versionLabel()}のまま)`, "info");
          return;
        }
        showToast(`版 v${version} として確定しました`, "ok");
        this.dispatchEvent(new CustomEvent("ai-build-saved", { bubbles: true }));
        await this.reloadContent();
        this.render();
      } catch (e) {
        showApiError(e);
      }
    }
  }
);
