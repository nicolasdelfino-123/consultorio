"""Run a real, offline transcription and Word roundtrip using fictional audio only."""
import argparse
from pathlib import Path
import sys
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from services.transcriber import transcribe
from services.session import Session
from services.text_processor import protect
from services.docx_exporter import export_docx
from docx import Document


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--model', type=Path, default=Path('models/small'))
    parser.add_argument('--audio', type=Path, default=Path('data/prueba_es.wav'))
    parser.add_argument('--output', type=Path, default=Path('data/documentos/prueba_local.docx'))
    args = parser.parse_args()
    # Inference must also succeed when Python socket connections are prohibited.
    with patch('socket.socket.connect', side_effect=AssertionError('Unexpected network access')), \
         patch('socket.socket.connect_ex', side_effect=AssertionError('Unexpected network access')):
        text, duration = transcribe(args.audio, args.model)
    if not text.strip():
        raise AssertionError('No voice was transcribed from the fictional sample')
    processed = protect(text, [('suicidio', '[S1]'), ('cocaína', '[S2]'), ('violencia', '[S3]')])
    # Check actual recognition, not merely that the model returned any string.
    for expected in ('[S1]', '[S2]', '[S3]'):
        if expected not in processed:
            raise AssertionError(f'Test speech did not yield expected protected term {expected}')
    session = Session.new('PRUEBA-FICTICIA')
    session.duration_seconds = duration
    args.output.parent.mkdir(parents=True, exist_ok=True)
    export_docx(session, processed, args.output)
    exported = '\n'.join(p.text for p in Document(args.output).paragraphs)
    if processed not in exported or 'PRUEBA-FICTICIA' not in exported:
        raise AssertionError('Word roundtrip did not preserve transcript/metadata')
    print(f'OK: {args.audio.suffix} · {duration:.1f} s · transcripción local y Word verificados')
    print(f'Documento ficticio: {args.output}')


if __name__ == '__main__':
    main()
