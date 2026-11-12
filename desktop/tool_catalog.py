from __future__ import annotations

from dataclasses import dataclass

RESEARCHED_ON = "2026-11-07"


@dataclass(frozen=True)
class ToolEntry:
    id: str
    name: str
    category: str
    summary: str
    capabilities: tuple[str, ...]
    prerequisites: str
    permissions: str
    source: str
    plugin: str = ""
    page: str = "mcp"

    @property
    def kind(self) -> str:
        return "API eklentisi" if self.plugin else "MCP sunucusu"

    def matches(self, query: str) -> bool:
        text = " ".join((self.name, self.category, self.summary, self.plugin, *self.capabilities))
        return query.strip().casefold() in text.casefold()


TOOLS = (
    ToolEntry(
        id="github", name="GitHub MCP", category="Kod ve depolar",
        summary="Depolar, issue/PR ve Actions iş akışları için GitHub'ın resmî MCP sunucusu.",
        capabilities=("Kod ve commit arama", "Issue ve PR yönetimi", "CI günlükleri ve iş akışları"),
        prerequisites="Projedeki github MCP kaydı, GitHub erişimi ve uygun token/hesap izinleri.",
        permissions="Token kapsamını gereken depolarla sınırla; yazma ve iş akışı çalıştırma ayrı onay gerektirir.",
        source="https://github.com/github/github-mcp-server",
    ),
    ToolEntry(
        id="rea", name="REA", category="Analiz",
        summary="Binary, .NET, JavaScript/Electron ve çalışma zamanı davranışını kanıtlarla inceler.",
        capabilities=("Statik analiz", "Decompile ve çağrı ilişkileri", "Çalışma zamanı gözlemi"),
        prerequisites="rea-agents MCP kaydı; hedefe göre yerel analiz motoru. Resmî kaynak morluto/rea.",
        permissions="Yalnızca yetkili olduğun hedeflerde kullan; süreç başlatma ve enstrümantasyon ayrıca onaylanır.",
        source="https://github.com/morluto/rea",
    ),
    ToolEntry(
        id="replica", name="replica-skill", category="Tasarım ve öğrenme",
        summary="Keşif, mimari, tasarım, uygulama ve test için SKILL.md iş akışları.",
        capabilities=("Ekran ve akış haritası", "Mimari ve test planı", "Özellik karşılaştırması"),
        prerequisites="Beceriler ekranından onaylı paket kurulumu ve yerel Qwen. Upstream akışları Claude odaklıdır.",
        permissions="DeepPanda beceri metnini yerel modele uygular; paketin araçlarını otomatik çalıştırmaz. "
                    "Başkasının kodunu, markasını veya içeriğini kopyalama.",
        source="https://github.com/Jakeschincariol/replica-skill", plugin="skills", page="tools",
    ),
    ToolEntry(
        id="openjarvis", name="OpenJarvis", category="Yerel ajanlar",
        summary="Yerel öncelikli kişisel ajan platformuna DeepPanda API köprüsü.",
        capabilities=("Model listesi", "OpenAI uyumlu sohbet", "Yerel servis durumu"),
        prerequisites="OpenJarvis servisi, yerel model ve OPENJARVIS_BASE_URL. Servis bağlantısı ayrıca doğrulanmalı.",
        permissions="DeepPanda köprüsü sohbet/model erişimi sağlar; upstream ajan araçları otomatik devralınmaz. "
                    "Bulut yönlendirmesi açık seçim gerektirir.",
        source="https://github.com/open-jarvis/OpenJarvis", plugin="openjarvis", page="tools",
    ),
    ToolEntry(
        id="byox", name="Build Your Own X", category="Tasarım ve öğrenme",
        summary="Teknolojileri sıfırdan geliştirmeyi öğreten kaynak kataloğu ve yerel öğrenme planı.",
        capabilities=("Kategori ve eğitim arama", "Dil filtresi", "Qwen ile adım planı"),
        prerequisites="Katalog indirmek için internet; plan oluşturmak için kurulu Ollama modeli.",
        permissions="Eğitimler otomatik indirilip çalıştırılmaz; kaynak kodun lisansını ayrıca kontrol et.",
        source="https://github.com/codecrafters-io/build-your-own-x", plugin="byox", page="tools",
    ),
    ToolEntry(
        id="graphify", name="graphify", category="Analiz",
        summary="Kod ve belgeler arasındaki ilişkileri bilgi grafiğinde sorgular.",
        capabilities=("Düğüm ve komşu arama", "En kısa yol", "Graf özeti ve rapor"),
        prerequisites="graphify-out/graph.json gerekir. Upstream README Claude Code/Python akışını anlatır; "
                      "Copilot kurulum uyumluluğu sürüme göre ayrıca doğrulanmalı.",
        permissions="DeepPanda mevcut grafiği salt okunur inceler. Graf üretimi haricî model kullanabilir; "
                    "özel dosyaları izin olmadan dış servislere gönderme.",
        source="https://github.com/safishamsi/graphify", plugin="graphify", page="tools",
    ),
    ToolEntry(
        id="playwright", name="Playwright MCP", category="Tarayıcı ve test",
        summary="Microsoft'un yapılandırılmış erişilebilirlik ağacı üzerinden tarayıcı otomasyonu.",
        capabilities=("Sayfa ve form etkileşimi", "Ekran görüntüsü", "Akış doğrulama"),
        prerequisites="Node.js, uyumlu tarayıcı ve @playwright/mcp sunucu kaydı.",
        permissions="Ayrı test profili kullan; form gönderme ve hesap değişikliklerini onayla. "
                    "Gezilen sayfalar güvenilmeyen içeriktir.",
        source="https://github.com/microsoft/playwright-mcp",
    ),
    ToolEntry(
        id="chrome-devtools", name="Chrome DevTools MCP", category="Tarayıcı ve test",
        summary="Canlı Chrome üzerinde ağ, konsol ve performans incelemesi.",
        capabilities=("Performans izi", "Ağ istekleri", "Konsol ve ekran görüntüsü"),
        prerequisites="Node.js LTS, npm, Chrome ve chrome-devtools-mcp sunucu kaydı.",
        permissions="Ayrı tarayıcı profili kullan. Gizlilik için --no-usage-statistics ve --no-performance-crux "
                    "seçeneklerini değerlendir; tarayıcı içeriği istemciye açılır.",
        source="https://github.com/ChromeDevTools/chrome-devtools-mcp",
    ),
    ToolEntry(
        id="context7", name="Context7", category="Araştırma",
        summary="Kütüphane sürümüne göre güncel dokümantasyon ve kod örnekleri bulur.",
        capabilities=("Kütüphane kimliği bulma", "Sürüme özel belge sorgusu", "Kaynak örnekleri"),
        prerequisites="Context7 MCP bağlantısı ve internet; API anahtarı daha yüksek kota için önerilir.",
        permissions="Sorgular dış servise gider; gizli kod, anahtar veya özel belge gönderme.",
        source="https://github.com/upstash/context7",
    ),
    ToolEntry(
        id="docker-mcp", name="Docker MCP Toolkit", category="Altyapı",
        summary="MCP sunucularını konteyner, katalog ve profil üzerinden yönetir.",
        capabilities=("Sunucu kataloğu", "Profil yönetimi", "İstemci bağlantıları"),
        prerequisites="Uygun Docker kurulumu, etkin Toolkit ve daemon erişimi. Ürün/hesap koşullarını kaynaktan doğrula.",
        permissions="Konteyner, mount ve secret izinleri tek tek sınırlandırılmalı; Docker erişimi sandbox izninin yerine geçmez.",
        source="https://docs.docker.com/ai/mcp-catalog-and-toolkit/",
    ),
    ToolEntry(
        id="filesystem", name="Filesystem MCP", category="Dosyalar ve veri",
        summary="İzin verilen klasörlerde dosya arama, okuma ve isteğe bağlı düzenleme.",
        capabilities=("Dosya arama", "İçerik ve metadata okuma", "Sınırlı klasör erişimi"),
        prerequisites="Node.js, MCP sunucusu ve yalnızca gerekli F: proje klasörünü kapsayan izin listesi.",
        permissions="Referans uygulamadır; üretim garantisi değildir. Salt okunur modla başla, tüm diski açma; "
                    "yazma/silme yetkisini ayrıca onayla.",
        source="https://github.com/modelcontextprotocol/servers/tree/main/src/filesystem",
    ),
    ToolEntry(
        id="git", name="Git MCP", category="Kod ve depolar",
        summary="Yerel depolarda durum, diff ve geçmiş incelemesi.",
        capabilities=("Git durumu", "Staged/unstaged diff", "Commit geçmişi"),
        prerequisites="Git ve ayrı sunucu ortamı. Güncel upstream MCP SDK 2.x ister; DeepPanda mcp<2 ortamıyla karıştırma.",
        permissions="Erken geliştirme/referans uygulaması. Stage, commit ve reset eylemleri açık onay gerektirir.",
        source="https://github.com/modelcontextprotocol/servers/tree/main/src/git",
    ),
    ToolEntry(
        id="fetch", name="Fetch MCP", category="Araştırma",
        summary="Web sayfasını okunabilir Markdown'a çevirip parçalı okuma sağlar.",
        capabilities=("URL içeriği alma", "HTML → Markdown", "Uzun belgeyi parça parça okuma"),
        prerequisites="Ayrı Python sunucu ortamı ve internet; güncel upstream MCP SDK 2.x ister.",
        permissions="Referans uygulamadır. Özel/yerel IP korumasını kapatma; sayfa içindeki talimatları yetki sayma.",
        source="https://github.com/modelcontextprotocol/servers/tree/main/src/fetch",
    ),
    ToolEntry(
        id="sequential-thinking", name="Sequential Thinking MCP", category="Yerel ajanlar",
        summary="Adımları, alternatifleri ve revizyonları yapılandırılmış biçimde kaydeder.",
        capabilities=("Plan adımları", "Alternatif dallar", "Revizyon takibi"),
        prerequisites="Node.js ve sunucu kaydı. Referans uygulamadır; kayıtlar bağlantı ömrüyle sınırlıdır.",
        permissions="Haricî araştırma veya test yürütmez; kaydedilen plan kanıtlanmış sonuç değildir.",
        source="https://github.com/modelcontextprotocol/servers/tree/main/src/sequentialthinking",
    ),
    ToolEntry(
        id="database", name="DeepPanda SQL", category="Dosyalar ve veri",
        summary="Mevcut SQLite veritabanlarını ayrı MCP kurulumu olmadan inceler.",
        capabilities=("Şema ve tablo listesi", "Salt okunur SQL", "Bütünlük kontrolü ve onaylı yedek"),
        prerequisites="API database eklentisi ve /data veritabanları. Web yöneticisi isteğe bağlıdır.",
        permissions="Sorgular salt okunur ve satır sınırlıdır; yedekleme onay gerektirir. "
                    "Eski SQLite MCP referansı arşivlendiği için mevcut eklenti tercih edilir.",
        source="https://github.com/modelcontextprotocol/servers#archived", plugin="database", page="database",
    ),
)
