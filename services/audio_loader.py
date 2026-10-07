"""Decode local media only; FFmpeg cannot follow HTTP/HTTPS references."""
import io
from pathlib import Path


def load_local_audio(path, sample_rate=16000):
    import av
    import numpy as np
    path = Path(path)
    if not path.is_file():
        raise ValueError('El archivo de audio no existe.')
    output = io.BytesIO()
    resampler = av.audio.resampler.AudioResampler(format='s16', layout='mono', rate=sample_rate)
    with av.open(str(path), mode='r', metadata_errors='ignore',
                 options={'protocol_whitelist': 'file,pipe'}) as container:
        if not container.streams.audio:
            raise ValueError('El archivo no contiene una pista de audio.')
        for frame in container.decode(audio=0):
            for converted in resampler.resample(frame):
                output.write(converted.to_ndarray().tobytes())
        for converted in resampler.resample(None):
            output.write(converted.to_ndarray().tobytes())
    if output.tell() == 0:
        raise ValueError('El archivo no contiene muestras de audio.')
    return np.frombuffer(output.getbuffer(), dtype=np.int16).astype(np.float32) / 32768.0
