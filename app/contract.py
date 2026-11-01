"""Conservative, explicit-text contract; no model or storage dependencies."""
import re

def free_duration(text):
    if re.search(r'\d+\s*(?:або|чи|[-–/])\s*\d+', text):
        return None
    values = re.findall(r'(?<![\w.])(-?\d+)\s*(?:хвилин(?:а|и)?|хв)(?!\w)', text, re.I)
    if len(values) != 1 or not 1 <= int(values[0]) <= 1440:
        return None
    return int(values[0])

def grounded(fields, text, duration):
    normalize = lambda s: ' '.join(s.casefold().split())
    source = normalize(text)
    return (fields.duration_minutes == duration and
            all(re.search(r'(?<!\w)' + re.escape(normalize(value)) + r'(?!\w)', source)
                for value in (fields.title, fields.topic)))
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
