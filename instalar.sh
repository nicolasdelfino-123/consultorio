#!/usr/bin/env bash
# Preparación local sin sudo: bash instalar.sh [base|small|medium]
set -Eeuo pipefail

trap 'codigo=$?; printf "\nLa instalación se detuvo en la línea %s (código %s). Corregí el error indicado y volvé a ejecutar bash instalar.sh.\n" "$LINENO" "$codigo" >&2; exit "$codigo"' ERR

cd -- "$(dirname -- "${BASH_SOURCE[0]}")"

if (( EUID == 0 )); then
    echo 'Ejecutá este script como tu usuario normal, sin sudo.' >&2
    exit 1
fi

if [[ ! -f /etc/os-release ]]; then
    echo 'Este instalador está preparado para Ubuntu.' >&2
    exit 1
fi
# Archivo de identificación del sistema, administrado por Ubuntu.
source /etc/os-release
if [[ "${ID:-}" != ubuntu && " ${ID_LIKE:-} " != *' ubuntu '* ]]; then
    echo 'Este instalador está preparado para Ubuntu y sus derivados.' >&2
    exit 1
fi

if (( $# > 1 )); then
    echo 'Uso: bash instalar.sh [base|small|medium]' >&2
    exit 1
fi
modelo_consultorio="${1:-small}"
case "$modelo_consultorio" in
    base|small|medium) ;;
    *) echo 'El modelo debe ser base, small o medium.' >&2; exit 1 ;;
esac

for archivo_consultorio in requirements-lock.txt main.py scripts/download_model.py scripts/create_test_audio.py scripts/verify_local.py; do
    if [[ ! -f "$archivo_consultorio" ]]; then
        echo "Falta $archivo_consultorio. El instalador debe estar en la carpeta del proyecto completo." >&2
        exit 1
    fi
done

printf '\n[1/6] Preparando bibliotecas locales, sin sudo ni cambios en Ubuntu.\n'
for herramienta_consultorio in python3 apt-get dpkg dpkg-deb dpkg-query curl; do
    if ! command -v "$herramienta_consultorio" >/dev/null 2>&1; then
        echo "Falta la herramienta $herramienta_consultorio. Informá este mensaje para adaptar la preparación." >&2
        exit 1
    fi
done
mkdir -p .local-libs/packages
raiz_instalacion_consultorio="$PWD"
arquitectura_consultorio="$(dpkg --print-architecture)"
for paquete_consultorio in \
    libportaudio2 libasound2t64 libjack-jackd2-0 \
    libegl1 libopengl0 libgl1 libxkbcommon0 libxkbcommon-x11-0 \
    libxcb-cursor0 libxcb-icccm4 libxcb-image0 libxcb-keysyms1 \
    libxcb-render-util0 libxcb-xinerama0 libxcb-xkb1 \
    libespeak-ng1 espeak-ng-data; do
    estado_paquete_consultorio="$(dpkg-query -W -f='${Status}' "$paquete_consultorio:$arquitectura_consultorio" 2>/dev/null || true)"
    if [[ -z "$estado_paquete_consultorio" ]]; then
        estado_paquete_consultorio="$(dpkg-query -W -f='${Status}' "$paquete_consultorio:all" 2>/dev/null || true)"
    fi
    if [[ "$estado_paquete_consultorio" == 'install ok installed' || -f ".local-libs/$paquete_consultorio.preparado" ]]; then
        continue
    fi
    printf 'Preparando %s dentro del proyecto…\n' "$paquete_consultorio"
    (
        cd -- "$raiz_instalacion_consultorio/.local-libs/packages"
        apt-get -o Acquire::Retries=2 -o Acquire::http::Timeout=30 download "$paquete_consultorio"
        archivo_paquete_consultorio=''
        for candidato_paquete_consultorio in "$paquete_consultorio"_*.deb; do
            if [[ -f "$candidato_paquete_consultorio" ]]; then
                archivo_paquete_consultorio="$candidato_paquete_consultorio"
            fi
        done
        if [[ -z "$archivo_paquete_consultorio" ]]; then
            echo "No se descargó el paquete $paquete_consultorio." >&2
            exit 1
        fi
        dpkg-deb --extract "$archivo_paquete_consultorio" "$raiz_instalacion_consultorio/.local-libs"
    )
    touch ".local-libs/$paquete_consultorio.preparado"
done
# Permite que ctypes descubra PortAudio en la carpeta privada.
for biblioteca_portaudio_consultorio in .local-libs/usr/lib/*-linux-gnu/libportaudio.so.2; do
    if [[ -f "$biblioteca_portaudio_consultorio" && ! -e "${biblioteca_portaudio_consultorio%.2}" ]]; then
        ln -s libportaudio.so.2 "${biblioteca_portaudio_consultorio%.2}"
    fi
done
source scripts/local_env.sh

printf '\n[2/6] Preparando el entorno Python del proyecto.\n'
python3 -c 'import sys; assert sys.version_info >= (3, 12), "Las versiones fijadas de esta V1 requieren Python 3.12 o posterior (Ubuntu 24.04 o posterior)"'
if [[ ! -x .venv/bin/python ]]; then
    python3 -m venv .venv
fi
.venv/bin/python -c 'import sys; assert sys.prefix != sys.base_prefix, "El entorno .venv no es válido"; assert sys.version_info >= (3, 12), "Las versiones fijadas requieren un entorno .venv con Python 3.12 o posterior"'
.venv/bin/python -m pip install -r requirements-lock.txt
.venv/bin/python -m pip check
.venv/bin/python -c 'import sounddevice; print("PortAudio cargado:", sounddevice.get_portaudio_version()[1])'

printf '\n[3/6] Preparando el modelo local %s.\n' "$modelo_consultorio"
carpeta_modelo_consultorio="models/$modelo_consultorio"
if [[ -s "$carpeta_modelo_consultorio/model.bin" && -s "$carpeta_modelo_consultorio/config.json" && -s "$carpeta_modelo_consultorio/tokenizer.json" && -s "$carpeta_modelo_consultorio/vocabulary.txt" ]]; then
    echo 'El modelo ya está descargado; se conserva y no se vuelve a descargar.'
else
    .venv/bin/python scripts/download_model.py "$modelo_consultorio" --direct
fi

printf '\n[4/6] Preparando audio ficticio para probar sin datos de pacientes.\n'
if [[ ! -s data/prueba_es.wav ]]; then
    .venv/bin/python scripts/create_test_audio.py data/prueba_es.wav
fi
for formato_consultorio in mp3 m4a; do
    if [[ ! -s "data/prueba_es.$formato_consultorio" ]]; then
        if ! command -v ffmpeg >/dev/null 2>&1; then
            echo "FFmpeg no está disponible. Se probará el WAV; la app admite MP3/M4A igualmente."
            continue
        fi
        ffmpeg -hide_banner -loglevel error -nostdin -n -i data/prueba_es.wav "data/prueba_es.$formato_consultorio"
    fi
done

printf '\n[5/6] Ejecutando pruebas automáticas de servicios e interfaz.\n'
QT_QPA_PLATFORM=offscreen .venv/bin/python -m unittest discover -s tests -v

printf '\n[6/6] Probando transcripción local y Word con audio ficticio.\n'
for formato_consultorio in wav mp3 m4a; do
    [[ -s "data/prueba_es.$formato_consultorio" ]] || continue
    .venv/bin/python scripts/verify_local.py \
        --model "$carpeta_modelo_consultorio" \
        --audio "data/prueba_es.$formato_consultorio" \
        --output "data/documentos/prueba_instalacion_$formato_consultorio.docx"
done

printf '\nInstalación y pruebas completadas.\n'
printf 'Abrí la aplicación con: bash run.sh\n'
printf 'Audios ficticios: data/prueba_es.wav, data/prueba_es.mp3 y data/prueba_es.m4a\n'
printf 'Documentos de prueba: data/documentos/prueba_instalacion_*.docx\n'
if [[ "$modelo_consultorio" != small ]]; then
    printf 'En Configuración de la aplicación, elegí el modelo %s.\n' "$modelo_consultorio"
fi
printf 'Todavía necesitás probar una grabación con tu micrófono físico.\n'
