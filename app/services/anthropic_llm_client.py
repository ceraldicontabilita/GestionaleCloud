"""
Stub locale che emula emergentintegrations.llm.chat usando anthropic diretto.
Permette di girare su Render senza il pacchetto proprietario di Emergent.
"""
import os
import base64
import anthropic
from dataclasses import dataclass, field
from typing import Optional

DEFAULT_MODEL = "claude-opus-4-5"

@dataclass
class ImageContent:
    image_data: str  # base64
    mime_type: str = "image/jpeg"

@dataclass 
class FileContentWithMimeType:
    file_data: str  # base64
    mime_type: str = "application/pdf"

@dataclass
class UserMessage:
    content: str
    images: list = field(default_factory=list)
    files: list = field(default_factory=list)

class LlmChat:
    def __init__(self, api_key: str, session_id: str = "", system_prompt: str = "", model: str = DEFAULT_MODEL):
        self.api_key = api_key
        self.system_prompt = system_prompt
        self.model = model
        self._client = anthropic.Anthropic(api_key=api_key)

    def with_model(self, provider: str, model: str):
        self.model = model
        return self

    async def send_message(self, message: UserMessage) -> str:
        content = []

        # Immagini
        for img in getattr(message, "images", []):
            content.append({
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": img.mime_type,
                    "data": img.image_data,
                }
            })

        # File (PDF)
        for f in getattr(message, "files", []):
            content.append({
                "type": "document",
                "source": {
                    "type": "base64",
                    "media_type": f.mime_type,
                    "data": f.file_data,
                }
            })

        content.append({"type": "text", "text": message.content})

        kwargs = {
            "model": self.model,
            "max_tokens": 4096,
            "messages": [{"role": "user", "content": content}],
        }
        if self.system_prompt:
            kwargs["system"] = self.system_prompt

        response = self._client.messages.create(**kwargs)
        return response.content[0].text
