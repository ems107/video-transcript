"""Variables de entorno que deben fijarse antes de importar librerías de IA.

Todo se descarga y se lee desde models/ y la app funciona sin conexión.
"""

import os
import warnings

from .config import MODELS_DIR

os.environ.setdefault("HF_HOME", str(MODELS_DIR / "hf"))
os.environ.setdefault("NLTK_DATA", str(MODELS_DIR / "nltk_data"))
os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")
os.environ.setdefault("HF_HUB_DISABLE_TELEMETRY", "1")
# pyannote: sin telemetría
os.environ.setdefault("PYANNOTE_METRICS_ENABLED", "0")

# torchcodec no se usa (el audio se pasa ya decodificado); silenciar su aviso
warnings.filterwarnings("ignore", message=".*torchcodec.*")
warnings.filterwarnings("ignore", message=".*libtorchcodec.*")
