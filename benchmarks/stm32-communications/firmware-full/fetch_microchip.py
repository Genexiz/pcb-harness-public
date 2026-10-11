"""Fetch the Microchip MCP251xFD CAN FD SPI API files into vendor/microchip.

The public repository does not redistribute these files: Microchip licenses
them for use exclusively with Microchip products and grants no explicit
redistribution right. This script downloads the official archive named in
sources.lock.json, checks the archive SHA-256, then extracts only the locked
files and checks each file hash. Nothing is written if any check fails.

    python benchmarks/stm32-communications/firmware-full/fetch_microchip.py
    python .../fetch_microchip.py --archive <already downloaded zip>
"""
import argparse
import hashlib
import io
import json
from pathlib import Path
import urllib.request
import zipfile

HERE = Path(__file__).resolve().parent


def extract(archive_bytes, lock, vendor_root):
    source = next(s for s in lock['sources'] if s['id'] == 'microchip')
    if hashlib.sha256(archive_bytes).hexdigest() != source['archive_sha256']:
        raise ValueError('Microchip archive SHA-256 differs from sources.lock.json')
    wanted = {name: digest for name, digest in lock['files'].items() if name.startswith('microchip/')
              and not name.startswith('microchip/spi/')}
    found = {}
    with zipfile.ZipFile(io.BytesIO(archive_bytes)) as archive:
        members = [m for m in archive.namelist() if not m.endswith('/')]
        for name, digest in wanted.items():
            basename = name.rsplit('/', 1)[1]
            matches = [m for m in members if m.rsplit('/', 1)[-1] == basename
                       and hashlib.sha256(archive.read(m)).hexdigest() == digest]
            if not matches:
                raise ValueError('locked Microchip file not found with matching hash: ' + name)
            found[name] = archive.read(matches[0])
    for name, data in found.items():
        target = Path(vendor_root) / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
    return sorted(found)


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--archive', help='Use a local copy of the official archive instead of downloading')
    args = parser.parse_args()
    lock = json.loads((HERE / 'sources.lock.json').read_text())
    if args.archive:
        data = Path(args.archive).read_bytes()
    else:
        url = next(s for s in lock['sources'] if s['id'] == 'microchip')['url']
        with urllib.request.urlopen(url, timeout=120) as response:
            data = response.read()
    for name in extract(data, lock, HERE / 'vendor'):
        print('verified', name)


if __name__ == '__main__':
    main()
