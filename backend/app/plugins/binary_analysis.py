from __future__ import annotations

import base64
import binascii
import hashlib
import re
from typing import Any

import capstone
import lief
from app.plugins.contracts import PluginManifest


class BinaryAnalysisApprovalRequired(Exception):
    pass


class BinaryAnalysisPlugin:
    manifest = PluginManifest(
        plugin_id="binary_analysis",
        display_name="Static Binary Analysis",
        description="Onaylı yerel PE/ELF/Mach-O dosyalarından metadata, symbol kayıtları, sınırlı disassembly ve strings çıkarır; binary çalıştırmaz.",
        actions=("inspect",),
    )
    max_binary_bytes = 10_000_000
    max_sections = 100
    max_libraries = 100
    max_symbols_per_library = 100
    max_disassembly_bytes = 256_000
    max_disassembly_instructions = 1_000
    max_function_records = 500
    max_strings = 500
    min_string_length = 4
    max_string_length = 512

    async def invoke(self, action: str, payload: dict[str, Any]) -> dict[str, Any]:
        if action != "inspect":
            raise ValueError(f"Unsupported binary analysis action: {action}")
        if payload.get("approved") is not True:
            raise BinaryAnalysisApprovalRequired("Static binary inspection requires approved=true.")
        filename = payload.get("filename")
        encoded = payload.get("content_base64")
        if not isinstance(filename, str) or not filename.strip() or len(filename) > 255:
            raise ValueError("filename must be a non-empty name up to 255 characters.")
        if not isinstance(encoded, str) or len(encoded) > self.max_binary_bytes * 4 // 3 + 16:
            raise ValueError("content_base64 is missing or exceeds the binary size limit.")
        try:
            raw = base64.b64decode(encoded, validate=True)
        except (ValueError, binascii.Error) as exc:
            raise ValueError("content_base64 is invalid.") from exc
        if not raw or len(raw) > self.max_binary_bytes:
            raise ValueError(f"Binary must be between 1 byte and {self.max_binary_bytes} bytes.")

        try:
            binary = lief.parse(raw)
        except Exception as exc:
            raise ValueError("LIEF could not parse this file as PE, ELF, or Mach-O metadata.") from exc
        if binary is None:
            raise ValueError("LIEF could not parse this file as PE, ELF, or Mach-O metadata.")
        try:
            result = self._metadata(binary, raw)
        except Exception as exc:
            raise ValueError("The parsed binary metadata is incomplete or unsupported.") from exc
        return {
            "status": "inspected",
            "static_only": True,
            "filename": filename.strip(),
            "sha256": hashlib.sha256(raw).hexdigest(),
            "size_bytes": len(raw),
            "metadata": result,
        }

    def _metadata(self, binary: Any, raw: bytes) -> dict[str, Any]:
        if isinstance(binary, lief.PE.Binary):
            return self._with_static_analysis(binary, self._pe_metadata(binary), raw)
        if isinstance(binary, lief.ELF.Binary):
            return self._with_static_analysis(binary, self._elf_metadata(binary), raw)
        if isinstance(binary, lief.MachO.Binary):
            return self._with_static_analysis(binary, self._macho_metadata(binary), raw)
        if isinstance(binary, lief.MachO.FatBinary):
            slices = [
                self._with_static_analysis(item, self._macho_metadata(item), raw)
                for item in list(binary)[:8]
            ]
            return {"format": "Mach-O Universal", "slice_count": len(binary), "slices": slices}
        raise ValueError("Unsupported binary format.")

    def _with_static_analysis(self, binary: Any, metadata: dict[str, Any], raw: bytes) -> dict[str, Any]:
        return {**metadata, "static_analysis": self._static_analysis(binary, raw)}

    def _static_analysis(self, binary: Any, raw: bytes) -> dict[str, Any]:
        machine = self._machine_name(binary)
        strings, strings_truncated = self._extract_strings(raw, self.max_strings)
        entrypoint = int(getattr(binary, "entrypoint", 0))
        functions, functions_truncated = self._function_records(getattr(binary, "functions", []))
        exports, exports_truncated = self._function_records(getattr(binary, "exported_functions", []))
        symbols = {
            "entrypoint": f"0x{entrypoint:x}" if entrypoint else None,
            "functions": functions,
            "functions_truncated": functions_truncated,
            "exports": exports,
            "exports_truncated": exports_truncated,
        }
        if "AMD64" in machine or "X86_64" in machine:
            architecture, mode, architecture_name = capstone.CS_ARCH_X86, capstone.CS_MODE_64, "x86_64"
        elif any(name in machine for name in ("I386", "I486", "I586", "I686", "X86")):
            architecture, mode, architecture_name = capstone.CS_ARCH_X86, capstone.CS_MODE_32, "x86"
        elif "ARM64" in machine or "AARCH64" in machine:
            architecture, mode, architecture_name = capstone.CS_ARCH_ARM64, capstone.CS_MODE_LITTLE_ENDIAN, "arm64"
        else:
            return {
                "supported": False,
                "architecture": machine or "unknown",
                "reason": "Instruction decoding is unavailable for this architecture.",
                "instructions": [],
                "strings": strings,
                "strings_truncated": strings_truncated,
                **symbols,
            }

        sections = self._entrypoint_first(self._executable_sections(binary), entrypoint)
        instructions, disassembly_truncated = self._disassemble_code(sections, architecture, mode)
        return {
            "supported": True,
            "architecture": architecture_name,
            "instructions": instructions,
            "disassembly_truncated": disassembly_truncated,
            "strings": strings,
            "strings_truncated": strings_truncated,
            **symbols,
        }

    def _function_records(self, functions: Any) -> tuple[list[dict[str, Any]], bool]:
        records = []
        truncated = False
        for index, function in enumerate(functions):
            if index >= self.max_function_records:
                truncated = True
                break
            name = getattr(function, "name", None)
            records.append({
                "name": name[:255] if isinstance(name, str) and name else None,
                "address": f"0x{int(function.address):x}",
                "size": int(function.size),
            })
        return records, truncated

    @staticmethod
    def _entrypoint_first(
        sections: list[tuple[str, int, bytes]], entrypoint: int
    ) -> list[tuple[str, int, bytes]]:
        for index, (name, address, content) in enumerate(sections):
            offset = entrypoint - address
            if 0 <= offset < len(content):
                return [(name, entrypoint, content[offset:]), *sections[:index], *sections[index + 1 :]]
        return sections

    @staticmethod
    def _machine_name(binary: Any) -> str:
        if isinstance(binary, lief.PE.Binary):
            value = binary.header.machine
        elif isinstance(binary, lief.ELF.Binary):
            value = binary.header.machine_type
        elif isinstance(binary, lief.MachO.Binary):
            value = binary.header.cpu_type
        else:
            return ""
        return str(value).split(".")[-1].upper()

    @staticmethod
    def _executable_sections(binary: Any) -> list[tuple[str, int, bytes]]:
        sections = []
        for section in binary.sections:
            if isinstance(binary, lief.PE.Binary):
                executable = any("MEM_EXECUTE" in str(value) for value in section.characteristics_lists)
                address = int(binary.optional_header.imagebase) + int(section.virtual_address)
            elif isinstance(binary, lief.ELF.Binary):
                executable = section.has(lief.ELF.Section.FLAGS.EXECINSTR)
                address = int(section.virtual_address)
            else:
                executable = section.has(lief.MachO.Section.FLAGS.PURE_INSTRUCTIONS) or section.has(
                    lief.MachO.Section.FLAGS.SOME_INSTRUCTIONS
                )
                address = int(section.virtual_address)
            content = bytes(section.content)
            if executable and content:
                sections.append((str(section.name)[:255], address, content))
        return sections

    def _disassemble_code(
        self,
        sections: list[tuple[str, int, bytes]],
        architecture: int,
        mode: int,
    ) -> tuple[list[dict[str, str]], bool]:
        decoder = capstone.Cs(architecture, mode)
        instructions: list[dict[str, str]] = []
        remaining_bytes = self.max_disassembly_bytes
        truncated = sum(len(content) for _, _, content in sections) > remaining_bytes
        for section_name, address, content in sections:
            if remaining_bytes <= 0 or len(instructions) >= self.max_disassembly_instructions:
                truncated = True
                break
            data = content[:remaining_bytes]
            for instruction in decoder.disasm(data, address):
                if len(instructions) >= self.max_disassembly_instructions:
                    truncated = True
                    break
                instructions.append({
                    "section": section_name,
                    "address": f"0x{instruction.address:x}",
                    "bytes": instruction.bytes.hex(),
                    "mnemonic": instruction.mnemonic,
                    "operands": instruction.op_str,
                })
            remaining_bytes -= len(data)
        return instructions, truncated

    def _extract_strings(self, raw: bytes, limit: int) -> tuple[list[dict[str, str]], bool]:
        matches: list[dict[str, str]] = []
        truncated = False
        patterns = (
            (re.compile(rb"[\x20-\x7e]{%d,%d}" % (self.min_string_length, self.max_string_length)), "ascii"),
            (
                re.compile(rb"(?:[\x20-\x7e]\x00){%d,%d}" % (self.min_string_length, self.max_string_length)),
                "utf-16le",
            ),
        )
        for pattern, encoding in patterns:
            encoding_matches = 0
            for match in pattern.finditer(raw):
                if encoding_matches >= limit + 1:
                    truncated = True
                    break
                try:
                    value = match.group().decode(encoding, errors="strict")
                except UnicodeDecodeError:
                    continue
                matches.append({"offset": f"0x{match.start():x}", "encoding": encoding, "value": value})
                encoding_matches += 1
        matches.sort(key=lambda item: int(item["offset"], 16))
        return matches[:limit], truncated or len(matches) > limit

    def _pe_metadata(self, binary: lief.PE.Binary) -> dict[str, Any]:
        optional = binary.optional_header
        machine = str(binary.header.machine).split(".")[-1]
        imports = []
        for library in list(binary.imports)[: self.max_libraries]:
            imports.append({
                "name": library.name[:255],
                "symbols": [symbol.name[:255] if symbol.name else f"ordinal:{symbol.ordinal}" for symbol in list(library.entries)[: self.max_symbols_per_library]],
            })
        return {
            "format": "PE",
            "architecture": machine,
            "bits": 64 if "64" in machine else 32,
            "entrypoint_rva": int(optional.addressof_entrypoint),
            "image_base": int(optional.imagebase),
            "subsystem": str(optional.subsystem).split(".")[-1],
            "dll_characteristics": [str(value).split(".")[-1] for value in optional.dll_characteristics_lists],
            "sections": [self._section(section) for section in list(binary.sections)[: self.max_sections]],
            "imports": imports,
            "truncated_sections": len(binary.sections) > self.max_sections,
            "truncated_libraries": len(binary.imports) > self.max_libraries,
        }

    def _elf_metadata(self, binary: lief.ELF.Binary) -> dict[str, Any]:
        libraries = list(binary.libraries)[: self.max_libraries]
        identity_class = str(binary.header.identity_class).split(".")[-1]
        return {
            "format": "ELF",
            "architecture": str(binary.header.machine_type).split(".")[-1],
            "bits": 64 if "64" in identity_class else 32,
            "entrypoint": int(binary.entrypoint),
            "interpreter": binary.interpreter or None,
            "libraries": [str(name)[:255] for name in libraries],
            "sections": [self._section(section) for section in list(binary.sections)[: self.max_sections]],
            "truncated_sections": len(binary.sections) > self.max_sections,
            "truncated_libraries": len(binary.libraries) > self.max_libraries,
        }

    def _macho_metadata(self, binary: lief.MachO.Binary) -> dict[str, Any]:
        libraries = list(binary.libraries)[: self.max_libraries]
        return {
            "format": "Mach-O",
            "architecture": str(binary.header.cpu_type).split(".")[-1],
            "bits": 64 if "64" in str(binary.header.cpu_type) else 32,
            "entrypoint": int(binary.entrypoint),
            "libraries": [str(name)[:255] for name in libraries],
            "sections": [self._section(section) for section in list(binary.sections)[: self.max_sections]],
            "truncated_sections": len(binary.sections) > self.max_sections,
            "truncated_libraries": len(binary.libraries) > self.max_libraries,
        }

    @staticmethod
    def _section(section: Any) -> dict[str, Any]:
        pe_section = isinstance(section, lief.PE.Section)
        return {
            "name": str(section.name)[:255],
            "virtual_size": int(getattr(section, "virtual_size", getattr(section, "size", 0))),
            "file_size": int(getattr(section, "sizeof_raw_data", getattr(section, "size", 0))),
            "executable": any("MEM_EXECUTE" in str(value) for value in section.characteristics_lists)
            if pe_section
            else None,
        }