import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch
from PySide6.QtWidgets import QApplication, QFileDialog, QMessageBox
from docx import Document
from ui.main_window import MainWindow, copy_audio
from services.session import Session

APP = QApplication.instance() or QApplication([])


def finish_worker(window, timeout=10):
    end = time.monotonic() + timeout
    while window.worker is not None and time.monotonic() < end:
        APP.processEvents()
        time.sleep(0.01)
    if window.worker is not None:
        raise AssertionError('Worker did not finish')
    APP.processEvents()


class UITest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.environment = patch.dict(os.environ, {'CONSULTORIO_DATA_DIR': str(self.root / 'data')})
        self.environment.start()
        with patch('ui.main_window.AudioRecorder.devices', return_value=[(0, 'Micrófono de prueba')]):
            self.window = MainWindow()
        self.errors = []
        self.window._error = self.errors.append

    def tearDown(self):
        finish_worker(self.window)
        self.window.dirty = False
        self.window.close()
        self.environment.stop()
        self.temp.cleanup()

    def test_import_preserves_original_and_transcribe_worker_keeps_ui_responsive(self):
        source = self.root / 'celular.m4a'
        source.write_bytes(b'audio-test')
        with patch.object(QFileDialog, 'getOpenFileName', return_value=(str(source), '')):
            self.window._import_audio()
        finish_worker(self.window)
        self.assertTrue(source.exists())
        self.assertNotEqual(self.window.audio, source)
        self.assertEqual(self.window.audio.read_bytes(), b'audio-test')
        self.window.store.add_rule('suicidio', '[S1]')
        self.window._model_directory = lambda: self.root
        for name in ('model.bin', 'config.json', 'tokenizer.json'):
            (self.root / name).touch()
        def fake_transcribe(audio, model, progress):
            time.sleep(0.1)
            progress(50)
            return 'Hay suicidio y texto.', 42
        with patch('ui.main_window.transcribe', side_effect=fake_transcribe):
            self.window._transcribe()
            self.assertFalse(self.window.start_button.isEnabled())
            self.assertIsNotNone(self.window.worker)
            # Events can be processed while inference runs.
            APP.processEvents()
            finish_worker(self.window)
        self.assertEqual(self.window.editor.toPlainText(), 'Hay [S1] y texto.')
        self.assertEqual(self.window.session.duration_seconds, 42)
        self.assertTrue(self.window.export_button.isEnabled())
        self.assertTrue(self.window.audio.exists())
        self.assertEqual(self.errors, [])

    def test_export_applies_rules_to_manual_edits_and_saves_code(self):
        self.window.store.add_rule('COCAINA', '[S2]')
        self.window.code.setText('PAC-009')
        self.window.editor.setPlainText('Texto corregido: COCAÍNA.')
        output = self.root / 'documento.docx'
        with patch.object(QFileDialog, 'getSaveFileName', return_value=(str(output), '')):
            self.assertTrue(self.window._export())
        result = '\n'.join(p.text for p in Document(output).paragraphs)
        self.assertIn('PAC-009', result)
        self.assertIn('Texto corregido: [S2].', result)
        self.assertNotIn('COCAÍNA', result)
        self.assertFalse(self.window.dirty)

    def test_audio_deletion_requires_confirmation_and_persisted_protected_draft(self):
        audio = self.root / 'audio.wav'
        audio.write_bytes(b'audio')
        self.window.audio = audio
        self.window.delete_option.setChecked(True)
        self.window._confirm = lambda *args: False
        self.window._transcribed(('suicidio', 5), [('suicidio', '[S1]')])
        self.assertTrue(audio.exists())
        self.window._confirm = lambda *args: True
        self.window._transcribed(('suicidio', 5), [('suicidio', '[S1]')])
        self.assertFalse(audio.exists())
        draft = self.window.root / 'sesiones' / f'{self.window.session.id}.json'
        self.assertEqual(Session.load(draft).transcript, '[S1]')
        self.assertIsNone(self.window.audio)

    def test_no_audio_deleted_on_empty_text_or_draft_save_failure(self):
        audio = self.root / 'audio.wav'
        audio.touch()
        self.window.audio = audio
        self.window.delete_option.setChecked(True)
        self.window._confirm = lambda *args: True
        self.window._transcribed(('', 5), [])
        self.assertTrue(audio.exists())
        with patch.object(Session, 'save', side_effect=PermissionError('disk')):
            self.window._transcribed(('Texto', 5), [])
        self.assertTrue(audio.exists())
        self.assertEqual(len(self.errors), 1)

    def test_failed_transcription_preserves_audio_and_recovers_controls(self):
        audio = self.root / 'broken.wav'
        audio.touch()
        self.window.audio = audio
        def fail(progress):
            raise ValueError('Audio inválido')
        self.window._run(fail, lambda result: None, 'Prueba')
        finish_worker(self.window)
        self.assertTrue(audio.exists())
        self.assertTrue(self.window.transcribe_button.isEnabled())
        self.assertTrue(self.window.import_button.isEnabled())
        self.assertEqual(self.errors, ['Audio inválido'])

    def test_close_during_work_is_rejected(self):
        from PySide6.QtGui import QCloseEvent
        self.window._run(lambda progress: time.sleep(0.15), lambda result: None, 'Prueba')
        event = QCloseEvent()
        self.window.closeEvent(event)
        self.assertFalse(event.isAccepted())
        finish_worker(self.window)

    def test_cancelled_export_does_not_discard_edited_text(self):
        self.window.editor.setPlainText('Cambios')
        with patch.object(QMessageBox, 'exec', return_value=QMessageBox.StandardButton.Save), \
             patch.object(QFileDialog, 'getSaveFileName', return_value=('', '')):
            self.assertFalse(self.window._discard_check())
        self.assertEqual(self.window.editor.toPlainText(), 'Cambios')

    def test_copy_failure_does_not_remove_original(self):
        source = self.root / 'original.wav'
        source.write_bytes(b'original')
        destination = self.root / 'missing-folder' / 'copy.wav'
        with self.assertRaises(OSError):
            copy_audio(source, destination)
        self.assertEqual(source.read_bytes(), b'original')

    def test_recording_controls_and_stop_worker_preserve_audio(self):
        import wave
        def fake_start(path, device):
            with wave.open(str(path), 'wb') as audio:
                audio.setnchannels(1)
                audio.setsampwidth(2)
                audio.setframerate(16000)
                audio.writeframes(b'\x00\x00' * 2000)
            self.window.recorder.frames = 2000
            self.window.recorder.rate = 16000
        with patch.object(self.window.recorder, 'start', side_effect=fake_start):
            self.window._start()
        self.assertTrue(self.window.recording)
        self.assertTrue(self.window.stop_button.isEnabled())
        self.assertFalse(self.window.import_button.isEnabled())
        self.window._stop()
        finish_worker(self.window)
        self.assertFalse(self.window.recording)
        self.assertTrue(self.window.audio.is_file())
        self.assertEqual(self.window.session.duration_seconds, 0.125)
        self.assertTrue(self.window.transcribe_button.isEnabled())

    def test_settings_write_error_is_reported_without_aborting_ui(self):
        with patch.object(self.window.store, 'set', side_effect=PermissionError('disk')):
            self.assertFalse(self.window._save_setting('model', 'base'))
        self.assertEqual(len(self.errors), 1)
        self.assertTrue(self.window.import_button.isEnabled())


if __name__ == '__main__':
    unittest.main()
