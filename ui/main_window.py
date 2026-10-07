from datetime import datetime
from pathlib import Path
import shutil
import uuid

from PySide6.QtCore import QThread, Signal, QTimer, Qt
from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QTextEdit, QComboBox, QCheckBox, QProgressBar, QMessageBox,
    QFileDialog, QTabWidget, QTableWidget, QTableWidgetItem, QHeaderView,
    QAbstractItemView, QFormLayout, QGroupBox,
)
from database.store import Store
from services.audio_recorder import AudioRecorder
from services.docx_exporter import export_docx
from services.paths import data_root, model_root
from services.session import Session, duration_label
from services.text_processor import protect
from services.transcriber import transcribe


class Worker(QThread):
    result = Signal(object)
    failed = Signal(str)
    progress = Signal(int)

    def __init__(self, job, parent=None):
        super().__init__(parent)
        self.job = job

    def run(self):
        try:
            self.result.emit(self.job(self.progress.emit))
        except Exception as error:
            # Errors are displayed locally; no clinical data is sent or logged.
            self.failed.emit(str(error) or type(error).__name__)


def copy_audio(source, destination):
    temporary = destination.with_suffix(destination.suffix + '.partial')
    try:
        shutil.copyfile(source, temporary)
        temporary.replace(destination)
    finally:
        temporary.unlink(missing_ok=True)
    return destination


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.root = data_root()
        self.store = Store(self.root / 'config.sqlite3')
        self.recorder = AudioRecorder()
        self.session = Session.new()
        self.audio = None
        self.recording = False
        self.worker = None
        self.dirty = False
        self.setWindowTitle('Asistente de Consultorio')
        self.resize(1000, 770)
        self.setMinimumSize(740, 580)
        self._build()
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._tick)
        self.timer.start(200)
        self._refresh_devices()
        self._refresh_rules()
        self._refresh_metadata()
        self._controls()

    def _build(self):
        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        layout.setContentsMargins(26, 22, 26, 22)
        heading = QLabel('Asistente de Consultorio')
        heading.setObjectName('heading')
        layout.addWidget(heading)
        layout.addWidget(QLabel('Grabación y transcripción en español · Procesamiento local'))
        self.tabs = QTabWidget()
        layout.addWidget(self.tabs)
        session_tab = QWidget()
        self.tabs.addTab(session_tab, 'Consulta')
        session_layout = QVBoxLayout(session_tab)
        form = QFormLayout()
        self.code = QLineEdit()
        self.code.setPlaceholderText('Opcional, por ejemplo PAC-001')
        self.code.setMaxLength(100)
        self.metadata = QLabel()
        form.addRow('Código de paciente', self.code)
        form.addRow('Sesión', self.metadata)
        session_layout.addLayout(form)
        audio_box = QGroupBox('1. Grabar o seleccionar un audio')
        audio_layout = QVBoxLayout(audio_box)
        microphone_row = QHBoxLayout()
        self.microphone = QComboBox()
        self.microphone.setPlaceholderText('Sin micrófono disponible')
        self.microphone.setMinimumWidth(200)
        self.refresh_devices = QPushButton('Actualizar micrófonos')
        self.refresh_devices.clicked.connect(self._refresh_devices)
        microphone_row.addWidget(QLabel('Micrófono'))
        microphone_row.addWidget(self.microphone, 1)
        microphone_row.addWidget(self.refresh_devices)
        audio_layout.addLayout(microphone_row)
        buttons = QHBoxLayout()
        self.start_button = QPushButton('Comenzar grabación')
        self.start_button.clicked.connect(self._start)
        self.stop_button = QPushButton('Finalizar grabación')
        self.stop_button.clicked.connect(self._stop)
        self.import_button = QPushButton('Seleccionar archivo de audio…')
        self.import_button.clicked.connect(self._import_audio)
        for button in (self.start_button, self.stop_button, self.import_button):
            buttons.addWidget(button)
        audio_layout.addLayout(buttons)
        self.audio_label = QLabel('Sin audio seleccionado')
        self.audio_label.setWordWrap(True)
        audio_layout.addWidget(self.audio_label)
        session_layout.addWidget(audio_box)
        row = QHBoxLayout()
        self.transcribe_button = QPushButton('2. Transcribir')
        self.transcribe_button.setObjectName('primary')
        self.transcribe_button.clicked.connect(self._transcribe)
        self.duration = QLabel('Duración: 00:00:00')
        row.addWidget(self.transcribe_button)
        row.addWidget(self.duration)
        row.addStretch()
        session_layout.addLayout(row)
        self.progress = QProgressBar()
        self.progress.setVisible(False)
        session_layout.addWidget(self.progress)
        session_layout.addWidget(QLabel('3. Revisar y editar la transcripción'))
        self.editor = QTextEdit()
        self.editor.setAcceptRichText(False)
        self.editor.setPlaceholderText('La transcripción aparecerá aquí. Revisala antes de exportar.')
        self.editor.textChanged.connect(self._edited)
        self.code.textChanged.connect(self._code_edited)
        session_layout.addWidget(self.editor, 1)
        self.delete_option = QCheckBox('Ofrecer eliminar la copia local del audio después de transcribir')
        self.delete_option.setChecked(self.store.get('offer_delete', '0') == '1')
        self.delete_option.toggled.connect(lambda value: self._save_setting('offer_delete', '1' if value else '0'))
        session_layout.addWidget(self.delete_option)
        row = QHBoxLayout()
        self.new_button = QPushButton('Nueva consulta')
        self.new_button.clicked.connect(self._new_session)
        self.export_button = QPushButton('4. Exportar a Word…')
        self.export_button.setObjectName('primary')
        self.export_button.clicked.connect(self._export)
        row.addWidget(self.new_button)
        row.addStretch()
        row.addWidget(self.export_button)
        session_layout.addLayout(row)
        settings_tab = QWidget()
        self.tabs.addTab(settings_tab, 'Configuración y palabras protegidas')
        settings_layout = QVBoxLayout(settings_tab)
        model_box = QGroupBox('Transcripción local')
        model_form = QFormLayout(model_box)
        self.model = QComboBox()
        self.model.addItems(['base', 'small', 'medium'])
        selected = self.store.get('model', 'small')
        self.model.setCurrentText(selected if selected in ('base', 'small', 'medium') else 'small')
        self.model.currentTextChanged.connect(self._model_changed)
        model_form.addRow('Modelo', self.model)
        self.model_path = QLabel()
        self.model_path.setWordWrap(True)
        model_form.addRow('Carpeta local', self.model_path)
        self.choose_model = QPushButton('Elegir carpeta del modelo…')
        self.choose_model.clicked.connect(self._choose_model)
        model_form.addRow(self.choose_model)
        note = QLabel('base: menor consumo · small: punto de partida · medium: más recursos.\n'
                      'La aplicación no descarga modelos. Preparalos siguiendo README.md.')
        note.setWordWrap(True)
        model_form.addRow(note)
        settings_layout.addWidget(model_box)
        settings_layout.addWidget(QLabel('Palabras protegidas'))
        rules_note = QLabel('Palabras o frases completas, sin distinguir mayúsculas ni tildes en vocales.\n'
                            'Se aplican al mostrar la transcripción y nuevamente al exportar.\n'
                            'El audio conserva las palabras originales; estos reemplazos no anonimizan toda la consulta.')
        rules_note.setWordWrap(True)
        settings_layout.addWidget(rules_note)
        self.rules_table = QTableWidget(0, 2)
        self.rules_table.setHorizontalHeaderLabels(['Palabra o frase', 'Reemplazo'])
        self.rules_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.rules_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.rules_table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.rules_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        settings_layout.addWidget(self.rules_table, 1)
        row = QHBoxLayout()
        self.term = QLineEdit()
        self.term.setPlaceholderText('Ejemplo: suicidio')
        self.replacement = QLineEdit()
        self.replacement.setPlaceholderText('Ejemplo: [S1]')
        self.term.setMaxLength(200)
        self.replacement.setMaxLength(200)
        self.add_rule_button = QPushButton('Guardar regla')
        self.add_rule_button.clicked.connect(self._add_rule)
        self.remove_rule_button = QPushButton('Eliminar seleccionada')
        self.remove_rule_button.clicked.connect(self._delete_rule)
        for widget in (self.term, self.replacement, self.add_rule_button, self.remove_rule_button):
            row.addWidget(widget)
        settings_layout.addLayout(row)
        folder = QLabel(f'Datos locales: {self.root}')
        folder.setWordWrap(True)
        settings_layout.addWidget(folder)
        self.status = QLabel('Listo para comenzar')
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        self.setStyleSheet('''
            QMainWindow { background: #f4f7fb; }
            QWidget { color: #183044; font-size: 14px; }
            QLabel#heading { font-size: 26px; font-weight: 600; }
            QLineEdit, QTextEdit, QComboBox, QTableWidget { background: white; border: 1px solid #bac9d4; border-radius: 5px; padding: 6px; }
            QPushButton { background: #e4edf3; border: 1px solid #b9cbd8; border-radius: 5px; padding: 9px 12px; }
            QPushButton:hover { background: #d1e3ee; }
            QPushButton#primary { background: #16677a; color: white; border: none; }
            QPushButton:disabled { background: #e4e8eb; color: #88969e; }
            QPushButton#primary:disabled { background: #e4e8eb; color: #88969e; }
            QGroupBox { border: 1px solid #cbd6df; border-radius: 7px; margin-top: 12px; padding-top: 14px; }
            QTabWidget::pane { border: 1px solid #cbd6df; background: #f4f7fb; }
            QTabBar::tab { padding: 10px 15px; }
        ''')
        self._update_model_label()

    def _error(self, message):
        QMessageBox.critical(self, 'No se pudo completar la operación', message)

    def _save_setting(self, key, value):
        try:
            self.store.set(key, value)
            return True
        except Exception as error:
            self._error(f'No se pudo guardar la configuración. Revisá permisos y espacio en disco.\n{error}')
            return False

    def _confirm(self, title, message):
        return QMessageBox.question(self, title, message, QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                                    QMessageBox.StandardButton.No) == QMessageBox.StandardButton.Yes

    def _controls(self):
        busy = self.worker is not None
        free = not busy and not self.recording
        self.start_button.setEnabled(free and self.microphone.count() > 0)
        self.stop_button.setEnabled(self.recording and not busy)
        self.import_button.setEnabled(free)
        self.transcribe_button.setEnabled(free and self.audio is not None)
        self.export_button.setEnabled(free and bool(self.editor.toPlainText().strip()))
        self.new_button.setEnabled(free)
        self.code.setEnabled(free)
        self.editor.setReadOnly(not free)
        for widget in (self.microphone, self.refresh_devices, self.model, self.choose_model,
                       self.add_rule_button, self.remove_rule_button, self.term, self.replacement, self.delete_option):
            widget.setEnabled(free)

    def _edited(self):
        self.dirty = True
        self._controls()

    def _code_edited(self):
        if self.editor.toPlainText().strip():
            self.dirty = True

    def _refresh_metadata(self):
        moment = datetime.fromisoformat(self.session.started_at)
        self.metadata.setText(moment.strftime('%d/%m/%Y · %H:%M:%S'))
        self.duration.setText('Duración: ' + duration_label(self.session.duration_seconds))

    def _tick(self):
        if self.recording:
            self.duration.setText('Grabando · ' + duration_label(self.recorder.duration))
            if self.recorder.error and self.worker is None:
                self._stop()

    def _refresh_devices(self):
        selected = self.microphone.currentData()
        self.microphone.clear()
        try:
            devices = self.recorder.devices()
            for index, name in devices:
                self.microphone.addItem(name, index)
            index = self.microphone.findData(selected)
            if index >= 0:
                self.microphone.setCurrentIndex(index)
            if not devices:
                self.status.setText('No hay micrófonos disponibles. Podés seleccionar un archivo de audio.')
        except Exception as error:
            self.status.setText(f'No se pudo acceder al micrófono: {error}. Podés importar un audio.')
        self._controls()

    def _run(self, job, callback, message):
        if self.worker is not None:
            return
        self.status.setText(message)
        self.progress.setRange(0, 0)
        self.progress.show()
        worker = Worker(job, self)
        self.worker = worker
        worker.result.connect(lambda result: self._handle_result(callback, result))
        worker.failed.connect(self._failed)
        worker.progress.connect(self._progress)
        worker.finished.connect(self._finished)
        self._controls()
        worker.start()

    def _handle_result(self, callback, result):
        try:
            callback(result)
        except Exception as error:
            self._failed(str(error))

    def _progress(self, value):
        self.progress.setRange(0, 100)
        self.progress.setValue(value)

    def _failed(self, message):
        self.status.setText('La operación falló. El audio no se elimina; podés volver a intentar.')
        self._error(message)

    def _finished(self):
        worker = self.worker
        self.worker = None
        if worker:
            worker.deleteLater()
        self.progress.hide()
        self._controls()

    def _discard_check(self):
        if self.dirty and self.editor.toPlainText().strip():
            box = QMessageBox(self)
            box.setWindowTitle('Transcripción sin exportar')
            box.setText('Hay texto sin exportar. ¿Querés guardarlo en Word antes de continuar?')
            box.setStandardButtons(QMessageBox.StandardButton.Save | QMessageBox.StandardButton.Discard | QMessageBox.StandardButton.Cancel)
            box.setDefaultButton(QMessageBox.StandardButton.Save)
            answer = box.exec()
            if answer == QMessageBox.StandardButton.Save:
                return self._export()
            return answer == QMessageBox.StandardButton.Discard
        return True

    def _reset(self):
        self.session = Session.new(self.code.text())
        self.audio = None
        self.editor.clear()
        self.dirty = False
        self.audio_label.setText('Sin audio seleccionado')
        self._refresh_metadata()
        self._controls()

    def _new_session(self):
        if self._discard_check():
            self.code.clear()
            self._reset()
            self.status.setText('Nueva consulta. Los audios anteriores se conservan en data/audio.')

    def _start(self):
        if not self._discard_check():
            return
        self._reset()
        self.audio = self.root / 'audio' / f'{self.session.id}.wav'
        try:
            self.recorder.start(self.audio, self.microphone.currentData())
            self.recording = True
            self.audio_label.setText('Audio local: ' + self.audio.name)
            self.status.setText('Grabando. Finalizá la grabación antes de transcribir.')
        except Exception as error:
            # Partial audio is kept on disk, never removed on a failed start.
            self.audio = None
            self._error(f'No se pudo iniciar el micrófono.\n{error}')
        self._controls()

    def _stop(self):
        def complete(duration):
            self.recording = False
            self.session.duration_seconds = duration
            self._refresh_metadata()
            self.status.setText('Grabación finalizada. El audio está guardado localmente.')
            if self.recorder.error:
                self._error(self.recorder.error + '\nSe conserva el audio disponible.')
            if duration == 0:
                self.audio = None
                self.status.setText('No se capturó audio. Revisá el micrófono e intentá nuevamente.')
        self._run(lambda progress: self.recorder.stop(), complete, 'Finalizando y guardando la grabación…')

    def _import_audio(self):
        filename, _ = QFileDialog.getOpenFileName(self, 'Seleccionar audio existente', '',
            'Audio (*.wav *.mp3 *.m4a *.mp4 *.aac *.flac *.ogg *.opus *.wma *.aiff *.webm);;Todos los archivos (*)')
        if not filename or not self._discard_check():
            return
        self._reset()
        source = Path(filename)
        destination = self.root / 'audio' / f'{self.session.id}{source.suffix.lower() or ".audio"}'
        def complete(path):
            self.audio = path
            self.audio_label.setText('Copia local: ' + path.name)
            self.status.setText('Audio importado. Se conserva el archivo original. Fecha de sesión: momento de importación.')
        self._run(lambda progress: copy_audio(source, destination), complete, 'Copiando audio a la carpeta local…')

    def _model_directory(self):
        name = self.model.currentText()
        return Path(self.store.get('model_path_' + name, str(model_root() / name)))

    def _update_model_label(self):
        directory = self._model_directory()
        ready = all((directory / file).is_file() for file in ('model.bin', 'config.json', 'tokenizer.json'))
        self.model_path.setText(str(directory) + (' · Disponible' if ready else ' · Falta preparar el modelo'))

    def _model_changed(self, value):
        self._save_setting('model', value)
        self._update_model_label()

    def _choose_model(self):
        directory = QFileDialog.getExistingDirectory(self, 'Seleccionar carpeta del modelo local', str(self._model_directory()))
        if directory:
            self._save_setting('model_path_' + self.model.currentText(), directory)
            self._update_model_label()

    def _transcribe(self):
        if self.audio is None or not self.audio.is_file():
            self._error('El archivo de audio no está disponible.')
            return
        directory = self._model_directory()
        if not all((directory / file).is_file() for file in ('model.bin', 'config.json', 'tokenizer.json')):
            self._error('Falta el modelo local. Preparalo con scripts/download_model.py según README.md,\n'
                        'o elegí su carpeta en Configuración.')
            return
        if self.editor.toPlainText().strip() and not self._discard_check():
            return
        self.session.patient_code = self.code.text().strip()
        audio = self.audio
        rules = self.store.rules()
        self._run(lambda progress: transcribe(audio, directory, progress),
                  lambda result: self._transcribed(result, rules), 'Transcribiendo localmente. Podés esperar sin cerrar la aplicación…')

    def _transcribed(self, result, rules):
        text, duration = result
        self.session.duration_seconds = duration
        self.session.transcript = protect(text, rules)
        self.editor.setPlainText(self.session.transcript)
        self.dirty = bool(self.session.transcript.strip())
        self._refresh_metadata()
        if not self.session.transcript.strip():
            self.status.setText('No se detectó voz. El audio se conserva. Revisá el archivo o probá otro modelo.')
            return
        self.status.setText('Transcripción lista. Revisá el texto antes de exportarlo.')
        if self.delete_option.isChecked():
            # Persist protected output before asking to delete its source.
            try:
                draft = self.root / 'sesiones' / f'{self.session.id}.json'
                self.session.save(draft)
            except Exception as error:
                self._error(f'No se pudo guardar una copia de la transcripción. El audio se conserva.\n{error}')
                return
            if self._confirm('Eliminar audio', f'La transcripción protegida quedó guardada en:\n{draft}\n\n'
                             '¿Eliminar la copia local del audio? Esta acción no se puede deshacer.\n'
                             'Si importaste un archivo, su original se conserva.'):
                try:
                    self.audio.unlink()
                    self.audio = None
                    self.audio_label.setText('Copia local del audio eliminada por confirmación del usuario')
                except OSError as error:
                    self._error(f'No se pudo eliminar el audio.\n{error}')

    def _export(self):
        text = protect(self.editor.toPlainText(), self.store.rules())
        if not text.strip():
            self._error('No hay texto para exportar.')
            return False
        filename, _ = QFileDialog.getSaveFileName(self, 'Exportar transcripción a Word',
            str(self.root / 'documentos' / f'consulta_{self.session.id}.docx'), 'Documento Word (*.docx)')
        if not filename:
            return False
        target = Path(filename)
        if target.suffix.lower() != '.docx':
            target = target.with_name(target.name + '.docx')
            if target.exists() and not self._confirm('Reemplazar documento', f'¿Reemplazar {target.name}?'):
                return False
        self.session.patient_code = self.code.text().strip()
        try:
            export_docx(self.session, text, target)
        except Exception as error:
            self._error(f'No se pudo guardar el Word. Si está abierto, cerralo y volvé a intentar.\n{error}')
            return False
        self.editor.setPlainText(text)
        self.session.transcript = text
        self.dirty = False
        self.status.setText(f'Documento guardado: {target}')
        return True

    def _refresh_rules(self):
        rules = self.store.rules()
        self.rules_table.setRowCount(len(rules))
        for row, values in enumerate(rules):
            for column, value in enumerate(values):
                self.rules_table.setItem(row, column, QTableWidgetItem(value))

    def _add_rule(self):
        try:
            existing = self.store.find_rule(self.term.text())
            if existing and not self._confirm('Actualizar regla', 'Esta palabra ya tiene una regla. ¿Reemplazarla?'):
                return
            self.store.add_rule(self.term.text(), self.replacement.text())
            self._refresh_rules()
            self.term.clear()
            self.replacement.clear()
            # Existing edited text is processed when rules change as well.
            processed = protect(self.editor.toPlainText(), self.store.rules())
            if processed != self.editor.toPlainText():
                self.editor.setPlainText(processed)
        except Exception as error:
            self._error(str(error))

    def _delete_rule(self):
        row = self.rules_table.currentRow()
        if row < 0:
            return
        term = self.rules_table.item(row, 0).text()
        if self._confirm('Eliminar regla', f'¿Eliminar la regla para «{term}»? El texto ya reemplazado no se restaura.'):
            try:
                self.store.delete_rule(term)
                self._refresh_rules()
            except Exception as error:
                self._error(str(error))

    def closeEvent(self, event: QCloseEvent):
        if self.worker is not None:
            self.status.setText('Esperá a que termine la operación antes de cerrar. El audio se conserva.')
            event.ignore()
            return
        if self.recording:
            if self._confirm('Grabación en curso', '¿Finalizar la grabación? Después podés cerrar la aplicación.'):
                self._stop()
            event.ignore()
            return
        if not self._discard_check():
            event.ignore()
            return
        self.store.close()
        event.accept()
