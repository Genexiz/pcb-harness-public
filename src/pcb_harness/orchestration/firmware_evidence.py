"""Real ARM ELF accounting with input/output integrity; partial firmware stays partial."""
from pathlib import Path
import json
import struct
import subprocess

from pcb_harness.circuit.bundle import read_json, resolve_local, sha256

INPUTS = ("probe.c", "startup.c", "stm32f103c8.ld", "build.py")
OUTPUTS = ("probe.elf", "probe.map", "probe.bin", "sections.txt", "commands.json")
FLASH, RAM = 0x08000000, 0x20000000


def elf_usage(data):
    try:
        header = struct.unpack_from("<16sHHIIIIIHHHHHH", data)
        ident, kind, machine, _, entry, phoff, shoff, _, ehsize, phsize, phnum, shsize, shnum, names_index = header
        if ident[:7] != b"\x7fELF\x01\x01\x01" or kind != 2 or machine != 40 or ehsize != 52 or phsize != 32 or shsize != 40:
            raise ValueError("expected ELF32 little-endian ARM executable")
        if not FLASH <= (entry & ~1) < FLASH + 65536 or not phnum or not shnum or names_index >= shnum:
            raise ValueError("invalid entry/ELF tables")
        if phoff + phnum * phsize > len(data) or shoff + shnum * shsize > len(data):
            raise ValueError("truncated ELF tables")
        sections = [struct.unpack_from("<IIIIIIIIII", data, shoff + i * shsize) for i in range(shnum)]
        names = sections[names_index]
        if names[4] + names[5] > len(data):
            raise ValueError("truncated ELF section names")
        strings = data[names[4]:names[4] + names[5]]
        static, stack, ram_end, flash_end = 0, 0, RAM, FLASH
        allocated_ranges = []
        for section in sections:
            name_offset, stype, flags, address, offset, size, *_ = section
            if name_offset >= len(strings):
                raise ValueError("invalid section name offset")
            name = strings[name_offset:].split(b"\0", 1)[0].decode("ascii")
            if stype != 8 and offset + size > len(data):
                raise ValueError("truncated ELF section")
            if flags & 2 and size:
                end = address + size
                if any(address < previous_end and previous_start < end
                       for previous_start, previous_end in allocated_ranges):
                    raise ValueError("overlapping allocated sections")
                allocated_ranges.append((address, end))
                if RAM <= address < RAM + 20480:
                    if end > RAM + 20480:
                        raise ValueError("RAM overflow")
                    ram_end = max(ram_end, address + size)
                    if name == ".stack":
                        stack += size
                    else:
                        static += size
                elif FLASH <= address < FLASH + 65536:
                    if end > FLASH + 65536:
                        raise ValueError("flash section overflow")
                else:
                    raise ValueError("allocated section outside STM32 memory")
        for i in range(phnum):
            ptype, offset, vaddr, paddr, filesz, memsz, _, _ = struct.unpack_from("<IIIIIIII", data, phoff + i * phsize)
            if ptype != 1:
                continue
            if filesz > memsz or offset + filesz > len(data):
                raise ValueError("invalid ELF load segment")
            if filesz:
                if not FLASH <= paddr or paddr + filesz > FLASH + 65536:
                    raise ValueError("flash load overflow")
                flash_end = max(flash_end, paddr + filesz)
            if memsz:
                if RAM <= vaddr < RAM + 20480:
                    if vaddr + memsz > RAM + 20480:
                        raise ValueError("RAM load overflow")
                    ram_end = max(ram_end, vaddr + memsz)
                elif FLASH <= vaddr < FLASH + 65536:
                    if vaddr + memsz > FLASH + 65536:
                        raise ValueError("flash segment overflow")
                else:
                    raise ValueError("load segment outside STM32 memory")
        if flash_end == FLASH or not stack:
            raise ValueError("missing flash image or explicit stack reservation")
        return {"flash_bytes": flash_end - FLASH, "ram_bytes": ram_end - RAM,
                "stack_bytes": stack, "static_data_bytes": static,
                "flash_limit_bytes": 65536, "ram_limit_bytes": 20480}
    except (struct.error, UnicodeError, IndexError) as error:
        raise ValueError(f"malformed ELF: {error}") from error


def build_probe(source_root, output, compiler):
    source_root, output, compiler = Path(source_root).absolute(), Path(output).absolute(), Path(compiler).absolute()
    sources = {name: sha256(resolve_local(source_root, name)) for name in INPUTS}
    output.mkdir(parents=True, exist_ok=False)
    commands = []

    def run(args):
        result = subprocess.run([str(arg) for arg in args], capture_output=True, text=True, timeout=120)
        commands.append({"argv": [str(arg) for arg in args], "exit_code": result.returncode,
                         "stdout": result.stdout, "stderr": result.stderr})
        (output / "commands.json").write_text(json.dumps(commands, indent=2) + "\n")
        if result.returncode:
            raise ValueError(f"firmware command failed: {result.stderr}")
        return result.stdout

    version = run([compiler, "--version"])
    flags = ["-mcpu=cortex-m3", "-mthumb", "-std=c11", "-Os", "-g", "-Wall", "-Wextra", "-Werror",
             "-ffreestanding", "-fno-builtin", "-ffunction-sections", "-fdata-sections", "-nostdlib"]
    run([compiler, *flags, source_root / "startup.c", source_root / "probe.c",
         "-T", source_root / "stm32f103c8.ld", f"-Wl,-Map={output / 'probe.map'},--gc-sections,--build-id=none",
         "-o", output / "probe.elf"])
    objcopy = compiler.with_name("arm-none-eabi-objcopy")
    run([objcopy, "-O", "binary", output / "probe.elf", output / "probe.bin"])
    sizes = run([compiler.with_name("arm-none-eabi-size"), "-A", output / "probe.elf"])
    (output / "sections.txt").write_text(sizes)
    usage = elf_usage((output / "probe.elf").read_bytes())
    evidence = {"schema_version": 1, "scope": "resource-probe", "compiler_version": version,
                "compiler_sha256": sha256(compiler), "sources": sources,
                "outputs": {name: sha256(output / name) for name in OUTPUTS}, "usage": usage}
    (output / "build.json").write_text(json.dumps(evidence, indent=2) + "\n")
    return verify_probe(source_root, output)


def verify_probe(source_root, build_root):
    try:
        evidence = read_json(resolve_local(build_root, "build.json"))
        if evidence["schema_version"] != 1 or evidence["scope"] != "resource-probe":
            raise ValueError("unsupported firmware evidence scope/version")
        if set(evidence["sources"]) != set(INPUTS) or set(evidence["outputs"]) != set(OUTPUTS):
            raise ValueError("incomplete firmware evidence manifest")
        for root, entries in ((source_root, evidence["sources"]), (build_root, evidence["outputs"])):
            for name, digest in entries.items():
                if sha256(resolve_local(root, name)) != digest:
                    raise ValueError(f"firmware hash drift: {name}")
        usage = elf_usage(resolve_local(build_root, "probe.elf").read_bytes())
        if usage != evidence["usage"]:
            raise ValueError("firmware usage differs from actual ELF")
        return {**usage, "capacity_probe_passed": usage["stack_bytes"] >= 4096,
                "full_firmware_status": "unknown", "scope": "resource-probe",
                "compiler_version": evidence["compiler_version"].splitlines()[0],
                "build_sha256": sha256(resolve_local(build_root, "build.json")),
                "limits": "CRC and queues plus chosen buffer/stack reservations; no peripheral drivers, USB descriptors, CAN setup or W5500 stack; no measured stack/WCET"}
    except (OSError, KeyError, TypeError) as error:
        raise ValueError(f"missing or invalid firmware evidence: {error}") from error
