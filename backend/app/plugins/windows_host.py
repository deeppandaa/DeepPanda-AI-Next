from __future__ import annotations

from typing import Any

from app.plugins.contracts import PluginManifest
from app.plugins.integration_errors import IntegrationUnavailableError

PATH = {"name": "path", "label": "Windows tam dosya yolu (masaüstü dahil)", "required": True, "maxLength": 1024}
DIRECTORY = {"name": "path", "label": "Yeni Windows klasörünün tam yolu", "required": True, "maxLength": 1024}
QUERY = {"name": "query", "label": "Ad / kimlik filtresi", "maxLength": 200}
LIMIT = {"name": "limit", "label": "Sonuç sınırı", "type": "number", "value": "50", "min": 1, "max": 200}
INSTANCE = {"name": "instance_id", "label": "Tam PnP Instance ID (envanterden)", "required": True, "maxLength": 2000}
REGISTRY = [
    {"name": "key", "label": r"Anahtar (HKCU\Software\... veya HKLM\SOFTWARE\...)", "required": True, "maxLength": 1024},
    {"name": "name", "label": "Değer adı (boş = varsayılan)", "maxLength": 255},
    {"name": "view", "label": "Kayıt görünümü", "type": "select", "options": ["64", "32"]},
]
PROJECT = {"name": "project", "label": "Proje adı (projects altında yeni/oluşturulmuş proje)",
           "required": True, "maxLength": 60, "pattern": r"[a-z][a-z0-9_-]{0,59}"}
PROJECT_FILES = {
    "name": "files", "label": "Dosyalar JSON: [{\"path\":\"main.py\",\"content\":\"...\"}]",
    "type": "json", "required": True,
    "schema": {"type": "array", "minItems": 1, "maxItems": 16, "items": {
        "type": "object", "properties": {
            "path": {"type": "string", "minLength": 1, "maxLength": 200},
            "content": {"type": "string", "maxLength": 32000},
        }, "required": ["path", "content"], "additionalProperties": False,
    }},
}

HOST_FORMS: list[dict[str, Any]] = [
    {"action": "status", "title": "Windows host yetenekleri / yönetici durumu", "fields": []},
    {"action": "system_info", "title": "Windows sistem bilgisi", "fields": []},
    {"action": "project_create", "title": "Tariften çok dosyalı Python projesi oluştur (projects altında; test ve README dahil)",
     "fields": [PROJECT, PROJECT_FILES,
                {"name": "criteria",
                 "label": "Ölçüt taslağı (orijinal isteği kapsaması beklenir; her madde yeni satırda)",
                 "required": True, "maxLength": 4000},
                {"name": "criteria_request_sha256", "label": "İlk isteğin SHA-256 parmak izi (ajan tarafından eklenir)",
                 "maxLength": 64, "pattern": r"[a-f0-9]{64}"}]},
    {"action": "project_update", "title": "Oluşturulmuş projenin dosyalarını düzelt (diff/hash ve yeni onay)",
     "fields": [PROJECT, PROJECT_FILES]},
    {"action": "project_environment", "title": "Projeye özel yalıtılmış Python ortamını kur; isteğe bağlı sabit paketleri indir (ayrı ağ onayı)",
     "fields": [PROJECT, {"name": "packages", "label": "Paketler: ad==sürüm, satır başına bir (boş = yalnız temel Python)",
                         "type": "lines", "maxLines": 20, "maxLineLength": 160}]},
    {"action": "project_test", "title": "Projenin test_*.py unittest testlerini çalıştır (gerçek sonuç; hata varsa project_update ile düzelt)",
     "fields": [PROJECT, {"name": "timeout", "label": "Süre sınırı (saniye)", "type": "number",
                         "value": "30", "min": 1, "max": 120}]},
    {"action": "project_package", "title": "Açık istekle Windows konsol EXE paketle ve sonlu açılış testi yap (ayrı onay; PyInstaller önceden kurulu olmalı)",
     "fields": [PROJECT,
               {"name": "entrypoint", "label": "Mevcut göreli Python giriş dosyası", "required": True, "maxLength": 260},
               {"name": "smoke_arguments", "label": "EXE açılış testi argümanları (satır başına bir)",
                "type": "lines", "maxLines": 20, "maxLineLength": 500},
               {"name": "timeout", "label": "Test/build/açılış toplam süre sınırı (saniye)",
                "type": "number", "value": "180", "min": 1, "max": 300}]},
    {"action": "directory_create", "title": "Host üzerinde yeni boş klasör oluştur (önizleme ve onay)", "fields": [DIRECTORY]},
    {"action": "file_read", "title": "Host dosyası oku (proje dışı dahil)", "fields": [PATH]},
    {"action": "file_write", "title": "Windows tam yolunda dosya / kod yaz veya oluştur (diff, yedek)", "fields": [
        PATH, {"name": "content", "label": "UTF-8 içerik (aynen korunur)", "type": "textarea",
               "required": True, "preserveWhitespace": True, "maxLength": 1_000_000}]},
    {"action": "file_delete", "title": "Tek host dosyasını yedekleyip kaldır", "fields": [PATH]},
    {"action": "python_run", "title": "Python dosyasını Windows'ta çalıştır (kod/hash önizleme ve ayrı onay)", "fields": [
        PATH,
        {"name": "arguments", "label": "Program argümanları (satır başına bir; kabuk komutu değil)",
         "type": "lines", "maxLines": 32, "maxLineLength": 1024},
        {"name": "timeout", "label": "Süre sınırı (saniye)", "type": "number", "value": "30", "min": 1, "max": 120},
    ]},
    {"action": "devices", "title": "USB / PnP aygıt tespiti ve hata kodları", "fields": [
        QUERY, LIMIT, {"name": "usb_only", "label": "Yalnız USB", "type": "checkbox"}]},
    {"action": "ports", "title": "COM / seri port envanteri (veri göndermez)", "fields": [QUERY, LIMIT]},
    {"action": "drivers", "title": "Aygıt sürücüleri / sürüm / imza kontrolü", "fields": [QUERY, LIMIT]},
    {"action": "driver_packages", "title": "Driver Store üçüncü taraf paketleri", "fields": []},
    {"action": "com_list", "title": "COM / DCOM uygulama envanteri", "fields": [QUERY, LIMIT]},
    {"action": "com_info", "title": "CLSID / AppID kaydı ve DCOM yapılandırması", "fields": [
        {"name": "clsid", "label": "CLSID (GUID)", "required": True, "maxLength": 38}]},
    {"action": "dcom_events", "title": "Son DistributedCOM olayları (tanı)", "fields": [{**LIMIT, "value": "20"}]},
    {"action": "registry_read", "title": "Kayıt defteri değerini oku", "fields": REGISTRY},
    {"action": "registry_set", "title": "Hedefli kayıt değeri düzelt / ekle (yedekli)", "fields": [
        *REGISTRY,
        {"name": "value_type", "label": "Değer türü", "type": "select",
         "options": ["REG_SZ", "REG_EXPAND_SZ", "REG_DWORD", "REG_QWORD", "REG_MULTI_SZ"]},
        {"name": "data", "label": "Veri (MULTI_SZ için satır başına bir)", "type": "textarea",
         "preserveWhitespace": True, "maxLength": 65_536}]},
    {"action": "registry_delete", "title": "Tek kayıt değerini kaldır (anahtar ağacı silinmez)", "fields": REGISTRY},
    {"action": "network_check", "title": "Dış / yerel hedefe DNS ve TCP bağlantı testi", "fields": [
        {"name": "host", "label": "Sunucu adı / IP (URL veya kimlik bilgisi değil)", "required": True, "maxLength": 253},
        {"name": "port", "label": "TCP portu", "type": "number", "value": "443", "min": 1, "max": 65535}]},
    *[
        {"action": f"device_{action}", "title": title, "fields": [INSTANCE]}
        for action, title in (
            ("enable", "Tek aygıtı etkinleştir"), ("disable", "Tek aygıtı devre dışı bırak"),
            ("restart", "Tek aygıtı yeniden başlat"), ("remove", "Tek aygıt kaydını kaldır (alt ağaç değil)"),
        )
    ],
    {"action": "device_scan", "title": "Yeni / çıkarılan aygıtları yeniden tara", "fields": []},
    {"action": "driver_install", "title": "Yerel imzalı INF sürücü paketini ekle / kur", "fields": [
        {"name": "path", "label": "Yalıtılmış sürücü klasöründeki tam .inf yolu", "required": True, "maxLength": 1024}]},
    {"action": "driver_remove", "title": "Kullanılmayan OEM sürücü paketini yedekle / kaldır", "fields": [
        {"name": "inf_name", "label": "Tam paket adı (oem42.inf gibi)", "required": True,
         "pattern": r"oem[0-9]+\.inf", "maxLength": 30}]},
    {"action": "rollback", "title": "Host dosya / kayıt değeri işlemini geri al", "fields": [
        {"name": "operation_id", "label": "Başarılı işlemde verilen operation_id", "required": True, "maxLength": 32}]},
]

HOST_MUTATIONS = frozenset({
    "directory_create", "file_write", "file_delete", "python_run", "project_create", "project_update",
    "project_environment", "project_test", "project_package", "registry_set", "registry_delete", "network_check",
    "device_enable", "device_disable", "device_restart", "device_remove", "device_scan",
    "driver_install", "driver_remove", "rollback",
})
HOST_READ_ONLY = frozenset(item["action"] for item in HOST_FORMS) - HOST_MUTATIONS
HOST_PRIVATE_READS = frozenset({"file_read", "registry_read"})

for form in HOST_FORMS:
    form["plugin"] = "windows_host"
    if form["action"] in HOST_MUTATIONS | HOST_PRIVATE_READS:
        form["approval"] = "Windows host işlemi hedef ve etkileri incelendikten sonra onaylanmalıdır."


class WindowsHostPlugin:
    manifest = PluginManifest(
        "windows_host", "Windows Host / USB / COM / Sürücü / Kayıt",
        "Windows Qt hostunda masaüstü dahil mutlak Windows yollarında klasör/dosya oluşturma, kod yazma ve okuma; "
        "USB/PnP/COM/DCOM tanısı, sürücüler, kayıt değerleri ve onaylı dış bağlantı testi. "
        "Mevcut Python dosyasını yerel sabit yorumlayıcıyla ayrı kod/hash onayından sonra çalıştırabilir; "
        "Tariften uygulama için project_create çok dosya yazar, project_environment ayrı ortam kurar, "
        "project_test gerçek unittest çalıştırır, project_update test hatalarını düzeltebilir. "
        "Yalnız açık EXE isteğinde project_package ayrı onayla konsol/onedir paket ve sonlu açılış testi yapar; "
        "önce project_environment ile pyinstaller==6.16.0 ayrıca kurulmalıdır. "
        "bu bir güvenlik sandbox'ı değildir, dosya yazmak çalıştırma onayı sayılmaz. "
        "Docker/web yalnız yetenek bildirir; Windows'u yönetemez. "
        "Değişiklikler önizleme/onay, dosya/kayıt işlemleri yedek ve yarış kontrolü gerektirir.",
        (*[item["action"] for item in HOST_FORMS], "preview"),
    )

    async def invoke(self, action: str, payload: dict[str, Any]) -> dict[str, Any]:
        if action == "status":
            return {
                "available": False, "execution_location": "Windows Qt desktop only",
                "reason": "Windows araçlarını Qt sohbetindeki Araçlar / MCP > Windows host bölümünden kullanın.",
                "actions": list(self.manifest.actions),
            }
        raise IntegrationUnavailableError(
            "Windows host işlemleri HTTP/Docker üzerinden çalıştırılmaz. Qt masaüstü istemcisini kullanın."
        )
