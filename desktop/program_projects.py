from __future__ import annotations

import base64
import difflib
import hashlib
import json
import re
import tempfile
import time
import uuid
from pathlib import Path, PureWindowsPath
from threading import Event
from typing import Any

from desktop.chat_context import (
    ChatCancelled,
    check_cancelled,
    validate_attachment_path,
)
from desktop.program_delivery import create_delivery
from desktop.python_runner import execution_environment, run_python

ACTIONS = frozenset({"project_create", "project_update", "project_environment", "project_test", "project_package"})
PACKAGER = "6.16.0"
EXTENSIONS = {".py", ".md", ".txt", ".json", ".toml", ".csv", ".html", ".css", ".js"}
TEST_SOURCE = """import json,os,sys,unittest
suite = unittest.defaultTestLoader.discover('.', pattern='test_*.py')
count = suite.countTestCases()
if not count:
    print('No unittest tests discovered', file=sys.stderr)
    raise SystemExit(2)
active_test = [None]
executed_lines = {}
line_truncated = set()
test_paths = {}
line_limit = 2000
def trace_test_lines(frame, event, _arg):
    active = active_test[0]
    if event == 'line' and active is not None:
        filename = os.path.normcase(os.path.abspath(frame.f_code.co_filename))
        if filename == active[1]:
            lines = executed_lines.setdefault(active[0], set())
            if frame.f_lineno not in lines:
                if len(lines) < line_limit:
                    lines.add(frame.f_lineno)
                else:
                    line_truncated.add(active[0])
    return trace_test_lines
class TrackingResult(unittest.TextTestResult):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.test_ids = []
    def startTest(self, test):
        test_id = test.id()
        self.test_ids.append(test_id)
        module = sys.modules.get(test.__class__.__module__)
        filename = getattr(module, '__file__', None)
        if isinstance(filename, str):
            filename = os.path.normcase(os.path.abspath(filename))
            active_test[0] = (test_id, filename)
            test_paths[test_id] = filename
        else:
            active_test[0] = None
        super().startTest(test)
    def stopTest(self, test):
        super().stopTest(test)
        active_test[0] = None
class TrackingRunner(unittest.TextTestRunner):
    resultclass = TrackingResult
previous_trace = sys.gettrace()
sys.settrace(trace_test_lines)
try:
    result = TrackingRunner(verbosity=2).run(suite)
finally:
    sys.settrace(previous_trace)
test_id_limit = 40
test_id_length_limit = 300
test_ids = [test_id for test_id in result.test_ids if len(test_id) <= test_id_length_limit]
skipped_test_ids = [test.id() for test, _reason in result.skipped]
bounded_test_ids = test_ids[:test_id_limit]
bounded_skipped_test_ids = [
    test_id for test_id in skipped_test_ids if len(test_id) <= test_id_length_limit
][:test_id_limit]
summary = {'tests': result.testsRun, 'failures': len(result.failures), 'errors': len(result.errors),
           'skipped': len(result.skipped), 'passed': result.wasSuccessful() and result.testsRun > len(result.skipped),
           'test_ids': bounded_test_ids,
           'test_ids_truncated': len(bounded_test_ids) != len(result.test_ids),
           'skipped_test_ids': bounded_skipped_test_ids,
           'skipped_test_ids_truncated': len(bounded_skipped_test_ids) != len(skipped_test_ids),
           'executed_test_lines': [
               {'test_id': test_id, 'path': os.path.relpath(test_paths[test_id], os.getcwd()).replace('\\\\', '/'),
                'lines': sorted(executed_lines.get(test_id, set())),
                'truncated': test_id in line_truncated}
               for test_id in bounded_test_ids if test_id in test_paths
           ]}
issues = [('failure', t, tb) for t, tb in result.failures] + [('error', t, tb) for t, tb in result.errors]
details = {'items': [{'test_id': t.id(), 'kind': kind, 'traceback': tb[-1500:],
                     'truncated': len(tb) > 1500} for kind, t, tb in issues[:8]],
           'omitted': max(0, len(issues) - 8)}
while len(json.dumps(details)) > 10000:
    largest = max(details['items'], key=lambda item: len(item['traceback']))
    if len(largest['traceback']) > 100:
        largest['traceback'] = largest['traceback'][len(largest['traceback']) // 2:]
        largest['truncated'] = True
    else:
        details['items'].pop()
        details['omitted'] += 1
print('DEEPPANDA_TEST_FAILURES=' + json.dumps(details))
print('DEEPPANDA_TEST_RESULT=' + json.dumps(summary))
raise SystemExit(0 if summary['passed'] else 1)
"""
ENV_SOURCE = """import json,subprocess,sys,venv
from pathlib import Path
config = json.loads(sys.argv[1])
target = Path(config['environment'])
if not target.exists():
    venv.EnvBuilder(with_pip=True).create(target)
exe = target / 'Scripts' / 'python.exe'
if config['packages']:
    subprocess.run([str(exe), '-I', '-m', 'pip', '--isolated', 'install',
                    '--disable-pip-version-check', '--no-input', '--only-binary=:all:',
                    '--index-url', 'https://pypi.org/simple', '--cache-dir', config['cache'],
                    *config['packages']], check=True)
subprocess.run([str(exe), '-I', '-m', 'pip', 'check'], check=True)
subprocess.run([str(exe), '-I', '-m', 'pip', 'freeze', '--all'], check=True)
"""
PACKAGE_SOURCE = """import importlib.metadata,json,subprocess,sys
from pathlib import Path
config = json.loads(sys.argv[1])
if importlib.metadata.version('pyinstaller') != config['packager_version']:
    raise RuntimeError('Install the approved pinned PyInstaller version with project_environment first')
output = Path(config['output'])
output.mkdir(parents=True, exist_ok=False)
dependencies = sorted([{
    'name': dist.metadata.get('Name', ''), 'version': dist.version,
    'license': dist.metadata.get('License-Expression') or dist.metadata.get('License') or 'UNKNOWN',
    'license_files': dist.metadata.get_all('License-File') or [],
} for dist in importlib.metadata.distributions()], key=lambda item: item['name'].lower())
(output / 'dependencies.json').write_text(json.dumps({
    'dependencies': dependencies,
    'notice': 'Metadata inventory only, not a license compatibility or redistribution approval.',
}, ensure_ascii=False, indent=2), encoding='utf-8')
subprocess.run([sys.executable, '-B', '-c', config['test_source']], check=True)
subprocess.run([sys.executable, '-I', '-m', 'PyInstaller', '--onedir', '--console',
    '--noupx', '--noconfirm', '--name', config['name'], '--distpath', str(output / 'dist'),
    '--workpath', str(output / 'work'), '--specpath', str(output),
    config['entrypoint']], check=True)
exe = output / 'dist' / config['name'] / (config['name'] + '.exe')
if not exe.is_file():
    raise RuntimeError('Packager did not produce the expected executable')
smoke = subprocess.run([str(exe), *config['smoke_arguments']])
print('DEEPPANDA_PACKAGE_RESULT=' + json.dumps({'smoke_exit_code': smoke.returncode}), flush=True)
raise SystemExit(smoke.returncode)
"""


class ProgramProjects:
    def __init__(self, root: Path, atomic: Any) -> None:
        self.root, self.atomic = root, atomic

    def target(self, name: str) -> Path:
        if not re.fullmatch(r"[a-z][a-z0-9_-]{0,59}", name):
            raise ValueError("Proje adı küçük harfle başlamalı; yalnız a-z, 0-9, _ ve - kullanılabilir.")
        if PureWindowsPath(name).is_reserved():
            raise ValueError("Windows aygıt adı proje adı olamaz.")
        parent = self.root / "projects"
        validate_attachment_path(parent if parent.exists() else self.root)
        target = parent / name
        if target.exists():
            validate_attachment_path(target)
            if not target.is_dir():
                raise ValueError("Proje hedefi klasör olmalıdır.")
        return target

    def marker(self, name: str) -> Path:
        return self.root / "data" / "program-projects" / (name + ".json")

    def managed(self, name: str) -> Path:
        target = self.target(name)
        marker = self.marker(name)
        if not target.is_dir() or not marker.is_file():
            raise ValueError("Önce project_create ile yeni proje oluşturun; mevcut klasör sahiplenilmez.")
        record = json.loads(marker.read_text(encoding="utf-8"))
        if record.get("project") != name or record.get("path") != str(target):
            raise ValueError("Proje kaydı hedefle eşleşmiyor.")
        return target

    @staticmethod
    def relative(name: str) -> Path:
        path = PureWindowsPath(name)
        if path.drive or path.root or not path.parts or len(path.parts) > 5 or any(
            part in {".", ".."} or part.startswith(".") or part != part.rstrip(" .")
            or not re.fullmatch(r"[A-Za-z0-9_-][A-Za-z0-9_.-]*", part)
            or PureWindowsPath(part).is_reserved() for part in path.parts
        ):
            raise ValueError("Proje dosyası güvenli göreli yol olmalıdır; gizli/üst/aygıt yolları kabul edilmez.")
        if path.suffix.casefold() not in EXTENSIONS:
            raise ValueError("Bu proje kaynak dosyası uzantısı desteklenmiyor.")
        return Path(*path.parts)

    def files(self, data: dict[str, Any]) -> dict[str, str]:
        files: dict[str, str] = {}
        total = 0
        for item in data["files"]:
            relative = self.relative(item["path"])
            key = str(relative)
            if key.casefold() in {name.casefold() for name in files}:
                raise ValueError("Yinelenen proje dosyası.")
            if any(relative.is_relative_to(Path(name)) or Path(name).is_relative_to(relative) for name in files):
                raise ValueError("Dosya ve klasör yolları çakışıyor.")
            raw = item["content"].encode("utf-8")
            total += len(raw)
            if len(raw) > 64000 or total > 128000:
                raise ValueError("Proje yazması dosya başına 64 KB/toplam 128 KB sınırını aşıyor.")
            if relative.suffix.casefold() == ".py":
                try:
                    compile(item["content"], key, "exec")
                except SyntaxError as exc:
                    raise ValueError(f"{key}: Python sözdizimi hatası: {exc}") from exc
            files[key] = item["content"]
        return files

    def tree(self, target: Path) -> dict[str, Any]:
        entries = {}
        total = 0
        for index, file in enumerate(sorted(target.rglob("*"))):
            if index >= 512:
                raise ValueError("Proje 512 giriş sınırını aşıyor.")
            validate_attachment_path(file)
            if file.is_file():
                if file.stat().st_nlink != 1:
                    raise ValueError("Proje hardlink dosyası içeremez.")
                total += file.stat().st_size
                if file.stat().st_size > 5_000_000 or total > 20_000_000:
                    raise ValueError("Proje içerik boyutu önizleme sınırını aşıyor.")
                entries[str(file.relative_to(target))] = {
                    "sha256": hashlib.sha256(file.read_bytes()).hexdigest(), "bytes": file.stat().st_size,
                }
            else:
                entries[str(file.relative_to(target))] = {"directory": True}
        return entries

    @staticmethod
    def source_evidence(target: Path, tree: dict[str, Any], max_chars: int = 24_000) -> list[dict[str, Any]]:
        files = [(path, metadata) for path, metadata in tree.items() if "sha256" in metadata]
        files.sort(key=lambda item: (
            0 if Path(item[0]).name.casefold().startswith("test")
            or Path(item[0]).stem.casefold().endswith("_test")
            or any(part.casefold() in {"test", "tests"} for part in Path(item[0]).parts[:-1])
            else 1,
            item[0].casefold(),
        ))
        evidence = []
        remaining = max_chars
        omitted = len(files) > 32
        for relative, metadata in files[:32]:
            if remaining <= 0:
                omitted = True
                break
            raw = (target / relative).read_bytes()
            if hashlib.sha256(raw).hexdigest() != metadata["sha256"]:
                raise ValueError(f"{relative} changed while acceptance review evidence was collected.")
            try:
                content = raw.decode("utf-8")
            except UnicodeDecodeError:
                evidence.append({"path": relative, "content": "", "truncated": True})
                continue
            excerpt = content[:remaining]
            evidence.append({
                "path": relative,
                "content": excerpt,
                "truncated": len(excerpt) < len(content),
            })
            remaining -= len(excerpt)
        if omitted:
            evidence.append({"path": "[additional source files omitted]", "content": "", "truncated": True})
        return evidence

    def interpreter(self) -> dict[str, str]:
        manifest = json.loads((self.root / "tools" / "python-runtime.json").read_text(encoding="utf-8"))
        exe = self.root / "runtimes" / ("python-" + manifest["version"]) / "tools" / "python.exe"
        digest = hashlib.sha256(exe.read_bytes()).hexdigest()
        if digest != manifest["executableSha256"]:
            raise ValueError("Proje temel Python hash doğrulaması başarısız.")
        return {"path": str(exe), "sha256": digest}

    def source_integrity(self, target: Path, before: dict[str, Any]) -> dict[str, Any]:
        after = self.tree(target)
        paths = {path for path in before.keys() | after.keys() if Path(path).suffix.casefold() == ".py"}
        changed = sorted(path for path in paths if before.get(path) != after.get(path))
        return {"unchanged": not changed, "changed_paths": changed[:8], "omitted": max(0, len(changed) - 8)}

    def environment(self, name: str) -> Path:
        self.target(name)
        return self.root / ".tools" / "venvs" / ("program-" + name)

    def environment_state(self, name: str) -> dict[str, str]:
        folder = self.environment(name)
        if any(path.is_symlink() or path.is_junction() for path in (folder, *folder.parents)):
            raise ValueError("Proje ortamında bağlantı/junction kabul edilmez.")
        if not folder.exists():
            return {}
        # This private environment is never a model file-write target.
        for path in (folder, folder / "Scripts", folder / "Scripts" / "python.exe", folder / "pyvenv.cfg"):
            if path.is_symlink() or path.is_junction():
                raise ValueError("Proje ortamında bağlantı/junction kabul edilmez.")
        return {str(path.relative_to(folder)): hashlib.sha256(path.read_bytes()).hexdigest()
                for path in (folder / "Scripts" / "python.exe", folder / "pyvenv.cfg")}

    def snapshot(self, action: str, data: dict[str, Any]) -> dict[str, Any]:
        name = data["project"]
        target = self.target(name)
        if action == "project_create":
            if target.exists() or self.marker(name).exists():
                raise ValueError("Proje zaten var; yeni oluşturma mevcut hedefi değiştirmez.")
            files = self.files(data)
            if not any(Path(key).name.startswith("test_") and key.endswith(".py") for key in files):
                raise ValueError("Yeni projede en az bir test_*.py unittest dosyası gerekir.")
            if not any(Path(key).name.casefold() == "readme.md" for key in files):
                raise ValueError("Yeni projede README.md gerekir.")
            return {"exists": False}
        target = self.managed(name)
        if action == "project_update":
            self.files(data)
        if action == "project_environment":
            for package in data.get("packages", []):
                if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*==[A-Za-z0-9][A-Za-z0-9_.+!-]*", package):
                    raise ValueError("Paket yalnız ad==tam-sürüm olmalıdır; URL, seçenek veya requirements yolu kabul edilmez.")
        if action in {"project_test", "project_package"} and not self.environment(name).is_dir():
            raise ValueError("Önce project_environment ile ayrı Python ortamını oluşturun.")
        if action == "project_package":
            entrypoint = target / self.relative(data["entrypoint"])
            validate_attachment_path(entrypoint)
            if entrypoint.suffix.casefold() != ".py" or not entrypoint.is_file():
                raise ValueError("Paket giriş noktası projenin mevcut .py dosyası olmalıdır.")
            if any("\x00" in argument for argument in data.get("smoke_arguments", [])):
                raise ValueError("Açılış testi argümanları NUL içeremez.")
            output_parent = self.root / "data" / "program-builds" / name
            for path in (output_parent, *output_parent.parents):
                if path.is_symlink() or path.is_junction():
                    raise ValueError("Paket çıktı yolunda bağlantı/junction kabul edilmez.")
        state = {"tree": self.tree(target), "interpreter": self.interpreter(),
                 "environment": self.environment_state(name),
                 "marker": hashlib.sha256(self.marker(name).read_bytes()).hexdigest()}
        if action == "project_update":
            state["previous_content"] = {
                relative: base64.b64encode((target / relative).read_bytes()).decode()
                if (target / relative).is_file() else None for relative in self.files(data)
            }
        return state

    def preview(self, action: str, data: dict[str, Any]) -> dict[str, Any]:
        target = self.target(data["project"])
        extra: dict[str, Any] = {"project_path": str(target)}
        if action in {"project_create", "project_update"}:
            diffs = []
            for name, content in self.files(data).items():
                file = target / name
                old = file.read_text(encoding="utf-8") if file.is_file() else ""
                diff = "".join(difflib.unified_diff(old.splitlines(True), content.splitlines(True), name, name))
                diffs.append({"path": name, "diff": diff[:8000], "truncated": len(diff) > 8000})
            extra["files"] = diffs
        if action in {"project_environment", "project_test", "project_package"}:
            extra["interpreter"] = self.interpreter()
            extra["environment_path"] = str(self.environment(data["project"]))
            extra["execution_warning"] = (
                "Sandbox değildir; proje kodu/paketleri mevcut kullanıcı yetkileriyle çalışır. "
                "Süre ve çıktı sınırı/alt süreç kapatma uygulanır; dosya/ağ etkileri geri alınmaz. "
                "Ortam hash'i yalnız başlatıcı/yapılandırmayı kapsar, bütün paketleri değil."
            )
        if action == "project_environment":
            extra["network_access"] = bool(data.get("packages"))
            extra["packages"] = data.get("packages", [])
            extra["package_warning"] = (
                "Yalnız PyPI wheel paketleri; transitif bağımlılıklar da indirilebilir. "
                "Bu tam hash-kilitli kurulum değildir; gerçek freeze çıktısı kaydedilir."
            )
        if action in {"project_test", "project_package"}:
            extra["integrity_warning"] = (
                "İşlem öncesi/sonrası Python kaynak hash'leri karşılaştırılır. Değişiklik test başarısını "
                "ve ZIP teslimini engeller; otomatik geri alma yoktur. Bu sürekli izleme değildir; "
                "işlem içinde değiştirilip geri alınan kaynakları veya Python dışı dosyaları kapsamaz."
            )
        if action == "project_package":
            extra.update(
                required_package=f"pyinstaller=={PACKAGER}",
                network_access=False, entrypoint=data["entrypoint"],
                output_parent=str(self.root / "data" / "program-builds" / data["project"]),
                smoke_arguments=data.get("smoke_arguments", []),
                package_warning=(
                    "Önce project_environment ile belirtilen PyInstaller sürümünü ayrıca onaylayıp kurun. "
                    "Paketleme indirme/kurulum yapmaz; unittest tekrar çalışır, sonra konsol/onedir EXE "
                    "yeni benzersiz klasöre yazılır ve belirtilen argümanlarla çalıştırılır. "
                    "Sonlu CLI açılış testi gerekir; açık kalan GUI zaman aşımı sayılır. "
                    "Proje/hook/test/EXE kodu kullanıcı yetkisiyle çalışır; sandbox değildir. "
                    "Lisans envanteri hukuki uygunluk onayı değildir; dağıtmadan inceleyin. "
                    "Veri dosyaları, özel hook/spec, imzalama ve tek dosya paketleme kapsam dışıdır. "
                    "Başarısız/iptal edilmiş kısmi çıktılar inceleme için kalır; otomatik tekrar yok."
                    " Başarılı onedir çıktı ve bağımlılık raporu son adımda dosya hash listeli ZIP'e alınır; "
                    "5000 dosya/512 MiB sınırı, aynı toplam süre ve iptal koşulları geçerlidir. "
                    "ZIP imzalı değildir; dağıtmadan içerik/lisansları inceleyin."
                ),
            )
        return extra

    def perform(
        self, action: str, data: dict[str, Any], before: dict[str, Any], *, cancelled: Event | None = None,
    ) -> dict[str, Any]:
        name = data["project"]
        target = self.target(name)
        if action in {"project_create", "project_update"}:
            files = self.files(data)
            if action == "project_create":
                target.parent.mkdir(exist_ok=True)
                stage = Path(tempfile.mkdtemp(prefix="project-stage-", dir=target.parent))
                try:
                    for relative, content in files.items():
                        file = stage / relative
                        file.parent.mkdir(parents=True, exist_ok=True)
                        file.write_bytes(content.encode("utf-8"))
                    stage.rename(target)
                finally:
                    if stage.exists():
                        for file in sorted(stage.rglob("*"), reverse=True):
                            file.unlink() if file.is_file() else file.rmdir()
                        stage.rmdir()
                self.marker(name).parent.mkdir(parents=True, exist_ok=True)
                self.atomic(self.marker(name), json.dumps({
                    "project": name, "path": str(target), "criteria": data["criteria"],
                    "criteria_request_sha256": data.get("criteria_request_sha256"),
                }).encode("utf-8"))
            else:
                for relative, content in files.items():
                    file = target / relative
                    file.parent.mkdir(parents=True, exist_ok=True)
                    self.atomic(file, content.encode("utf-8"))
            for relative, content in files.items():
                if (target / relative).read_bytes() != content.encode("utf-8"):
                    raise ValueError("Yazılan proje içeriği doğrulanamadı; dosyaları inceleyin.")
            return {"project": name, "path": str(target), "written_files": list(files), "tested": False}
        interpreter = Path(before["interpreter"]["path"])
        if action == "project_package":
            return self.package(data, cancelled=cancelled)
        if action == "project_environment":
            config = {"environment": str(self.environment(name)), "packages": data.get("packages", []),
                      "cache": str(self.root / "_tmp" / "pip-cache")}
            result = run_python(
                interpreter, target / "_environment_setup.py",
                base64.b64encode(ENV_SOURCE.encode()).decode(), [json.dumps(config)], 120, self.root,
                cancelled=cancelled,
            )
            result["environment_ready"] = (
                result["exit_code"] == 0 and not result["timed_out"] and not result.get("cancelled")
            )
            if result["environment_ready"]:
                marker = self.marker(name)
                record = json.loads(marker.read_text(encoding="utf-8"))
                record["environment"] = {
                    **config, "output": result["stdout"], "output_truncated": result["stdout_truncated"],
                }
                self.atomic(marker, json.dumps(record, ensure_ascii=False).encode("utf-8"))
        else:
            interpreter = self.environment(name) / "Scripts" / "python.exe"
            env = execution_environment(self.root)
            env["PYTHONDONTWRITEBYTECODE"] = "1"
            with tempfile.TemporaryDirectory(prefix=f"program-{name}-", dir=env["TEMP"]) as scratch:
                env.update(TEMP=scratch, TMP=scratch, TMPDIR=scratch)
                result = run_python(
                    interpreter, target / "_test_runner.py",
                    base64.b64encode(TEST_SOURCE.encode()).decode(), [], data["timeout"], self.root,
                    environment=env, cancelled=cancelled,
                )
            if result.get("cancelled"):
                return {**result, "tests": None, "passed": False, "project": name, "path": str(target)}
            summaries = [line.removeprefix("DEEPPANDA_TEST_RESULT=") for line in result["stdout"].splitlines()
                         if line.startswith("DEEPPANDA_TEST_RESULT=")]
            summary = json.loads(summaries[-1]) if summaries else None
            result["tests"] = summary
            details = [line.removeprefix("DEEPPANDA_TEST_FAILURES=") for line in result["stdout"].splitlines()
                       if line.startswith("DEEPPANDA_TEST_FAILURES=")]
            result["failure_details"] = json.loads(details[-1]) if details else None
            result["source_integrity"] = self.source_integrity(target, before["tree"])
            result["passed"] = bool(
                result["exit_code"] == 0 and not result["timed_out"] and summary
                and summary.get("passed") is True and summary.get("tests", 0) > 0
                and result["source_integrity"]["unchanged"]
            )
            if result["passed"]:
                try:
                    result["source_files"] = self.source_evidence(target, before["tree"])
                except ValueError as exc:
                    result["source_integrity"]["unchanged"] = False
                    result["source_integrity"]["changed_paths"] = ["source_evidence_snapshot"]
                    result["passed"] = False
                    result["integrity_error"] = (
                        f"Bağımsız inceleme kanıtı tutarlılık kontrolü başarısız ({exc}); "
                        "test başarısı geçersiz sayıldı, otomatik geri alma yok."
                    )
            if not result["source_integrity"]["unchanged"]:
                result["integrity_error"] = (
                    result.get("integrity_error")
                    or "Test sırasında Python kaynakları değişti; test başarısı geçersiz. "
                    "Otomatik geri alma yok; değişen dosyaları inceleyin."
                )
            elif not result["passed"]:
                remaining = 24000
                sources = []
                for relative in before["tree"]:
                    if relative.endswith(".py") and remaining > 0:
                        content = (target / relative).read_text(encoding="utf-8")
                        excerpt = content[:min(12000, remaining)]
                        sources.append({"path": relative, "content": excerpt, "truncated": len(excerpt) < len(content)})
                        remaining -= len(excerpt)
                result["source_files"] = sources
        result.update(project=name, path=str(target))
        return result

    def package(self, data: dict[str, Any], *, cancelled: Event | None = None) -> dict[str, Any]:
        deadline = time.monotonic() + data["timeout"]
        name = data["project"]
        target = self.managed(name)
        before_tree = self.tree(target)
        output = self.root / "data" / "program-builds" / name / uuid.uuid4().hex
        config = {
            "output": str(output), "name": name, "packager_version": PACKAGER,
            "entrypoint": str(target / self.relative(data["entrypoint"])),
            "smoke_arguments": data.get("smoke_arguments", []), "test_source": TEST_SOURCE,
        }
        env = execution_environment(self.root)
        env["PYTHONDONTWRITEBYTECODE"] = "1"
        result = run_python(
            self.environment(name) / "Scripts" / "python.exe", target / "_package_runner.py",
            base64.b64encode(PACKAGE_SOURCE.encode()).decode(), [json.dumps(config)],
            data["timeout"], self.root, environment=env, cancelled=cancelled,
        )
        summaries = [line.removeprefix("DEEPPANDA_PACKAGE_RESULT=") for line in result["stdout"].splitlines()
                     if line.startswith("DEEPPANDA_PACKAGE_RESULT=")]
        summary = json.loads(summaries[-1]) if summaries else None
        exe = output / "dist" / name / (name + ".exe")
        report = output / "dependencies.json"
        passed = bool(
            result["exit_code"] == 0 and not result["timed_out"] and not result.get("cancelled")
            and summary and summary.get("smoke_exit_code") == 0 and exe.is_file() and report.is_file()
        )
        integrity = self.source_integrity(target, before_tree)
        if not integrity["unchanged"]:
            passed = False
            result["integrity_error"] = (
                "Paketleme/test sırasında Python kaynakları değişti; paket doğrulanamadı. "
                "Teslim ZIP oluşturulmadı; otomatik geri alma yok."
            )
        result.update(
            project=name, path=str(target), output_path=str(output), packaged=passed,
            smoke_test=summary, dependency_report=str(report) if report.is_file() else None,
            source_integrity=integrity,
            verification_scope=(
                "Fresh unittest, finite CLI launch exit code and ZIP file hashes; "
                "not full application correctness, authenticity or another-machine compatibility."
            ),
        )
        if passed:
            def delivery_check() -> None:
                if cancelled is not None:
                    check_cancelled(cancelled)
                if time.monotonic() >= deadline:
                    raise TimeoutError("Teslim ZIP oluşturma/doğrulama toplam paketleme süresini aştı.")

            try:
                delivery = create_delivery(
                    output, name, check=delivery_check,
                )
            except ChatCancelled:
                result.update(packaged=False, cancelled=True)
            except TimeoutError as exc:
                result.update(packaged=False, timed_out=True, delivery_error=str(exc))
            else:
                result.update(
                    executable=str(exe),
                    **delivery,
                )
        output.parent.mkdir(parents=True, exist_ok=True)
        self.atomic(output.with_suffix(".json"), json.dumps(result, ensure_ascii=False).encode("utf-8"))
        return result
