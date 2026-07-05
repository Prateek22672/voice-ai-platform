"""Text normalization before TTS: abbreviations, numbers, sentence split.
This pipeline (not the model alone) is what makes commercial TTS sound polished."""
import re

_ABBREV = {"Dr.": "Doctor", "Mr.": "Mister", "Mrs.": "Missus", "St.": "Street",
           "etc.": "etcetera", "e.g.": "for example", "i.e.": "that is",
           "vs.": "versus", "approx.": "approximately"}

def _to_words(s: str) -> str:
    try:
        from num2words import num2words
        return num2words(int(s.replace(",", "")))
    except Exception:
        return s

def _num_to_words(m):
    return _to_words(m.group(0))

def normalize(text: str) -> str:
    for k, v in _ABBREV.items():
        text = text.replace(k, v)
    text = re.sub(r"\$(\d[\d,]*)", lambda m: _to_words(m.group(1)) + " dollars", text)
    text = re.sub(r"\b\d[\d,]{0,8}\b", _num_to_words, text)
    text = re.sub(r"\s+", " ", text).strip()
    return text

def split_sentences(text: str) -> list[str]:
    """Split so TTS can start streaming after the first sentence — never wait for full text."""
    parts = re.split(r"(?<=[.!?])\s+", text)
    return [p for p in parts if p.strip()]
