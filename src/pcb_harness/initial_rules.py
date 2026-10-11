"""Validated M0 rule subset only; general fabrication compiler is M3."""
from pathlib import Path
import hashlib
import re

def validate_probe_rules(path):
    """Only this experimentally verified M0 rule subset is supported here.

    A general rule compiler/validator belongs to M3. Native KiCad 10 CLI can
    silently ignore malformed rule files, so unknown text is never accepted.
    """
    pattern=(r'\s*\(version\s+1\)\s*\(rule\s+"M0 minimum routing width"\s*'
        r'\(condition\s+"A.Type == \'Track\'"\)\s*'
        r'\(constraint\s+track_width\s*\(min\s+0\.2mm\)\)\s*\)\s*')
    text=Path(path).read_text()
    if not re.fullmatch(pattern,text):
        raise ValueError('unsupported/malformed M0 custom rule; explicit mm and verified rule subset required')
    return {'passed':True,'scope':'known M0 rule subset only',
        'sha256':hashlib.sha256(text.encode()).hexdigest()}
