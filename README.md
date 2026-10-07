# Asistente de Consultorio — V1 de escritorio

Aplicación local en Python para Ubuntu. Graba desde un micrófono o importa un archivo,
transcribe en español con faster-whisper, reemplaza palabras configuradas, permite
editar el texto y exporta un Word editable. No hay servidor, cuentas, APIs clínicas,
nube, diagnósticos ni aplicaciones móviles.

## Estructura

```text
main.py                     Entrada de la aplicación
ui/main_window.py           Interfaz PySide6 y workers
services/audio_recorder.py  Captura PCM y escritura WAV en segundo plano
services/audio_loader.py    Decodificación local sin protocolos de red
services/transcriber.py     faster-whisper local, CPU int8
services/text_processor.py  Reemplazos literales
services/docx_exporter.py   Exportación atómica de Word
services/session.py         Metadatos y borrador protegido
services/paths.py           Ubicación de datos/modelos
database/store.py           Configuración y reglas en SQLite
scripts/download_model.py  Preparación independiente del modelo
models/                     Modelos locales (no incluidos en el código)
data/audio/                 WAV grabados y copias de archivos importados
data/documentos/            Carpeta propuesta para Word
data/sesiones/              Copia protegida antes de una eliminación de audio
tests/                      Pruebas de servicios e interfaz
```

## Preparación en Ubuntu

Para preparar todo automáticamente desde esta carpeta, ejecutá **sin sudo**:

```bash
bash instalar.sh
```

El script prepara las bibliotecas faltantes dentro de `.local-libs`, sin sudo,
sin configurar paquetes pendientes y sin modificar Secure Boot. Los paquetes se
descargan de los repositorios ya configurados de Ubuntu y se extraen en el proyecto;
no se ejecutan sus scripts de instalación del sistema.
Prepara `.venv`, instala las versiones fijadas, descarga `small` solo si falta y
ejecuta las pruebas automáticas y transcripciones con audio ficticio.
Python 3.12, el soporte de venv, apt-get, dpkg-deb y curl deben estar disponibles,
como sucede en la computadora de desarrollo usada para esta V1. Si está disponible
FFmpeg se preparan también los ejemplos MP3 y M4A; de lo contrario se prueba el WAV.
Necesita Internet durante la preparación y Python 3.12 o posterior para el archivo
de versiones fijadas. No elimina audios ni transcripciones de consultas.
Después abrí la aplicación con `bash run.sh` y probá el micrófono físico.
`run.sh` activa la ruta de las bibliotecas privadas antes de iniciar Python.
Para preparar otro modelo: `bash instalar.sh base` o `bash instalar.sh medium`.

Preparación manual:

Python 3.12 o posterior para las versiones fijadas; desarrollo verificado con Python 3.12. Desde esta carpeta:

```bash
sudo apt update
sudo apt install python3-venv libportaudio2 libxcb-cursor0
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements-lock.txt
python scripts/download_model.py small
python main.py
```

La preparación inicial necesita Internet para instalar dependencias y descargar los
pesos públicos del modelo. El script de preparación no recibe ningún audio ni texto
clínico. Una vez preparado, la aplicación funciona desconectada: establece el modo
offline del Hub, carga una carpeta local y exige `local_files_only=True`.

También podés copiar una carpeta de modelo **faster-whisper / CTranslate2** preparada
en otra computadora y elegirla en Configuración. Los modelos `.pt` de Whisper y los
modelos GGML no son compatibles con este motor. La carpeta debe incluir `model.bin`,
`config.json`, `tokenizer.json` y los restantes archivos descargados por el script.
Si el archivo grande queda detenido al descargarlo con el Hub, usá
`python scripts/download_model.py small --direct` (requiere `curl`). Los archivos
parciales no se consideran modelos disponibles hasta completar la descarga.

Para abrirla después de la preparación:

```bash
./run.sh
```

Si ya hay un `.venv` preparado, no hace falta reinstalarlo. No ejecutar como root.
`requirements.txt` declara las dependencias principales; `requirements-lock.txt`
fija las versiones exactas instaladas y probadas en este entorno Ubuntu/Python 3.12.

## Uso

1. En **Configuración y palabras protegidas**, elegí `base`, `small` o `medium`.
   El modelo seleccionado debe estar preparado. `small` es el valor inicial.
   `base` consume menos recursos; `medium` exige más memoria y tarda más. El tiempo
   depende de la CPU, la longitud de la consulta y el modelo; no es transcripción en vivo.
2. Agregá reglas, por ejemplo `suicidio` → `[S1]`, `cocaína` → `[S2]`.
   Se guardan en SQLite. No vienen activadas automáticamente.
3. En **Consulta**, escribí un código opcional. Seleccioná el micrófono, presioná
   **Comenzar grabación** y luego **Finalizar grabación**.
4. Alternativamente, seleccioná un WAV, MP3, M4A, FLAC, OGG u otro formato decodificable
   por PyAV. Se trabaja con una copia local; el archivo original no se modifica.
   No se necesita instalar FFmpeg para transcribir: PyAV incluye las bibliotecas de
   decodificación. Un archivo corrupto o no compatible muestra un error recuperable.
5. Presioná **Transcribir**. El procesamiento se hace en un worker: la ventana sigue
   respondiendo. Esperá a que termine antes de cerrar o empezar otra consulta.
6. Revisá y corregí el texto. Presioná **Exportar a Word** y elegí dónde guardarlo.
   El Word incluye código, fecha, hora con zona horaria, duración y texto editable.
   Las reglas vuelven a aplicarse al exportar, incluso a texto ingresado manualmente.
7. **Nueva consulta** conserva los audios anteriores. Si hay texto sin exportar,
   podés guardarlo, descartarlo o cancelar.

Para un archivo importado, la fecha y hora de sesión corresponden al momento de
importación, no a una fecha inferida de la grabación. La duración se obtiene del audio
al transcribir. En una captura de micrófono, la duración cuenta las muestras guardadas.

## Eliminación de audio y datos locales

La opción de ofrecer eliminación está desactivada al comenzar. Si la activás, una
transcripción no vacía se guarda primero como borrador protegido en `data/sesiones`.
Después aparece una confirmación explícita (la respuesta predeterminada es **No**).
Solo si elegís **Sí** se elimina el audio que está dentro de `data/audio`. El original
de una importación siempre se conserva. Un error o una transcripción vacía no eliminan
audio. Si guardaste el borrador y cerraste sin exportar, el campo `transcript` del JSON
conserva el texto protegido, legible con un editor de texto.

Los audios, documentos, borradores y SQLite quedan en disco local sin cifrado propio.
Los reemplazos no eliminan palabras del audio ni detectan automáticamente nombres u
otros datos identificatorios. El texto reemplazado no se restaura al borrar una regla.
Se reemplazan palabras o frases completas sin distinguir mayúsculas ni tildes en
vocales: `COCAINA` también protege `cocaína`. `ñ` sigue siendo distinta de `n`.
Al guardar una regla equivalente con otra escritura se actualiza la regla existente.
No se encadenan reemplazos dentro de una misma pasada.
Usá etiquetas estables como `[S1]` y no otras palabras que tengan reglas.

No se guardan nombres obligatorios ni registros de audio/texto en logs. La ruta de
datos puede cambiarse con `CONSULTORIO_DATA_DIR`. No elijas una carpeta sincronizada
si necesitás mantener estos archivos exclusivamente en la computadora.

## Pruebas

```bash
source .venv/bin/activate
QT_QPA_PLATFORM=offscreen python -m unittest discover -s tests -v
```

Las pruebas automáticas usan carpetas temporales y audio simulado, sin consultas reales.
Verifican persistencia SQLite, palabras/frases y tildes, grabación WAV y vaciado de buffer,
errores de captura, Word editable, conservación del Word anterior ante un fallo,
importación sin modificar originales, worker, confirmaciones y recuperación tras errores.
No sustituyen una prueba física del micrófono.
También prueban la decodificación y el remuestreo de un WAV real y el rechazo de
referencias a medios remotos: PyAV está limitado a los protocolos `file` y `pipe`.

Prueba manual recomendada con una frase inventada:

- Grabar 15–30 segundos, finalizar, verificar duración, transcribir y editar una oración.
- Exportar y abrir el DOCX con LibreOffice; comprobar metadatos y texto.
- Importar el mismo audio convertido a MP3/M4A y repetir el flujo.
- Cerrar y abrir: comprobar que modelo y reglas persistieron.
- Activar eliminación, rechazar la confirmación y verificar que el audio sigue presente.
- Repetir aceptando; verificar el borrador y que el original importado sigue presente.
- Seleccionar un archivo inválido; comprobar que se puede volver a importar otro.

Las verificaciones ejecutadas en este entorno y sus límites están en `docs/VALIDACION.md`.

Para repetir la prueba real con el audio ficticio incluido en esta carpeta de trabajo:

```bash
python scripts/verify_local.py --audio data/prueba_es.wav
python scripts/verify_local.py --audio data/prueba_es.mp3
python scripts/verify_local.py --audio data/prueba_es.m4a
```

Esta herramienta bloquea las conexiones de sockets de Python durante la inferencia,
comprueba los términos de prueba y vuelve a leer el DOCX generado. Si no tenés esos
audios, `python scripts/create_test_audio.py` genera el WAV en Ubuntu cuando está
disponible la biblioteca opcional eSpeak. Los audios de prueba son ficticios y no
son parte de la aplicación ni de sus dependencias de uso.

## Si algo falla

- **Micrófono no disponible / PortAudio library not found:** instalar `libportaudio2`,
  con `bash instalar.sh` y abrir con `bash run.sh`,
  revisar dispositivo y permisos en Configuración de sonido de Ubuntu, luego pulsar
  Actualizar micrófonos. La importación funciona aunque no haya un micrófono disponible.
- **Qt no inicia con xcb:** instalar `libxcb-cursor0`. Ejecutar desde una sesión gráfica
  normal. `QT_QPA_PLATFORM=offscreen` se usa solo para pruebas sin pantalla.
- **Falta modelo:** preparar el modelo elegido o seleccionar su carpeta local.
- **Word no se guarda:** cerrar el documento si está abierto y revisar permisos/espacio.
  Una escritura fallida no sobrescribe el Word anterior.
- **No se detectó voz:** revisar el micrófono, el volumen o el archivo. Se conserva el audio.
- **Pérdida de muestras / disco lleno:** la captura se finaliza y muestra el problema;
  se conserva el audio parcial. No asumir que la consulta quedó grabada completa.

La distribución para Windows se evaluará después de validar esta V1. No se generó
un ejecutable ni se desarrolló código para iPhone, Android o Xcode.

Referencias de las dependencias: [faster-whisper](https://github.com/SYSTRAN/faster-whisper),
[sounddevice](https://python-sounddevice.readthedocs.io/),
[cambios de PyAV](https://pyav.basswood.io/docs/stable/development/changelog.html).
Se fija PyAV por debajo de la versión 19 porque esa versión quitó un argumento que
faster-whisper 1.2.1 utiliza al decodificar audio.

## para ejecutarlo
bash run.sh