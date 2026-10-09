"""Avisos al dueño. Un notificador es un callable(mensaje: str).

Los avisos NO llevan el texto del cliente: solo qué pasó, el teléfono enmascarado
y la fecha. FileNotifier es el canal por defecto del servidor (un archivo que el
dueño revisa o enlaza a lo que use); cualquier otro canal es un callable más.
"""
import time


def mask_phone(phone):
    p = str(phone or "")
    return ("*" * max(len(p) - 4, 0)) + p[-4:]


class ListNotifier:
    """En memoria: pruebas y simulador."""
    def __init__(self):
        self.messages = []

    def __call__(self, msg):
        self.messages.append(msg)


class FileNotifier:
    def __init__(self, path):
        self.path = path

    def __call__(self, msg):
        with open(self.path, "a", encoding="utf-8") as f:
            f.write(f"{time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())} {msg}\n")
