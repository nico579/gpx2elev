"""Shared FR/EN catalog. Calculations and export schemas stay language independent."""
import json
from pathlib import Path
import re

CATALOG = json.loads((Path(__file__).parent / 'assets/translations.json').read_text(encoding='utf-8'))


def _patterns():
    patterns = []
    for french, english in CATALOG.items():
        pieces = re.split(r'(\{\d+\})', french)
        if len(pieces) == 1:
            continue
        pattern = ''.join('(.+?)' if re.fullmatch(r'\{\d+\}', p) else re.escape(p) for p in pieces)
        indices = [int(p[1:-1]) for p in pieces if re.fullmatch(r'\{\d+\}', p)]
        patterns.append((re.compile(pattern), english, indices))
    return patterns


PATTERNS = _patterns()
LITERALS = sorted(((fr, en) for fr, en in CATALOG.items() if not re.search(r'\{\d+\}', fr)), key=lambda p: -len(p[0]))


def translate(text, language='fr'):
    if language != 'en':
        return text
    for pattern, english, indices in PATTERNS:
        def replace(match):
            values = dict(zip(indices, match.groups()))
            return re.sub(r'\{(\d+)\}', lambda m: values[int(m[1])], english)
        text = pattern.sub(replace, text)
    for french, english in LITERALS:
        text = text.replace(french, english)
    return text


def number(value, decimals=0, language='fr'):
    text = f'{value:,.{decimals}f}'
    return text.replace(',', '\u202f').replace('.', ',') if language == 'fr' else text
