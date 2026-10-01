"use strict";
/*
 * <character-editor-panel> — Edit > Character Editor が開く、人物パネル(docs/architecture.md 9節)。
 * 世界観(プロジェクト)の人物・人物のまとまり・人物関係を編集する。作品を選んでいなくても開ける。
 * どの作品からも使われない人物・設定の少ない人物は普通のことなので、不備として扱わない(名前だけで登録できる)。
 * apiFetch/state/showToast/showApiError/textField/fieldError/escapeHtml/escapeAttr/EditorDraftをグローバル利用する。
 *
 * Dramaturgy Editorと同じ編集用の下書き(editor_draft.js)を通して編集し、ヘッダーのSave Versionで確定する。
 *
 * タブ:
 * - Characters: 人物の一覧と編集(名前・読み・性別・年齢・話し方・特徴・経歴)。Import from Proposalで、作品を選び、
 *   企画書の登場人物を取り込む(作業補助の生成AIを使う。名前が同じなら同じ人物とみなす)。未登録はImportで骨組みから登録し、
 *   登録済みはCheckで矛盾を確かめてから、キャンセル・統合(Merge)・置き換え(Replace)を選ぶ。矛盾の理由は今は保存しない
 * - Groups: 人物のまとまり(名前・種類・説明・メンバー)
 * - Relationships: 人物関係(誰から誰へ・ラベル・呼び方・口調・時期・説明)
 * 経歴・人物関係の時期は、下書きにある時期(temporal_nodes)から選ぶだけ(時期の編集の置き場所は保留)。
 * 他から参照されている人物・人物関係は削除せず、参照している所を示す(参照切れを作らない)。
 */

// 新しい要素を編集中であることを示す選択の値
const CE_NEW = "__new__";

// 語尾の種類(core.model.drama.speech_style.SentenceEndingKind)と表示名
const CE_ENDING_KINDS = [
  ["normal", "通常"],
  ["conjecture", "推測"],
  ["question", "疑問"],
  ["negation", "否定"],
  ["command", "命令"],
  ["request", "依頼"],
  ["exclamation", "感嘆"],
];

// 語尾の例の区切り(1つの入力欄に複数の例を書く)
const CE_EXAMPLE_SEPARATOR = " / ";

// 空文字をnullに(部分YAMLのnullは、その属性を消す)
function ceText(value) {
  const text = (value || "").trim();
  return text || null;
}

// 対応表からnullの項目を除く(丸ごと置き換える一覧の要素・新しい要素に使う)
function ceCompact(obj) {
  return Object.fromEntries(Object.entries(obj).filter(([, v]) => v !== null && v !== undefined));
}

customElements.define(
  "character-editor-panel",
  class extends HTMLElement {
    constructor() {
      super();
      this.projectId = null;
      this.draft = null; // 編集用の下書き(EditorDraft)
      this.content = null; // 下書きの中身(モデル定義YAMLの対応表)
      this.activeTab = "characters";
      this.selectedCharacterId = null; // CE_NEWなら新しい人物
      this.characterView = "detail"; // detail / import
      this.importDramaturgyId = null;
      this.importResults = {}; // 企画書の登場人物の名前 → {conflict, reasons}(Checkの結果)
      this.importBusy = null; // 生成AIを呼んでいる登場人物の名前
      this.selectedGroupId = null;
      this.selectedRelationshipId = null;
      this.relationshipFilter = ""; // 人物のkey(空ならすべて)
    }

    connectedCallback() {
      this.innerHTML = `
        <div class="panel-header" id="ce-header"></div>
        <div class="panel-tabs" id="ce-tabs"></div>
        <div class="panel-body" id="ce-body"><p class="placeholder">読み込んでいます…</p></div>
      `;
    }

    async load(projectId) {
      this.projectId = projectId;
      this.draft = new EditorDraft(projectId);
      this.importResults = {};
      try {
        if (!(await this.draft.ensure())) {
          this.dispatchEvent(new CustomEvent("character-editor-closed", { bubbles: true }));
          return;
        }
        await this.reloadContent();
      } catch (e) {
        showApiError(e);
      }
    }

    async reloadContent() {
      this.content = await this.draft.content();
      if (this.selectedCharacterId && this.selectedCharacterId !== CE_NEW && !this.characterById(this.selectedCharacterId)) {
        this.selectedCharacterId = null;
      }
      if (this.selectedGroupId && this.selectedGroupId !== CE_NEW && !this.groups().some((g) => g.id === this.selectedGroupId)) {
        this.selectedGroupId = null;
      }
      if (
        this.selectedRelationshipId &&
        this.selectedRelationshipId !== CE_NEW &&
        !this.relationships().some((r) => r.id === this.selectedRelationshipId)
      ) {
        this.selectedRelationshipId = null;
      }
      this.render();
    }

    // 部分YAMLを下書きに重ねて、読み直す
    async edit(patch) {
      await this.draft.edit(patch);
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

    // ---------------------------------------------------------------
    // 下書きの中身の参照
    // ---------------------------------------------------------------

    characters() {
      return this.content.characters || [];
    }
    groups() {
      return this.content.character_groups || [];
    }
    relationships() {
      return this.content.relationships || [];
    }
    dramaturgies() {
      return this.content.dramaturgies || [];
    }
    temporalNodes() {
      return this.content.temporal_nodes || [];
    }
    characterById(id) {
      return this.characters().find((c) => c.id === id) || null;
    }
    characterByKey(key) {
      return this.characters().find((c) => c.key === key) || null;
    }
    characterName(key) {
      const c = this.characterByKey(key);
      return c ? c.name : key;
    }
    nodeLabel(key) {
      const node = this.temporalNodes().find((n) => n.key === key);
      return node ? node.label || node.string_date || node.key : key;
    }
    // 名前で同じ人物とみなす(前後の空白は無視。企画書の取り込みと同じ規則)
    characterByName(name) {
      const target = (name || "").trim();
      return this.characters().find((c) => (c.name || "").trim() === target) || null;
    }
    // 要素の一覧に新しく加わったものの識別子(追加の直後に選ぶため)
    static newId(before, after) {
      const known = new Set(before.map((x) => x.id));
      const added = after.find((x) => !known.has(x.id));
      return added ? added.id : null;
    }

    // ---------------------------------------------------------------
    // 枠
    // ---------------------------------------------------------------

    render() {
      this.renderHeader();
      this.renderTabs();
      this.renderBody();
    }

    renderHeader() {
      const header = this.querySelector("#ce-header");
      header.innerHTML = `
        <div class="panel-header-row">
          <span class="panel-header-title">Character Editor</span>
          <div class="panel-header-actions">
            <span class="panel-header-version">${escapeHtml(this.draft.versionLabel())}</span>
            <button type="button" class="${this.draft.versionButtonClass()}" id="ce_save_version">Save Version</button>
          </div>
        </div>
      `;
      header.querySelector("#ce_save_version").addEventListener("click", (ev) =>
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
        this.dispatchEvent(new CustomEvent("character-editor-saved", { bubbles: true }));
        await this.reloadContent();
      } catch (e) {
        showApiError(e);
      }
    }

    renderTabs() {
      const tabs = this.querySelector("#ce-tabs");
      tabs.innerHTML = "";
      for (const [key, label] of [
        ["characters", "Characters"],
        ["groups", "Groups"],
        ["relationships", "Relationships"],
      ]) {
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
      const body = this.querySelector("#ce-body");
      if (this.activeTab === "characters") this.renderCharactersTab(body);
      else if (this.activeTab === "groups") this.renderGroupsTab(body);
      else if (this.activeTab === "relationships") this.renderRelationshipsTab(body);
    }

    // 一覧(左)の共通の組み立て。items: [{id, alias, name}]
    renderMaster(master, items, selectedId, emptyLabel, onSelect, extraButtons) {
      master.innerHTML = "";
      if (items.length === 0) master.innerHTML = `<div class="panel-master-empty">${escapeHtml(emptyLabel)}</div>`;
      for (const it of items) {
        const item = document.createElement("div");
        item.className = "panel-master-item" + (it.id === selectedId ? " selected" : "");
        item.innerHTML = `<div class="item-alias">${escapeHtml(it.alias)}</div><div class="item-name">${escapeHtml(it.name)}</div>`;
        item.addEventListener("click", () => onSelect(it.id));
        master.appendChild(item);
      }
      for (const [label, onClick] of extraButtons) {
        const btn = document.createElement("button");
        btn.className = "panel-master-add";
        btn.textContent = label;
        btn.addEventListener("click", onClick);
        master.appendChild(btn);
      }
    }

    // ---------------------------------------------------------------
    // Characters
    // ---------------------------------------------------------------

    renderCharactersTab(body) {
      body.innerHTML = `
        <div class="panel-master-detail">
          <div class="panel-master" id="ce-character-master"></div>
          <div class="panel-detail" id="ce-character-detail"></div>
        </div>
      `;
      const items = [...this.characters()]
        .sort((a, b) => (a.reading || a.name).localeCompare(b.reading || b.name, "ja"))
        .map((c) => ({ id: c.id, alias: c.name, name: [c.reading, c.gender, c.age].filter(Boolean).join(" · ") || " " }));
      const selected = this.characterView === "import" ? null : this.selectedCharacterId;
      this.renderMaster(body.querySelector("#ce-character-master"), items, selected, "(No Characters)", (id) => {
        this.characterView = "detail";
        this.selectedCharacterId = id;
        this.renderBody();
      }, [
        ["+ Add Character", () => {
          this.characterView = "detail";
          this.selectedCharacterId = CE_NEW;
          this.renderBody();
        }],
        ["Import from Proposal...", () => {
          this.characterView = "import";
          this.renderBody();
        }],
      ]);
      const detail = body.querySelector("#ce-character-detail");
      if (this.characterView === "import") this.renderImport(detail);
      else this.renderCharacterDetail(detail);
    }

    renderCharacterDetail(detail) {
      if (!this.selectedCharacterId) {
        detail.innerHTML = `<p class="placeholder">左の一覧から人物を選ぶか、「+ Add Character」で追加するか、「Import from Proposal...」で企画書から取り込んでください。</p>`;
        return;
      }
      const character = this.selectedCharacterId === CE_NEW ? null : this.characterById(this.selectedCharacterId);
      this.renderCharacterForm(detail, character, this.characterToForm(character));
    }

    // 人物(CharacterSpecの対応表)を、編集フォームの値にする
    characterToForm(character) {
      const c = character || {};
      const speech = c.speech_style || {};
      return {
        name: c.name || "",
        reading: c.reading || "",
        gender: c.gender || "",
        age: c.age || "",
        first_person: speech.first_person || "",
        tone: speech.tone || "",
        speech_description: speech.description || "",
        endings: (speech.endings || []).map((e) => ({
          kind: e.kind,
          examples: (e.examples || []).join(CE_EXAMPLE_SEPARATOR),
          description: e.description || "",
        })),
        characteristics: (c.characteristics || []).map((ch) => ({
          item: ch.item || "",
          definition: ch.definition || "",
          description: ch.description || "",
          features: (ch.features || []).map((f) => ({
            item: f.item || "",
            value: f.value || "",
            definition: f.definition || "",
            description: f.description || "",
          })),
        })),
        biographies: (c.biographies || []).map((b) => ({
          id: b.id,
          period: b.period ? b.period.ref : "",
          episode: b.episode || "",
          involved: (b.involved_relationships || []).map((r) => r.ref),
        })),
        deletedBiographyIds: [],
      };
    }

    // この人物を使っている所(作品の参照・配役・人物関係・まとまり)。削除できるかの判断と表示に使う
    characterUsages(character) {
      const usages = [];
      for (const d of this.dramaturgies()) {
        if ((d.characters || []).some((r) => r.ref === character.key)) usages.push(`作品「${d.title}」の登場人物`);
        if ((d.casts || []).some((cast) => cast.character && cast.character.ref === character.key)) usages.push(`作品「${d.title}」の配役`);
      }
      const relationshipCount = this.relationships().filter((r) => r.source.ref === character.key || r.target.ref === character.key).length;
      if (relationshipCount) usages.push(`人物関係 ${relationshipCount}件`);
      for (const g of this.groups()) {
        if ((g.members || []).some((m) => m.ref === character.key)) usages.push(`まとまり「${g.name}」`);
      }
      return usages;
    }

    renderCharacterForm(detail, character, form) {
      this.characterForm = form;
      const isNew = !character;
      const area = (id, label, value, hint) => `
        <div class="field">
          <label for="${id}">${label}</label>
          <textarea id="${id}" class="prose">${escapeHtml(value)}</textarea>
          ${hint ? `<div class="field-hint">${hint}</div>` : ""}
        </div>`;
      const kindOptions = (current) =>
        CE_ENDING_KINDS.map(([v, l]) => `<option value="${v}" ${v === current ? "selected" : ""}>${escapeHtml(l)}</option>`).join("");
      const endingsHtml = form.endings
        .map(
          (e, i) => `
        <div class="panel-form-row cf-ending" data-index="${i}">
          <div class="field" style="flex: 0 0 110px"><select class="cf-ending-kind">${kindOptions(e.kind)}</select></div>
          <div class="field"><input type="text" class="cf-ending-examples" placeholder="例(「${CE_EXAMPLE_SEPARATOR.trim()}」で区切る)" value="${escapeAttr(e.examples)}"></div>
          <div class="field"><input type="text" class="cf-ending-description" placeholder="説明" value="${escapeAttr(e.description)}"></div>
          <button type="button" class="btn" data-action="remove-ending" data-index="${i}" title="この語尾を消す">×</button>
        </div>`
        )
        .join("");
      const characteristicsHtml = form.characteristics
        .map(
          (ch, i) => `
        <div class="agent-task cf-characteristic" data-index="${i}">
          <div class="panel-form-row">
            <div class="field"><label>Item</label><input type="text" class="cf-char-item" placeholder="まとまりの名前(例: 人物像)" value="${escapeAttr(ch.item)}"></div>
            <div class="field"><label>Definition</label><input type="text" class="cf-char-definition" placeholder="名前の意味(任意)" value="${escapeAttr(ch.definition)}"></div>
            <button type="button" class="btn" data-action="remove-characteristic" data-index="${i}" title="このまとまりを消す">×</button>
          </div>
          <div class="field"><textarea class="prose cf-char-description" placeholder="説明(任意)">${escapeHtml(ch.description)}</textarea></div>
          ${ch.features
            .map(
              (f, j) => `
            <div class="panel-form-row cf-feature" data-index="${j}">
              <div class="field"><input type="text" class="cf-feat-item" placeholder="項目" value="${escapeAttr(f.item)}"></div>
              <div class="field"><input type="text" class="cf-feat-value" placeholder="値" value="${escapeAttr(f.value)}"></div>
              <div class="field"><input type="text" class="cf-feat-definition" placeholder="項目の意味(任意)" value="${escapeAttr(f.definition)}"></div>
              <div class="field"><input type="text" class="cf-feat-description" placeholder="説明(任意)" value="${escapeAttr(f.description)}"></div>
              <button type="button" class="btn" data-action="remove-feature" data-index="${i}" data-feature="${j}" title="この項目を消す">×</button>
            </div>`
            )
            .join("")}
          <div><button type="button" class="btn" data-action="add-feature" data-index="${i}">+ Add Feature</button></div>
        </div>`
        )
        .join("");
      const nodes = this.temporalNodes();
      const ownRelationships = character
        ? this.relationships().filter((r) => r.source.ref === character.key || r.target.ref === character.key)
        : [];
      const biographiesHtml = form.biographies
        .map((b, i) => {
          const periodOptions = [
            `<option value="" ${b.period ? "" : "selected"}>(時期を選ぶ)</option>`,
            ...nodes.map((n) => `<option value="${escapeAttr(n.key)}" ${n.key === b.period ? "selected" : ""}>${escapeHtml(this.nodeLabel(n.key))}</option>`),
          ].join("");
          const relationshipChecks = ownRelationships
            .map(
              (r) => `
              <label class="field-hint"><input type="checkbox" class="cf-bio-relationship" value="${escapeAttr(r.key)}" ${b.involved.includes(r.key) ? "checked" : ""}>
                ${escapeHtml(this.relationshipLabel(r))}</label>`
            )
            .join("");
          return `
          <div class="agent-task cf-biography" data-index="${i}" data-id="${escapeAttr(b.id || "")}">
            <div class="panel-form-row">
              <div class="field"><label>Period</label><select class="cf-bio-period">${periodOptions}</select></div>
              <button type="button" class="btn" data-action="remove-biography" data-index="${i}" title="この経歴を消す">×</button>
            </div>
            <div class="field"><label>Episode</label><textarea class="prose cf-bio-episode">${escapeHtml(b.episode)}</textarea></div>
            ${ownRelationships.length ? `<div class="field"><label>Involved Relationships</label>${relationshipChecks}</div>` : ""}
          </div>`;
        })
        .join("");
      const usages = character ? this.characterUsages(character) : [];
      detail.innerHTML = `
        <div class="panel-section-title">${escapeHtml(isNew ? "New Character" : character.name)}</div>
        <div class="panel-form panel-form--wide">
          ${isNew ? "" : `<div class="panel-readonly-id">ID: ${escapeHtml(character.id)}</div>`}
          <div class="field-hint">名前だけでも登録できます。設定は、必要になったときに足してください。</div>
          <div class="panel-form-row">
            ${textField("cf_name", "Name", form.name)}
            ${textField("cf_reading", "Reading", form.reading, "読み(かな)")}
          </div>
          <div class="panel-form-row">
            ${textField("cf_gender", "Gender", form.gender)}
            ${textField("cf_age", "Age", form.age, "年齢・年代(例: 40代)")}
          </div>
          <div class="panel-section-title">Speech Style</div>
          <div class="panel-form-row">
            ${textField("cf_first_person", "First Person", form.first_person, "一人称")}
            ${textField("cf_tone", "Tone", form.tone, "相手を問わない既定の口調(相手ごとの口調は人物関係に書く)")}
          </div>
          ${area("cf_speech_description", "Description", form.speech_description, "話し方の説明")}
          <div class="field">
            <label>Sentence Endings</label>
            ${endingsHtml || `<p class="field-hint">(語尾はありません)</p>`}
            <div><button type="button" class="btn" data-action="add-ending">+ Add Ending</button></div>
          </div>
          <div class="panel-section-title">Characteristics</div>
          <div class="field-hint">人物像の特徴を、まとまり(例: 人物像・外見)と項目(項目: 値)の2階層で書きます。</div>
          ${characteristicsHtml || `<p class="field-hint">(特徴はありません)</p>`}
          <div><button type="button" class="btn" data-action="add-characteristic">+ Add Characteristic</button></div>
          <div class="panel-section-title">Biographies</div>
          ${biographiesHtml || `<p class="field-hint">(経歴はありません)</p>`}
          <div>
            <button type="button" class="btn" data-action="add-biography" ${nodes.length ? "" : "disabled"}>+ Add Biography</button>
            ${nodes.length ? "" : `<div class="field-hint">経歴には時期が要ります。時期(temporal_nodes)がまだ無いため追加できません。</div>`}
          </div>
          ${usages.length ? `<div class="field-hint">使われている所: ${escapeHtml(usages.join("・"))}</div>` : ""}
          <div class="field-error" id="err_cf_form"></div>
          <div class="panel-actions">
            <button type="button" class="btn btn-primary" data-action="save">Save</button>
            ${isNew ? `<button type="button" class="btn" data-action="cancel-new">Cancel</button>` : `<button type="button" class="btn btn-danger" data-action="delete">Delete Character</button>`}
          </div>
        </div>
      `;
      detail.querySelectorAll("[data-action]").forEach((btn) => {
        btn.addEventListener("click", (ev) => this.onCharacterAction(detail, character, ev.currentTarget));
      });
    }

    async onCharacterAction(detail, character, button) {
      const action = button.dataset.action;
      const index = Number(button.dataset.index);
      if (action === "save") return this.withButtonBusy(button, "Saving...", () => this.saveCharacter(detail, character));
      if (action === "delete") return this.deleteCharacter(character);
      if (action === "cancel-new") {
        this.selectedCharacterId = null;
        this.renderBody();
        return;
      }
      // 行の追加・削除: 入力中の値を読み直してから組み立て直す
      const form = this.readCharacterForm(detail);
      if (action === "add-ending") form.endings.push({ kind: "normal", examples: "", description: "" });
      else if (action === "remove-ending") form.endings.splice(index, 1);
      else if (action === "add-characteristic") form.characteristics.push({ item: "", definition: "", description: "", features: [] });
      else if (action === "remove-characteristic") form.characteristics.splice(index, 1);
      else if (action === "add-feature") form.characteristics[index].features.push({ item: "", value: "", definition: "", description: "" });
      else if (action === "remove-feature") form.characteristics[index].features.splice(Number(button.dataset.feature), 1);
      else if (action === "add-biography") form.biographies.push({ id: null, period: "", episode: "", involved: [] });
      else if (action === "remove-biography") {
        const [removed] = form.biographies.splice(index, 1);
        if (removed.id) form.deletedBiographyIds.push(removed.id);
      }
      this.renderCharacterForm(detail, character, form);
    }

    readCharacterForm(detail) {
      const value = (id) => detail.querySelector(`#${id}`).value;
      const within = (el, selector) => el.querySelector(selector).value;
      return {
        name: value("cf_name"),
        reading: value("cf_reading"),
        gender: value("cf_gender"),
        age: value("cf_age"),
        first_person: value("cf_first_person"),
        tone: value("cf_tone"),
        speech_description: value("cf_speech_description"),
        endings: [...detail.querySelectorAll(".cf-ending")].map((row) => ({
          kind: within(row, ".cf-ending-kind"),
          examples: within(row, ".cf-ending-examples"),
          description: within(row, ".cf-ending-description"),
        })),
        characteristics: [...detail.querySelectorAll(".cf-characteristic")].map((block) => ({
          item: within(block, ".cf-char-item"),
          definition: within(block, ".cf-char-definition"),
          description: within(block, ".cf-char-description"),
          features: [...block.querySelectorAll(".cf-feature")].map((row) => ({
            item: within(row, ".cf-feat-item"),
            value: within(row, ".cf-feat-value"),
            definition: within(row, ".cf-feat-definition"),
            description: within(row, ".cf-feat-description"),
          })),
        })),
        biographies: [...detail.querySelectorAll(".cf-biography")].map((block) => ({
          id: block.dataset.id || null,
          period: within(block, ".cf-bio-period"),
          episode: within(block, ".cf-bio-episode"),
          involved: [...block.querySelectorAll(".cf-bio-relationship:checked")].map((cb) => cb.value),
        })),
        deletedBiographyIds: [...this.characterForm.deletedBiographyIds],
      };
    }

    // フォームの値を、部分YAMLの人物にする。入力に誤りがあればnull(理由はフォームに出す)
    characterPatch(detail, form, character) {
      fieldError(detail, "cf_name", "");
      fieldError(detail, "cf_form", "");
      const name = form.name.trim();
      if (!name) {
        fieldError(detail, "cf_name", "入力してください");
        return null;
      }
      const other = this.characterByName(name);
      if (other && (!character || other.id !== character.id)) {
        fieldError(detail, "cf_name", "同じ名前の人物がいます(企画書の取り込みでは、名前が同じなら同じ人物とみなします)");
        return null;
      }
      if (form.characteristics.some((ch) => !ch.item.trim() || ch.features.some((f) => !f.item.trim()))) {
        fieldError(detail, "cf_form", "特徴のまとまりと項目には名前(Item)を入れてください");
        return null;
      }
      if (form.biographies.some((b) => !b.period || !b.episode.trim())) {
        fieldError(detail, "cf_form", "経歴には時期とエピソードを入れてください");
        return null;
      }
      const endings = form.endings.map((e) =>
        ceCompact({
          kind: e.kind,
          examples: e.examples.split(CE_EXAMPLE_SEPARATOR.trim()).map((s) => s.trim()).filter(Boolean),
          description: ceText(e.description),
        })
      );
      const characteristics = form.characteristics.map((ch) =>
        ceCompact({
          item: ch.item.trim(),
          definition: ceText(ch.definition),
          description: ceText(ch.description),
          features: ch.features.map((f) =>
            ceCompact({ item: f.item.trim(), value: ceText(f.value), definition: ceText(f.definition), description: ceText(f.description) })
          ),
        })
      );
      const biographies = [
        ...form.biographies.map((b) =>
          ceCompact({
            id: b.id,
            period: { ref: b.period },
            episode: b.episode.trim(),
            involved_relationships: b.involved.map((key) => ({ ref: key })),
          })
        ),
        ...form.deletedBiographyIds.map((id) => ({ id, delete: true })),
      ];
      const patch = {
        name,
        reading: ceText(form.reading),
        gender: ceText(form.gender),
        age: ceText(form.age),
        speech_style: {
          first_person: ceText(form.first_person),
          tone: ceText(form.tone),
          description: ceText(form.speech_description),
          endings,
        },
        characteristics,
        biographies,
      };
      // 新しい人物は値のある項目だけを書く(nullは既存の値を消す指定のため)
      if (!character) return { ...ceCompact(patch), speech_style: ceCompact(patch.speech_style) };
      return { id: character.id, ...patch };
    }

    async saveCharacter(detail, character) {
      const form = this.readCharacterForm(detail);
      const patch = this.characterPatch(detail, form, character);
      if (!patch) return;
      const before = this.characters();
      try {
        await this.edit({ characters: [patch] });
        if (!character) this.selectedCharacterId = this.constructor.newId(before, this.characters());
        this.renderBody();
        showToast("下書きに保存しました(Save Versionで確定)", "ok");
      } catch (e) {
        showApiError(e);
      }
    }

    async deleteCharacter(character) {
      const usages = this.characterUsages(character);
      if (usages.length) {
        showToast(`「${character.name}」は使われているため削除できません(${usages.join("・")})。先に外してください`, "error");
        return;
      }
      if (!confirm(`人物「${character.name}」を削除します。よろしいですか?(Save Versionで確定するまでは正本に残ります)`)) return;
      try {
        await this.edit({ characters: [{ id: character.id, delete: true }] });
        this.selectedCharacterId = null;
        this.renderBody();
        showToast("下書きから削除しました(Save Versionで確定)", "ok");
      } catch (e) {
        showApiError(e);
      }
    }

    // ---------------------------------------------------------------
    // Characters > Import from Proposal
    // ---------------------------------------------------------------

    renderImport(detail) {
      const dramaturgies = this.dramaturgies();
      if (dramaturgies.length === 0) {
        detail.innerHTML = `<p class="placeholder">作品がありません。Edit > New Dramaturgy... で作品を作り、Dramaturgy EditorのProposalタブで企画書を書いてください。</p>`;
        return;
      }
      if (!dramaturgies.some((d) => d.id === this.importDramaturgyId)) {
        this.importDramaturgyId = dramaturgies.some((d) => d.id === state.selectedDramaturgyId)
          ? state.selectedDramaturgyId
          : dramaturgies[0].id;
      }
      const dramaturgy = dramaturgies.find((d) => d.id === this.importDramaturgyId);
      const options = dramaturgies
        .map((d) => `<option value="${escapeAttr(d.id)}" ${d.id === dramaturgy.id ? "selected" : ""}>${escapeHtml(d.title)}</option>`)
        .join("");
      const proposalCharacters = (dramaturgy.proposal && dramaturgy.proposal.characters) || [];
      const rows = proposalCharacters.map((pc) => this.importRowHtml(dramaturgy, pc)).join("");
      detail.innerHTML = `
        <div class="panel-section-title">Import from Proposal</div>
        <div class="panel-form panel-form--wide">
          <div class="field">
            <label for="ci_dramaturgy">Dramaturgy</label>
            <select id="ci_dramaturgy">${options}</select>
            <div class="field-hint">選んだ作品の企画書の登場人物を、プロジェクトの人物として取り込みます。名前が同じ人物は、同じ人物とみなします。
              取り込みには作業補助の生成AI(Project > Preferences の Assistive LLM)を使い、結果は下書きに入ります(Save Versionで確定)。手元の生成AIでは数十秒かかることがあります。</div>
          </div>
          ${
            proposalCharacters.length
              ? `<div class="data-table-wrap"><table class="data-table">
                  <thead><tr><th>Name</th><th>Description</th><th>Status</th></tr></thead>
                  <tbody>${rows}</tbody>
                </table></div>`
              : `<p class="field-hint">この作品の企画書には、登場人物がいません(0人)。人物は左の「+ Add Character」で登録できます。</p>`
          }
        </div>
      `;
      detail.querySelector("#ci_dramaturgy").addEventListener("change", (ev) => {
        this.importDramaturgyId = ev.target.value;
        this.importResults = {};
        this.renderImport(detail);
      });
      detail.querySelectorAll("[data-import-action]").forEach((btn) => {
        btn.addEventListener("click", () => this.onImportAction(btn.dataset.importAction, btn.dataset.name, dramaturgy));
      });
    }

    importRowHtml(dramaturgy, pc) {
      const name = (pc.name || "").trim();
      const description = escapeHtml(pc.description || "");
      if (!name) {
        return `<tr><td>(名前なし)</td><td>${description}</td><td>名前が無いため取り込めません</td></tr>`;
      }
      const registered = this.characterByName(name);
      const inWork = registered && (dramaturgy.characters || []).some((r) => r.ref === registered.key);
      const busy = this.importBusy !== null;
      const running = this.importBusy === name;
      const button = (action, label, primary) =>
        `<button type="button" class="btn ${primary ? "btn-primary" : ""}" data-import-action="${action}" data-name="${escapeAttr(name)}" ${busy ? "disabled" : ""}>${label}</button>`;
      const n = escapeHtml(name);
      // 状態の欄に、状態・Checkの結果・操作のボタンを縦に並べる(列を増やすと表が横にはみ出すため)
      const row = (status, actions) =>
        `<tr><td>${n}</td><td>${description}</td><td>${status}<div class="panel-actions">${actions}</div></td></tr>`;
      if (!registered) return row("未登録", running ? "Generating..." : button("create", "Import", true));
      const status = `登録済み${inWork ? "(この作品の登場人物)" : ""}`;
      const result = this.importResults[name];
      if (!result) return row(escapeHtml(status), running ? "Checking..." : button("check", "Check", false));
      // Checkの結果: 矛盾があればキャンセル・統合・置き換え、無ければ同じ人物として作品に加えるか統合する
      const reasons = result.reasons.length
        ? `<ul>${result.reasons.map((r) => `<li>${escapeHtml(r)}</li>`).join("")}</ul>`
        : "";
      const message = result.conflict
        ? `<div class="field-error">登録済みの設定と企画書の説明に矛盾があります。</div>${reasons}`
        : `<div class="field-hint">矛盾は見つかりませんでした。</div>`;
      const actions = running
        ? "Generating..."
        : [
            button("cancel", "Cancel", false),
            button("merge", "Merge", !result.conflict),
            result.conflict ? button("replace", "Replace", false) : "",
            !result.conflict && !inWork ? button("link", "Add to Dramaturgy", false) : "",
          ].join("");
      return row(escapeHtml(status) + message, actions);
    }

    async onImportAction(action, name, dramaturgy) {
      if (action === "cancel") {
        delete this.importResults[name];
        this.renderBody();
        showToast(`「${name}」は取り込みませんでした。企画書で別の名前にするか、矛盾を解消してください`, "info");
        return;
      }
      if (action === "link") return this.linkToDramaturgy(name, dramaturgy);
      if (action === "replace" && !confirm(`「${name}」の読み・性別・年齢・話し方・特徴を、企画書から作った骨組みで置き換えます(経歴・人物関係は残ります)。よろしいですか?`)) {
        return;
      }
      const base = this.draft.base();
      this.importBusy = name;
      this.renderBody();
      try {
        if (action === "check") {
          this.importResults[name] = await apiFetch(`${base}/character-import/check`, {
            method: "POST",
            bodyObj: { dramaturgy_id: dramaturgy.id, name },
          });
        } else {
          const result = await apiFetch(`${base}/character-import`, {
            method: "POST",
            bodyObj: { dramaturgy_id: dramaturgy.id, name, mode: action },
          });
          this.draft.noteChange();
          delete this.importResults[name];
          const verb = { create: "登録しました", merge: "統合しました", replace: "置き換えました" }[action];
          showToast(`「${name}」を${verb}。内容を確かめてください(下書きに入りました。Save Versionで確定)`, "warn");
          this.selectedCharacterId = result.character_id;
        }
      } catch (e) {
        showApiError(e);
      } finally {
        this.importBusy = null;
      }
      await this.reloadContent();
    }

    // 矛盾の無い登録済みの人物を、同じ人物としてこの作品の登場人物に加える(生成AIは使わない)
    async linkToDramaturgy(name, dramaturgy) {
      const character = this.characterByName(name);
      const refs = [...(dramaturgy.characters || []), { ref: character.key }];
      try {
        await this.edit({ dramaturgies: [{ id: dramaturgy.id, characters: refs }] });
        delete this.importResults[name];
        this.renderBody();
        showToast(`「${name}」を作品「${dramaturgy.title}」の登場人物に加えました(Save Versionで確定)`, "ok");
      } catch (e) {
        showApiError(e);
      }
    }

    // ---------------------------------------------------------------
    // Groups
    // ---------------------------------------------------------------

    renderGroupsTab(body) {
      body.innerHTML = `
        <div class="panel-master-detail">
          <div class="panel-master" id="ce-group-master"></div>
          <div class="panel-detail" id="ce-group-detail"></div>
        </div>
      `;
      const items = this.groups().map((g) => ({
        id: g.id,
        alias: g.name,
        name: [g.kind, `${(g.members || []).length}人`].filter(Boolean).join(" · "),
      }));
      this.renderMaster(body.querySelector("#ce-group-master"), items, this.selectedGroupId, "(No Groups)", (id) => {
        this.selectedGroupId = id;
        this.renderBody();
      }, [["+ Add Group", () => {
        this.selectedGroupId = CE_NEW;
        this.renderBody();
      }]]);
      this.renderGroupDetail(body.querySelector("#ce-group-detail"));
    }

    renderGroupDetail(detail) {
      if (!this.selectedGroupId) {
        detail.innerHTML = `<p class="placeholder">左の一覧からまとまりを選ぶか、「+ Add Group」で追加してください。</p>`;
        return;
      }
      const group = this.selectedGroupId === CE_NEW ? null : this.groups().find((g) => g.id === this.selectedGroupId);
      const g = group || {};
      const members = new Set((g.members || []).map((m) => m.ref));
      const checks = [...this.characters()]
        .sort((a, b) => (a.reading || a.name).localeCompare(b.reading || b.name, "ja"))
        .map(
          (c) => `<label class="field-hint"><input type="checkbox" class="gf-member" value="${escapeAttr(c.key)}" ${members.has(c.key) ? "checked" : ""}> ${escapeHtml(c.name)}</label>`
        )
        .join("");
      detail.innerHTML = `
        <div class="panel-section-title">${escapeHtml(group ? group.name : "New Group")}</div>
        <div class="panel-form">
          ${group ? `<div class="panel-readonly-id">ID: ${escapeHtml(group.id)}</div>` : ""}
          ${textField("gf_name", "Name", g.name || "")}
          ${textField("gf_kind", "Kind", g.kind || "", "種類(自由に書く。例: 家族・職場)")}
          <div class="field">
            <label for="gf_description">Description</label>
            <textarea id="gf_description" class="prose">${escapeHtml(g.description || "")}</textarea>
          </div>
          <div class="field">
            <label>Members</label>
            ${checks || `<p class="field-hint">(人物がいません)</p>`}
          </div>
          <div class="panel-actions">
            <button type="button" class="btn btn-primary" id="gf_save">Save</button>
            ${group ? `<button type="button" class="btn btn-danger" id="gf_delete">Delete Group</button>` : `<button type="button" class="btn" id="gf_cancel">Cancel</button>`}
          </div>
        </div>
      `;
      detail.querySelector("#gf_save").addEventListener("click", (ev) =>
        this.withButtonBusy(ev.currentTarget, "Saving...", () => this.saveGroup(detail, group))
      );
      const del = detail.querySelector("#gf_delete");
      if (del) del.addEventListener("click", () => this.deleteGroup(group));
      const cancel = detail.querySelector("#gf_cancel");
      if (cancel) cancel.addEventListener("click", () => {
        this.selectedGroupId = null;
        this.renderBody();
      });
    }

    async saveGroup(detail, group) {
      const name = detail.querySelector("#gf_name").value.trim();
      fieldError(detail, "gf_name", "");
      if (!name) {
        fieldError(detail, "gf_name", "入力してください");
        return;
      }
      const patch = {
        name,
        kind: ceText(detail.querySelector("#gf_kind").value),
        description: ceText(detail.querySelector("#gf_description").value),
        members: [...detail.querySelectorAll(".gf-member:checked")].map((cb) => ({ ref: cb.value })),
      };
      const before = this.groups();
      try {
        await this.edit({ character_groups: [group ? { id: group.id, ...patch } : ceCompact(patch)] });
        if (!group) this.selectedGroupId = this.constructor.newId(before, this.groups());
        this.renderBody();
        showToast("下書きに保存しました(Save Versionで確定)", "ok");
      } catch (e) {
        showApiError(e);
      }
    }

    async deleteGroup(group) {
      if (!confirm(`まとまり「${group.name}」を削除します(人物は消えません)。よろしいですか?`)) return;
      try {
        await this.edit({ character_groups: [{ id: group.id, delete: true }] });
        this.selectedGroupId = null;
        this.renderBody();
        showToast("下書きから削除しました(Save Versionで確定)", "ok");
      } catch (e) {
        showApiError(e);
      }
    }

    // ---------------------------------------------------------------
    // Relationships
    // ---------------------------------------------------------------

    relationshipLabel(r) {
      return `${this.characterName(r.source.ref)} → ${this.characterName(r.target.ref)}: ${r.label}`;
    }

    // この人物関係を使っている所(作品の参照・経歴)
    relationshipUsages(relationship) {
      const usages = [];
      for (const d of this.dramaturgies()) {
        if ((d.relationships || []).some((r) => r.ref === relationship.key)) usages.push(`作品「${d.title}」`);
      }
      for (const c of this.characters()) {
        if ((c.biographies || []).some((b) => (b.involved_relationships || []).some((r) => r.ref === relationship.key))) {
          usages.push(`「${c.name}」の経歴`);
        }
      }
      return usages;
    }

    renderRelationshipsTab(body) {
      const characterOptions = [
        `<option value="">(すべての人物)</option>`,
        ...this.characters().map(
          (c) => `<option value="${escapeAttr(c.key)}" ${c.key === this.relationshipFilter ? "selected" : ""}>${escapeHtml(c.name)}</option>`
        ),
      ].join("");
      body.innerHTML = `
        <div class="field">
          <label for="rf_filter">Character</label>
          <select id="rf_filter">${characterOptions}</select>
        </div>
        <div class="panel-master-detail">
          <div class="panel-master" id="ce-relationship-master"></div>
          <div class="panel-detail" id="ce-relationship-detail"></div>
        </div>
      `;
      body.querySelector("#rf_filter").addEventListener("change", (ev) => {
        this.relationshipFilter = ev.target.value;
        this.renderBody();
      });
      const filter = this.relationshipFilter;
      const items = this.relationships()
        .filter((r) => !filter || r.source.ref === filter || r.target.ref === filter)
        .map((r) => ({
          id: r.id,
          alias: `${this.characterName(r.source.ref)} → ${this.characterName(r.target.ref)}`,
          name: r.label + (r.period ? ` · ${this.nodeLabel(r.period.ref)}` : ""),
        }));
      this.renderMaster(body.querySelector("#ce-relationship-master"), items, this.selectedRelationshipId, "(No Relationships)", (id) => {
        this.selectedRelationshipId = id;
        this.renderBody();
      }, [["+ Add Relationship", () => {
        this.selectedRelationshipId = CE_NEW;
        this.renderBody();
      }]]);
      this.renderRelationshipDetail(body.querySelector("#ce-relationship-detail"));
    }

    renderRelationshipDetail(detail) {
      if (!this.selectedRelationshipId) {
        detail.innerHTML = `<p class="placeholder">左の一覧から人物関係を選ぶか、「+ Add Relationship」で追加してください。</p>`;
        return;
      }
      const relationship = this.selectedRelationshipId === CE_NEW ? null : this.relationships().find((r) => r.id === this.selectedRelationshipId);
      if (this.characters().length === 0) {
        detail.innerHTML = `<p class="placeholder">人物がいません。先にCharactersタブで人物を登録してください。</p>`;
        return;
      }
      const r = relationship || { source: { ref: this.relationshipFilter }, target: { ref: "" } };
      const characterSelect = (id, current) =>
        `<select id="${id}">${[
          `<option value="" ${current ? "" : "selected"}>(選ぶ)</option>`,
          ...this.characters().map((c) => `<option value="${escapeAttr(c.key)}" ${c.key === current ? "selected" : ""}>${escapeHtml(c.name)}</option>`),
        ].join("")}</select>`;
      const period = r.period ? r.period.ref : "";
      const periodOptions = [
        `<option value="" ${period ? "" : "selected"}>(時期を決めない)</option>`,
        ...this.temporalNodes().map((n) => `<option value="${escapeAttr(n.key)}" ${n.key === period ? "selected" : ""}>${escapeHtml(this.nodeLabel(n.key))}</option>`),
      ].join("");
      const usages = relationship ? this.relationshipUsages(relationship) : [];
      detail.innerHTML = `
        <div class="panel-section-title">${escapeHtml(relationship ? this.relationshipLabel(relationship) : "New Relationship")}</div>
        <div class="panel-form">
          ${relationship ? `<div class="panel-readonly-id">ID: ${escapeHtml(relationship.id)}</div>` : ""}
          <div class="panel-form-row">
            <div class="field"><label for="rf_source">Source</label>${characterSelect("rf_source", r.source.ref)}<div class="field-error" id="err_rf_source"></div></div>
            <div class="field"><label for="rf_target">Target</label>${characterSelect("rf_target", r.target.ref)}<div class="field-error" id="err_rf_target"></div></div>
          </div>
          <div class="field-hint">SourceからTargetを見た関係です(逆向きの関係は別に作ります)。</div>
          ${textField("rf_label", "Label", r.label || "", "短い名前(例: 幼馴染)")}
          <div class="panel-form-row">
            ${textField("rf_form_of_address", "Form of Address", r.form_of_address || "", "SourceがTargetをどう呼ぶか")}
            ${textField("rf_tone", "Tone", r.tone || "", "SourceがTargetに話す口調")}
          </div>
          <div class="field">
            <label for="rf_period">Period</label>
            <select id="rf_period">${periodOptions}</select>
            <div class="field-hint">同じ2人の関係が時期によって変わるときに使います。</div>
          </div>
          <div class="field">
            <label for="rf_description">Description</label>
            <textarea id="rf_description" class="prose">${escapeHtml(r.description || "")}</textarea>
          </div>
          ${usages.length ? `<div class="field-hint">使われている所: ${escapeHtml(usages.join("・"))}</div>` : ""}
          <div class="panel-actions">
            <button type="button" class="btn btn-primary" id="rf_save">Save</button>
            ${relationship ? `<button type="button" class="btn btn-danger" id="rf_delete">Delete Relationship</button>` : `<button type="button" class="btn" id="rf_cancel">Cancel</button>`}
          </div>
        </div>
      `;
      detail.querySelector("#rf_save").addEventListener("click", (ev) =>
        this.withButtonBusy(ev.currentTarget, "Saving...", () => this.saveRelationship(detail, relationship))
      );
      const del = detail.querySelector("#rf_delete");
      if (del) del.addEventListener("click", () => this.deleteRelationship(relationship));
      const cancel = detail.querySelector("#rf_cancel");
      if (cancel) cancel.addEventListener("click", () => {
        this.selectedRelationshipId = null;
        this.renderBody();
      });
    }

    async saveRelationship(detail, relationship) {
      const value = (id) => detail.querySelector(`#${id}`).value;
      let ok = true;
      for (const id of ["rf_source", "rf_target", "rf_label"]) {
        fieldError(detail, id, "");
        if (!value(id).trim()) {
          fieldError(detail, id, id === "rf_label" ? "入力してください" : "選んでください");
          ok = false;
        }
      }
      if (!ok) return;
      const patch = {
        source: { ref: value("rf_source") },
        target: { ref: value("rf_target") },
        label: value("rf_label").trim(),
        period: value("rf_period") ? { ref: value("rf_period") } : null,
        form_of_address: ceText(value("rf_form_of_address")),
        tone: ceText(value("rf_tone")),
        description: ceText(value("rf_description")),
      };
      const before = this.relationships();
      try {
        await this.edit({ relationships: [relationship ? { id: relationship.id, ...patch } : ceCompact(patch)] });
        if (!relationship) this.selectedRelationshipId = this.constructor.newId(before, this.relationships());
        this.renderBody();
        showToast("下書きに保存しました(Save Versionで確定)", "ok");
      } catch (e) {
        showApiError(e);
      }
    }

    async deleteRelationship(relationship) {
      const usages = this.relationshipUsages(relationship);
      if (usages.length) {
        showToast(`この人物関係は使われているため削除できません(${usages.join("・")})。先に外してください`, "error");
        return;
      }
      if (!confirm(`人物関係「${this.relationshipLabel(relationship)}」を削除します。よろしいですか?`)) return;
      try {
        await this.edit({ relationships: [{ id: relationship.id, delete: true }] });
        this.selectedRelationshipId = null;
        this.renderBody();
        showToast("下書きから削除しました(Save Versionで確定)", "ok");
      } catch (e) {
        showApiError(e);
      }
    }
  }
);
