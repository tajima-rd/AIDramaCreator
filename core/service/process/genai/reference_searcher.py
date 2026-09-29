# core/service/process/genai/reference_searcher.py
"""
参考資料(Dataset)を検索し、生成AIに渡す文脈を作る(core.genai.ragのQIDMへの統合)。

- 資料は常に検索して渡す(2026-09-29ユーザー決定。長い文脈を扱えるモデルでも丸ごとは渡さない)
- 索引は資料ごとにdatasets/.index/<ファイル名>.npz(core.infra.store.dataset_file_store.index_path)。
  下書きで初めて使うときに作り、資料の中身・名前・埋め込みのモデルが変わっていれば作り直す。
  埋め込みの設定が無ければ、保存済みの索引の埋め込みは使わず語による検索だけにする
- 埋め込みのモデルはプロジェクトの設定(Project.embedding)。未設定なら語による検索だけ
- 語の切り出しは、SudachiPyが入っていれば形態素と2文字ずつ(SudachiTokenizer)、無ければ2文字ずつ
- 問いは複数(ステップの決まった問い・利用者の発言等)を渡し、問いごとに探して順位で統合する。順位は資料ごとに
  付ける(各資料で最も近い断片が同じ点数になる)。論文PDFと補足資料を一緒に探すと、論文のページが上位を占め、
  補足資料の初期分布の表が文脈から外れたため(2026-09-29、Gemma 4での確認)
- **問いを資料の言語にする**(2026-09-29ユーザー決定: 言語が違うときだけ訳す)。利用者と資料の言語の
  組み合わせ(日本語の利用者と英語・日本語の論文、英語の利用者と英語・母国語の論文、言語の違う資料の混在)の
  どれでも語による検索が一致するように:
  - 資料ごとに1回、生成AIに主な言語を判定させ、決まった問い(英語)をその言語に訳させて保存する
    (datasets/.index/<ファイル名>.language.yaml。資料が変わるまで使い回す。新しい決まった問いは追加で訳させる)。
    検索には各資料の言語に訳した決まった問いを使う
  - 利用者の発言は、資料と違う言語で書かれていそうなとき(core.genai.rag.language_differs。生成AIを使わない
    見積もり)だけ、生成AIにその資料の言語で検索語を作らせる。同じ言語なら追加の呼び出しは無い
  - 生成AIを渡さなければ(generator=None)、問いはそのまま使う。埋め込みの設定があれば、言語が違っても意味で
    見つかるため、訳した問いと併用する
"""

import os
from dataclasses import dataclass

from core.genai import EmbeddingGenerator, TextGenerator
from core.genai.rag import (
    ChunkIndex,
    EmbeddingRetriever,
    HybridRetriever,
    LexicalRetriever,
    Retriever,
    Tokenizer,
    build_context,
    index_document,
    language_differs,
    search_many,
)
from core.genai.rag.chunk_index import content_hash
from core.infra.store.dataset_file_store import (
    index_path,
    read_reference_language,
    write_reference_language,
)
from core.infra.store.dataset_registry_store import resolve_filename
from core.project.dataset import file_format
from core.project.project import Project
from core.prompt.reference_search import (
    ReferenceLanguageResponse,
    SearchTermsResponse,
    language_prompt,
    language_request,
    search_terms_prompt,
    search_terms_request,
    translation_request,
)
from core.schema.formats.reference_language import ReferenceLanguage
from core.service.process.genai.generator_builder import build_embedding_generator

# 文脈に入れる候補の数(近い順に、文脈の上限の文字数まで入れる。既定の断片の長さでは8件ほど入る)
CANDIDATES = 20


@dataclass(frozen=True)
class ReferenceContext:
    text: str  # 生成AIに渡す文脈(断片ごとに「### [資料の名前 場所]」の見出し)
    missing: list[str]  # 見つからなかった資料のfile_id
    queries: list[str]  # 検索に使った問い(資料の言語に訳したものを含む)


def default_tokenizer() -> Tokenizer | None:
    """SudachiPyが入っていればSudachiTokenizer、無ければNone(既定の2文字ずつ)。"""
    try:
        from core.genai.rag.sudachi_tokenizer import SudachiTokenizer

        return SudachiTokenizer()
    except ImportError:
        return None


def default_embedder(project: Project) -> EmbeddingGenerator | None:
    return build_embedding_generator(project) if project.embedding is not None else None


def _is_usable(index: ChunkIndex, data: bytes, filename: str, embedder: EmbeddingGenerator | None) -> bool:
    if not index.is_current(data) or index.source != filename:
        return False
    return embedder is None or index.embedding_model == embedder.model_name


def load_or_build_index(
    datasets_dir: str, filename: str, data: bytes, embedder: EmbeddingGenerator | None
) -> ChunkIndex:
    """保存済みの索引が使えればそれを、使えなければ作って保存したものを返す。"""
    path = index_path(datasets_dir, filename)
    if os.path.isfile(path):
        try:
            index = ChunkIndex.load(path)
        except (ValueError, KeyError, OSError):
            index = None  # 形式の版が違う・壊れている索引は作り直す
        if index is not None and _is_usable(index, data, filename, embedder):
            if embedder is None and index.has_embeddings:
                # 埋め込みの設定が無いときは語による検索だけにする(問いを埋め込めないため)
                return ChunkIndex(source=index.source, chunks=index.chunks, source_hash=index.source_hash)
            return index
    index = index_document(filename, data, file_format(filename), embedder=embedder)
    index.save(path)
    return index


def reference_texts(project: Project, file_ids: list[str]) -> list[str]:
    """参考資料のテキスト(断片ごと)。保存済みの索引を使い、無ければ作る(埋め込みは作らない)。
    生成AIの出力に資料に無い文字が無いかの照合に使う(draft_character_checker)。"""
    layout = project.layout
    texts: list[str] = []
    for file_id in file_ids:
        filename = resolve_filename(layout.project_db_path, file_id)
        path = os.path.join(layout.datasets_dir, os.path.basename(filename)) if filename else None
        if not path or not os.path.isfile(path):
            continue
        with open(path, "rb") as f:
            data = f.read()
        index = load_or_build_index(layout.datasets_dir, os.path.basename(filename), data, None)
        texts += [c.text for c in index.chunks]
    return texts


def reference_language(
    datasets_dir: str,
    index: ChunkIndex,
    data: bytes,
    fixed_queries: list[str],
    generator: TextGenerator,
) -> ReferenceLanguage:
    """資料の言語と、決まった問いの訳。保存済みで足りればそれを、足りなければ生成AIに判定・訳させて保存する。"""
    source_hash = content_hash(data)
    saved = read_reference_language(datasets_dir, index.source)
    if saved is not None and saved.source_hash == source_hash:
        untranslated = [q for q in dict.fromkeys(fixed_queries) if q not in saved.queries]
        if not untranslated:
            return saved
        request = translation_request(saved.language, untranslated)
    else:
        saved = None
        untranslated = list(dict.fromkeys(fixed_queries))
        request = language_request("\n\n".join(c.text for c in index.chunks), untranslated)
    response = generator.generate_structured(request, ReferenceLanguageResponse, system_instruction=language_prompt())
    # 訳の数が合わなければ訳せなかった問いは英語のまま使う(次回また訳させる)
    translated = dict(zip(untranslated, response.queries, strict=False)) if response.queries else {}
    result = ReferenceLanguage(
        source_hash=source_hash,
        language=saved.language if saved is not None else response.language.strip() or "unknown",
        queries={**(saved.queries if saved is not None else {}), **{k: v for k, v in translated.items() if v.strip()}},
    )
    write_reference_language(datasets_dir, index.source, result)
    return result


def message_search_terms(
    message: str,
    indexes: list[ChunkIndex],
    languages: dict[str, str],
    lexical: LexicalRetriever,
    generator: TextGenerator,
    looking_for: list[str] | tuple[str, ...] = (),
) -> list[str]:
    """発言と違う言語の資料があれば、生成AIにその言語で検索語を作らせる(無ければ呼ばずに空)。"""
    targets = list(dict.fromkeys(
        languages[index.source] for index in indexes
        if index.source in languages and language_differs(message, index, lexical)
    ))
    if not targets:
        return []
    response = generator.generate_structured(
        search_terms_request(message, targets, looking_for), SearchTermsResponse, system_instruction=search_terms_prompt()
    )
    return [q.query for q in response.queries if q.query.strip()]


def _retriever(lexical: LexicalRetriever, indexes: list[ChunkIndex], embedder: EmbeddingGenerator | None) -> Retriever:
    return lexical if embedder is None else HybridRetriever([lexical, EmbeddingRetriever(indexes, embedder)])


def search_references(
    project: Project,
    file_ids: list[str],
    *,
    fixed_queries: list[str] | tuple[str, ...] = (),
    message: str = "",
    extra_queries: list[str] | tuple[str, ...] = (),
    generator: TextGenerator | None = None,
    translate_ahead: list[str] | tuple[str, ...] = (),
    embedder: EmbeddingGenerator | None = None,
    tokenizer: Tokenizer | None = None,
) -> ReferenceContext:
    """資料を問いで探し、近い断片から文脈を作る。

    - fixed_queries: 決まった問い(英語)。generatorがあれば各資料の言語に訳したものを使う
    - message: 利用者の発言。generatorがあり、資料と違う言語で書かれていそうなら資料の言語の検索語を足す
    - extra_queries: そのまま使う問い(下書きにある名前等、既に資料の言語のもの)
    - translate_ahead: 今は使わないが先に訳しておく決まった問い(後のステップで生成AIを呼ぶ回数を減らす)
    - embedder・tokenizerを省くとプロジェクトの既定
    """
    layout = project.layout
    embedder = embedder if embedder is not None else default_embedder(project)
    tokenizer = tokenizer if tokenizer is not None else default_tokenizer()
    indexes: list[ChunkIndex] = []
    contents: list[bytes] = []
    missing: list[str] = []
    for file_id in file_ids:
        filename = resolve_filename(layout.project_db_path, file_id)
        path = os.path.join(layout.datasets_dir, os.path.basename(filename)) if filename else None
        if not path or not os.path.isfile(path):
            missing.append(file_id)
            continue
        with open(path, "rb") as f:
            data = f.read()
        indexes.append(load_or_build_index(layout.datasets_dir, os.path.basename(filename), data, embedder))
        contents.append(data)
    if not indexes:
        return ReferenceContext(text="", missing=missing, queries=[])

    lexical = LexicalRetriever(indexes, tokenizer)
    queries = list(fixed_queries)
    message_queries: list[str] = []
    if generator is not None:
        to_translate = [*fixed_queries, *translate_ahead]
        languages = {
            index.source: reference_language(layout.datasets_dir, index, data, to_translate, generator)
            for index, data in zip(indexes, contents, strict=True)
        }
        queries = [languages[index.source].queries.get(q, q) for index in indexes for q in fixed_queries]
        if message.strip():
            message_queries = message_search_terms(
                message, indexes, {k: v.language for k, v in languages.items()}, lexical, generator, fixed_queries
            )
    queries = list(dict.fromkeys(q for q in [*queries, message, *message_queries, *extra_queries] if q.strip()))
    # 資料ごとに順位を付ける: 長い論文の断片が、短い補足資料の必要な表を文脈から締め出さないように
    hits = search_many(_retriever(lexical, indexes, embedder), queries, top_k=CANDIDATES, per_source=True)
    return ReferenceContext(text=build_context(hits), missing=missing, queries=queries)
