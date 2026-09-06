import os
import numpy as np
from memory_layer.config import log

_fastembed_model = None


def get_fastembed_model():
    """Lazily load FastEmbed model singleton, caching result and suppressing warnings."""
    global _fastembed_model
    if _fastembed_model is None:
        try:
            os.environ["HF_HUB_DISABLE_SYMLINKS_WARNING"] = "1"
            from fastembed import TextEmbedding
            _fastembed_model = TextEmbedding(model_name="BAAI/bge-small-en-v1.5")
        except Exception as e:
            log.warning(f"⚠️ fastembed initialization warning: {e}")
            _fastembed_model = False
    return _fastembed_model


def embed_text_memory(text: str) -> np.ndarray | None:
    """Embed text using local fastembed (384-dim) or return None on failure."""
    model = get_fastembed_model()
    if model:
        try:
            embeddings = list(model.embed([text]))
            vec = np.array(embeddings[0], dtype=np.float32)
            norm = np.linalg.norm(vec)
            if norm > 0:
                vec = vec / norm
            return vec
        except Exception as e:
            log.warning(f"Embedding error: {e}")
    return None
