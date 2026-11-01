"""Conservative, explicit-text contract; no model or storage dependencies."""
import re
from pydantic import BaseModel, ConfigDict, Field

class VideoFields(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    title: str = Field(min_length=1, max_length=200)
    topic: str = Field(min_length=1, max_length=200)
    duration_minutes: int = Field(strict=True, gt=0, le=1440)

PATTERN = re.compile(
    r"\s*(?:Відео\s+|Урок\s+|Назва\s*:\s*)(?P<title>[^,;\n]+?)\s*[,;]\s*"
    r"тема\s*:?\s+(?P<topic>[^,;\n]+?)\s*[,;]\s*"
    r"тривалість\s*:?\s+(?P<duration_minutes>\d+)\s*(?:хвилин|хв)\s*\.?\s*",
    re.IGNORECASE,
)

def explicit_fields(text):
    match = PATTERN.fullmatch(text)
    if not match:
        return None
    fields = match.groupdict()
    fields['duration_minutes'] = int(fields['duration_minutes'])
    try:
        return VideoFields(**fields).model_dump()
    except ValueError:
        return None
