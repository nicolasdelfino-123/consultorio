# Validación de la V1 en Ubuntu

Fecha: 6 de octubre de 2026.

## Comprobaciones ejecutadas

- Python 3.12.3, PySide6 6.11.2, faster-whisper 1.2.1, PyAV 18.1.0 y python-docx 1.2.0.
- `python -m compileall` sobre módulos, scripts y pruebas: correcto.
- `python -m pip check`: dependencias compatibles, sin requisitos rotos.
- `QT_QPA_PLATFORM=offscreen python -m unittest discover -s tests -v`:
  **24 pruebas correctas** (incluida la corrección de palabras protegidas sin tilde).
- Inicio de la ventana real en modo headless, sin PortAudio: la aplicación abre,
  informa el problema y mantiene habilitada la importación de archivos.
- Capturas de las dos pestañas: `interfaz.png` y `configuracion.png`.
- Audio de prueba ficticio sintetizado localmente en español con eSpeak,
  convertido a WAV, MP3 y M4A. No se usaron datos de pacientes.
- Modelo `small` descargado y validado con SHA-256:
  `3e305921506d8872816023e4c273e75d2419fb89b24da97b4fe7bce14170d671`.
- Inferencia real con `small` CPU int8 sobre los tres formatos, cada uno de unos
  12,5 segundos. Los tres reconocieron las palabras de prueba en español, aplicaron
  `[S1]`, `[S2]` y `[S3]`, generaron un Word y verificaron su contenido al reabrirlo.
  Durante esas inferencias se bloquearon las conexiones de sockets de Python.
- Rechazo de una playlist local con referencia HTTPS por parte de FFmpeg:
  el lector solo habilita los protocolos `file` y `pipe`.
- Flujo real desde la ventana PySide6 en modo headless: importar M4A,
  transcribir con el worker, editar manualmente y exportar. El Word se reabrió
  y conservó el código y la corrección con palabras protegidas. Durante la
  inferencia se procesaron 250 eventos de un timer, confirmando que el hilo
  gráfico siguió respondiendo. El audio original y la copia importada se conservaron.

La inferencia real detectó inicialmente una incompatibilidad entre PyAV 19.0.1 y
faster-whisper 1.2.1. Se corrigió fijando PyAV por debajo de 19 y se repitieron las
pruebas con PyAV 18.1.0. Las versiones finales están en `requirements-lock.txt`.

Las pruebas automáticas comprueban el contenido del DOCX al volver a abrirlo,
reglas literales con tildes y frases, persistencia de reglas y ajustes, escritura
WAV, cierre de una captura fallida, uso de worker, controles de grabación,
importación conservando el original, edición y exportación, cierre durante una
operación, confirmación de borrado y conservación de datos frente a errores.
También verifican que la regla `COCAINA` reemplace `cocaína` en la transcripción
y en el Word, incluso con acentos Unicode descompuestos, sin modificar otras
palabras. Se conserva la diferencia entre `n` y `ñ` y la coincidencia de palabras
completas. Guardar una regla equivalente actualiza la existente tras la
confirmación de la interfaz, sin crear duplicados por tildes.

## Límite de la prueba física

La captura de micrófono se probó con un dispositivo simulado y bytes PCM conocidos.
La preparación inicial no contaba con PortAudio. El instalador fue adaptado para
descargar y extraer `libportaudio2` en `.local-libs`, sin sudo ni configuración
de paquetes de Ubuntu. Se ejecutó completo: código de salida 0, PortAudio cargado,
21 pruebas correctas y transcripciones reales a Word de WAV, MP3 y M4A.
El entorno restringido no expone un dispositivo `/dev/snd`; sigue pendiente
comprobar la captura con el micrófono físico del usuario.

Para validar la captura real, ejecutar en la terminal propia de Ubuntu:

```bash
bash instalar.sh
bash run.sh
```

Luego grabar una frase ficticia, finalizar, transcribir y abrir el Word. La interfaz
no bloquea la importación ni el resto del flujo cuando falta un micrófono.

Esta validación no afirma que se hayan probado Windows, una instalación móvil,
consultas de varias horas o todos los dispositivos de audio posibles.
