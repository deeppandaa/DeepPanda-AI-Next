from __future__ import annotations

import base64
import json
import re
from pathlib import Path
from typing import Any

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from desktop.context import AppContext, error_text
from desktop.tasks import run_background
from desktop.widgets import ResultView, StatusLabel
from desktop.windows_host import HOST_FORMS

WEB_FORMS_FILE = Path(__file__).with_name("tool_forms.json")
DRAFT = "__task_draft__"

_DOC = 20_000_000

# Forms for features that live in the web app's main panels (app.js / cloud.js) and for the new
# integrations. Same schema as frontend/tools.js TOOLS so one form builder serves both.
EXTRA_GROUPS: list[dict[str, Any]] = [
    {"id": "multi_agent", "label": "Çoklu ajan", "forms": [
        {"title": "Yerel çoklu ajan akışı", "plugin": "multi_agent", "action": "run",
         "approval": "İstek Qwen/Ollama üzerinde beş yerel ajan aşamasından geçirilsin mi? Ajanlar dosya, ağ veya araç erişimi kullanmaz.",
         "fields": [
             {"name": "request", "label": "İstek", "type": "textarea", "required": True, "maxLength": 6000},
             {"name": "model", "label": "Yerel model (boş = otomatik)"}]},
    ]},
    {"id": "memory", "label": "Hafıza", "forms": [
        {"title": "Hafızada ara", "plugin": "memory", "action": "search", "fields": [
            {"name": "query", "label": "Arama", "required": True, "maxLength": 500},
            {"name": "project", "label": "Proje"}, {"name": "category", "label": "Kategori"},
            {"name": "source", "label": "Kaynak"},
            {"name": "limit", "label": "Sınır", "type": "number", "value": "20", "min": 1, "max": 100}]},
        {"title": "Zaman çizelgesi", "plugin": "memory", "action": "timeline", "fields": [
            {"name": "project", "label": "Proje"},
            {"name": "limit", "label": "Sınır", "type": "number", "value": "20", "min": 1, "max": 100}]},
        {"title": "Kategoriler / projeler", "plugin": "memory", "action": "taxonomy", "fields": []},
        {"title": "Not kaydet", "plugin": "memory", "action": "remember",
         "approval": "Bu not kalıcı hafızaya kaydedilsin mi?", "fields": [
            {"name": "title", "label": "Başlık", "required": True, "maxLength": 200},
            {"name": "project", "label": "Proje"},
            {"name": "category", "label": "Kategori", "value": "general"},
            {"name": "content", "label": "İçerik", "type": "textarea", "required": True, "maxLength": 20000}]},
        {"title": "Öğrenme önerileri", "plugin": "memory", "action": "proposals", "fields": []},
        {"title": "Öneriyi hafızaya kaydet", "plugin": "memory", "action": "approve_proposal",
         "approval": "Bu öneri kalıcı hafızaya kaydedilsin mi?", "fields": [
            {"name": "proposal_id", "label": "Öneri ID", "required": True}]},
        {"title": "Öneriyi reddet", "plugin": "memory", "action": "reject_proposal", "fields": [
            {"name": "proposal_id", "label": "Öneri ID", "required": True}]},
        {"title": "Kaynağı önizle", "plugin": "memory", "action": "preview_source", "fields": [
            {"name": "source", "label": "Kaynak", "required": True}]},
        {"title": "Kaynağı sil", "plugin": "memory", "action": "delete_source",
         "approval": "Bu kaynağa ait tüm hafıza kayıtları silinsin mi?", "fields": [
            {"name": "source", "label": "Kaynak", "required": True}]},
        {"title": "Hafızayı dışa aktar", "plugin": "memory", "action": "export",
         "approval": "Hafıza dışa aktarılsın mı?", "fields": []},
    ]},
    {"id": "documents", "label": "Belgeler", "forms": [
        {"title": "Belge yükle", "plugin": "documents", "action": "ingest", "approval": "Belge yüklensin ve dizinlensin mi?",
         "fields": [{"name": "file", "label": "Belge", "type": "file", "required": True, "maxBytes": _DOC}]},
        {"title": "Belgeler", "plugin": "documents", "action": "list", "fields": [
            {"name": "limit", "label": "Sınır", "type": "number", "value": "100", "min": 1, "max": 500}]},
        {"title": "Belgelerde ara", "plugin": "documents", "action": "search", "fields": [
            {"name": "query", "label": "Arama", "required": True, "maxLength": 500},
            {"name": "limit", "label": "Sınır", "type": "number", "value": "10", "min": 1, "max": 10}]},
        {"title": "Belge önizle", "plugin": "documents", "action": "preview", "fields": [
            {"name": "document_id", "label": "Belge ID", "required": True}]},
        {"title": "Belge sil", "plugin": "documents", "action": "delete", "approval": "Belge kalıcı olarak silinsin mi?",
         "fields": [{"name": "document_id", "label": "Belge ID", "required": True}]},
        {"title": "Belgeyi bilgi tabanına dizinle", "plugin": "knowledge", "action": "index",
         "approval": "Belge Qdrant bilgi tabanına dizinlensin mi?", "fields": [
            {"name": "document_id", "label": "Belge ID", "required": True}]},
        {"title": "Bilgi tabanında ara", "plugin": "knowledge", "action": "search", "fields": [
            {"name": "query", "label": "Arama", "required": True},
            {"name": "limit", "label": "Sınır", "type": "number", "value": "5", "min": 1, "max": 20}]},
        {"title": "Bilgi tabanından kaldır", "plugin": "knowledge", "action": "delete",
         "approval": "Belge bilgi tabanından kaldırılsın mı?", "fields": [
            {"name": "document_id", "label": "Belge ID", "required": True}]},
        {"title": "Belge analizi (LangGraph)", "plugin": "analysis", "action": "run",
         "approval": "Belge yerel modelle analiz edilsin mi?", "fields": [
            {"name": "document_id", "label": "Belge ID", "required": True},
            {"name": "question", "label": "Soru", "type": "textarea", "required": True,
             "value": "Mimariyi, giriş noktalarını, bağımlılıkları, güven sınırlarını ve riskleri özetle."},
            {"name": "model", "label": "Model (boş = otomatik)"}]},
    ]},
    {"id": "tasks", "label": "Görevler", "forms": [
        {"title": "Görev taslağı (plan)", "plugin": DRAFT, "action": "draft", "fields": [
            {"name": "request", "label": "İstek", "type": "textarea", "required": True, "maxLength": 4000},
            {"name": "model", "label": "Model (boş = otomatik)"}]},
        {"title": "Görev oluştur", "plugin": "tasks", "action": "create", "fields": [
            {"name": "request", "label": "İstek", "type": "textarea", "required": True},
            {"name": "steps", "label": "Adımlar (satır başına bir)", "type": "lines", "required": True, "maxLines": 20}]},
        {"title": "Görevler", "plugin": "tasks", "action": "list", "fields": [
            {"name": "limit", "label": "Sınır", "type": "number", "value": "50", "min": 1, "max": 100}]},
        {"title": "Görev ayrıntısı", "plugin": "tasks", "action": "get", "fields": [
            {"name": "task_id", "label": "Görev ID", "required": True}]},
        {"title": "Görevi onayla", "plugin": "tasks", "action": "approve", "approval": "Görev planı onaylansın mı?",
         "fields": [{"name": "task_id", "label": "Görev ID", "required": True}]},
        {"title": "Adım durumu", "plugin": "tasks", "action": "update_step", "approval": "Adım durumu güncellensin mi?",
         "fields": [
            {"name": "task_id", "label": "Görev ID", "required": True},
            {"name": "step_index", "label": "Adım no", "type": "number", "value": "0", "min": 0, "max": 50},
            {"name": "status", "label": "Durum", "type": "select", "options": ["in_progress", "completed", "blocked", "pending"]},
            {"name": "evidence", "label": "Kanıt / not", "type": "textarea"}]},
        {"title": "Görevi doğrula", "plugin": "tasks", "action": "verify", "fields": [
            {"name": "task_id", "label": "Görev ID", "required": True}]},
        {"title": "Adım için değişiklik öner (Qwen)", "plugin": "task_assistant", "action": "propose_change",
         "approval": "Yerel model bu adım için dosya değişikliği önersin mi? (dosyaya yazılmaz)", "fields": [
            {"name": "task_id", "label": "Görev ID", "required": True},
            {"name": "step_index", "label": "Adım no", "type": "number", "value": "0", "min": 0, "max": 50},
            {"name": "path", "label": "Dosya yolu", "required": True},
            {"name": "context_paths", "label": "Bağlam dosyaları", "type": "lines", "maxLines": 10},
            {"name": "instruction", "label": "Talimat", "type": "textarea", "required": True},
            {"name": "model", "label": "Model (boş = otomatik)"}]},
    ]},
    {"id": "workspace", "label": "Çalışma alanı (proje içi)", "forms": [
        {"title": "Proje içindeki dosyaları listele", "plugin": "workspace", "action": "list", "fields": [
            {"name": "path", "label": "Proje içi göreli klasör", "value": "."}]},
        {"title": "Proje içindeki dosyayı oku", "plugin": "workspace", "action": "read", "fields": [
            {"name": "path", "label": "Proje içi göreli dosya yolu", "required": True}]},
        {"title": "Proje içi dosyanın yazma önizlemesi", "plugin": "workspace", "action": "preview_write", "fields": [
            {"name": "path", "label": "Proje içi göreli dosya yolu", "required": True},
            {"name": "content", "label": "Yeni içerik", "type": "textarea", "required": True}]},
        {"title": "Proje içi göreli yola dosya yaz (masaüstü için Windows host)", "plugin": "workspace", "action": "write", "approval": "Dosya yazılsın mı? (yedek alınır)",
         "fields": [
            {"name": "path", "label": "Proje içi göreli yol; Windows masaüstü yolu değil", "required": True},
            {"name": "content", "label": "İçerik", "type": "textarea", "required": True},
            {"name": "expected_sha256", "label": "Beklenen SHA-256 (önizlemeden)"}]},
        {"title": "Komut çalıştır", "plugin": "workspace", "action": "run", "approval": "Komut çalışma alanında çalıştırılsın mı?",
         "fields": [
            {"name": "command", "label": "Komut", "required": True},
            {"name": "timeout_seconds", "label": "Zaman aşımı (sn)", "type": "number", "value": "120", "min": 1, "max": 900}]},
        {"title": "Yedekten geri al", "plugin": "workspace", "action": "rollback", "approval": "Dosya yedekten geri alınsın mı?",
         "fields": [{"name": "backup_id", "label": "Yedek ID", "required": True}]},
        {"title": "Kod grafiği oluştur", "plugin": "codegraph", "action": "build", "fields": []},
        {"title": "Kod grafiğinde ara", "plugin": "codegraph", "action": "search", "fields": [
            {"name": "query", "label": "Arama", "required": True},
            {"name": "limit", "label": "Sınır", "type": "number", "value": "50", "min": 1, "max": 200}]},
        {"title": "Kod grafiğinde yol", "plugin": "codegraph", "action": "path", "fields": [
            {"name": "source", "label": "Kaynak", "required": True}, {"name": "target", "label": "Hedef", "required": True}]},
        {"title": "Tanılama taraması", "plugin": "diagnostics", "action": "scan", "fields": []},
    ]},
    {"id": "research", "label": "Araştırma", "forms": [
        {"title": "Web'de ara", "plugin": "research", "action": "search", "fields": [
            {"name": "query", "label": "Arama", "required": True},
            {"name": "limit", "label": "Sınır", "type": "number", "value": "5", "min": 1, "max": 10}]},
        {"title": "Kaynaklı araştırma başlat", "plugin": "research", "action": "start",
         "approval": "Verilen adresler indirilip yerel modelle araştırma yapılsın mı?", "fields": [
            {"name": "question", "label": "Soru", "type": "textarea", "required": True},
            {"name": "urls", "label": "Adresler (satır başına bir)", "type": "lines", "required": True, "maxLines": 10},
            {"name": "model", "label": "Model (boş = otomatik)"}]},
        {"title": "GitHub depolarında araştır", "plugin": "research", "action": "start_github",
         "approval": "GitHub depoları okunup araştırma yapılsın mı?", "fields": [
            {"name": "question", "label": "Soru", "type": "textarea", "required": True},
            {"name": "repositories", "label": "Depolar (owner/name)", "type": "lines", "required": True, "maxLines": 10},
            {"name": "model", "label": "Model (boş = otomatik)"}]},
        {"title": "Araştırmayı hafızaya kaydet", "plugin": "research", "action": "save_to_memory",
         "approval": "Araştırma sonucu hafızaya kaydedilsin mi?", "fields": [
            {"name": "job_id", "label": "İş ID", "required": True}]},
        {"title": "Sayfa incele (tarayıcı)", "plugin": "browser", "action": "inspect", "approval": "Sayfa tarayıcıda açılıp incelensin mi?",
         "fields": [{"name": "url", "label": "Adres", "type": "url", "required": True}]},
        {"title": "İkili dosya incele (PE lab)", "plugin": "binary_analysis", "action": "inspect",
         "approval": "Dosya statik olarak incelensin mi? (çalıştırılmaz)", "fields": [
            {"name": "file", "label": "EXE/DLL/ELF", "type": "file", "required": True, "maxBytes": 10_000_000}]},
    ]},
    {"id": "repo_watch", "label": "Repo izleme", "forms": [
        {"title": "İzlenen depolar", "plugin": "repo_watch", "action": "list", "fields": []},
        {"title": "Depo ekle", "plugin": "repo_watch", "action": "add", "approval": "Depo izlemeye eklensin mi?",
         "fields": [{"name": "repository", "label": "Depo (owner/name)", "required": True}]},
        {"title": "Güncelleme kontrolü", "plugin": "repo_watch", "action": "check", "approval": "GitHub'dan güncelleme kontrol edilsin mi?",
         "fields": [{"name": "repository", "label": "Depo", "required": True}]},
        {"title": "README anlık görüntüsü", "plugin": "repo_watch", "action": "snapshot_readme",
         "approval": "README indirilsin mi?", "fields": [{"name": "repository", "label": "Depo", "required": True}]},
        {"title": "Dosya anlık görüntüsü", "plugin": "repo_watch", "action": "snapshot_files", "approval": "Dosyalar indirilsin mi?",
         "fields": [{"name": "repository", "label": "Depo", "required": True},
                    {"name": "paths", "label": "Yollar", "type": "lines", "required": True, "maxLines": 20}]},
        {"title": "Depoyu kaldır", "plugin": "repo_watch", "action": "remove", "approval": "Depo izlemeden kaldırılsın mı?",
         "fields": [{"name": "repository", "label": "Depo", "required": True}]},
        {"title": "Otomatik kontrol durumu", "plugin": "repo_watch", "action": "polling_status", "fields": []},
        {"title": "Otomatik kontrolü ayarla", "plugin": "repo_watch", "action": "configure_polling",
         "approval": "Otomatik kontrol ayarı değiştirilsin mi?", "fields": [
            {"name": "enabled", "label": "Etkin", "type": "checkbox"},
            {"name": "interval_minutes", "label": "Aralık (dk)", "type": "number", "value": "60", "min": 5, "max": 1440}]},
    ]},
    {"id": "cloud", "label": "Bulut API", "forms": [
        {"title": "Sağlayıcılar", "plugin": "cloud_providers", "action": "catalog", "fields": []},
        {"title": "API anahtarı kaydet", "plugin": "cloud_providers", "action": "save_key", "fields": [
            {"name": "provider", "label": "Sağlayıcı ID", "required": True},
            {"name": "api_key", "label": "API anahtarı", "type": "password", "required": True}]},
        {"title": "API anahtarını kaldır", "plugin": "cloud_providers", "action": "remove_key",
         "approval": "Sağlayıcının kayıtlı anahtarı silinsin mi?", "fields": [
            {"name": "provider", "label": "Sağlayıcı ID", "required": True}]},
        {"title": "Modeller", "plugin": "cloud_providers", "action": "models", "fields": [
            {"name": "provider", "label": "Sağlayıcı ID", "required": True}]},
        {"title": "Birden çok modele danış", "plugin": "cloud_providers", "action": "consult",
         "approval": "Soru seçili bulut sağlayıcılarına gönderilsin mi?", "fields": [
            {"name": "providers", "label": "Sağlayıcılar (satır başına)", "type": "lines", "required": True, "maxLines": 6},
            {"name": "task", "label": "Görev türü", "type": "select", "options": ["info", "code", "review", "debug"]},
            {"name": "message", "label": "Soru", "type": "textarea", "required": True}]},
    ]},
    {"id": "skills", "label": "Beceriler (replica-skill)", "forms": [
        {"title": "Önerilen beceri paketleri", "plugin": "skills", "action": "sources", "fields": []},
        {"title": "Beceri paketi kur (GitHub)", "plugin": "skills", "action": "install",
         "approval": "Beceri paketi GitHub'dan indirilip /data/skills altına kurulsun mu?", "fields": [
            {"name": "repo", "label": "Depo", "value": "Jakeschincariol/replica-skill", "required": True},
            {"name": "ref", "label": "Dal/etiket", "value": "HEAD"}]},
        {"title": "Kurulu beceriler", "plugin": "skills", "action": "list", "fields": []},
        {"title": "Beceri ayrıntısı", "plugin": "skills", "action": "get", "fields": [
            {"name": "skill", "label": "Beceri (paket:ad)", "required": True, "placeholder": "replica-skill:replica-recon"}]},
        {"title": "Beceriyi uygula (Qwen)", "plugin": "skills", "action": "apply", "fields": [
            {"name": "skill", "label": "Beceri (paket:ad)", "required": True, "placeholder": "replica-skill:replica-architect"},
            {"name": "message", "label": "İstek", "type": "textarea", "required": True},
            {"name": "model", "label": "Model (boş = qwen2.5-coder:7b)"}]},
    ]},
    {"id": "openjarvis", "label": "OpenJarvis", "forms": [
        {"title": "Durum", "plugin": "openjarvis", "action": "status", "fields": []},
        {"title": "Modeller", "plugin": "openjarvis", "action": "models", "fields": []},
        {"title": "Jarvis'e sor", "plugin": "openjarvis", "action": "chat", "fields": [
            {"name": "message", "label": "Mesaj", "type": "textarea", "required": True},
            {"name": "model", "label": "Model (boş = ilk model)"}]},
    ]},
    {"id": "byox", "label": "Build Your Own X", "forms": [
        {"title": "Kategoriler", "plugin": "byox", "action": "categories", "fields": []},
        {"title": "Eğitim ara", "plugin": "byox", "action": "search", "fields": [
            {"name": "query", "label": "Arama"}, {"name": "language", "label": "Dil", "placeholder": "Python"},
            {"name": "category", "label": "Kategori", "placeholder": "Database"},
            {"name": "limit", "label": "Sınır", "type": "number", "value": "50", "min": 1, "max": 500}]},
        {"title": "Öğrenme planı çıkar (Qwen)", "plugin": "byox", "action": "plan", "fields": [
            {"name": "url", "label": "Eğitim adresi (aramadan)", "type": "url", "required": True},
            {"name": "goal", "label": "Hedefim", "type": "textarea"},
            {"name": "model", "label": "Model (boş = otomatik)"}]},
        {"title": "Kataloğu yenile", "plugin": "byox", "action": "refresh", "fields": []},
    ]},
    {"id": "graphify", "label": "graphify", "forms": [
        {"title": "Durum", "plugin": "graphify", "action": "status", "fields": []},
        {"title": "Grafik özeti", "plugin": "graphify", "action": "summary", "fields": [
            {"name": "top", "label": "En bağlantılı düğüm sayısı", "type": "number", "value": "15", "min": 1, "max": 100}]},
        {"title": "Düğüm ara", "plugin": "graphify", "action": "query", "fields": [
            {"name": "query", "label": "Arama", "required": True},
            {"name": "limit", "label": "Sınır", "type": "number", "value": "20", "min": 1, "max": 100}]},
        {"title": "Komşular", "plugin": "graphify", "action": "neighbors", "fields": [
            {"name": "node", "label": "Düğüm", "required": True},
            {"name": "depth", "label": "Derinlik", "type": "number", "value": "1", "min": 1, "max": 3},
            {"name": "relation", "label": "İlişki (isteğe bağlı)"},
            {"name": "limit", "label": "Sınır", "type": "number", "value": "50", "min": 1, "max": 300}]},
        {"title": "En kısa yol", "plugin": "graphify", "action": "path", "fields": [
            {"name": "source", "label": "Kaynak", "required": True}, {"name": "target", "label": "Hedef", "required": True},
            {"name": "max_hops", "label": "En fazla adım", "type": "number", "value": "8", "min": 1, "max": 20}]},
        {"title": "GRAPH_REPORT.md", "plugin": "graphify", "action": "report", "fields": []},
    ]},
]


PAGE_TOOL_SPECS: list[dict[str, Any]] = [
    {"plugin": "system", "action": "hardware",
     "title": "API çalışma ortamının CPU/RAM/GPU donanımı (Docker ise Linux konteyneri)", "fields": []},
    {"plugin": "system", "action": "model_assets", "title": "API ortamındaki yerel model dosyaları", "fields": []},
    {"plugin": "system", "action": "readiness", "title": "API çalışma ortamı ve model hazırlığı", "fields": []},
    {"plugin": "ollama", "action": "models", "title": "Kurulu yerel modeller", "fields": []},
    {"plugin": "ollama", "action": "pull", "title": "Yerel Ollama modeli indir (indirme için onay gerekir)", "fields": [
        {"name": "model", "label": "Yerel model adı", "required": True, "maxLength": 232,
         "pattern": "[A-Za-z0-9][A-Za-z0-9._/-]{0,150}(?::[A-Za-z0-9._-]{1,80})?"}]},
    {"plugin": "workflows", "action": "catalog", "title": "Çalışma modları", "fields": []},
    {"plugin": "workflows", "action": "get", "title": "Çalışma modu ayrıntısı", "fields": [
        {"name": "mode", "label": "Mod", "type": "select",
         "options": ["standard", "plan", "debug", "review", "audit", "minimal"]}]},
    {"plugin": "database", "action": "overview", "title": "Veritabanlarını listele", "fields": []},
    {"plugin": "database", "action": "tables", "title": "Veritabanı tabloları ve sütunları", "fields": [
        {"name": "database", "label": "Veritabanı dosya adı", "required": True, "maxLength": 130}]},
    {"plugin": "database", "action": "query", "title": "Veritabanında salt okunur SQL sorgusu", "fields": [
        {"name": "database", "label": "Veritabanı dosya adı", "required": True, "maxLength": 130},
        {"name": "sql", "label": "SELECT, WITH, EXPLAIN veya VALUES sorgusu", "type": "textarea",
         "required": True, "maxLength": 20_000},
        {"name": "limit", "label": "Satır sınırı", "type": "number", "min": 1, "max": 500}]},
    *[
        {"plugin": "database", "action": action, "title": title, "fields": [
            {"name": "database", "label": "Veritabanı dosya adı", "required": True, "maxLength": 130}]}
        for action, title in (("check", "Veritabanı bütünlüğü"), ("backup", "Veritabanını yedekle"))
    ],
    {"plugin": "jobs", "action": "list", "title": "Arka plan işlerini listele", "fields": [
        {"name": "status", "label": "Durum", "type": "select",
         "options": ["queued", "running", "cancel_requested", "succeeded", "failed", "cancelled"]},
        {"name": "limit", "label": "Sınır", "type": "number", "min": 1, "max": 100}]},
    *[
        {"plugin": "jobs", "action": action, "title": title, "fields": [
            {"name": "job_id", "label": "İş kimliği", "required": True, "maxLength": 32}]}
        for action, title in (("get", "İş ayrıntısı"), ("cancel", "İşi iptal et"), ("retry", "İşi yeniden dene"))
    ],
    {"plugin": "jobs", "action": "recover_stale", "title": "Takılı işleri kurtar", "fields": [
        {"name": "stale_after_seconds", "label": "En az hareketsiz süre (saniye)", "type": "number",
         "min": 60, "max": 604_800},
        {"name": "limit", "label": "İş sınırı", "type": "number", "min": 1, "max": 100}]},
    {"plugin": "jobs", "action": "recovery_candidates", "title": "Takılı iş kurtarma önizlemesi", "fields": [
        {"name": "stale_after_seconds", "label": "En az hareketsiz süre (saniye)", "type": "number",
         "min": 60, "max": 604_800},
        {"name": "limit", "label": "İş sınırı", "type": "number", "min": 1, "max": 100}]},
    {"plugin": "memory", "action": "import", "title": "Seçilen hafıza JSON yedeğini onayla ve içe aktar", "fields": [
        {"name": "file", "label": "Seçili hafıza yedeği", "type": "file", "required": True}]},
    {"plugin": "reports", "action": "status", "title": "Rapor araçlarının durumu", "fields": []},
    {"plugin": "evaluation", "action": "suites", "title": "Ölçüm ve test paketleri", "fields": []},
    {"plugin": "multi_agent", "action": "roles", "title": "Çoklu ajan rolleri", "fields": []},
]


def load_groups() -> list[dict[str, Any]]:
    try:
        web_groups = json.loads(WEB_FORMS_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        web_groups = []
    return [*EXTRA_GROUPS, {"id": "windows_host", "label": "Windows host / USB / COM / Kayıt", "forms": HOST_FORMS},
            *(group for group in web_groups if group["id"] != "windows_host")]


def _number(raw: Any, default: float) -> float:
    try:
        return float(raw)
    except (TypeError, ValueError):
        return default


class FormWidget(QWidget):
    """Builds one tool form from a TOOLS-style spec and runs it through the shared approval flow."""

    result_ready = Signal(str, str, object)

    def __init__(self, ctx: AppContext, spec: dict[str, Any]) -> None:
        super().__init__()
        self.ctx = ctx
        self.spec = spec
        self.inputs: dict[str, Any] = {}
        self.file_paths: dict[str, Path | None] = {}
        layout = QVBoxLayout(self)
        title = QLabel(spec["title"])
        title.setObjectName("formTitle")
        layout.addWidget(title)
        hint = QLabel(f"{spec['plugin']} › {spec['action']}" if spec["plugin"] != DRAFT else "/api/tasks/draft")
        hint.setObjectName("hint")
        layout.addWidget(hint)
        form = QFormLayout()
        for field in spec.get("fields", []):
            form.addRow(self._caption(field), self._build_field(field))
        layout.addLayout(form)
        buttons = QHBoxLayout()
        self.run_button = QPushButton("Onayla ve çalıştır" if spec.get("approval") else "Çalıştır")
        self.run_button.setObjectName("primary")
        self.run_button.clicked.connect(self.submit)
        buttons.addWidget(self.run_button)
        buttons.addStretch(1)
        layout.addLayout(buttons)
        self.status = StatusLabel()
        layout.addWidget(self.status)
        self.result = ResultView(ctx)
        layout.addWidget(self.result, 1)

    @staticmethod
    def _caption(field: dict[str, Any]) -> str:
        label = field.get("label", field["name"])
        if field.get("maxBytes"):
            label += f" (en fazla {field['maxBytes'] // 1_000_000} MB)"
        return label + (" *" if field.get("required") else "")

    def _build_field(self, field: dict[str, Any]) -> QWidget:
        kind = field.get("type", "text")
        value = field.get("value")
        if kind in {"textarea", "lines", "json"}:
            widget: Any = QPlainTextEdit()
            widget.setFixedHeight(110 if kind != "json" else 140)
            if value is not None:
                widget.setPlainText(str(value))
            if field.get("placeholder"):
                widget.setPlaceholderText(field["placeholder"])
        elif kind == "select":
            widget = QComboBox()
            for option in field.get("options", []):
                widget.addItem(option or "Tümü", option)
            if value is not None:
                index = widget.findData(value)
                if index >= 0:
                    widget.setCurrentIndex(index)
        elif kind == "number":
            widget = QDoubleSpinBox()
            raw_step = field.get("step", 1)
            step = 0.01 if raw_step == "any" else _number(raw_step, 1.0) or 1.0
            widget.setDecimals(0 if step >= 1 else 2)
            widget.setSingleStep(step)
            low = _number(field.get("min"), -1_000_000.0)
            widget.setRange(low, _number(field.get("max"), 1_000_000.0))
            widget.setSpecialValueText("")
            widget.setValue(_number(value, low if field.get("min") is not None else 0.0))
        elif kind == "checkbox":
            widget = QCheckBox()
            widget.setChecked(bool(value))
        elif kind == "file":
            container = QWidget()
            row = QHBoxLayout(container)
            row.setContentsMargins(0, 0, 0, 0)
            label = QLabel("Dosya seçilmedi")
            button = QPushButton("Seç…")
            self.file_paths[field["name"]] = None

            def choose(_checked: bool = False, name: str = field["name"], target: QLabel = label) -> None:
                path, _filter = QFileDialog.getOpenFileName(self, field.get("label", "Dosya"), "", field.get("filter", ""))
                if path:
                    self.file_paths[name] = Path(path)
                    target.setText(Path(path).name)

            button.clicked.connect(choose)
            row.addWidget(button)
            row.addWidget(label, 1)
            self.inputs[field["name"]] = container
            return container
        else:
            widget = QLineEdit()
            if kind == "password":
                widget.setEchoMode(QLineEdit.EchoMode.Password)
            if value is not None:
                widget.setText(str(value))
            if field.get("placeholder"):
                widget.setPlaceholderText(field["placeholder"])
            if field.get("maxLength"):
                widget.setMaxLength(int(field["maxLength"]))
        self.inputs[field["name"]] = widget
        return widget

    def build_payload(self) -> dict[str, Any]:
        payload: dict[str, Any] = {}
        for field in self.spec.get("fields", []):
            name, kind, label = field["name"], field.get("type", "text"), field.get("label", field["name"])
            widget = self.inputs[name]
            if kind == "file":
                path = self.file_paths.get(name)
                if path is None:
                    if field.get("required"):
                        raise ValueError(f"{label} seçilmedi.")
                    continue
                data = path.read_bytes()
                if field.get("maxBytes") and len(data) > field["maxBytes"]:
                    raise ValueError(f"{label} en fazla {field['maxBytes'] // 1_000_000} MB olabilir.")
                payload["filename"] = path.name
                payload["content_base64"] = base64.b64encode(data).decode("ascii")
            elif kind == "checkbox":
                payload[name] = widget.isChecked()
            elif kind == "number":
                if widget.text().strip() != "":
                    number = widget.value()
                    payload[name] = int(number) if float(number).is_integer() else number
            elif kind == "select":
                payload[name] = widget.currentData()
            elif kind in {"textarea", "json", "lines"}:
                text = widget.toPlainText()
                if kind == "json":
                    if text.strip():
                        try:
                            payload[name] = json.loads(text)
                        except ValueError as exc:
                            raise ValueError(f"{label} geçerli JSON olmalı.") from exc
                elif kind == "lines":
                    lines = [line.strip() for line in text.splitlines() if line.strip()]
                    if field.get("maxLines") and len(lines) > field["maxLines"]:
                        raise ValueError(f"{label} en fazla {field['maxLines']} satır olabilir.")
                    if field.get("maxLineLength") and any(len(line) > field["maxLineLength"] for line in lines):
                        raise ValueError(f"{label} satırları en fazla {field['maxLineLength']} karakter olabilir.")
                    if lines:
                        payload[name] = lines
                elif field.get("preserveWhitespace"):
                    payload[name] = text
                elif text.strip():
                    payload[name] = text.strip()
            else:
                text = widget.text().strip()
                if text:
                    if field.get("pattern") and not re.fullmatch(field["pattern"], text):
                        raise ValueError(f"{label} biçimi geçersiz.")
                    payload[name] = text
            if field.get("required") and kind not in {"file", "checkbox", "number", "select"} and name not in payload:
                raise ValueError(f"{label} zorunlu.")
        if (
            self.spec["plugin"] == "reports"
            and self.spec["action"] == "export"
            and not payload.get("content")
            and payload.get("report") is None
        ):
            raise ValueError("İçerik veya rapor verisi girilmeli.")
        return payload

    def submit(self) -> None:
        try:
            payload = self.build_payload()
        except (ValueError, OSError) as exc:
            self.status.set(str(exc), "error")
            return
        self.run_button.setEnabled(False)
        self.status.set("Çalışıyor…", "busy")
        if self.spec["plugin"] == DRAFT:
            run_background(
                lambda: self.ctx.api.draft_task(payload["request"], payload.get("model")),
                self._done,
                self._failed,
            )
            return
        approval = self.spec.get("approval")
        if approval and self.spec["plugin"] == "prompt_library" and self.spec["action"] in {"online_search", "online_get"}:
            approval = f"{approval}\n{payload.get('query') or payload.get('id') or ''}"
        started = self.ctx.call_action(
            self, self.spec["plugin"], self.spec["action"], payload,
            approval=approval, on_done=self._done, on_error=self._failed,
        )
        if not started:
            self.run_button.setEnabled(True)
            self.status.set("Onay verilmedi; işlem yapılmadı.", "warn")

    def _done(self, result: Any) -> None:
        self.run_button.setEnabled(True)
        message = "Tamamlandı."
        kind = "ok"
        if isinstance(result, dict):
            if self.spec["plugin"] == "windows_host" and result.get("status") == "failed":
                message = "İşlem başarısız; gerçek çıktı ve işlem kaydını inceleyin."
                kind = "error"
            elif self.spec["action"] == "local_search" and result.get("installed") is False:
                message = "Yerel katalog henüz indirilmedi; önce 'Yerel katalog indir / yenile'."
            elif isinstance(result.get("skipped_reports"), list) and result["skipped_reports"]:
                message = f"Tamamlandı; okunamayan raporlar: {', '.join(map(str, result['skipped_reports']))}"
        self.status.set(message, kind)
        self.result.show_result(result)
        self.result_ready.emit(self.spec["plugin"], self.spec["action"], result)

    def _failed(self, error: Exception) -> None:
        self.run_button.setEnabled(True)
        self.status.set(error_text(error), "error")
