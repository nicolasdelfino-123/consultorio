import json
import math
import os
import uuid
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path


@dataclass
class Session:
    id: str
    patient_code: str
    started_at: str
    duration_seconds: float = 0
    transcript: str = ''

    @classmethod
    def new(cls, code=''):
        return cls(str(uuid.uuid4()), code.strip(), datetime.now().astimezone().isoformat())

    def save(self, path):
        atomic_json(path, {'format': 'consultorio-session', 'version': 1, **asdict(self)})

    @classmethod
    def load(cls, path):
        path = Path(path)
        if path.stat().st_size > 10 * 1024 * 1024:
            raise ValueError('El archivo de sesión es demasiado grande.')
        raw = json.loads(path.read_text(encoding='utf-8'))
        if raw.get('format') != 'consultorio-session' or raw.get('version') != 1:
            raise ValueError('Formato de sesión no compatible.')
        for key in ('id', 'patient_code', 'started_at', 'transcript'):
            if not isinstance(raw.get(key), str):
                raise ValueError('Archivo de sesión incompleto.')
        datetime.fromisoformat(raw['started_at'].replace('Z', '+00:00'))
        uuid.UUID(raw['id'])
        duration = raw.get('duration_seconds')
        if isinstance(duration, bool) or not isinstance(duration, (int, float)) or not math.isfinite(duration) or duration < 0:
            raise ValueError('Duración inválida.')
        return cls(**{key: raw[key] for key in cls.__dataclass_fields__})


def atomic_json(path, value):
    path = Path(path)
    temporary = path.with_name(path.name + '.' + uuid.uuid4().hex + '.tmp')
    try:
        with temporary.open('w', encoding='utf-8') as stream:
            json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def duration_label(seconds):
    seconds = max(0, int(seconds))
    return f'{seconds // 3600:02d}:{seconds // 60 % 60:02d}:{seconds % 60:02d}'
