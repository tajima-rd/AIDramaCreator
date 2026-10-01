# core/schema/api/__init__.py
"""
core と api の間でやり取りされるAPIリクエスト/レスポンスの型。

1つの型は必ずcore/service/apiの1つの関数(=1つの処理)に対応させ、複数の処理の
結果を1つにまとめた型は作らない。ディスクに永続化されるYAMLファイル形式の
スキーマ(core.schema.formats)とは別物。ファイルはcore/service/api・api/routersと同じリソース単位。
"""

from .agent_default import AgentDefaultListResult
from .dataset import (
    DatasetContent,
    DatasetDeleteResult,
    DatasetFileLocation,
    DatasetFileUploadRequest,
    DatasetListResult,
    DatasetMetadataUpdateRequest,
    DatasetSummary,
)
from .drama_draft import (
    DramaDraftChangeResult,
    DramaDraftConfirmRequest,
    DramaDraftConfirmResult,
    DramaDraftCreateRequest,
    DramaDraftImportPathRequest,
    DramaDraftInfo,
    DramaDraftListResult,
    DramaDraftRevisionListResult,
    DramaDraftRevisionSummary,
)
from .drama_model import DramaModelVersionListResult, DramaModelVersionSummary
from .preference import (
    ApiKeyInfo,
    ApiKeyUpdateRequest,
    ApiUrlCandidateInfo,
    ApiUrlCandidateListResult,
    EmbeddingConnectionTestRequest,
    EmbeddingConnectionTestResult,
    GenaiClientInfo,
    GenaiSettingInfo,
    LlmConnectionTestRequest,
    LlmConnectionTestResult,
    ModelListRequest,
    ModelListResult,
    PreferenceInfo,
    PreferenceUpdateRequest,
)
from .project import (
    ProjectCreateRequest,
    ProjectInfo,
    ProjectListResult,
    ProjectOpenRequest,
    ProjectPropertiesUpdateRequest,
    ProjectSaveAsRequest,
    ProjectUpdatePathRequest,
)

__all__ = [
    "AgentDefaultListResult",
    "DramaDraftChangeResult",
    "DramaDraftConfirmRequest",
    "DramaDraftConfirmResult",
    "DramaDraftCreateRequest",
    "DramaDraftImportPathRequest",
    "DramaDraftInfo",
    "DramaDraftListResult",
    "DramaDraftRevisionListResult",
    "DramaDraftRevisionSummary",
    "DramaModelVersionListResult",
    "DramaModelVersionSummary",
    "DatasetContent",
    "DatasetDeleteResult",
    "DatasetFileLocation",
    "DatasetFileUploadRequest",
    "DatasetListResult",
    "DatasetMetadataUpdateRequest",
    "DatasetSummary",
    "ApiKeyInfo",
    "ApiKeyUpdateRequest",
    "ApiUrlCandidateInfo",
    "ApiUrlCandidateListResult",
    "EmbeddingConnectionTestRequest",
    "EmbeddingConnectionTestResult",
    "GenaiClientInfo",
    "GenaiSettingInfo",
    "LlmConnectionTestRequest",
    "LlmConnectionTestResult",
    "ModelListRequest",
    "ModelListResult",
    "PreferenceInfo",
    "PreferenceUpdateRequest",
    "ProjectCreateRequest",
    "ProjectInfo",
    "ProjectListResult",
    "ProjectOpenRequest",
    "ProjectPropertiesUpdateRequest",
    "ProjectSaveAsRequest",
    "ProjectUpdatePathRequest",
]
