"""Create an isolated live project; never overwrite an earlier run or baseline."""
from pathlib import Path
import shutil

ROOT = Path(__file__).resolve().parents[2]
source = ROOT / 'fixtures/capability'
destination = ROOT / 'runs/capability/live'
if destination.exists():
    raise SystemExit(f'refusing to overwrite existing live project: {destination}')
shutil.copytree(source, destination)
print(destination / 'board.kicad_pcb')
