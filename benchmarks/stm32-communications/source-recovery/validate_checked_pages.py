"""Optional pypdf audit of originals and the frozen physical-page extraction.

Run with a Python environment containing pypdf; production loaders do not
depend on this tool. This verifies documentary extraction, not circuit claims.
"""
import argparse
import hashlib
import json
from pathlib import Path

from pypdf import PdfReader


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repository-root', default=str(Path(__file__).resolve().parents[3]))
    args = parser.parse_args()
    repo = Path(args.repository_root)
    root = repo / 'benchmarks/stm32-communications/source-recovery'
    spec = json.loads((root / 'completion-input.json').read_text())
    by_id = {d['id']: d for d in spec['documents']}
    readers = {}
    for did, doc in by_id.items():
        original = repo / doc['repository_path']
        raw = original.read_bytes()
        assert len(raw) == doc['bytes'], did
        assert hashlib.sha256(raw).hexdigest() == doc['sha256'], did
        if 'validation' in doc:
            validation = doc['validation']
            assert raw.startswith(b'%PDF-'), did
            reader = PdfReader(original)
            assert not reader.is_encrypted, did
            assert len(reader.pages) == validation['page_count'], did
            assert validation['verified_revision_or_title'] in reader.pages[0].extract_text(), did
            readers[did] = reader
        else:
            text = raw.decode()
            assert did == 'max3232idwr-part'
            assert 'MAX3232IDWR' in text and 'ACTIVE_true' in text and 'SOIC (DW)' in text
    checks = json.loads((root / 'page-checks.json').read_text())['pages']
    for check in checks:
        did, number = check['source_id'], check['physical_pdf_page']
        assert check['source_sha256'] == by_id[did]['sha256']
        assert readers[did].pages[number - 1].extract_text() == check['text'], (did, number)
    print(json.dumps({'original_documents_verified': len(by_id), 'original_pdf_revisions_verified': len(readers),
                      'physical_pdf_pages_verified': len(checks), 'human_confirmed': False}))


if __name__ == '__main__':
    main()
