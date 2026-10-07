"""One-time setup only. Downloads public model weights, never clinical files."""
import argparse
import os
import shutil
import subprocess
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description='Preparar un modelo para uso completamente local.')
    parser.add_argument('model', choices=['base', 'small', 'medium'], default='small', nargs='?')
    parser.add_argument('--output', type=Path)
    parser.add_argument('--direct', action='store_true', help='Descargar el archivo grande por HTTP directo usando curl.')
    args = parser.parse_args()
    target = args.output or Path(__file__).resolve().parents[1] / 'models' / args.model
    # Standard HTTP avoids a separate native CAS backend and keeps setup caches
    # inside the chosen model directory.
    os.environ['HF_HUB_DISABLE_XET'] = '1'
    os.environ['HF_HUB_DISABLE_TELEMETRY'] = '1'
    os.environ.setdefault('HF_HOME', str(target / '.cache' / 'hub'))
    os.environ.setdefault('HF_HUB_DOWNLOAD_TIMEOUT', '30')
    from huggingface_hub import snapshot_download
    patterns = ['config.json', 'tokenizer.json', 'vocabulary.*', 'preprocessor_config.json']
    if not args.direct:
        patterns.append('model.bin')
    elif not shutil.which('curl'):
        parser.error('La opción --direct requiere curl. En Ubuntu: sudo apt install curl')
    snapshot_download(repo_id=f'Systran/faster-whisper-{args.model}', local_dir=str(target), allow_patterns=patterns)
    if args.direct:
        temporary = target / 'model.bin.direct.tmp'
        subprocess.run(['curl', '--fail', '--location', '--retry', '2', '--connect-timeout', '15',
                        '--max-time', '1800', '--output', str(temporary),
                        f'https://huggingface.co/Systran/faster-whisper-{args.model}/resolve/main/model.bin?download=true'],
                       check=True)
        temporary.replace(target / 'model.bin')
    print(f'Modelo preparado en {target}. Ya podés transcribir sin Internet.')


if __name__ == '__main__':
    main()
