"""ELF accounting must include data's flash image and reserved stack."""
from pathlib import Path
import struct
import subprocess
import pytest

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "benchmarks/stm32-communications/firmware"


def tiny_elf():
    # ARM executable with text in flash, data in RAM/flash LMA, BSS + stack NOBITS.
    names = b"\0.text\0.data\0.bss\0.stack\0.shstrtab\0"
    image = bytearray(600)
    ident = b"\x7fELF\x01\x01\x01" + bytes(9)
    struct.pack_into("<16sHHIIIIIHHHHHH", image, 0, ident, 2, 40, 1, 0x08000001,
                     52, 300, 0, 52, 32, 2, 40, 6, 5)
    struct.pack_into("<IIIIIIII", image, 52, 1, 128, 0x08000000, 0x08000000, 16, 16, 5, 4)
    struct.pack_into("<IIIIIIII", image, 84, 1, 144, 0x20000000, 0x08000010, 4, 28, 6, 4)
    struct.pack_into("<IIIIIIIIII", image, 340, 1, 1, 6, 0x08000000, 128, 16, 0, 0, 4, 0)
    struct.pack_into("<IIIIIIIIII", image, 380, 7, 1, 3, 0x20000000, 144, 4, 0, 0, 4, 0)
    struct.pack_into("<IIIIIIIIII", image, 420, 13, 8, 3, 0x20000004, 0, 8, 0, 0, 4, 0)
    struct.pack_into("<IIIIIIIIII", image, 460, 18, 8, 3, 0x2000000c, 0, 16, 0, 0, 4, 0)
    struct.pack_into("<IIIIIIIIII", image, 500, 25, 3, 0, 0, 550, len(names), 0, 0, 1, 0)
    image[550:550+len(names)] = names
    return bytes(image)


def test_elf_accounts_data_load_and_stack():
    from pcb_harness.orchestration.firmware_evidence import elf_usage
    result = elf_usage(tiny_elf())
    assert result["flash_bytes"] == 20
    assert result["ram_bytes"] == 28
    assert result["stack_bytes"] == 16
    assert result["static_data_bytes"] == 12


def test_ram_load_extent_counts_even_when_larger_than_named_sections():
    from pcb_harness.orchestration.firmware_evidence import elf_usage
    image = bytearray(tiny_elf())
    struct.pack_into("<I", image, 84 + 20, 20000)
    assert elf_usage(image)["ram_bytes"] == 20000


@pytest.mark.parametrize("mutation,reason", [
    (lambda image: struct.pack_into("<I", image, 84 + 20, 20481), "RAM"),
    (lambda image: struct.pack_into("<II", image, 52 + 16, 65537, 65537), "segment"),
    (lambda image: struct.pack_into("<IIIIIIIIII", image, 340, 1, 8, 6, 0x08000000, 0, 65537, 0, 0, 4, 0), "flash"),
    (lambda image: struct.pack_into("<I", image, 460 + 12, 0x20000008), "overlap"),
])
def test_elf_complete_allocated_ranges_are_checked(mutation, reason):
    from pcb_harness.orchestration.firmware_evidence import elf_usage
    image = bytearray(tiny_elf())
    mutation(image)
    with pytest.raises(ValueError, match=reason):
        elf_usage(image)


@pytest.mark.parametrize("data", [b"", b"not an elf", tiny_elf()[:520]])
def test_malformed_elf_is_rejected(data):
    from pcb_harness.orchestration.firmware_evidence import elf_usage
    with pytest.raises(ValueError):
        elf_usage(data)


def test_resource_probe_host_crc_and_buffers(tmp_path):
    # Real C implementation: CRC rejection and bounded queue/full behavior.
    binary = tmp_path / "probe-host"
    result = subprocess.run(["/usr/bin/clang", "-std=c11", "-Wall", "-Wextra", "-Werror", "-DPROBE_HOST_TEST",
                             str(SOURCE / "probe.c"), str(ROOT / "tests/firmware/probe_host.c"),
                             "-o", str(binary)], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert subprocess.run([str(binary)], capture_output=True).returncode == 0


def test_cross_build_binds_inputs_and_outputs_and_never_claims_complete_firmware(tmp_path):
    compiler = ROOT / "runs/m4/toolchain/arm-gnu-toolchain-13.2.Rel1-darwin-arm64-arm-none-eabi/bin/arm-none-eabi-gcc"
    if not compiler.is_file():
        pytest.skip("Arm GNU cross compiler unavailable; see benchmark README")
    from pcb_harness.orchestration.firmware_evidence import build_probe, verify_probe
    output = tmp_path / "build"
    build_probe(SOURCE, output, compiler)
    result = verify_probe(SOURCE, output)
    assert result["capacity_probe_passed"]
    assert result["stack_bytes"] == 4096
    assert result["full_firmware_status"] == "unknown"
    (output / "probe.map").write_text("tampered")
    with pytest.raises(ValueError, match="hash"):
        verify_probe(SOURCE, output)


def test_missing_build_evidence_is_not_capacity_acceptance(tmp_path):
    from pcb_harness.orchestration.firmware_evidence import verify_probe
    with pytest.raises(ValueError):
        verify_probe(SOURCE, tmp_path)
