import os
import re

from pydantic import BaseModel, Field
from enum import Enum
from typing import Optional, List, Union
from pathlib import Path

class AudioTag(Enum):
    AMAZED = "[amazed]"
    CRYING = "[crying]"
    CURIOUS = "[curious]"
    EXCITED = "[excited]"
    SIGHS = "[sighs]"
    GASP = "[gasp]"
    GIGGLES = "[giggles]"
    LAUGHS = "[laughs]"
    MISCHIEVOUSLY = "[mischievously]"
    PANICKED = "[panicked]"
    SARCASTIC = "[sarcastic]"
    SERIOUS = "[serious]"
    SHOUTING = "[shouting]"
    TIRED = "[tired]"
    TREMBLING = "[trembling]"
    WHISPERS = "[whispers]"
    VERY_FAST = "[very_fast]"
    VERY_SLOW = "[very_slow]"

    @classmethod
    def get_all_values(cls):
        return {item.value for item in cls}

class GeminiVoice(Enum):
    # ID = (Display Name for API, Gender, Character Description)
    ZEPHYR = ("Zephyr", "Female", "Bright")
    PUCK = ("Puck", "Male", "Upbeat")
    CHARON = ("Charon", "Male", "Informative")
    KORE = ("Kore", "Female", "Firm")
    FENRIR = ("Fenrir", "Male", "Excitable")
    LEDA = ("Leda", "Female", "Youthful")
    ORUS = ("Orus", "Male", "Firm")
    AOEDE = ("Aoede", "Female", "Breezy")
    CALLIRRHOE = ("Callirrhoe", "Female", "Easy-going")
    AUTONOE = ("Autonoe", "Female", "Bright")
    ENCELADUS = ("Enceladus", "Male", "Breathy")
    IAPETUS = ("Iapetus", "Male", "Clear")
    UMBRIEL = ("Umbriel", "Male", "Easy-going")
    ALGENIB = ("Algenib", "Male", "Gravelly")
    DESPINA = ("Despina", "Female", "Smooth")
    ERINOME = ("Erinome", "Female", "Clear")
    LAOMEDEIA = ("Laomedeia", "Female", "Upbeat")
    ACHERNAR = ("Achernar", "Female", "Soft")
    ALGIEBA = ("Algieba", "Male", "Smooth")
    SCHEDAR = ("Schedar", "Male", "Even")
    GACRUX = ("Gacrux", "Female", "Mature")
    PULCHERRIMA = ("Pulcherrima", "Female", "Forward")
    ACHIRD = ("Achird", "Male", "Friendly")
    ZUBENELGENUBI = ("Zubenelgenubi", "Male", "Casual")
    VINDEMIATRIX = ("Vindemiatrix", "Female", "Gentle")
    SADACHBIA = ("Sadachbia", "Male", "Lively")
    SADALTAGER = ("Sadaltager", "Male", "Knowledgeable")
    SULAFAT = ("Sulafat", "Female", "Warm")
    ALNILAM = ("Alnilam", "Male", "Firm")
    RASALGETHI = ("Rasalgethi", "Male", "Informative")

    @property
    def voice_name(self) -> str:
        """The exact string required by the Google GenAI API."""
        return self.value[0]

    @property
    def gender(self) -> str:
        """The perceived gender of the voice."""
        return self.value[1]

    @property
    def description(self) -> str:
        """Human-readable characteristics for reference."""
        return self.value[2]

    def __str__(self):
        return f"{self.voice_name} ({self.gender}, {self.description})"

class DirectorNotes(BaseModel):
    # Required attributes
    style: str = Field(..., description="Specific vocal style instructions")
    pace: str = Field(..., description="Speed and cadence of delivery")

    # Optional attributes
    dynamics: Optional[str] = Field(default=None, description="Instructions for volume and emphasis")

class Actor(BaseModel):
    # Required attributes
    character_name: str = Field(..., description="Name of the character")
    voice: GeminiVoice = Field(..., description="Selected Gemini prebuilt voice")
    label: str = Field(..., description="Label for the character")
    gender: str = Field(..., description="Gender of the character")
    personality_title: str = Field(..., description="Short archetype title, e.g., 'The Morning Hype'")

    # Optional attributes
    personality_description: Optional[str] = Field(default=None, description="Detailed personality traits")
    accent: str = Field(default="General English", description="Character's accent")

    @property
    def character_name(self) -> str:
        return self.character_name
    
    @property
    def voice_name(self) -> str:
        # Access the voice_name property from the updated 3-item tuple Enum structure
        return self.voice.voice_name
    @property
    def label(self) -> str:
        return self.label
    
    @property
    def gender(self) -> str:
        return self.gender

    def get_character_map(self):
        return [self.character_name, self.label]

class Transcript(BaseModel):
    # Required attributes
    actor: Actor = Field(...)
    directors_note: DirectorNotes = Field(...)
    scene_description: str = Field(..., alias="scene", description="Visual and situational context")
    context: str = Field(..., description="The format or high-level setting")
    text: str = Field(..., description="The actual text to be spoken")
    order: int = Field(default=0, description="Sequential order in a scene")

    def check_transcript_tags(self):
        found_tags = re.findall(r"\[.*?\\?\]", self.text)
        recommended = AudioTag.get_all_values()
        for tag in found_tags:
            if tag not in recommended:
                print(f"Warning: Unknown or custom tag found: {tag}. (Recommended tags: {sorted(list(recommended))})")
    
class Scene(BaseModel):
    # Required attributes
    scene_id: str = Field(..., description="Unique identifier for the scene")
    title: str = Field(..., description="Title of the scene")
    transcript: List[Transcript] = Field(..., description="")

    # Optional attributes
    # prompts: List[Transcript] = Field(default_factory=list, description="List of audio prompts in the scene")

    # def add_prompt(self, prompt: Transcript):
    #     self.prompts.append(prompt)

    def export_json(self, target: Optional[Union[str, Path]] = None, indent: int = 2) -> Optional[str]:
        """Returns JSON string if target is None, else writes to the provided path."""
        json_data = self.model_dump_json(indent=indent, by_alias=True)
        if target:
            Path(target).write_text(json_data, encoding="utf-8")
            print(f"Scene exported to: {target}")
            return None
        return json_data

    @classmethod
    def import_json(cls, source: Union[str, Path]) -> "Scene":
        """Intelligently imports from a raw JSON string or a file path."""
        if isinstance(source, Path) or (isinstance(source, str) and os.path.exists(source)):
            return cls.model_validate_json(Path(source).read_text(encoding="utf-8"))
        return cls.model_validate_json(source)

