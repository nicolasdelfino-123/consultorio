import queue
import threading
import wave


class AudioRecorder:
    """Bounded audio buffer; file writes happen outside PortAudio callback."""
    def __init__(self):
        self.stream = None
        self.error = None
        self.frames = 0
        self.rate = 16000
        self._queue = queue.Queue(maxsize=256)
        self._done = threading.Event()
        self._thread = None

    @staticmethod
    def devices():
        import sounddevice as sd
        return [(i, device['name']) for i, device in enumerate(sd.query_devices()) if device['max_input_channels'] > 0]

    @property
    def duration(self):
        return self.frames / self.rate

    def start(self, path, device=None):
        import sounddevice as sd
        self.error = None
        self.frames = 0
        self._done.clear()
        self._queue = queue.Queue(maxsize=256)
        details = sd.query_devices(device, 'input')
        self.rate = int(details['default_samplerate'])
        self._file = wave.open(str(path), 'wb')
        self._file.setnchannels(1)
        self._file.setsampwidth(2)
        self._file.setframerate(self.rate)
        self._thread = threading.Thread(target=self._write, daemon=True)
        self._thread.start()
        try:
            self.stream = sd.RawInputStream(samplerate=self.rate, channels=1, dtype='int16',
                                            device=device, callback=self._callback)
            self.stream.start()
        except Exception:
            self.stop()
            raise

    def _callback(self, data, frames, timing, status):
        if status:
            self.error = 'El micrófono perdió muestras. El audio puede estar incompleto.'
        try:
            self._queue.put_nowait(bytes(data))
        except queue.Full:
            self.error = 'El disco no pudo guardar audio a tiempo. La grabación está incompleta.'
            import sounddevice as sd
            raise sd.CallbackAbort

    def _write(self):
        try:
            while not self._done.is_set() or not self._queue.empty():
                try:
                    data = self._queue.get(timeout=0.1)
                except queue.Empty:
                    continue
                # Update the WAV header while recording so a partial capture is
                # readable even if the process is interrupted before normal stop.
                self._file.writeframes(data)
                self.frames += len(data) // 2
        except Exception:
            self.error = 'No se pudo guardar el audio. Revisá espacio y permisos del disco.'
        finally:
            try:
                self._file.close()
            except Exception:
                self.error = 'No se pudo finalizar el archivo de audio. Revisá el disco.'

    def stop(self):
        try:
            if self.stream:
                try:
                    self.stream.stop()
                finally:
                    self.stream.close()
        except Exception:
            self.error = 'Se perdió la conexión con el micrófono. Se conserva el audio disponible.'
        finally:
            self.stream = None
            self._done.set()
            if self._thread:
                self._thread.join()
                self._thread = None
        return self.duration
