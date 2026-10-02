"use strict";
/*
 * ProposalForm — 企画書(Proposal)のフォーム。Dramaturgy EditorのProposalタブと、Build with AIのProposalタブで共通に使う。
 * 題・キャッチコピー・ログライン・企画意図・対象地域・あらすじ・登場人物(名前と説明の行を追加・削除)を編集し、Saveで
 * 呼び出し側(onSave)に、下書きへ重ねる企画書の値(空の項目はnull=消す。登場人物は一覧ごと)を渡す。
 * withImportならImport from YAML(企画書のYAMLをフォームに読み込む。下書きにはSaveで入る)を置く。
 * textField/escapeHtml/escapeAttr/showToast/jsyamlをグローバル利用する。入力欄のidは"pp_"で始まる(1画面に1つだけ置く)。
 */

// 企画書(モデル定義YAMLのproposal。core.schema.formats.dramaturgy_definition.ProposalSpec)の項目
const PROPOSAL_FIELDS = ["title", "catchphrase", "logline", "intent", "target_area", "synopsis", "characters"];
const PROPOSAL_TEXT_FIELDS = ["title", "catchphrase", "logline", "intent", "target_area", "synopsis"];
const PROPOSAL_CHARACTER_FIELDS = ["name", "description"];
// 項目の表示名(Build with AIの提案の表示にも使う)
const PROPOSAL_FIELD_LABELS = {
  title: "Title",
  catchphrase: "Catchphrase",
  logline: "Logline",
  intent: "Intent",
  target_area: "Target Area",
  synopsis: "Synopsis",
  characters: "Characters",
};

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
    ...Object.fromEntries(PROPOSAL_TEXT_FIELDS.map((key) => [key, text_(proposal[key])])),
    characters: characters.map((c) => ({ name: text_(c.name), description: text_(c.description) })),
  };
}

class ProposalForm {
  // onSave(values)は、下書きへ重ねる企画書の値を受け取って保存する(失敗は呼び出し側で知らせる)
  constructor(container, { onSave, withImport = false }) {
    this.container = container;
    this.onSave = onSave;
    this.withImport = withImport;
  }

  render(proposal) {
    const p = proposal || {};
    const area = (id, label, value, hint) => `
      <div class="field">
        <label for="${id}">${label}</label>
        <textarea id="${id}" class="prose">${escapeHtml(value || "")}</textarea>
        ${hint ? `<div class="field-hint">${hint}</div>` : ""}
      </div>`;
    this.container.innerHTML = `
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
          ${this.withImport ? `<button type="button" class="btn" id="pp_import">Import from YAML</button>` : ""}
          <button type="button" class="btn btn-primary" id="pp_save">Save</button>
          ${this.withImport ? `<input type="file" id="pp_import_file" accept=".yaml,.yml" hidden>` : ""}
        </div>
      </div>
    `;
    this.renderCharacters((p.characters || []).map((c) => ({ ...c })));
    if (this.withImport) {
      const fileInput = this.container.querySelector("#pp_import_file");
      this.container.querySelector("#pp_import").addEventListener("click", () => fileInput.click());
      fileInput.addEventListener("change", async () => {
        const file = fileInput.files[0];
        fileInput.value = ""; // 同じファイルを選び直しても読めるように
        if (file) await this.importFile(file);
      });
    }
    this.container.querySelector("#pp_add_character").addEventListener("click", () => {
      this.renderCharacters([...this.readCharacters(), { name: "", description: "" }]);
    });
    this.container.querySelector("#pp_save").addEventListener("click", async (ev) => {
      const button = ev.currentTarget;
      button.disabled = true;
      button.textContent = "Saving...";
      try {
        await this.onSave(this.values());
      } finally {
        if (button.isConnected) {
          button.disabled = false;
          button.textContent = "Save";
        }
      }
    });
  }

  // 企画書のYAMLを読み、フォームに入れる(下書きにはSaveで保存する)。今の入力は置き換わる。
  async importFile(file) {
    let proposal;
    try {
      proposal = proposalFromYaml(await file.text());
    } catch (e) {
      showToast(`${file.name}を読めません: ${e.message}`, "error");
      return;
    }
    for (const key of PROPOSAL_TEXT_FIELDS) {
      this.container.querySelector(`#pp_${key}`).value = proposal[key];
    }
    this.renderCharacters(proposal.characters);
    showToast(`${file.name}の企画書をフォームに読み込みました。確かめてからSaveしてください`, "warn");
  }

  // 登場人物の行(名前・説明・削除)。入力中の値は、行を足す・消すときにDOMから読み直して保つ。
  renderCharacters(characters) {
    const container = this.container.querySelector("#pp_characters");
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
        const current = this.readCharacters();
        current.splice(index, 1);
        this.renderCharacters(current);
      });
    });
  }

  readCharacters() {
    return [...this.container.querySelectorAll(".proposal-character-row")].map((row) => ({
      name: row.querySelector(".pc-name").value,
      description: row.querySelector(".pc-description").value,
    }));
  }

  // 下書きへ重ねる企画書の値(空の項目はnull=その属性を消す)。名前も説明も空の登場人物は捨てる。
  // 登場人物の一覧は丸ごと置き換わる(識別子の無い仮の設定のため)
  values() {
    const value = (key) => this.container.querySelector(`#pp_${key}`).value.trim() || null;
    const characters = this.readCharacters()
      .map((c) => ({ name: c.name.trim() || null, description: c.description.trim() || null }))
      .filter((c) => c.name || c.description)
      .map((c) => Object.fromEntries(Object.entries(c).filter(([, v]) => v !== null)));
    return { ...Object.fromEntries(PROPOSAL_TEXT_FIELDS.map((key) => [key, value(key)])), characters };
  }
}
