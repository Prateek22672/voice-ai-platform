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

# Interjections the LLM is encouraged to use ("Hmm,", "Ohh —"). Spell them the way the TTS
# pronounces them most naturally (a trailing comma reads as a short human pause).
_INTERJECTIONS = {
    r"\bhmm+\b": "hmm", r"\bmm+\b": "mmm", r"\bohh+\b": "ohh",
    r"\bahh+\b": "ahh", r"\buhm+\b": "um", r"\bok\b": "okay",
}

def _is_indic(text: str) -> bool:
    """Devanagari (Hindi) or Telugu script present — skip the ENGLISH-only transforms
    (abbreviations, number-to-English-words, interjection spellings) for these."""
    return any("ऀ" <= c <= "ॿ" or "ఀ" <= c <= "౿" for c in text)

def normalize(text: str) -> str:
    # Speakability guard: strip anything the LLM shouldn't have emitted for a voice call —
    # markdown marks, emoji and other symbols read out loud sound broken.
    text = re.sub(r"[*_`#>|~\[\]]+", " ", text)
    text = re.sub(r"[\U0001F000-\U0001FAFF☀-➿️]", "", text)  # emoji / dingbats
    text = text.replace("—", ", ").replace("–", ", ").replace("…", ", ")     # dash/ellipsis -> spoken pause
    if not _is_indic(text):
        for pat, rep in _INTERJECTIONS.items():
            text = re.sub(pat, rep, text, flags=re.IGNORECASE)
        for k, v in _ABBREV.items():
            text = text.replace(k, v)
        text = re.sub(r"\$(\d[\d,]*)", lambda m: _to_words(m.group(1)) + " dollars", text)
        text = re.sub(r"\b\d[\d,]{0,8}\b", _num_to_words, text)
    text = re.sub(r"\s*,\s*,+", ", ", text)          # collapse ",  ," left by the replacements
    text = re.sub(r"\s+([,.!?;:।])", r"\1", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text

def split_sentences(text: str) -> list[str]:
    """Split so TTS can start streaming after the first sentence — never wait for full text.
    (। = Hindi danda, a full stop in Devanagari text.)"""
    parts = re.split(r"(?<=[.!?।])\s+", text)
    return [p for p in parts if p.strip()]
