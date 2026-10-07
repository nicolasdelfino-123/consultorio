import os
import sys
from pathlib import Path


def data_root():
    override = os.environ.get('CONSULTORIO_DATA_DIR')
    if override:
        root = Path(override).expanduser().resolve()
    elif getattr(sys, 'frozen', False):
        root = Path(os.environ.get('LOCALAPPDATA', Path.home())) / 'AsistenteConsultorio' / 'data'
    else:
        root = Path(__file__).resolve().parents[1] / 'data'
    root.mkdir(mode=0o700, parents=True, exist_ok=True)
    for name in ('audio', 'documentos', 'sesiones'):
        (root / name).mkdir(mode=0o700, exist_ok=True)
    return root


def model_root():
    if getattr(sys, 'frozen', False):
        return Path(sys.executable).parent / 'models'
    return Path(__file__).resolve().parents[1] / 'models'
