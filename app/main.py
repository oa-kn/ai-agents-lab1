import json
from uuid import uuid4
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, ConfigDict, Field, ValidationError
from app.contract import VideoFields, explicit_fields
from app.ai import extract_video, ModelUnavailable

app = FastAPI(title="AI Agents Lab 1 — Educational Videos", version="1.0")
videos = []

class VideoRecord(VideoFields):
    id: str

class VideoText(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra='forbid')
    text: str = Field(min_length=1, max_length=2000)

def reject(status, reason, http=422):
    raise HTTPException(http, detail={'status': status, 'reason': reason})

def save(fields):
    record = {'id': str(uuid4()), **fields.model_dump()}
    videos.append(record)
    return record

@app.post('/videos', status_code=201, response_model=VideoRecord)
def create_video(video: VideoFields):
    return save(video)

@app.get('/videos', response_model=list[VideoRecord])
def get_videos():
    return videos

@app.post('/videos/ai', status_code=201, response_model=VideoRecord,
          responses={422:{'description':'Уточнення або відхилена пропозиція'},
                     503:{'description':'Модель недоступна; скористайтеся ручним створенням'}})
def create_video_ai(data: VideoText):
    expected = explicit_fields(data.text)
    if expected is None:
        reject('needs_clarification', 'Вкажіть: Відео НАЗВА, тема ТЕМА, тривалість N хвилин (1–1440).')
    try:
        proposal = extract_video(data.text)
    except (ModelUnavailable, TimeoutError):
        reject('model_unavailable', 'Модель недоступна. Додайте відео вручну або повторіть пізніше.', 503)
    if isinstance(proposal, str):
        try:
            proposal = json.loads(proposal)
        except (ValueError, TypeError):
            reject('invalid_proposal', 'Модель повернула неправильний JSON.')
    if proposal is None:
        reject('needs_clarification', 'Модель не визначила всі обов’язкові поля.')
    try:
        fields = VideoFields.model_validate(proposal)
    except ValidationError:
        reject('invalid_proposal', 'Пропозиція не відповідає схемі відео.')
    if fields.model_dump() != expected:
        reject('semantic_mismatch', 'Поля моделі суперечать явно вказаним даним повідомлення.')
    return save(fields)
