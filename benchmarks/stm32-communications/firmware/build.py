"""Build the explicitly incomplete resource probe, retaining commands/hashes."""
import argparse
from pathlib import Path
from pcb_harness.orchestration.firmware_evidence import build_probe

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--compiler", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    print(build_probe(Path(__file__).parent, args.output, args.compiler))
