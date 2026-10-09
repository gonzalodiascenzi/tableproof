"""Carga un archivo `.env` local (excluido por .gitignore) en el entorno.

No pisa variables que ya existan y devuelve solo los NOMBRES cargados: nunca
valores. El archivo real no se commitea; la plantilla es `.env.example`.
"""
import os


def load_env(path=".env", environ=None):
    environ = os.environ if environ is None else environ
    if not os.path.exists(path):
        return []
    loaded = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            k, v = k.strip(), v.strip().strip('"').strip("'")
            if k and v and k not in environ:
                environ[k] = v
                loaded.append(k)
    return loaded
