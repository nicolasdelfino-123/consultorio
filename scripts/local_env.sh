#!/usr/bin/env bash
# Bibliotecas privadas de esta aplicación. No modifica el sistema.
raiz_bibliotecas_consultorio="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
for directorio_bibliotecas_consultorio in \
    "$raiz_bibliotecas_consultorio/.local-libs/usr/lib/"*-linux-gnu \
    "$raiz_bibliotecas_consultorio/.local-libs/lib/"*-linux-gnu \
    "$raiz_bibliotecas_consultorio/.local-libs/usr/lib" \
    "$raiz_bibliotecas_consultorio/.local-libs/lib"; do
    if [[ -d "$directorio_bibliotecas_consultorio" ]]; then
        export LD_LIBRARY_PATH="$directorio_bibliotecas_consultorio${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
        export LIBRARY_PATH="$directorio_bibliotecas_consultorio${LIBRARY_PATH:+:$LIBRARY_PATH}"
    fi
done
if [[ -d "$raiz_bibliotecas_consultorio/.local-libs/usr/share/espeak-ng-data" ]]; then
    export CONSULTORIO_ESPEAK_DATA="$raiz_bibliotecas_consultorio/.local-libs/usr/share"
fi
unset raiz_bibliotecas_consultorio directorio_bibliotecas_consultorio
