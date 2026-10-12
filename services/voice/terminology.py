"""Narrow repairs for explicitly requested desktop vocabulary, not general rewriting."""
import re
TECH_HINTS='computer use, Brave, Brave Origin, YouTube, ZCode, Vansrouter, MCP, browser, screenshot, voice command'
PROMPT=('Percakapan Indonesia dan English bercampur. Transcribe verbatim, do not translate English terms. '
        'Istilah teknis: '+TECH_HINTS+'. '
        'Contoh ucapan: Pakai computer use lalu buka Brave Origin dan cari video di YouTube. '
        'Open the browser and take a screenshot.')
_COMPUTER_USE=re.compile(r'\b(?:komputer|computer)\s+(?:rius|yus|ius|use)\b',re.IGNORECASE)
def normalize_terms(text):
    return _COMPUTER_USE.sub('computer use',text)
