import json
import tempfile
import unittest
import wave
from pathlib import Path
from unittest.mock import patch

from docx import Document
from database.store import Store
from services.docx_exporter import export_docx
from services.session import Session
from services.text_processor import protect


class ServicesTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def test_protection_whole_words_case_accents_and_longest_phrase(self):
        rules = [('suicidio', '[S1]'), ('cocaína', '[S2]'), ('violencia', '[S3]'), ('violencia familiar', '[S4]')]
        self.assertEqual(protect('SUICIDIO, cocaína; violencia familiar. antisuicidio.', rules),
                         '[S1], [S2]; [S4]. antisuicidio.')

    def test_protection_is_literal_and_does_not_cascade(self):
        self.assertEqual(protect('a+b aab suicidio', [('a+b', '[X]'), ('suicidio', 'violencia'), ('violencia', '[S3]')]),
                         '[X] aab violencia')
        self.assertEqual(protect('İ i ı I', [('i', '[X]')]), '[X] [X] [X] [X]')

    def test_unaccented_rule_protects_accented_transcript_without_changing_other_text(self):
        import unicodedata
        text = 'Sesión: cocaína, COCAINA, Cocaína y ' + unicodedata.normalize('NFD', 'cocaína') + '. cocainas.'
        self.assertEqual(protect(text, [('COCAINA', 'c2')]), 'Sesión: c2, c2, c2 y c2. cocainas.')
        self.assertEqual(protect('cocaina cocaína', [('cocaína', 'c2')]), 'c2 c2')

    def test_accent_insensitivity_preserves_enye_and_whole_words(self):
        import unicodedata
        self.assertEqual(protect('año ano montaña', [('ano', '[A]')]), 'año [A] montaña')
        self.assertEqual(protect(unicodedata.normalize('NFD', 'año'), [('año', '[Y]')]), '[Y]')
        self.assertEqual(protect('suici suicidio antisuicidio', [('suicidio', 'SU1')]), 'suici SU1 antisuicidio')

    def test_equivalent_rules_update_without_accent_duplicates(self):
        store = Store(self.root / 'rules.db')
        store.add_rule('COCAINA', 'c2')
        self.assertEqual(store.find_rule('cocaína'), ('COCAINA', 'c2'))
        store.add_rule('cocaína', '[C2]')
        self.assertEqual(store.rules(), [('cocaína', '[C2]')])
        store.close()

    def test_rules_and_settings_persist_with_unicode_case(self):
        path = self.root / 'test.db'
        store = Store(path)
        store.add_rule('COCAÍNA', '[A]')
        store.add_rule('cocaína', '[B]')
        store.set('model', 'base')
        store.close()
        store = Store(path)
        self.assertEqual(store.get('model'), 'base')
        self.assertEqual(store.rules(), [('cocaína', '[B]')])
        store.delete_rule('COCAÍNA')
        self.assertEqual(store.rules(), [])
        with self.assertRaises(ValueError):
            store.add_rule(' ', 'value')
        store.close()

    def test_word_contains_metadata_and_editable_paragraphs(self):
        session = Session.new('PAC-001')
        session.duration_seconds = 3661
        output = self.root / 'test.docx'
        export_docx(session, 'Texto editado.\nSegunda línea [S1].', output)
        paragraphs = '\n'.join(p.text for p in Document(output).paragraphs)
        for expected in ('PAC-001', 'Fecha:', 'Hora:', '01:01:01', 'Texto editado.', 'Segunda línea [S1].'):
            self.assertIn(expected, paragraphs)

    def test_failed_word_write_preserves_previous_document(self):
        output = self.root / 'test.docx'
        export_docx(Session.new(), 'Original', output)
        before = output.read_bytes()
        with patch('services.docx_exporter.os.replace', side_effect=PermissionError('locked')):
            with self.assertRaises(PermissionError):
                export_docx(Session.new(), 'Cambio', output)
        self.assertEqual(before, output.read_bytes())
        self.assertEqual(list(self.root.glob('*.tmp')), [])
        with self.assertRaises(ValueError):
            export_docx(Session.new(), '', output)

    def test_protected_draft_roundtrip_and_invalid_duration(self):
        session = Session.new('PAC-002')
        session.transcript = 'Protegido [S1]'
        path = self.root / 'draft.json'
        session.save(path)
        self.assertEqual(Session.load(path), session)
        raw = json.loads(path.read_text())
        raw['duration_seconds'] = -1
        path.write_text(json.dumps(raw))
        with self.assertRaises(ValueError):
            Session.load(path)

    def test_local_model_missing_never_requests_download(self):
        from services.transcriber import transcribe
        with self.assertRaisesRegex(ValueError, 'Modelo local incompleto'):
            transcribe(self.root / 'absent.wav', self.root / 'absent-model')

    def test_real_wav_decode_and_resampling(self):
        from services.audio_loader import load_local_audio
        audio = self.root / 'test.wav'
        with wave.open(str(audio), 'wb') as stream:
            stream.setnchannels(1)
            stream.setsampwidth(2)
            stream.setframerate(32000)
            stream.writeframes(b'\x00\x40' * 16000)
        decoded = load_local_audio(audio)
        self.assertEqual(len(decoded), 8000)
        self.assertEqual(str(decoded.dtype), 'float32')
        self.assertAlmostEqual(float(decoded[100]), 0.5, places=3)

    def test_remote_media_references_are_rejected_by_decoder(self):
        import av
        from services.audio_loader import load_local_audio
        playlist = self.root / 'remote.m3u8'
        playlist.write_text('#EXTM3U\n#EXT-X-VERSION:3\n#EXT-X-TARGETDURATION:5\n'
                            '#EXT-X-MEDIA-SEQUENCE:0\n#EXTINF:5,\nhttps://example.invalid/audio.ts\n#EXT-X-ENDLIST\n')
        previous_level = av.logging.get_level()
        av.logging.set_level(av.logging.ERROR)
        try:
            with av.logging.Capture(local=True) as messages:
                with self.assertRaises((av.error.FFmpegError, ValueError)):
                    load_local_audio(playlist)
        finally:
            av.logging.set_level(previous_level)
        self.assertTrue(any('whitelist' in message[2] for message in messages), messages)


class RecorderTest(unittest.TestCase):
    def test_audio_is_streamed_to_valid_wav_and_stop_drains_buffer(self):
        import types
        import sys
        from services.audio_recorder import AudioRecorder
        class Stream:
            def __init__(self, **options):
                self.callback = options['callback']
            def start(self):
                self.callback(b'\x01\x00' * 800, 800, None, None)
                self.callback(b'\x02\x00' * 800, 800, None, None)
            def stop(self):
                pass
            def close(self):
                pass
        fake = types.SimpleNamespace(query_devices=lambda *args: {'default_samplerate': 16000}, RawInputStream=Stream)
        with tempfile.TemporaryDirectory() as folder, patch.dict(sys.modules, {'sounddevice': fake}):
            output = Path(folder) / 'recording.wav'
            recorder = AudioRecorder()
            recorder.start(output)
            self.assertEqual(recorder.stop(), 0.1)
            with wave.open(str(output)) as audio:
                self.assertEqual(audio.getnframes(), 1600)
                self.assertEqual(audio.getnchannels(), 1)
                self.assertEqual(audio.getsampwidth(), 2)
                self.assertEqual(audio.readframes(1600), b'\x01\x00' * 800 + b'\x02\x00' * 800)

    def test_start_failure_closes_writer_and_keeps_partial_audio(self):
        import types
        import sys
        from services.audio_recorder import AudioRecorder
        def fail(**kwargs):
            raise RuntimeError('No microphone')
        fake = types.SimpleNamespace(query_devices=lambda *args: {'default_samplerate': 16000}, RawInputStream=fail)
        with tempfile.TemporaryDirectory() as folder, patch.dict(sys.modules, {'sounddevice': fake}):
            output = Path(folder) / 'recording.wav'
            recorder = AudioRecorder()
            with self.assertRaises(RuntimeError):
                recorder.start(output)
            self.assertIsNone(recorder._thread)
            with wave.open(str(output)) as audio:
                self.assertEqual(audio.getnframes(), 0)


if __name__ == '__main__':
    unittest.main()
