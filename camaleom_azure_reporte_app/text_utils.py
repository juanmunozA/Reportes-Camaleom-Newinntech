from __future__ import annotations

import re
import unicodedata
from typing import Any

import pandas as pd

def normalizar_texto(texto: Any) -> str:
    texto = "" if pd.isna(texto) else str(texto)
    texto = unicodedata.normalize("NFKD", texto)
    texto = "".join(c for c in texto if not unicodedata.combining(c))
    texto = texto.lower()
    texto = re.sub(r"[^a-z0-9]+", " ", texto)
    return re.sub(r"\s+", " ", texto).strip()
