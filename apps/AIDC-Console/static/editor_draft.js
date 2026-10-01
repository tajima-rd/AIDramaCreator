"use strict";
/*
 * EditorDraft — Dramaturgy Editorと人物パネル(Character Editor)が共有する、編集用の下書き(題がEDITOR_DRAFT_TITLEの、
 * openな下書き。プロジェクトに1つ)。正本を変えるのは下書きの確定だけ(docs/architecture.md 7節)なので、両パネルはこれを通して編集する:
 * - 各タブのSaveは、変えた部分だけの部分YAMLを下書きへの直接編集(POST .../edit)として送る
 * - ヘッダーのSave Versionで下書きを確定し、版を1つ作る。確定した後は、新しい版を元に編集用の下書きを作り直す
 * - 下書きの元にした版が今の版より古ければ確定できない(409)。変更の無い古い下書きは黙って作り直し、
 *   変更があれば破棄してよいかを確かめる
 * apiFetchをグローバル利用する。
 */

const EDITOR_DRAFT_TITLE = "Dramaturgy Editor";

// 編集用の下書き(無ければnull)と、その変更の数(作成の行を除いた履歴の数)
async function findEditorDraft(projectId) {
  const result = await apiFetch(`/projects/${projectId}/drama-drafts?status=open`);
  const draft = (result.drafts || []).find((d) => d.title === EDITOR_DRAFT_TITLE) || null;
  if (!draft) return { draft: null, changeCount: 0 };
  const revisions = await apiFetch(`/projects/${projectId}/drama-drafts/${draft.draft_id}/revisions`);
  return { draft, changeCount: Math.max(0, (revisions.revisions || []).length - 1) };
}

class EditorDraft {
  constructor(projectId) {
    this.projectId = projectId;
    this.draftId = null;
    this.currentVersion = null; // 確定した最新の版(未確定ならnull)
    this.changeCount = 0; // 編集用の下書きにある、まだ確定していない変更の数
  }

  base() {
    return `/projects/${this.projectId}/drama-drafts/${this.draftId}`;
  }

  // 編集用の下書きを用意する(再開・作り直し・新規)。利用者が破棄を断ればfalse。
  async ensure() {
    const versions = await apiFetch(`/projects/${this.projectId}/drama-model/versions`);
    this.currentVersion = versions.current_version ?? null;
    const { draft, changeCount } = await findEditorDraft(this.projectId);
    if (draft && (draft.base_version ?? null) === this.currentVersion) {
      this.draftId = draft.draft_id;
      this.changeCount = changeCount;
      return true;
    }
    if (draft) {
      if (
        changeCount > 0 &&
        !confirm(
          `編集用の下書きは古い版(v${draft.base_version ?? "-"})を元にしているため確定できません。` +
            `まだ確定していない変更(${changeCount}件)を破棄して、今の版(v${this.currentVersion})から開き直しますか?`
        )
      ) {
        return false;
      }
      await apiFetch(`/projects/${this.projectId}/drama-drafts/${draft.draft_id}/discard`, { method: "POST" });
    }
    await this.create();
    return true;
  }

  async create() {
    const created = await apiFetch(`/projects/${this.projectId}/drama-drafts`, {
      method: "POST",
      bodyObj: { title: EDITOR_DRAFT_TITLE },
    });
    this.draftId = created.draft_id;
    this.changeCount = 0;
  }

  // 下書きの中身(モデル定義YAMLの対応表)
  async content() {
    return apiFetch(`${this.base()}/content`);
  }

  // 部分YAMLを下書きに重ねる(直接編集)
  async edit(patch) {
    await apiFetch(`${this.base()}/edit`, { method: "POST", bodyObj: patch });
    this.changeCount += 1;
  }

  // サーバー側で下書きを変えた(生成AIの提案のApply等)ときに、未確定の変更を数える
  noteChange() {
    this.changeCount += 1;
  }

  versionLabel() {
    const version = this.currentVersion === null ? "未確定" : `v${this.currentVersion}`;
    return version + (this.changeCount > 0 ? ` · 未確定の変更 ${this.changeCount}件` : "");
  }

  // Save Versionのボタンのクラス(変更が無ければグレー、確定していない変更があれば緑)
  versionButtonClass() {
    return this.changeCount > 0 ? "btn btn-version-pending" : "btn btn-version-clean";
  }

  // 下書きを確定し、新しい版から下書きを作り直す。確定した版の番号(変更が無ければnull)を返す。
  async confirm() {
    if (this.changeCount === 0) return null;
    const result = await apiFetch(`${this.base()}/confirm`, { method: "POST", bodyObj: {} });
    this.currentVersion = result.version;
    await this.create();
    return result.version;
  }
}
