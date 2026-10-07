import os
from pathlib import Path
from services.audio_loader import load_local_audio

# No hub access or telemetry during clinical use, even on missing model files.
os.environ['HF_HUB_OFFLINE'] = '1'
os.environ['HF_HUB_DISABLE_TELEMETRY'] = '1'
os.environ['TRANSFORMERS_OFFLINE'] = '1'


def transcribe(audio, model_directory, progress=lambda value: None):
    directory = Path(model_directory)
    required = ('model.bin', 'config.json', 'tokenizer.json')
    if not all((directory / file).is_file() for file in required):
        raise ValueError('Modelo local incompleto. Preparalo siguiendo README.md antes de transcribir.')
    from faster_whisper import WhisperModel
    import onnxruntime
    onnxruntime.disable_telemetry_events()
    audio_samples = load_local_audio(audio)
    model = WhisperModel(str(directory), device='cpu', compute_type='int8', local_files_only=True)
    segments, info = model.transcribe(audio_samples, language='es', beam_size=5, vad_filter=True,
                                     condition_on_previous_text=False)
    parts = []
    for segment in segments:
        parts.append(segment.text.strip())
        progress(min(99, int(segment.end / max(info.duration, 1) * 100)))
    progress(100)
    return '\n'.join(part for part in parts if part), info.duration
