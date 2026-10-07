import sys
from PySide6.QtWidgets import QApplication, QMessageBox
from ui.main_window import MainWindow


def main():
    app = QApplication(sys.argv)
    app.setApplicationName('Asistente de Consultorio')
    try:
        window = MainWindow()
    except Exception as error:
        QMessageBox.critical(None, 'No se pudo iniciar', f'Revisá permisos de la carpeta de datos.\n{error}')
        return 1
    window.show()
    return app.exec()


if __name__ == '__main__':
    sys.exit(main())
