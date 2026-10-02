# core/service/api/voice.py
"""
音声合成の声(話者)の一覧の公開API。プロジェクトの音声合成の設定(project.yamlのgenai.tts)の提供元から取得する。

エラーは例外で返す: project_idが未登録ならProjectNotFoundError、設定・APIキーが無い・提供元が一覧を返せないならValueError、
提供元の呼び出しの失敗はそのまま。
"""

from typing import Optional

from core.infra.store.project_file_store import read_project
from core.infra.store.project_registry_store import resolve_layout
from core.schema.api.voice import VoiceListResult, VoiceSummary
from core.service.process.genai import voice_catalog


def list_voices(project_id: str, language: Optional[str] = None) -> VoiceListResult:
    """languageを渡すと、その言語(ja・ja-JP等。言語の部分が同じもの)の声だけ。"""
    project = read_project(resolve_layout(project_id).root_dir)
    try:
        voices = voice_catalog.list_voices(project, language)
    except NotImplementedError as exc:
        raise ValueError(f"音声合成の提供元({project.tts.client})からは声の一覧を取得できません。") from exc
    return VoiceListResult(
        provider=project.tts.client,
        model=project.tts.model,
        voices=[
            VoiceSummary(
                voice_id=v.voice_id,
                display_name=v.display_name,
                language_code=v.language_code,
                gender=v.gender,
                pitch=v.pitch,
                accent=v.accent,
                persona=v.persona,
                context=v.context,
                description=v.description,
            )
            for v in voices
        ],
    )
