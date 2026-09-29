# core/project/__init__.py
"""
プロジェクトの定義(静的な状態の定義。docs/architecture.md「ファイルの命名規則」のA)。

- project: Project(project.yamlに対応する集約の根)とProjectLayout(構成要素の所在)
- dataset: Dataset(datasets/配下のCSVとサイドカーのデータメタデータYAML)

登録・所在の解決・作成・更新・Datasetのファイル操作等の操作は、core.infra.store
(project_registry_store/project_file_store/dataset_file_store)とcore.service.process
(edit/)にある。
"""
