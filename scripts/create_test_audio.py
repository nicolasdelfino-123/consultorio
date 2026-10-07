"""Ubuntu-only development fixture: synthesize fictional speech locally with eSpeak."""
import ctypes
import ctypes.util
import sys
import os
import wave
from pathlib import Path


def create(path):
    library = ctypes.util.find_library('espeak-ng') or ctypes.util.find_library('espeak')
    if not library:
        raise RuntimeError('Esta herramienta opcional requiere espeak-ng; no es una dependencia de la app.')
    engine = ctypes.CDLL(library)
    engine.espeak_Initialize.argtypes = [ctypes.c_int, ctypes.c_int, ctypes.c_char_p, ctypes.c_int]
    data_directory = os.environ.get('CONSULTORIO_ESPEAK_DATA')
    rate = engine.espeak_Initialize(2, 0, os.fsencode(data_directory) if data_directory else None, 0)
    if rate <= 0:
        raise RuntimeError('No se pudo inicializar eSpeak.')
    chunks = []
    callback_type = ctypes.CFUNCTYPE(ctypes.c_int, ctypes.POINTER(ctypes.c_short), ctypes.c_int, ctypes.c_void_p)
    @callback_type
    def callback(samples, count, events):
        if samples and count:
            chunks.append(ctypes.string_at(samples, count * 2))
        return 0
    engine.espeak_SetSynthCallback.argtypes = [callback_type]
    engine.espeak_SetSynthCallback(callback)
    engine.espeak_SetVoiceByName.argtypes = [ctypes.c_char_p]
    if engine.espeak_SetVoiceByName(b'es') != 0:
        raise RuntimeError('Falta la voz española de eSpeak.')
    engine.espeak_SetParameter(1, 145, 0)
    text = ('Esta es una prueba de transcripción local en español. '
            'Las palabras de prueba son suicidio, cocaína y violencia. '
            'La grabación se guarda en la computadora. Fin de la prueba.').encode('utf-8')
    engine.espeak_Synth.argtypes = [ctypes.c_void_p, ctypes.c_size_t, ctypes.c_uint, ctypes.c_int,
                                  ctypes.c_uint, ctypes.c_uint, ctypes.c_void_p, ctypes.c_void_p]
    buffer = ctypes.create_string_buffer(text)
    if engine.espeak_Synth(buffer, len(text) + 1, 0, 1, 0, 1, None, None) != 0:
        raise RuntimeError('No se pudo sintetizar el audio.')
    engine.espeak_Synchronize()
    engine.espeak_Terminate()
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), 'wb') as audio:
        audio.setnchannels(1)
        audio.setsampwidth(2)
        audio.setframerate(rate)
        audio.writeframes(b''.join(chunks))
    print(f'Audio ficticio local generado en {path}')


if __name__ == '__main__':
    create(sys.argv[1] if len(sys.argv) > 1 else 'data/prueba_es.wav')
