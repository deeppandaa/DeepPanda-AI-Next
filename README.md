# DeepPanda AI Next

Yeni, tek başına çalışan AI ürünü. Eski LocalQwenAgent bu alandan bağımsız kalır.

## Mimari sınır

- Web istemcisi yalnızca API ile konuşur.
- API, eklentilere yalnızca `PluginGateway` üzerinden erişir.
- Eklentiler sabit bir manifest ve action sözleşmesi uygular; kendiliğinden yüklenmez.
- Ollama ayrı bir container'da çalışır. Model ağırlıkları Docker volume'unda tutulur, image'a kopyalanmaz.
- Workspace plugin'i yalnızca bu proje köküne erişir; analyzer eylemleri salt okunur, yazma/komut eylemleri açık onay ve backup gerektirir.
- API ve web portları yalnızca `127.0.0.1` üzerinde açılır.

## Başlatma

Docker Compose kurulu makinede **yeni, boş bir kurulum** için bu dizinde:

```powershell
.\setup_freellmapi.ps1
docker compose up --build -d
```

FreeLLMAPI, production modunda `.freellmapi.env` içindeki `ENCRYPTION_KEY` olmadan başlamaz. Mevcut veriyi taşıyorsan çalışan servisin anahtarını aynen koru; eksik dosya için yeni anahtar üretmek eski kayıtlı sağlayıcı anahtarlarını okunamaz hale getirir. Tamamlanan geçiş ve korunan yedekler [ana planda](MASTER_PLAN.md#13-tamamlanan-birleştirme-ve-geri-dönüş) kayıtlıdır.

Ardından Qwen modelini açıkça indir:

```powershell
docker compose exec ollama ollama pull qwen2.5-coder:7b
```

Model indirme çok sayıda GB yer kullanır ve yalnızca bu komutla başlar. Ollama aynı anda tek model yüklü tutar. Genel yanıt varsayılanı **Qwen 2.5 Coder 7B**'dir; ölçülmüş öncelikler kod değişikliği ve öğrenme için **Qwen 3.6** seçer. `DEEPPANDA_BRAIN_MODEL` boş bırakılarak konuya göre seçim etkinleştirilmiştir; dolu bir değer bütün alanları geçersiz kılan açık bir yerel model tercihi olur. Kullanıcının sohbet kutusundaki açık model seçimi korunur. API health kontrolü `http://127.0.0.1:8787/api/health` adresindedir; web arayüzü yalnızca istenirse açılır.

### Ollama GPU / CPU seçimi

Varsayılan Compose, Ollama için `gpus: all` ister. NVIDIA sürücüsü ve GPU destekli Docker Desktop/WSL gerekir; GPU verilemezse servis başlangıcı açıkça hata verir, sessiz CPU geri dönüşü eklenmez. GPU'suz kullanım bilinçli seçilmelidir:

```powershell
docker compose -f docker-compose.yml -f docker-compose.cpu.yml up -d
```

CPU modunu sonraki `up` işlemlerinde de aynı iki `-f` ile kullanın; Qt Sistem sayfasının standart başlatma düğmesi varsayılan GPU Compose'u kullanır. CPU'dan GPU'ya geri geçişte `docker compose up -d --no-deps ollama` yeterlidir. İki seçenek de aynı model volume'unu kullanır; tekrar model indirilmez.

Doğrulama: `docker compose exec ollama ollama ps` gerçek model yükünden sonra `100% GPU` göstermelidir; boş liste yalnız yüklü model olmadığını gösterir. Her modelin tamamının VRAM'e sığacağı garanti değildir. Bu makinede 10 Kasım'da Qwen 2.5 Coder 7B, 4096 bağlam ve aynı istem/seed ile üç ısınmış koşunun ortancası **CPU 11,686 → GPU 50,149 token/sn (4,29×)** oldu; yaklaşık 5 GB toplam GPU belleği gözlendi. Bu **CPU/GPU karşılaştırmasıdır**, Tensor Core unlock etkisi değildir.

`tools\benchmark-ollama.py --label cpu` veya `--label gpu`, mevcut kurulu modelin gerçek VRAM durumunu denetleyerek ölçer; GPU ayarını kendisi değiştirmez. Proje Python'uyla çalıştırılır, 3 ısınmış yanıtı `data\model-evaluations` altında kaydeder ve sohbet geçmişi oluşturmaz.

## Birleşik kurulum

7 Kasım 2026'da çalışan uygulama `F:\DeepPanda Agentic Al` altında birleştirildi. API ve web imajları buradan derlendi; yedi servis aynı kök `docker-compose.yml` dosyasına bağlıdır.

- Kaynak, Compose dosyaları, `.env`, `.ai-next-cloud.env`, `.freellmapi.env` ve Qt ayarları bu köktedir. Mevcut anahtar dosyalarını yeniden üretme veya örneklerle üzerlerine yazma.
- API'nin `/workspace`, `/models`, `/runtimes` host bağlantıları sırasıyla proje kökü, `models` ve `runtimes` altındadır. `.venv`, `.tools`, geçici dosyalar ve geçiş yedekleri de proje içindedir.
- Veritabanları ve altı kurulu model mevcut beş Docker named volume'unda korunur. Bunlar host `models` klasörüne kopyalanmadı. **Ortak Docker Engine diski `F:\DeepPanda-Docker-Data` altında kalır**; başka projeler de içerdiğinden bu uygulamanın klasörüne taşınmadı.
- SHA-256 doğrulanmış veri yedekleri ve geri dönüş bilgileri `data\backups\consolidation-20261107-2150` altındadır. Bu klasör gizli yapılandırma içerir; paylaşma veya commit etme. Eski proje klasörleri silinmedi.

Mevcut kurulumu tek kökten yeniden açmak:

```powershell
docker compose --profile web --profile manager up -d --no-build --wait
.\run-desktop.ps1
```

Web: `http://127.0.0.1:8788`; API: `http://127.0.0.1:8787`; salt-okunur SQL yöneticisi: `http://127.0.0.1:8789`. Yeniden derleme ve doğrulama adımları [ana plandadır](MASTER_PLAN.md#7-son-kontrol-tarifi).

## Servis profilleri

Hazır ayarlar `.env.example` içindedir; yalnız `.env` henüz yoksa `Copy-Item .env.example .env` ile kopyalayıp düzenle (commit edilmez). Compose proje adı `deeppanda-ai-next` olarak sabittir, böylece mevcut `ai_data`, `ollama_data`, `freellmapi_data`, `qdrant_data`, `redis_data` volume'ları korunur.

| Servis | Varsayılan adres | Nasıl başlar |
|---|---|---|
| API (FastAPI + PluginGateway) | `127.0.0.1:8787` (`API_HOST_PORT`) | `docker compose up -d` |
| Ollama (Qwen 2.5) | `127.0.0.1:11435` (`OLLAMA_HOST_PORT`) | `docker compose up -d` |
| FreeLLMAPI | `127.0.0.1:3001` (`FREELLMAPI_HOST_PORT`) | `docker compose up -d` |
| Qdrant | `127.0.0.1:6333`, `127.0.0.1:6334` | `docker compose up -d` |
| Redis | `127.0.0.1:6379` | `docker compose up -d` |
| Web arayüzü | `127.0.0.1:8788` (`WEB_HOST_PORT`) | `docker compose --profile web up -d web` |
| SQL yöneticisi (sqlite-web) | `127.0.0.1:8789` (`DB_MANAGER_HOST_PORT`) | `docker compose --profile manager up -d db-manager` |

SQL yöneticisi API ile aynı `ai_data` volume'unu (`/data/*.db`: `memory.db`, `tasks.db`, `jobs.db`, ...) bağlar. Varsayılan `DB_MANAGER_MODE=readonly`; yazma gerekiyorsa `readwrite` yap. `SQLITE_WEB_PASSWORD` doluysa yönetici parola ister. API tarafındaki `database` eklentisi aynı dosyaları salt-okunur sorgular (en fazla 500 satır), bütünlük kontrolü yapar ve onaylı yedek alır; `DB_MANAGER_URL` ile yöneticinin adresini istemcilere bildirir. Var olan model klasörünü kullanmak için `OLLAMA_MODELS_HOST_DIR` verip `docker-compose.models.yml` dosyasını ekle.

## Qt kontrol merkezi

Günlük kullanım için web arayüzü gerekmez; masaüstü istemcisi API'nin tüm özelliklerini tek pencerede sunar:

```powershell
.\run-desktop.ps1
```

Depoda tutulan bir Windows launcher oluşturmak için:

```powershell
.\build-desktop-launcher.ps1
.\dist\DeepPanda.exe
```

Windows'un **Yüklü uygulamalar** listesine kaydolan, kullanıcı hesabına
kurulan gerçek `Setup.exe` paketini üretmek için:

```powershell
.\packaging\windows\Build-DeepPandaSetup.ps1
.\dist\DeepPanda-Setup.exe
```

`DeepPanda-Setup.exe` kullanıcı kapsamlı kurulur; yönetici izni istemez,
Başlat menüsüne kısayol ve Windows kaldırma kaydı ekler. Kaldırma işlemi
kurulum klasöründeki ayar/projeleri silmeden önce onay ister; Docker named
volume'larına dokunmaz. Kurucu SHA-256 sabitli Python runtime'ını pakete
alır, ancak Qt paketleri için ilk kurulum sırasında internet/PyPI erişimi
gerekir. Docker Desktop, API/AI servisleri ve model verileri kurulum paketine
dahil değildir; servisler ayrıca yapılandırılıp başlatılmalıdır.

Yalnızca geliştirme/depo kökündeki mevcut ortamı hazırlamak için
`install-desktop.cmd` veya `.\install-desktop.ps1` kullanılabilir; bu kaynak
klasörünü Windows uygulamalar listesine kaydetmez. `-VerifyOnly` kurulu
geliştirme ortamını değişiklik yapmadan denetler. `-StartServices` ise açıkça
verildiğinde Docker imajlarını indirebilir/build edebilir ve Compose
servislerini başlatır; gizli `.env` dosyaları otomatik oluşturulmaz.

Launcher Windows PowerShell üzerinden mevcut `run-desktop.ps1` akışını açar;
Qt uygulamasını, proje içindeki Python çalışma zamanını ve bağımlılıkları
kullanır. `dist\DeepPanda.exe` depo kökü altındaki `dist` klasöründe kalmalıdır.
Bu tek başına taşınabilir/bağımsız bir paket değildir; backend/API ve proje
dosyalarını içermez. Mevcut çalışma zamanı kurulum/başlatma adımları geçerlidir.

Gerekli kaynak ve araç klasörleri (`desktop`, `backend`, `tools`, `frontend`,
Compose dosyaları) aynı depo kökünde bulunur. Bu mevcut çalışma klasörü için
yapı doğrudur; `data`, Docker named volume'ları, kullanıcı `.env` dosyaları ve
modeller uygulama koduna dahil değildir ve taşınabilir kurulum paketine
kopyalanmamalıdır. `dist\DeepPanda.exe` yalnızca bu kök içindeki launcher'dır.

`packaging\offline` ayrı bir Docker/web dağıtım akışıdır; Qt launcher kurucusu
değildir. Çevrimdışı paket, Docker image ve kalıcı model/veri volume'larıyla
ayrı hazırlanır; kendi gereksinimleri ve adımları
`packaging\offline\README-OFFLINE.md` içindedir.

Script ilk çalıştırmada `setup-python.ps1` ile Microsoft'un resmî NuGet kaynağından SHA-256 sabitlenmiş Python 3.12.10 çalışma zamanını `runtimes\python-3.12.10` altına indirir. Sistem Python'u veya `py` launcher gerekmez. Proje içinde `.venv` oluşturur, eksikse `desktop/requirements.txt` (PySide6, httpx, mcp, jsonschema) paketlerini kurar. Mevcut aynı sürüm `.venv` dışarıdaki Python'a bağlıysa önce eski yapılandırma/başlatıcılar `_tmp` altında yedeklenir, paketler silinmeden proje Python'una bağlanır. Farklı sürüm ortam otomatik değiştirilmez. Ayarlar `desktop/settings.ini` dosyasına yazılır (gitignored).

### Tek proje kökü ve bağımlılık konumları

Etkin kök `F:\DeepPanda Agentic Al` olarak kalır; kaynak alt klasörler düzleştirilmez.

| İçerik | Kök altındaki konum |
|---|---|
| Kaynak kod / araç manifestleri | `backend`, `desktop`, `frontend`, `tools` |
| Python çalışma zamanı / Qt paketleri | `runtimes\python-3.12.10\tools`, `.venv` |
| Taşınabilir Node / MCP paketleri | `.tools\runtime`, `tools\node_modules` |
| pip indirme önbelleği / geçici dosyalar | `_tmp\pip-cache`, `_tmp\temp` |
| Hugging Face / Torch / CuPy / CUDA önbellekleri | `.tools\cache` altındaki ayrı dizinler |
| Araç tarayıcıları / profilleri / çıktıları | `.tools\browsers`, `.tools\profiles`, `.tools\output` |
| Yalıtılmış GPU test paketleri | `.tools\venvs\gpu-benchmark` |
| Eski köklerin doğrulanmış arşivi | `_arsiv\legacy-20261110\DeepPanda-Proje` |

`tools\project-env.ps1` değişkenleri yalnız çalıştırıldığı süreç ve çocuklarına uygular; Windows kullanıcı profilini, kimlik bilgilerini, global PATH'i veya diğer projelerin ortamlarını taşımaz. Qt ve GPU test başlatıcıları bu ortamı kullanır. Yerel MCP kayıtları da proje içi Python/Node yollarını ve araçlara özel izole önbellekleri kullanır.

```powershell
.\setup-python.ps1 -VerifyOnly
.\setup-tools.ps1 -VerifyOnly
.\run-gpu-benchmark.ps1
```

Son komut eksik GPU test ortamını sabitlenmiş `tools\requirements-gpu-benchmark.txt` ile oluşturur; Qt ortamına CuPy/CUDA paketi yüklemez. Ada (`sm_89`) için sentetik MMA hızını ölçer; tek başına unlock'ın etkinliğini veya Ollama hız kazancını kanıtlamaz. Gerçek karşılaştırma aynı koşullarda açık/kapalı ölçüm gerektirir.

Başlatma/ortam ve MCP korumalarının regresyonları, kurulu yerel Node ile çalışır:

```powershell
& .\.tools\runtime\node-v24.22.2-win-x64\node.exe --test .\tools\test-local-mcp.mjs .\tools\test-project-env.mjs
```

**Dışarıda kalması gerekenler:** Docker Desktop/WSL, NVIDIA sürücüsü, Windows SDK/sistem araçları ve kullanıcıya ait VS Code/GitHub ayarları ortak altyapıdır. Beş Docker named volume'u ve yaklaşık 51 GB model mevcut ortak Docker diskinde korunur; bu klasöre kopyalanıp canlı veri bağlantısı değiştirilmez. Eski `F:\DeepPanda-Proje` geri dönüş için silinmedi; proje içindeki arşiv etkin bağımlılık değildir. Kullanıcının masaüstündeki test çıktıları da yerinde bırakılır. Tam görev listesi [ana planın 18. bölümündedir](MASTER_PLAN.md#18-10-kasım-görev-listesi-ve-tek-kök-çalışması).

VS Code için `.vscode/settings.json`, proje `.venv` yorumlayıcısını ve backend import yolunu tanımlar. Editörde daha önce seçilmiş başka bir yorumlayıcı varsa **Python: Select Interpreter** ile `F:\DeepPanda Agentic Al\.venv\Scripts\python.exe` seçilmelidir; varsayılan ayar mevcut seçimi zorla değiştirmez.

- **Sohbet:** aramalı oturumlar, ölçümlü model seçimi, Ajan / Sor / Plan modları, dosya/klasör ekleme ve sürükle-bırak, gerçek token akışı, durdurma, araç/onay izleri, diff önizleme ve son yazmayı geri alma. Araçlar/MCP çekmecesi 137 formu (30 Windows host aracı dahil) ve host MCP araçlarını sohbetten açar. Kopyalama, soruyu düzenleyip yeni tur olarak gönderme ve Markdown dışa aktarma mevcuttur.
- **Araçlar:** web arayüzündeki tüm araç formları (`desktop/tool_forms.json`, `frontend/tools.js` dosyasından `node desktop/sync_tool_forms.mjs` ile üretilir) ve hafıza, belgeler, görevler, çalışma alanı, araştırma, repo izleme, bulut, beceriler, OpenJarvis, Build Your Own X, graphify ve yerel çoklu ajan formları; aramalı ağaç ve "Gelişmiş" bölümünde herhangi bir eklenti eylemini JSON ile çalıştırma.
- **Gelişmiş araçlar:** 15 araçlık araştırılmış katalog; ad/yetenek araması, kategori ve bağlantı türü filtresi, gereksinimler, izin/veri sınırları ve resmî kaynaklar. Yerleşik araç seçimi ilgili forma, haricî MCP seçimi MCP ekranına götürür. Katalog çevrimdışı çalışır; API kaydı ayrıca kontrol edilir ve kurulu/bağlı olmayan araçlar hazırmış gibi gösterilmez.
- **İşler:** arka plan işleri, durum filtresi, ayrıntı, iptal, yeniden deneme ve takılı işleri kurtarma.
- **Veritabanı:** veritabanı/tablo gezgini, salt-okunur SQL editörü, bütünlük kontrolü, yedek ve gerekirse SQL yöneticisini başlatıp açma.
- **MCP / Copilot:** VS Code/Copilot `mcp.json` ve proje `mcp-servers.json` sunucularını listeler, araçlarını getirir ve bu bilgisayarda çalıştırır. `GITHUB_TOKEN` yoksa `gh auth token` yalnızca istemci süreci için alınır.
- **Sistem:** API, Ollama/Qwen 2.5, OpenJarvis, graphify, SQL yöneticisi ve web durumu; yığını başlatma, konteyner durumu, API günlükleri, Qwen 2.5 indirme, API'yi yeniden derleme, web arayüzünü açma ve tanılama taraması.
  Ayrıca **Yerel MCP araçlarını kur/doğrula** düğmeleri, tek onayla proje içindeki kurulum betiğini çalıştırır ve çıktısını gösterir.

Otomatik ajan yalnızca açık salt-okunur izin listesindeki API eylemlerini sormadan çalıştırır. Diğer eylemler ve bütün MCP çağrıları işlem bazında onay ister; model kendine onay veremez. Mevcut manuel formların kendi onay politikaları korunur.

### Birleşik sohbet kullanımı ve sınırlar

- **Ajan:** yerel model web/Qt formları, Windows host, Qt sistem durumu ve yapılandırılmış MCP sunucularından önce araç grubunu, sonra gerçek eylem/argüman şemasını seçer. Qt veritabanı/işler işlemleri ve yalnız plan üreten **Görev taslağı** da seçilebilir; taslak görev kaydı oluşturmaz. Genel görevler en fazla üç, onaylı program akışı en fazla sekiz araç adımıdır; aynı çağrı ve başarısız işlemin kör tekrarı durdurulur. Proje testinden sonra en fazla iki onaylı kaynak düzeltmesi ve yeniden test istisnası vardır. Gerçek tamamlanmış/başarısız araç çıktıları sohbet içinde gösterilir ve yanıt modelinin bağlamına katılır. **Sor** ve **Plan** otomatik eylem çalıştırmaz; kullanıcının açıkça eklediği dosyaların salt-okunur önizlemesi yine yapılır.
- Büyük MCP katalogları 64 araçlık/şema boyutu sınırlarına uygun sayfalarla sunulur; uyumsuz şemalar açıkça uyarılır. Varsayılan olarak seçilen MCP sunucusunun oturumu aynı turdaki adımlar arasında korunur ve tur sonunda kapanır. Aşağıdaki ayrı canlı oturum tercihiyle aynı açık sohbetin sonraki mesajında da kullanılabilir. MCP keşfi yerel sunucu sürecini başlatabilir; **her MCP araç çağrısı ayrıca onay ister**. Sunucu, motor veya kimlik bilgisi eksikse hata gösterilir; isteğe bağlı graphify kendiliğinden kurulmaz.
- Qt sistem sayfasının sabit Docker durum komutu sohbetten kullanılabilir; API günlüklerini okumak ayrıca onay ister ve özel bilgi içerebilir. API `system.hardware` sonucu API'nin çalıştığı ortama aittir (Docker'da Linux); Windows aygıtları için `windows_host` kullanılmalıdır. Sistem sayfasındaki yığın başlatma, yeniden derleme/kurulum ve pencere açma düğmeleri sohbet ajanına genel bir host kabuğu olarak verilmez; bunlar manuel kalır.
- Proje çalışma alanı araçları yalnız proje içindeki göreli yolları kullanır; mutlak Windows/UNC yolları ve Linux'ta ters eğik çizgili belirsiz yollar reddedilir. Masaüstü gibi Windows konumları için Qt'deki `windows_host` araçları ve hedefe özel onay gerekir; web/Docker Windows host dosyalarına doğrudan yazmaz.
- Otomatik seçim yalnız şeması bilinen, kullanıcıya sunulan eylemleri kapsar; iç worker/oturum kayıtları ve parola girilmesi gereken formlar modele açılmaz. Hafıza yedeği içe aktarma yalnız kullanıcı tarafından seçilen geçerli JSON ekinden ve dosya/adet önizlemesiyle onaylandıktan sonra yapılır. Gelişmiş JSON eylemleri ve parola alanları gerektiğinde manuel kullanılabilir.
- **Ekler:** dosya başına 10 MiB, toplam 20 MiB, en fazla 32 dosya; klasörde 1000 giriş ve 12 derinlik sınırı. Gizli ortam/anahtar dosyaları, özel runtime/veri dizinleri ve link/junction yolları reddedilir. Klasör taraması eksik kalırsa uyarı gösterilir; bu bir tam depo taraması değildir.
- Dosya adına/uzantısına göre metin/kod, Office/PDF çıkarımı, görsel OCR, arşiv envanteri, SQLite şeması, statik binary inceleme, ses veya video metadata yolu seçilir. Binary inceleme onay gerektirir; dosya çalıştırılmaz, belge kalıcı olarak ingest edilmez. Desteklenmeyen tür ve eksik bağımlılık açıkça raporlanır. ZIP ve sıkıştırılmamış TAR yalnızca listelenir; arşiv açılıp çalıştırılmaz. Yerel konuşma modeli yoksa ses analizi kullanılamaz; otomatik model indirilmez.
- Seçili bağlam 48.000 karakterle sınırlıdır. Manuel panelden son beş sonuç, ajanla genel görevde üç/program akışında sekiz sonuç eklenebilir; yanıt bağlamında toplam son sekiz sonuç korunur, eski sonuçların çıkarıldığı bildirilir. Her araç önizlemesi JSON olarak en fazla 5000 karakterdir ve kesilme işaretlenir; test sonucu/çıkış kodu yapılandırılmış olarak korunur. API toplam 48.000 karakterlik araç sonucu sınırını ayrıca doğrular. Birlikte sığmadıklarında araç sonuçları korunur, seçili bağlam kısaltılır ve sohbet bunu bildirir.
- Asistan yanıtlarının kalıcı oturum kaydı 48.000 karaktere kadar izin verir; kullanıcı mesajı sınırı 20.000 karakter olarak kalır. Böylece kapsamlı program inceleme özeti yanıtın kaydedilmesini engellemez.
- Otomatik ajanla workspace yazmasında gerçek diff gösterilir, onaydan önceki SHA-256 ile yarış kontrolü yapılır ve yedek alınır. Durdurma tamamlanmış araç etkilerini geri almaz; son workspace yazması ayrı onayla geri alınabilir.
- Yerel akış gerçek Ollama tokenlarını NDJSON üzerinden taşır; kesilen yarım tur kaydedilmez. Planlama/analiz gibi senkron çağrılarda durdurma çağrının güvenli dönüşünde uygulanır; MCP çağrısı iptal edilip oturum kapatılsa da uzak sunucuda başlatılmış yan etkiler geri alınmış sayılmaz. Pencere aktif sohbet işçisini bekleyerek kapanır. CPU'da araç planlamasının ek model çağrıları normal sorudan belirgin yavaş olabilir; model yanlış araç seçebilir veya hiç seçmeyebilir.
- Buluta ek/araç bağlamı gönderimi açık sağlayıcı seçimi ve ayrı veri aktarımı onayı ister. OpenJarvis bu panelde yalnızca eksiz/araç bağlamsız **Sor** modundadır. Sohbet geçmişi mesajları saklar; eklerin ham içeriği ve canlı araç izleri yeniden açılan oturuma geri yüklenmez. Ek yolları için aşağıdaki isteğe bağlı yerel hatırlama kullanılabilir.
- Kısayollar: `Ctrl+Enter` gönder, `Ctrl+N` yeni sohbet, `Ctrl+O` dosya, `Ctrl+Shift+O` klasör, `Esc` durdur. Komutlar: `/ask`, `/plan`, `/agent`, `/tools`, `/clear`, `/help`.

### Sohbet ek yollarını isteğe bağlı hatırlama

Sohbette **Bu sohbetin ek yollarını bu bilgisayarda hatırla** varsayılan kapalıdır.
İşaretlenip gizlilik açıklaması onaylanınca yalnız seçili dosya/klasör yolları
`data\chat-continuity` altında API adresi ve sohbet kimliğine göre ayrı kaydedilir.
Dosya içeriği, araç sonuçları, canlı işlem izi, anahtar veya MCP oturumu bu kayda yazılmaz.
Yol adları da hassas bilgi içerebilir; bu yerel dizini paylaşmayın.

- İlk sohbet yanıtında oturum kimliği oluşunca ve ekler değiştirildiğinde yol listesi kaydedilir.
- Sohbet tekrar açılınca yollar yeniden doğrulanır; eksik, özel veya bağlantı/junction
  yolları atlanır ve uyarı gösterilir. Dosya içerikleri açılışta okunmaz.
- **Gönder**, dosyaların o andaki güncel içeriğini mevcut sınırlarla okur; bu bir içerik
  anlık görüntüsü veya eski dosya sürümünü geri getirme değildir. Buluta aktarım onayları korunur.
- Yeni sohbette hatırlama tekrar kapalıdır; önceki sohbetin kaydı korunur.
  İşareti kaldırmak yalnız mevcut sohbetin yol kaydını siler, ekleri veya kaynak dosyaları silmez.
  Sohbet silinince o API adresine ait yerel yol kaydı da silinir; başarısız silme açıkça bildirilir.
- Başka bilgisayar/Qt kurulumu ile senkronizasyon ve ham araç izi kalıcılığı yoktur.
  Canlı MCP için aşağıdaki ayrı, yalnız bellekte yaşayan tercih kullanılır.
  Sohbet değiştirme eski araç bağlamını, izini ve geri alma
  hedefini temizler; önceki sohbetin işlemini yanlışlıkla geri almaya yönlendirmez.

### Sohbet araç özetlerini isteğe bağlı hatırlama

**Bu sohbetin araç adlarını ve durumlarını yerelde hatırla** ayrı, varsayılan kapalı bir
gizlilik tercihidir; ek yolu tercihinden bağımsızdır. Onaydan sonraki, sohbetin araç
sonucu gösteriminden geçen olayların yalnız **adı ve durumu** tutulur. Bu, bütün
sağlayıcıları/Cline olaylarını kapsayan tam işlem günlüğü değildir.

- API/oturum bazlı `.tools.json` kaydı `data\chat-continuity` altında atomik yazılır.
  Yalnız son 100 özet saklanır; çıkarılan eski özetlerin sayısı arayüzde gösterilir.
  İlk yeni sohbetin kimliği başarılı yanıtta oluşana kadar kayıt bellektedir.
  Mevcut oturumda olaylar hemen kaydedilir; sonraki iptal önceki tamamlanmış işlemi silmez.
- Ham çıktı, argüman, komut, dosya içeriği veya geri alma hedefi kaydedilmez.
  Bilinen `save_key/delete_key/remove_key/login/auth` işlemleri hariçtir.
  **Araç adları özel sunucu/işlem adları içerebilir**; bu genel amaçlı bir sır
  ayıklayıcısı veya şifreli kasa değildir. Yerel kayıt dizinini paylaşmayın.
- Yeniden açılan özetler ayrı, çalıştırılmadıklarını belirten bölümde gösterilir;
  sohbet/model bağlamına katılmaz, araç çağrısı veya izin oluşturmaz.
- Yeni sohbette tercih kapanır, önceki kayıt korunur. İşareti kaldırmak yalnız araç
  özetlerini siler; ek yolu kaydı ve kaynak dosyalar korunur. Sohbet silinince her iki
  yerel kayıt da temizlenmeye çalışılır; okuma/yazma/silme hataları açıkça gösterilir.

### Aynı açık sohbette isteğe bağlı canlı MCP oturumu

**MCP oturumlarını bu açık sohbette mesajlar arasında tut** varsayılan kapalıdır.
Ayrı açıklamayı onaylamak yalnız bağlantı ömrünü uzatır; yeni bir araç izni vermez.
Her MCP çağrısı yine işlem bazında onay ister. Onay tek başına sunucu başlatmaz;
ajan o sunucuyu ilk seçtiğinde mevcut keşif/başlatma akışı çalışır.

- Aynı açık sohbetin ajan turları en fazla dört sunucunun bağlantı/durumunu bellekte
  paylaşır. MCP bağlamları bir sahip async görevde açılıp aynı görevde kapatılır;
  araç çıktıları, canlı oturum veya bu tercih diske yazılmaz. Bağımsız ek yolu/özet
  tercihleri ve API'nin sohbet mesajı saklaması değişmez. Sunucunun kendi kalıcılık
  davranışı ve tuttuğu veriler bu tercihle denetlenmez.
- Son ajan araç turundan sonra **10 dakika boşta** kalınca bağlantılar kapanır.
  Bu açıkta çalışan bir çağrının süre sınırı değildir; kapanmış oturumu yeniden
  kullanmak için tercih yeniden onaylanır. Pencere/uygulama yeniden açıldığında
  canlı durum geri yüklenmez; geçmiş sohbetten de canlandırılmaz.
- İşareti kaldırma, yeni sohbet, sohbet açma, etkin sohbeti silme, tur iptali/hatası
  ve pencere kapanışı bağlantıları kapatır. Arayüz kapanışı bekler; başarısız kapanış
  görünür hata verir ve yeni oturuma geçişi durdurur. MCP çağrı hatası veya onay reddi
  de mevcut bağlantıları bırakır; o çağrı kendiliğinden tekrarlanmaz.
- API adresi/proje kökü/MCP yapılandırması değiştiğinde eski durum sessizce başka
  hedefte kullanılmaz. Kimlik bilgisi değiştirirken tercihi önce kapatın: mevcut
  açık bağlantı önceki yetkilendirmeyi kullanabilir. Bağlantı bozulursa otomatik
  yeniden bağlanma veya çağrıyı yeniden yürütme aynı turda yapılmaz. Bağlantıları
  temizlenmiş ama tercihi hâlâ etkin bir sohbete yeni mesaj gönderirseniz ajan
  sunucuyu yeniden seçip yeni bağlantı açabilir; eski durumun sürdüğünü varsaymayın.
- Sunucu süreçleri/tarayıcı durumu daha uzun yaşayabilir. Bağlantıyı kapatmak uzaktaki
  işlemleri, ayrı başlatılmış tarayıcıları veya önceki yan etkileri geri almaz.
  Bu bir sandbox değildir. Cline, OpenJarvis ve manuel MCP paneli kendi bağlantı
  ömürlerini kullanır; bu tercih yalnız birleşik sohbet ajanının MCP yolunu kapsar.

Gerçek izole stdio kabulünde iki ayrı ajan turunda aynı süreç sayacı **1 → 2** oldu;
yeni sohbette **1**'e döndü. Bu, bütün üçüncü taraf tarayıcı/uzak sunucuların
kalıcılık davranışının doğrulandığı anlamına gelmez.

### Windows host: dosya, USB / COM / DCOM, sürücü ve kayıt defteri

**Qt > Araçlar (veya sohbetin Araçlar/MCP çekmecesi) > Windows host / USB / COM / Kayıt** bölümünde 31 araç vardır. Ajan modu bu araçları da seçebilir. Linux Docker, Windows donanımını yönetmez: `windows_host` HTTP eklentisi yalnız yetenek/erişim durumu bildirir ve diğer çağrıları reddeder; web paneli Qt'ye yönlendirir. Yeni yönetici HTTP servisi açılmaz.

- **Bilgi ve tanı:** Windows sürümü, USB/PnP aygıt kimliği/sınıfı/hata kodu, COM seri portları, aygıta bağlı sürücü sürümü/sağlayıcısı/imza durumu ve üçüncü taraf Driver Store paketleri. Envanter filtre/sınırla çalışır; eksik liste `truncated` ile belirtilir. Native komut metni 32.000 karakterle sınırlıdır.
- **COM/DCOM:** DCOM uygulama/AppID listesi; seçilen CLSID için HKCU/HKLM, 32/64 görünümde ProgID, sunucu kayıtları ve AppID'nin LocalService/DllSurrogate/custom izin varlığı; son yedi günün DistributedCOM olayları. Tam CLSID kataloğu değildir. COM nesnesi etkinleştirilmez, kayıtlı sunucu yolu açılmaz, izin ACL'leri değiştirilmez. Tek başına 10016 olayı toplu izin düzeltme gerekçesi değildir.
- **Dosyalar ve klasörler:** proje dışındaki yerel, normal, tek bağlantılı dosyalarda onaylı UTF-8 okuma/yazma/oluşturma ve tek dosya silme; 1 MB sınırı. Onaylı klasör oluşturma yalnız mevcut bir üst klasör altında yeni, boş, tek bir klasör oluşturur; mevcut hedefi değiştirmez ve otomatik geri alınmaz. Yazma diff ve hash ile önizlenir; içerik boşlukları/satır sonları korunur. Klasör ağacı silinmez. UNC/aygıt/ADS yolları, link/junction, Windows/Program Files/ProgramData/AppData, kimlik bilgileri ve özel runtime/veri dizinleri dışlanır.
- **Python çalıştırma (`python_run`):** normal kullanıcı olarak açılan Qt'de, yukarıdaki dosya sınırlarını geçen mevcut UTF-8 `.py` dosyasını sabit proje Python'uyla çalıştırır. Kod önizlemesi (16.000 karakter; kesilme işaretli), kaynak SHA-256, yorumlayıcı yolu/hash'i, çalışma dizini, en fazla 32 literal argüman ve 1–120 sn süre sınırı ayrı tek kullanımlık onay ister. Dosyayı yazma onayı çalıştırma onayı değildir. Kaynak/yorumlayıcı değişirse eski plan reddedilir; yürütülen kaynak yeniden açılan dosya değil onaylanan baytlardır. Kabuk kullanılmaz; stdout/stderr ayrı ayrı 32.000 baytla sınırlıdır, kesilme belirtilir. Sıfır olmayan çıkış/zaman aşımı başarısız sayılır; çıktı, çıkış kodu ve `isolation_mode=windows_job_object_process_tree_lifetime_only` / `sandboxed=false` sınır beyanı yerel işlem kaydına yazılır. Windows Job Object kurulmadan kullanıcı kodu başlatılmaz; normal bitişte ve zaman aşımında alt süreçler de sonlandırılır. Uygulamalar arka planda açık bırakılmaz; bu araç kalıcı GUI programı başlatıcısı değildir.
  **Bu bir güvenlik sandbox'ı değildir:** kod kullanıcı yetkileriyle dosyalara/ağa/Windows API'lerine erişebilir; içe aktardığı yerel modüller ve diğer dosyalar tek kaynak hash'inin kapsamında değildir. Yalnız güvendiğiniz kodu onaylayın. Ortamdan sağlayıcı anahtarları/PYTHONPATH aktarılmaz fakat kullanıcı dosyalarına erişim engellenmez. Etkiler otomatik geri alınmaz; yönetici Qt'de yürütme reddedilir. `python_run` temel Python paketlerini kullanır, bağımlılık yüklemez; stdin etkileşimi yoktur. Sohbette **Durdur/Esc**, çalışan yerel `python_run`, `project_environment`, `project_test` ve `project_package` için iptal sinyali gönderir; yürütücü en fazla yaklaşık 100 ms aralıkla denetler, Windows Job Object ağacını kapatıp çıktı okuyucularının bitmesini bekler. Bu denetim aralığı uçtan uca kesin süre garantisi değildir. İptal başarı/zaman aşımı olarak değil işlem günlüğünde `cancelled` olarak tutulur; o ana kadarki stdout/stderr korunur. İptal edilmiş test/ortam/paket başarı sayılmaz, otomatik düzeltme/tekrar başlatılmaz. Kısmen oluşmuş ortam/çıktı ve dosya değişiklikleri geri alınmaz. Diğer senkron host araçları ve HTTP sunucu işleri bu süreç iptali kapsamında değildir; manuel araç formlarında ayrı durdurma düğmesi henüz yoktur. Çok dosyalı projeler aşağıdaki ayrı araçları kullanır.
- **Aygıt kontrolü:** tam Instance ID ile etkinleştirme, devre dışı bırakma, yeniden başlatma veya aygıt kaydını kaldırma; ayrıca donanımı yeniden tarama. Sistem/depolama/ağ/görüntü/giriş gibi kritik sınıflar ve USB hub/birleşik aygıtlar otomatik değiştirilmez.
- **Sürücüler:** yalıtılmış yerel INF klasörünün hash önizlemesi (512 giriş, 256 MB), onaydan sonra geçerli CAT imzası ve Windows PnPUtil ile kurulum. İmza doğrulaması sertifika denetimi için ağa erişebilir; Windows imza zorlaması kapatılmaz. Kaldırma yalnız hiçbir envanter aygıtıyla ilişkilendirilmeyen tam `oemNN.inf` paketinde, başarılı paket yedeğinden sonra yapılır; `/force`, `/uninstall` ve otomatik reboot kullanılmaz.
- **Kayıt defteri:** HKCU/HKLM `Software` altında hedefli tek değer okuma/ekleme/düzeltme/silme; açık 32/64 görünüm, SZ/EXPAND_SZ/DWORD/QWORD/MULTI_SZ. Anahtar ağacı, SYSTEM/SAM/SECURITY, parola/token, güvenlik/autorun/policy ve COM/DCOM izinleri değiştirilmez. Bu bir toplu “registry cleaner” değildir.
- **Dış bağlantı:** onaylı sunucu/IP ve port için DNS/TCP testi; dosya, kimlik bilgisi veya HTTP gövdesi göndermez. TCP başarısı TLS/site/hizmet sağlığı demek değildir. Genel bilgi/yanıt sunma sohbetle; web araştırması ve izinli dış içerik erişimi mevcut araştırma/tarayıcı araçlarıyla devam eder.

Dosya/kayıt okumaları hedefe özel onay ister. Değişiklik/dış bağlantı akışı **önizleme → kullanıcı onayı → aynı planı uygulama** şeklindedir; model onay veremez. Plan tek kullanımlık, 10 dakika geçerli ve son hedef durumuna bağlıdır. Ayrıntılı onay penceresinin varsayılanı **Vazgeç** olur. Aygıt/sürücü ve HKLM değişiklikleri yönetici Qt süreci gerektirir; otomatik UAC yükseltme yoktur.

Qt ajanı, istekte açık bir Windows mutlak yolu bulunurken aynı yol sonuyla proje içi göreli bir workspace hedefi önerirse çağrıyı durdurur; hedef netleştirilmelidir. Bu kontrol modelin bütün yanlış yol seçimlerini yakalamaz: onay penceresindeki gerçek hedef ve diff mutlaka incelenmelidir.

Genel dosya araçlarında bir ajan turunda aynı araç üzerinden aynı dosya hedefine ikinci kez yazılmaz; ek düzeltme için yeni bir mesaj gerekir. Farklı dosyalara yazma, araç adımı sınırı ve her hedef için ayrı onay koşuluyla mümkündür. Yönetilen proje araçları aşağıdaki sınırlı test/düzeltme döngüsünü kullanır.

Dosya/kayıt önceki değerleri ve işlem günlüğü `data\windows-host` altında kalır; bu dizin hassas kullanıcı içeriği içerebilir, paylaşmayın. Başarılı sonucun `operation_id` değeriyle **Host dosya / kayıt değeri işlemini geri al** formu kullanılır (sohbetteki workspace geri alma düğmesinden ayrıdır). Sonradan değişen hedef veya önizleme sonrası değişen günlük reddedilir. Yeni kayıt anahtarları yalnız boşsa kaldırılır. Donanım/sürücü işlemleri bu otomatik geri alma kapsamında değildir; hata/zaman aşımında etki oluşmuş olabilir, yeniden çalıştırmadan önce envanteri kontrol edin.

### Tariften çok dosyalı Python projesi

Normal kullanıcı olarak açılan Qt'de `project_create` yeni `projects\<ad>` klasörüne kaynak, `test_*.py` ve README yazar; kabul ölçütleri `data\program-projects` kaydında saklanır. Mevcut klasör sessizce sahiplenilmez. Her yazmada en fazla 16 dosya, dosya başına 32.000 karakter/64 KB ve toplam 128 KB sınırı vardır. Sözdizimi, güvenli göreli yollar, link/hardlink ve bütün proje ağacının değişmediği denetlenir. `project_update` gerçek diff ve yeni onay ister; eski değiştirilen dosya baytları host işlem kaydında saklanır, otomatik proje geri alma henüz yoktur.

`project_environment` ayrı `.tools\venvs\program-<ad>` ortamı kurar. `packages=[]` ağsız temel Python ortamıdır. Paketler yalnız açık `ad==tam-sürüm` biçiminde, sabit PyPI üzerinden wheel olarak kurulur; URL, pip seçeneği ve requirements yolu argüman olarak kabul edilmez. Transitif paketler indirilebilir; bu tam hash-kilitli kurulum değildir. Kurulumun ağ/paket önizlemesi ayrı onay ister; `pip check` ve gerçek freeze çıktısı sahiplik kaydına ve işlem günlüğüne yazılır. Asistanın `.venv` ortamı değiştirilmez. Ortam hash kontrolü yalnız başlatıcı/yapılandırmayı kapsar, bütün paketleri değil.

`project_test` o ortamda `unittest` keşfi çalıştırır; gerçek çıkış kodu, süre aşımı, test kimlikleri ve skipped testler kaydedilir. Bağımsız kabul kanıtı için başarılı koşumda her test kimliğine bağlı, test kaynak dosyasındaki çalıştırılan satırlar da kaydedilir (test başına en fazla 2.000 satır; kimlik ve satır listesi kırpılması açıkça işaretlenir). Sıfır test veya tamamı skipped başarı değildir. Test başına geçici dizin kök içinde oluşturulup süreçler kapandıktan sonra temizlenir. Hatalı testte sınırlı Python kaynakları ve traceback yerel modelin düzeltme bağlamına eklenir. Bu araçlar da sandbox değildir; dosya/ağ etkilerini geri almaz ve yönetici Qt'de reddedilir.

Test ve paketleme öncesi/sonrası `.py` dosyalarının SHA-256/boyut kayıtları
karşılaştırılır; ekleme, silme veya değişiklik başarıyı geçersiz kılar.
`source_integrity` en fazla sekiz değişen yol ve açık `omitted` sayısı içerir;
`integrity_error` uzun araç çıktısında da korunur. Testte kaynak değişirse
incelemeci/otomatik onarım çağrılmadan durulur; paketlemede teslim ZIP'i
üretilmez. Kısmi çıktılar inceleme için kalır; otomatik geri alma yoktur.
Bu yalnız iki anlık görüntünün karşılaştırmasıdır: Python dışı dosyaları veya
işlem içinde değiştirilip eski haline getirilen kaynakları kapsamaz.

Örnek akış: `project_create` → `project_environment` → `project_test` → gerekirse `project_update` → `project_test`. Kullanıcı mesajında açık araç adı varsa ilk o şema seçilir; sonraki aşama şeması tek projeye daraltılır. Model yine işlem seçmeyebilir veya yanlış kod üretebilir. Başarısız test, arada onaylı düzeltme olmadan yeniden çalıştırılmaz; en fazla iki düzeltme, toplam sekiz adım. Dosya yazılması veya ortam kurulması test başarısı sayılmaz; yanıt başındaki **doğrulanmış araç durumu** gerçek son teste dayanır. Üretilen testlerin geçmesi uygulamanın kusursuzluğunun garantisi değildir.

Doğrulanmış test/paket durumu yalnız **bu sohbet turunda**, gerçek Windows host
API aracından alınan sonuçlardan üretilir. Önceki tur sonuçları model bağlamında
kalabilir ama yeni başarı kanıtı değildir; adı benzer MCP araçları bu durumu
onaylayamaz. Son sekiz sonuçla sınırlanan model bağlamı ile güncel turun
doğrulama kaydı birbirinden ayrıdır.

**Aynı Sohbet ekranında tek tur teslim:** ilk araç oluşturma/güncelleme/ortam/test
ise ve mesaj açıkça `then project_package` (veya `sonra project_package`,
`ardından project_package`) diyorsa, test başarısından sonra tur bitmez;
aynı proje için paketleme şemasına geçilir. Paketleyici `pyinstaller==6.16.0`
ilk testten önce ayrı onaylı proje ortamında hazırlanır; mevcut uygulama
bağımlılıkları kaldırılmaz. Yalnız paketlemeden söz etmek veya paketlemeyi
reddetmek kurulumu başlatmaz. Başarısız ortam, test, ikinci test veya onay
reddinde teslim yapılmaz. Sekiz planlama/eylem, iki onarım ve ayrı onay
sınırları değişmez. Doğrudan `project_package` isteğinin mevcut davranışı
korunur. Yeni bir sayfa/ayrı sohbet sistemi eklenmedi.

**Entegre ikinci yerel ajan ve çift test:** Qt **Ayarlar > Program ikinci ajan modeli**
alanına kurulu ve birincilden farklı yerel model adı girin (örnek
`qwen3.8:latest`); boş alan özelliği kapatır. Sohbette birincil yerel modeli
açıkça seçin. Varsayılan kapalıdır; bu kurulumda kullanıcı isteğiyle etkinleştirildi.
Başarısız `project_test` sonrasında ikinci model gerçek hata ve sınırlı tam kaynak
kanıtını bağımsız inceler; raporu sohbetin araç izinde görünür. Rapor yalnız
tavsiyedir, yürütme izni/başarı kanıtı değildir. Asıl model raporu gerçek kanıtla
karşılaştırıp yalnız uygulama koduna düzeltme önerir; aynı proje, ayrı onay ve
iki düzeltme sınırı korunur.

İnceleme artık gerçek tam dosyalardan birebir kaynak alıntısı gerektirir; olmayan
dosya/alıntı veya kesilmiş kaynaktan alıntı yazmayı durdurur. Hatalı alıntı raporu
araç izinde hata olarak saklanır. Alıntının varlığı teşhisin mantıken doğru
olduğunu kanıtlamaz. Her başarısız test için kimlik, hata türü ve sınırlı
traceback ayrı yapılandırılmış kanıttır (en fazla sekiz hata, toplam 10.000
JSON karakteri; kesinti/atlanma işaretlidir). Sonraki onarım aynı turdaki önceki
onaylı değişikliklerin sınırlı diff'ini ve önceki test durumunu da görür.
Toplam 48.000 karakterlik kanıt sınırı aşılırsa sessiz eksiltme yerine işlem
durur; yeniden deneme sayıları ve testleri değiştirmeme koruması değişmez.

İncelemeciye ilk kabul gereksinimleri de verilir. Üretilen testin beklenen
değeri girdisiyle/sözleşmeyle çelişiyorsa `test_conflicts` raporlanır ve asıl
modelden yeni düzeltme istenmeden durulur. Testler otomatik değiştirilmez;
doğru uygulama yanlış teste uydurulmaz. Bu model tabanlı bir uyarıdır, bütün
yanlış testleri matematiksel olarak yakalama garantisi değildir.
Her çelişki güncel `failure_details` içindeki benzersiz bir başarısız test
kimliğiyle eşleşmeli ve ilgili test modülünün tam kaynağından doğrulanmış
alıntıya dayanmalıdır; uydurma kimlik, tekrar veya yalnız uygulama alıntısı
reddedilir. Bu bağlama denetimi raporun anlamsal doğruluğunu kanıtlamaz.

Kaynak yazan `project_create` / `project_update` argüman çağrıları 32.768 token
bağlam / 8.192 çıktı kullanır; diğer argüman çağrıları 16.384/4.096,
boş argümanlı grup seçimi 8.192/256 sınırında kalır. Gerçek GUI üretiminde
4.096 çıktı sınırı kaynak JSON'unu kesti; kapsamlı bütçe artışından sonra aynı
yerel model dosyaları yazıp testleri çalıştırabildi. 24.000 karakter JSON sınırı
ve `done_reason=length` reddi korunur; sıradan sohbetin bütçesi değişmez.
Bağlam, giriş ve çıktı için ortak bütçedir: gerçek bir onarımda 7.053 giriş
token'ı, eski 8.192 sınırında çıktıyı 1.138 token'da kesti (`done_reason=length`).
Bu durum artık genel “geçersiz JSON” yerine açık bütçe/kesilme hatası üretir;
kesilmiş yanıt geçerli JSON görünse bile kabul edilmez. Süreyi artırmak tek
başına bu sorunu çözmez. Büyük giriş/çıktılar yeni sınırlara da sığmayabilir.

Ajanın araçlardan sonraki **son metin yanıtı** da ayrı bir model çağrısıdır.
Gerçek Qt denemesinde bu çağrı eski varsayılan 4.096 bağlamı tüketip boş yanıt
döndürdü (2.675 giriş + 1.421 üretim token'ı, `done_reason=length`).
Artık yalnız yerel ajan + araç sonucu özetleme çağrısı 16.384 bağlam / 4.096
çıktı ve `think=false` kullanır. Ollama adaptörü bu açık seçenekleri JSON
olmayan ve akışlı çağrılarda da iletir; sıradan sohbetin varsayılanları,
bulut ve FreeLLMAPI değiştirilmez. Kesilmiş son yanıt hata olarak gösterilir,
tamamlanmış sohbet/başarılı sonuç diye kaydedilmez.

Özellik açıkken ilk başarılı testten sonra aynı argümanlarla **ayrı onaylı ikinci
gerçek test** otomatik istenir (modelin “başarılı” demesine dayanmaz).
İkinci test reddedilir/başarısız olursa doğrulanmış başarı verilmez.
**Test sonucu, kabul ve bilinmeyenler ayrı gösterilir:** program araçlarından
sonra deterministik başlık test durumunu bildirir; gereksinim kapsamı,
bağımsız kabul ve çalıştırma izolasyonu ayrıca **henüz doğrulanmadı** kalır.
Başarılı unittest veya paketleme bunları otomatik başarılı yapmaz. Modelin
serbest metni açıkça “kabul kanıtı değildir” başlığı altındadır. Sohbet durum
alanı geçen testlerde yeşil tamamlandı yerine uyarı, başarısız test/paketlemede
hata gösterir. Paketleme sonrası kaynak/ortam yazması önceki teslim durumunu
güncel doğrulama olarak kullanmaz.

Qt yalnız o turda üretilen son sonuçların sayısını `current_turn_tool_results`
ile gönderir; önceki araç sonuçları, benzer adlı MCP araçları ve Sor modu bu
başlığı üretemez. Sayı gerçek sonuç listesini aşamaz ve boolean kabul edilmez.
Başlık artık API'de **sohbet kaydından önce** oluşturulur: ilk ekrandaki metin
ile yeniden açılan konuşma aynı ayrımı korur. Bunlar istemcinin bildirdiği
sonuçlardır; API'nin Windows'u bağımsız gözlemlediği anlamına gelmez.
Eski istemci bu alanı göndermiyorsa API eski sonuçları yeni tur diye varsaymaz.

**Gereksinim taslağı — kısmi D1 uygulaması:** onay önizlemesi sonrası
tamamlanan gerçek `project_create` aracı, modelin oluşturduğu `criteria`
taslağını ayrı bir istemci-bildirimli alan olarak API'ye taşır. İlk kullanıcı
mesajının SHA-256 parmak izi proje kaydına ve doğrulama metadata'sına eklenir
(özgün metin zaten sohbetin kullanıcı mesajı olarak saklanır). Sohbet yanıtında
taslak proje kaydında korunur, sonraki test/güncelleme/ortam/paketleme
sonuçlarıyla da taşınır; en fazla 32 satır, kaynak olduğu açıkça belirtilerek
ve her biri
**HENÜZ DOĞRULANMADI** durumunda gösterilir; taşma işaretlenir. Bu liste
orijinal isteğin tüm gereksinimlerini kapsadığını, ölçütlerin doğru olduğunu,
kullanıcının bunları gereksinim olarak onayladığını veya programın geçtiğini
kanıtlamaz. Hash yalnız metin kimliğini bağlar. Yalnız bu turdaki kanonik
`project_create` sonucu ölçütü taşıyabilir; Sor, önceki sonuç ve benzer isimli
MCP aracı yetkili kaynak değildir. Ayrı kabul denetimi ölçüt taslağını hash'i
eşleşen özgün istekle karşılaştırıp görünür eksikleri birebir alıntılamaya
çalışır; model değerlendirmesi eksiksiz kapsam kanıtı değildir ve doğrulanmış
kabul kapısına yükseltilmez.

İncelemeci ayarı varsa, başarılı `project_test` sonrasında da ayrı salt-okunur
kabul denetimi yapılır: her ölçüt testle ilişkili, eksik, çelişkili veya
doğrulanamaz sınıflandırılır; her iddia güncel ve tam proje dosyasından birebir
alıntı ister. İnceleme girdisi test öncesi dosya hash'lerine göre hazırlanır;
eksik/kesilmiş kaynak veya geçersiz alıntı raporu reddedilir. Özgün istek metni
yalnız mevcut mesajın hash'i proje kaydındaki hash ile eşleşiyorsa incelemeciye
verilir; farklı bir takip mesajı yanlışlıkla özgün istek gibi gösterilmez.
`test_linked` ve `conflict` sınıfları ayrıca başarılı son `project_test`
koşumunda çalışmış, atlanmamış test kimliğini ve Python test fonksiyonunun
gövdesinde çalıştırılan uygulama fonksiyonu/sınıfıyla ilişkili, koşum satır
izinde hem assertion'ın hem uygulama çağrısının yürütüldüğü doğrulanan gerçek bir `assert`,
`unittest.assert*` veya `with pytest.raises/warns(...)` ifadesini içeren tam
test dosyası alıntısı ister. İlk 40 test kimliği tutulur; atlanan test kimliği
listesi kesilmişse rapor fail-closed olarak reddedilir. Sabit `assert True`, assertion'a bağlı olmayan
uygulama çağrısı, yorum, çağrılmayan iç yardımcı veya tek başına
`pytest.raises/warns(...)` çağrısı yeterli değildir. Kısa devreli veya koşullu
dalda kalan uygulama çağrısı da çalıştırılmış kabul edilmez. Bu statik ilişki
kontrolü ayrıca sabit doğrulukla geçebilen `assert ... or True` ve
`assert ... or 3 > 2`, `assertTrue(... or True)` gibi açıkça vakumlu
assertion'ları reddeder. Yine de testin gereksinimi semantik olarak doğru
sınadığını kanıtlamaz. Atanmış uygulama sonucu assertion'dan önce başka bir
atamayla değiştirilmişse eski çağrı da assertion kanıtı sayılmaz. Sabit boolean
ifadeleriyle her zaman geçen `unittest.assertEqual/assertIs` ve her zaman
başarısız olan `assertNotEqual/assertIsNot` ifadeleri de kabul edilmez.
Rapor yalnızca tavsiyedir: `test_linked` gereksinimin karşılandığını kanıtlamaz,
hiçbir ölçütü doğrulanmışa yükseltmez ve kod/test değişikliği başlatmaz.
Kapsam durumu, inceleme özeti, ölçüt başına tavsiye sınıfı/gerekçe/kaynak yolu
ve tam kaynak alıntısı ile olası açık/bulgular proje test sonucu yanında
sohbet yanıtına ve kalıcı oturum geçmişine eklenir. Değişken metinler güvenli
Markdown kod alanlarında gösterilir; inceleme istemciden bildirildiği için bu
kayıt bağımsız doğrulama sayılmaz.

İncelemeler ve son doğrulama, sekiz planlama/eylem turuna ek sınırlı çağrılardır;
onarım başına en fazla iki yazma denemesi vardır. İlk test zaten geçerse hata
incelemesi yapılmaz; kaynak kanıtı varsa kabul incelemesi yapılır ve ayrı onaylı
ikinci test yine çalışır. Eksik/aynı/bulut incelemeci veya otomatik birincil model
seçimi incelemeyi açık hata ile durdurur; indirme, sessiz başka modele geçiş veya
izinsiz yazma yoktur. Ayarda incelemeciyi seçerek bu isteğe bağlı özelliği açıp
kapatabilirsiniz. İptal sonraki model/yazma/test çağrısını engeller; sürmekte olan
HTTP model çağrısının sunucuda anında kesilmesi garanti değildir.

Onarım bağlamında kaynak bütünlüğü ihlali, iptal, süre aşımı, test assertion
başarısızlığı, test hatası ve sınıflandırılamayan durumlar ayrı işaretlenir.
Bu mekanik sınıflandırma semantik kök neden teşhisi değildir. İptal/süre
aşımında otomatik uygulama yazması yerine durulur; süre değişikliği yeni
istek/onay gerektirir. Onarımda eldeki sınırlı kaynak kanıtının birleşik durumu
AST tabanlı hash ile izlenir: aynı turda daha önce denenmiş duruma biçim değiştirerek
dönüş, onay/yazma öncesi engellenir. Farklı bir düzeltme hâlâ iki deneme
sınırında mümkündür. Birebir/eşdeğer döngüyü yakalamak, bütün mantıksal olarak
aynı başarısız yaklaşımları tanımak veya kodu güvenli kılmak değildir.
Bu tüm dosya sisteminin hash'i değildir; eksik/kesilmiş kanıt için mevcut
dosya-yazma korumaları ayrıca geçerlidir.

Bu kurulumda istemci zaman aşımı 600'den 660 saniyeye çıkarıldı; model sunucusunun
600 saniyelik sınırı değişmedi. Bu her çağrı içindir, bütün turun toplam süresi
değildir. Test/çalıştırma süre sınırları ve süreç ağacı iptali korunur.
Mevcut açık Qt penceresindeki kaydedilmemiş girişler korunur; yeni kod ve kayıtlı
tercihler sonraki açılışta yüklenir.

**Yardım kodu vermeden daha ayrıntılı görev denemesi:** yerel model
[invoice_audit](projects/invoice_audit/README.md) CSV fatura denetçisini ve ilk
12 testini kendi yazdı. İlk iki test çalışması geçti; bağımsız kabul girdileri
üç eksik yakaladı. Yerel modelin eklediği üç regresyon testiyle entegre ikinci
ajan + iki onarım çalıştı: hata sayısı 3 → 2 → 1. İki test dosyası değişmeden
korundu; bu ilk tur **14/15** ile başarı ilan etmeden durdu.
Sonraki teşhis çalışmasında yukarıdaki kaynak kanıtı ve token bütçesi düzeltildi.
Gerçek Qwen3.8 incelemesi ardından Qwen3.6 yalnız uygulamayı bir kez güncelledi:
değişmeyen **15 test iki ayrı onaylı çalışmada geçti**; ilk 15 bağımsız CLI girdisi
ve 60 ek boşluk/status/sıra kombinasyonu **75/75** geçti. Kod asistanı uygulama
çözümü yazmadı veya modele somut çözüm ipucu vermedi. Doğrulanan incelemeci
`qwen3.8:latest` bu kurulumda açıkça kaydedildi; sessiz fallback yoktur.
Yeni kanıt yerel `data\program-builds\invoice-grounded-repair.json` içindedir.
Bu sonuç tüm programların otomatik doğru üretileceği anlamına gelmez; örnek
paketlenmedi. İlk testlerin geçmesi tek başına kabul değildir.

**Gerçek Qt kabulü:** ayrı görünür üretim sohbet sayfasında tek Gönder ve gerçek
onay düğmeleriyle mevcut fatura projesi iki kez 15/15 test edildi; son model
yanıtı ve sohbet kaydı geri okundu. Ayrı tariften süre-hesaplama denemesinde
model yanlış beklenen değerli bir test üretti. Yeni çelişki kontrolü bunu ikinci
yerel ajanla teşhis edip kod/test değiştirmeden durdu; yanlış başarı vermeden
açıklama ve sohbet kaydı oluştu. Süre programının bağımsız CLI kontrolleri
31/31, değişmeyen model testleri 7/8'dir. Sıfırdan kusursuz program ve paket
teslimi bu süre-hesaplama denemesinde tamamlanmış sayılmaz.

**Yeni tek-tur üretim ve teslim kabulü:** gerçek kontrol merkezi `MainWindow`
üzerindeki mevcut Sohbet sayfasında tek Gönder ile Qwen3.6
`qt_number_report` uygulamasını, sekiz testi ve README'yi tariften yazdı.
Beş ayrı native onayla oluşturma → ortam → test → ikinci test → paketleme
tamamlandı; **8/8 iki kez** geçti, EXE ve SHA-256 manifestli ZIP teslim edildi.
Uygulama/testler sonradan elle değiştirilmedi; oluşturma diff'inden hesaplanan
Python hash'leri teslim sonunda aynıydı. ZIP CRC, tam dosya listesi ve hash'leri
yeniden doğrulandı; çıkarılan EXE, çocuk PATH'inde Python klasörü olmadan
**43/43 bağımsız CLI kontrolünü** geçti. Son Türkçe model yanıtı ve iki
kullanıcı/asistan mesajı API'den geri okundu. İlk gözlem betiği UI'deki beş
meşru araç izi satırını da mesaj sayıp hatalı alarm verdi; değişmeyen kayıt
yeniden doğrulandı, üretim/uygulama tekrar edilerek sonuç düzeltilmedi.
Yerel kanıt `data\program-builds\native-single-chat-delivery.json` içindedir.
Bu tek makinede bir konsol örneğinin kabulüdür; her tarifin doğru üretimi,
GUI kalitesi, temiz başka PC, imzalama/lisans uygunluğu veya sıfır hata
garantisi değildir. Önceden açık ana Qt korunmuş, yeni bölüm açılmamıştır;
deneme üretim kontrol merkezi penceresinin aynı Sohbet sayfasında yapılmıştır.

**Grafikli program denemesi — henüz tam kabul değil:** aynı üretim Sohbet
sayfasında Qwen3.6 `qt_expense_panel` dosyalarını kendi yazdı. İlk 11 test iki
kez geçse de bağımsız gerçek GUI kontrolü yalnız **16/26** idi; eksik Sil
düğmesi, tema, yanlış toplam metni ve Unicode tutar kabulü yakalandı.
Ayrı onaylı model test düzeltmeleri ve Qwen3.8 incelemeli uygulama onarımları
sonunda gerçek düğme tıklamaları, toplam/silme/grafik güncellemesi, ASCII
doğrulaması, koyu lacivert/turkuaz çizim ve minimum boyutta çakışmama geçti:
**31/33 bağımsız kontrol**. Kalan iki kontrol, denemede belirtilen kaynak
uzunluğu sınırlarıdır (`app.py` 6426/4300, test 6258/3100 karakter; üst sınırlar
hariçtir). Modelin kendi son testleri **16/18**: uzunluk ve renk yerine CSS'te
`dark/navy/cyan` sözcükleri arayan yanlış tema testi başarısızdır.
Yalnız bu sözcükleri yoruma ekleyerek testi kandıran bir düzeltme yapılmadı.
Son ayrı test güncellemesi önceki 12 testin yöntem/iddia AST'sini koruyup altı
regresyon ekledi; sonraki iki uygulama onarımı boyunca onaylı test SHA-256'sı
değişmedi. İki onarım sınırında duruldu; otomatik test zayıflatma, paketleme,
Copilot'un uygulama çözümü yazması veya “tamamı başarılı” kabulü yoktur.
Kanıtlar `data\program-builds\native-visual-contract-repair.json` ve
`visual-independent-final.json`/`.png` içindedir.

**Kanıtlı sonuç/onarım koruması sonrası yeni deneme:** önceki kayıtlar
korunarak aynı gerçek Sohbet akışında yerel model uygulama ve testleri ayrı
onayla güncelledi. 18 test adı korundu; yanlış tema sözcük kontrolü hex-renk
kontrolüne dönüştü (gerçek çizim testi yerine geçmez). Kendi testleri
**17/18**, ayrı gerçek GUI kontrolleri yine **31/33**: uygulama 6836, test
6454 karakter; `<4300`/`<3100` sınırları hâlâ sağlanmadı. İncelemeci eski
biçimli kaynak alıntısı verdiği için kanıt kontrolü uygulama yazmadan durdu.
İlk testten inceleme sonuna kadar test hash'i değişmedi. Ekrandaki son
yanıt ile API sohbet kaydı birebir aynı ve gereksinimler **HENÜZ
DOĞRULANMADI** kaldı; başarısız test hata durumunda gösterildi.
Kod asistanı uygulama çözümü yazmadı, tam kabul/paketleme yapılmadı.
Kanıtlar `data\program-builds\native-evidence-reliability.json`/`.png` ve
`visual-reliability-independent.json`/`.png` içindedir.
Altyapının donmuş kaynak regresyonu **584 test + 644 alt test** geçti;
bu, modelin GUI görevinin tamamlandığı anlamına gelmez.
[Gelişim listesinde](MASTER_PLAN.md#d--kanıta-dayalı-gelişim-sırası) ilk
kanıt/onarım/regresyon dilimi tamamlandı; madde bazlı genel kabul motoru,
genel bağımsız test denetimi ve OS izolasyonu sonraki aşamalardır.

**Son rol karşılaştırması:** kalıcı ayarı değiştirmeden Qwen3.8 geliştirici /
Qwen3.6 incelemeciyle de aynı mevcut Sohbet akışı denendi; güncel kaynaklar
gerçek dosya eki önizlemelerinden okundu. Dosyalar **6191/6254** karaktere
indi ama `<4300`/`<3100` sağlanmadı. Kendi testleri **16/18**: yeni tema
testi gösterilmemiş pencerenin gri paletini ölçtü; görünür GUI'nin ayrı
etkileşim/çizim kontrolleri yine **31/33**. İncelemecinin `...` içeren/
yeniden biçimlenmiş alıntıları birebir kaynak kontrolünde reddedildi;
otomatik uygulama yazması olmadı. Test hash'i, ilk yanıt/kayıt eşitliği ve
doğrulanmadı başlığı korundu. Kaydedilmiş incelemeci `qwen3.8:latest`
olarak kaldı. Son model görevi **engelli**, tam kabul/paketleme yoktur.
Yeni kanıtlar aynı klasörde `native-evidence-role-swap.json`/`.png` ve
`visual-reliability-role-swap.json`/`.png`; önceki sonuçlar korunmuştur.

Otomatik hata düzeltmesi artık kısaltılmış sohbet çıktısını değil, son başarısız testin
ayrı yapılandırılmış kaynak/traceback kanıtını kullanır (48.000 karakter; stdout/stderr
kesilirse açık işaret). Yalnız bu kanıtta tam içeriği bulunan mevcut uygulama `.py`
dosyaları değiştirilebilir. Test adlı dosyalar (`test*`, `*_test.py`, `test/tests`
klasörleri), README, yeni/eksik kaynak ve yalnız yorum/biçim değişikliği yazmadan ve
onay istemeden reddedilir. Bu koruma yalnız başarısız test sonrası otomatik döngüdedir;
kullanıcının ayrı istediği/onayladığı `project_update` ile test düzenleme korunur.
Bu yapısal korumadır; uygulamanın testleri dolaylı etkilemesini engelleyen sandbox değildir.

Gerçek yerel [repair_acceptance](projects/repair_acceptance/README.md) denemesinde
`qwen3.6:latest`, bilinçli hatalı stok toplama kodunu tek onaylı düzeltmede onardı:
önce 6 testte 2 hata, sonra aynı altı test geçti; test dosyasının SHA-256'sı değişmedi.
Başlangıç kodu ve testleri kod asistanı hazırladı, düzeltmeyi yerel model yaptı.
Bu tek başına sıfırdan tarif → program → teslim zincirini doğrulamaz; sonraki kabul aşağıdadır.

**Tariften üretilen teslim:** ayrı [stock_generated](projects/stock_generated/README.md)
örneğinin uygulama kodu, CLI, altı testi ve README'sini gerçek yerel `qwen3.6:latest`
yazdı. Uygulama koduna elle düzeltme yapılmadı; sonradan eklenen sekiz bağımsız kabul
testiyle 14/14 test geçti. Onaylı paketlemenin ZIP'i çıkarılıp EXE, çocuk PATH'inde
Python olmadan 16 ayrı kesin çıktı/çıkış kodu kontrolünü geçti.

ZIP'in tamamını çıkarın; EXE'yi `_internal` klasörüyle birlikte tutun:

```powershell
.\stock_generated\stock_generated.exe --db .\stok.db add elma 10
.\stock_generated\stock_generated.exe --db .\stok.db add elma 5
.\stock_generated\stock_generated.exe --db .\stok.db get elma
```

Son komut `{"name": "elma", "quantity": 15}` döndürür; kalıcı SQLite dosyası
belirttiğiniz `--db` yoluna yazılır. Teslim yolu/hash ve işlem kanıtları
[MASTER_PLAN.md](MASTER_PLAN.md) içinde kayıtlıdır.
Bu gerçek yerel API/ajan/host hattında kontrollü, aşamalı kabulüdür; tek Qt mesajında
kesintisiz üretim/teslim, farklı temiz Windows bilgisayarı, GUI veya genel model
güvenilirliği kanıtı değildir. İlk testte alt Python sürecinin `__pycache__`
oluşturup sonraki proje işlemini engellemesi araç tarafında düzeltildi;
testlerin alt süreçlerine de bytecode yazmama tercihi aktarılır.

Bu temel akış Python/unittest içindir. Sohbetin Durdur/Esc işlevi yerel Python çalıştırma, proje ortam kurulumu, proje testleri ve aşağıdaki onaylı paketlemenin süreç ağacını iptal eder; etkileri geri almaz. Diğer araçlar için anında iptal, kalıcı GUI başlatma ve her dilde build desteği tamamlanmış özellikler değildir. Canlı model kabulünün son durumu ve açık işler [MASTER_PLAN.md](MASTER_PLAN.md) bölüm 18'de kaydedilir.

### İsteğe bağlı Windows konsol EXE paketleme

`project_package` normal proje testinden sonra kendiliğinden çağrılmaz; ayrı istek ve
hedef/hash/etki önizlemesi onayı gerekir. Qt formunda veya Ajan modunda açık araç adıyla kullanılır:

1. Oluşturulmuş projeye özel ortamda `project_environment` ile `packages=["pyinstaller==6.16.0"]`
   kurulumunu ayrıca onaylayın. Uygulamanın diğer sabit sürümlü bağımlılıkları da aynı ortamda olmalıdır.
   Asistanın/Qt'nin Python ortamı değiştirilmez; paketleme aracı eksik paketleri otomatik indirmez.
2. Örneğin `project_package`, `project="exe_smoke_demo"`, `entrypoint="app.py"`,
   `smoke_arguments=["--self-test"]`, `timeout=180` kullanın. Giriş noktası yönetilen projenin
   mevcut göreli `.py` dosyası olmalıdır; toplam test/build/açılış/ZIP doğrulama süresi
   en fazla 300 saniyedir.
3. Kurulu paket/sürüm/lisans metadata envanteri `dependencies.json` olarak yazılır.
   Bu hukuki uygunluk onayı veya bütün transitif lisansların doğrulanması değildir;
   eksik metadata `UNKNOWN` olabilir. Dağıtmadan gerçek lisans dosyalarını ayrıca inceleyin.
4. Güncel `unittest` testleri yeniden çalışır; sıfır/tamamı skipped/başarısız test paketlemeyi
   durdurur. PyInstaller konsol **onedir**, UPX olmadan, yeni
   `data\program-builds\<proje>\<benzersiz-kimlik>` altında çıktı üretir.
   Kaynaklara build/spec dosyası yazılmaz ve alt süreçlerde bytecode yazımı kapalıdır.
5. EXE verilen argümanlarla çalıştırılır; yalnız sıfır çıkış kodu, tamamlanmış build ve mevcut
   EXE/rapor ve aşağıdaki teslim ZIP'i birlikte doğrulanınca başarı sayılır.
6. `<proje>-windows.zip` uygulamanın `dist\<proje>` dosya ağacını, kökte
   `dependencies.json` ve `delivery-manifest.json` içerir. ZIP önce geçici adla oluşturulur;
   her dosyanın ZIP içindeki SHA-256 değeri kaynak okunurken hesaplanan değerle karşılaştırılır.
   Başarıda `delivery_archive`, `delivery_sha256`, `delivery_manifest` ve EXE yolu/hash döner;
   bu alanlar uzun araç çıktısında da korunur. **ZIP'in tamamını yeni bir klasöre çıkarın,
   sonra içindeki `<proje>\<proje>.exe` dosyasını açın**; yalnız `.exe`yi taşımayın.

Teslim ZIP'i build/work/spec dosyalarını, kaynak ağacını, işlem günlüklerini ve Python
ortamını içermez; yalnız oluşturulan dağıtım dosyaları ve bağımlılık raporunu alır.
Uygulamanın bilinçli olarak içine gömdüğü veri ve rapor metadata'sı yine özel bilgi içerebilir;
paylaşmadan içeriği inceleyin. Sınır **5000 dosya/dizin girdisi, toplam 512 MiB kaynak dosyasıdır**.
ZIP yeniden sıkıştırılmadan yazılır; dosyalar kesilmez, sınır aşımı hatadır.
Link/junction/hardlink çıktılar reddedilir. Dosya listesi göreli yol, boyut ve SHA-256 içerir;
yerel mutlak proje yolu veya komut argümanı eklenmez.
Hash'ler bozulmayı karşılaştırmaya yarar; **dijital imza, özgünlük veya zararsızlık kanıtı değildir**.

Bu sonlu, etkileşimsiz CLI açılış kontrolüdür; uygulamanın bütün davranışlarının doğru olduğu
anlamına gelmez. Açık kalan GUI süre aşımına uğrar. Özel spec/hook, ek veri dosyası seçimi,
tek dosya paket, imzalama/kurulum sihirbazı ve diğer diller kapsam dışıdır. Build hook'ları,
testler ve EXE kullanıcı yetkileriyle çalışır; otomatik indirme yapılmaması ağ izolasyonu değildir.
İptal/zaman aşımı süreç ağacını kapatır; kısmi çıktılar ve önceki yan etkiler geri alınmaz.
ZIP aşaması da aynı toplam süre/iptal kontrolüne dahildir; yarım `.zip.partial` temizlenir,
başarılı teslim yolu verilmez. Her deneme benzersiz klasör kullanır; önceki teslim sessizce ezilmez.

Gerçek kabul örneği [exe_smoke_demo](projects/exe_smoke_demo/README.md) kod asistanının elle
yazdığı küçük bir test projesidir; bağımsız yerel model başarısı sayılmaz. Üretilen EXE'nin
`--self-test` ile `EXE_SUM=42` yazıp sıfırla çıkması ve kaynak ağacının değişmemesi doğrulandı.
Sonraki ZIP kabulünde 13 dosya hash ile doğrulandı; ZIP bağımsız geçici klasöre çıkarıldı,
çocuk süreç PATH'inde Python olmadan aynı EXE çıktısı/exit 0 tekrar alındı. Bu aynı Windows
makinesindeki testtir; temiz bir başka makinede/Windows sürümünde uyumluluk garantisi değildir.

### Cline hesabını Qt sohbetine bağlama

Cline ayrı ve açıkça seçilen bir sağlayıcıdır; otomatik yerel model seçimi onu çağırmaz. Resmî Windows x64 CLI **3.0.74**, sabit npm lock/integrity ile `.tools\cline` altına kurulur. Global npm/VS Code kurulumu değiştirilmez; kurulum betikleri kapalıdır.

1. Proje Node ortamı hazır değilse önce `.\setup-tools.ps1`; ardından `.\setup-cline.ps1` çalıştırın. Aynı işlem Qt **Sistem > Cline kur / doğrula** düğmesinden yapılabilir.
2. `.\run-desktop.ps1` ile normal kullanıcı Qt'sini açın; model listesinden **Cline (hesabım / ACP)** seçin.
3. **Cline hesabını bağla** düğmesi resmî `cline auth cline` girişini ayrı konsolda açar. Hesap girişini/tarayıcı OAuth işlemini ve model seçimini orada tamamlayın. Şifre/anahtar sohbete girilmez; mevcut VS Code Cline kimlik bilgileri okunup kopyalanmaz.
4. **Cline klasörü seç** ile mevcut bir çalışma klasörü seçin (varsayılan `projects`). Klasör ve açık Cline model tercihi yerel Qt ayarında hatırlanır; kimlik bilgileri bu ayara yazılmaz.
5. **Cline bağlantısını doğrula** ile gerçek ACP el sıkışması, yeni oturum ve Cline'ın sunduğu model kataloğunu kontrol edin. Bu işlem mesaj/geçmiş/model istemi göndermez ve araç izni vermez; Cline sağlayıcı/katalog ağına erişebilir. Oturum hatası, hata koduyla açıkça gösterilir; yalnız el sıkışması “hesap bağlı” sayılmaz.
6. Cline model kutusundan **Hesapta seçili model (varsayılan)** veya katalogdaki açık bir model seçin. ACP'nin modern `session/set_config_option` model seçicisi ve eski `session/set_model` yolu desteklenir; diğer yapılandırma/otomatik izin seçenekleri modele açılmaz. Her yeni turda model yeni oturum kataloğuyla yeniden doğrulanır; kaybolmuş model sessizce başka modele çevrilmez. Ardından mesaj gönderin. Her turda mesaj/geçmiş ve klasör erişimi için bulut/kullanım ücreti uyarısı ayrıca onaylanır. Gerçek seçili model yanıt metadata'sında gösterilir; hesap/bakiye Cline tarafından yönetilir.
7. **Cline kısa yanıt testi**, açık ücret uyarısı/onayı sonrasında seçili modele yalnız sabit bir test istemi gönderir. `projects` altında boş geçici klasör kullanılır ve sonunda temizlenir; ortak geçmiş/ekler gönderilmez, bütün araç izin istekleri reddedilir. Test ancak tamamlanan yanıt tam `CLINE_CONNECTION_OK` olduğunda ve bildirilen araç çağrısı olmadığında geçer; sohbet geçmişine mesaj eklemez. Bu, Cline için sandbox garantisi değildir.

Profil/kimlik bilgileri ve Cline'ın kendi oturumları `.tools\cline-state\{config,data}` içinde kalır; bu özel/ignored alanı paylaşmayın. Asistan sağlayıcı anahtarları sürece miras verilmez. Qt bu dosyalardan anahtar okuyup kendi ayarına taşımaz. Mevcut hesabın CLI tarafında ayrıca giriş gerektirmesi normaldir.

Bağlantı resmî **ACP 1 / stdio** üzerindendir, `--auto-approve false` sabittir. Cline'ın izin istekleri Qt'nin varsayılanı Vazgeç olan onay penceresine gelir; yalnız **allow_once**, hiçbir zaman kalıcı/otomatik izin seçilmez. Ajan Act; Sor/Plan Plan modudur ve bu iki modda yalnız read/search izin istekleri kabul edilebilir. Bazı okumalar Cline tarafından ayrıca sorulmayabilir; bu nedenle seçilen klasör/bulut erişimi onayı önemlidir. Genel Qt yerel ajanının Sor/Plan davranışından ayrı bir sağlayıcı akışıdır. Yönetici Qt'de Cline reddedilir.

Metin akışı ve sınırlı araç sonuçları aynı sohbet izinde gösterilir; yalnız tamamlanmış yanıt ortak sohbet geçmişine yazılır. Her Qt turu yeni Cline ACP oturumu açar; ortak geçmişin son on mesajı (24.000 karakter sınırı ve açık kesilme işareti) bağlama verilir. Cline MCP/araç oturumlarının sonraki Qt turunda otomatik sürmesi veya mevcut Qt MCP kataloğunun Cline'a otomatik taşınması yoktur. Ekler/manuel araç bağlamı sessizce gönderilmez; bu ilk sürümde bunlar kaldırılıp Cline çalışma klasörü kullanılmalıdır.

Toplam süre Qt istek zaman aşımı ayarına bağlıdır (varsayılan 600 sn); en fazla 64 araç çağrısı, 1 MB protokol iletisi ve 64.000 karakter yanıt sınırı vardır. İptal/süre aşımı/bağlantı hatası başarı olarak kaydedilmez; kendi Windows Job Object süreç ağacı kapatılır. Bu sandbox veya otomatik geri alma değildir; dosya/ağ/komut etkileri kalabilir, kalıcı GUI/daemon başlatma garantisi yoktur.

**Doğrulama sınırı:** gerçek CLI/ACP el sıkışması ve `session/new` artık geçti; son kontrolde 307 model bildirildi. Ancak varsayılan modelle ve katalogda ücretsiz etiketli `recursive/flint-v1.0:free` modeli açıkça seçerek yapılan araç izinsiz kısa yanıt denemeleri `session/prompt -32603` verdi; sağlayıcı mesajındaki `insufficient balance` sinyali bakiye engelini doğruladı. Ücretsiz etiketi bu hesapta bakiye kontrolünü aşmadı. Qt yalnız sabit, hassas veri içermeyen bakiye/giriş yönlendirmesi gösterir; ham sağlayıcı hatası/anahtar gösterilmez. Cline hesabındaki kredi ve kişisel/kurum faturalandırma seçimini resmî Cline arayüzünden kontrol edin; otomatik ödeme, bakiye yükleme veya sessiz alternatif modele geçiş yapılmaz. **Oturum hazır; gerçek model yanıtı henüz doğrulanmadı.** Hesap engeli giderildiğinde **Cline kısa yanıt testi** ile tekrar deneyin. İzin, ret, mod, araç izi, iptal, model seçimi/katalog hatası, yerel tercihler, ortak geçmiş ve kısa yanıt testinin başarı/hata uçları yerel fixture'larla test edilir.

Resmî başvurular: [Cline CLI](https://docs.cline.bot/usage/cli-overview.md), [hesap girişi](https://docs.cline.bot/getting-started/authorizing-with-cline.md), [ACP](https://docs.cline.bot/usage/acp.md).

### NVIDIA NIM API bağlantısı

NVIDIA, Cline'dan bağımsız **Bulut: NVIDIA NIM** sağlayıcısıdır (`cloud:nvidia`).
Resmî `https://integrate.api.nvidia.com/v1` OpenAI uyumlu API kullanılır; ek SDK kurulmaz.
Otomatik yerel model seçimi NVIDIA'yı kendiliğinden kullanmaz. NVIDIA hesabındaki deneme,
kota, model erişimi ve ücret koşulları geçerlidir; sınırsız/ücretsiz erişim garanti edilmez.

1. Qt **Ayarlar > NVIDIA NIM API > NVIDIA API sayfasını aç** ile [NVIDIA Build](https://build.nvidia.com/) hesabınıza girip API anahtarı oluşturun.
2. Anahtarı **sohbete değil maskeli API anahtarı alanına** girin. Model ID'yi seçip **Anahtar + modeli kaydet** deyin.
   Varsayılan `meta/llama-3.1-8b-instruct`; erişiminiz olan başka model ID'si de girilebilir.
   Anahtar onayda gösterilen mevcut API sunucusunun `/data/cloud-providers.json` deposunda saklanır;
   Qt INI/sohbet geçmişine yazılmaz, başarıda alan temizlenir. Bu depo şifreli anahtar kasası değildir;
   API sunucusunu/veri volume'unu güvenilir tutun, paylaşmayın.
3. **Kayıtlı modelleri getir** yalnız NVIDIA model kataloğunu sorgular; gerçek model yanıtını doğrulamaz.
   Seçim, testte anında kullanılır; sohbet varsayılanını değiştirmek için anahtarla birlikte kaydedin.
4. **Kısa yanıt testi**, ayrı onayla yalnız sabit istem gönderir; geçmiş, dosya, ek veya araç sonucu göndermez.
   Tam `NVIDIA_CONNECTION_OK` ve tamamlanmış (`stop`) yanıt şarttır; kota/ücret uygulanabilir.
5. Sohbet model listesini **↻** ile yenileyip **Bulut: NVIDIA NIM** seçin.
   Mevcut Sor/Plan/Ajan akışları ve yan etkiler için ayrı araç onayları kullanılır; seçili bağlamın
   buluta aktarılması ayrıca onay ister. Web sağlayıcı listesi de aynı katalogdan NVIDIA'yı gösterir.
   Anahtarı silmek için **Araçlar > Bulut API > API anahtarını kaldır**, sağlayıcı `nvidia`.

Alternatif olarak mevcut `.ai-next-cloud.env` dosyasına **yerel olarak**, üzerine yazmadan
`NVIDIA_API_KEY` ve isteğe bağlı `NVIDIA_MODEL` eklenebilir (örnekler `.ai-next-cloud.env.example` içinde).
Ortam anahtarı UI kaydından önceliklidir; UI'den kaldırmak ortam anahtarını silmez.
Ortam dosyası değişirse `docker compose up -d --no-deps --force-recreate api` gerekir.
Qt'den kaydetmek için container yenilemek gerekmez.

Resmî protokol: [NVIDIA LLM API](https://docs.api.nvidia.com/nim/reference/llm-apis).
Anahtar kaydı/katalog ve gerçek yanıt ayrı kanıtlardır; anahtar olmadan canlı hesap yanıtı doğrulanmış sayılmaz.

### VS Code referansı

Kurulu **VS Code 1.145.2 / Copilot Chat 0.73.0** paket ve yerelleştirme metadata'sı REA ile incelendi: model/oturum seçimi, ekler, araç seçimi/onayı, modlar ve durdurma yüzeyleri referans alındı. Qt uygulaması özgün kodla yazıldı; Microsoft kaynak/varlıkları kopyalanmadı. İnceleme metadata ile sınırlıdır; canlı VS Code davranışı veya bulut iç işleyişi doğrulanmadı. Editör içi çok dosyalı düzenleme, Copilot bulut servisleri, extension host ve tüm özel agent/skill davranışları birebir eşdeğer değildir.

### Gelişmiş araç kataloğu

Kaynaklar 7 Kasım 2026'da kontrol edildi. Katalog **otomatik kurulum, sunucu çalıştırma veya yetki genişletme yapmaz**. API'de eklenti kaydının bulunması; haricî servisin, modelin, beceri paketinin veya grafiğin hazır olduğunu kanıtlamaz. MCP bağlantıları ayrıca MCP / Copilot ekranındaki "Araçları getir" ile doğrulanır.

| Araç / resmî kaynak | Kullanım | DeepPanda bağlantısı |
|---|---|---|
| [GitHub MCP](https://github.com/github/github-mcp-server) | Depo, issue/PR, Actions | MCP; proje kaydı mevcut, token ve erişim testi gerekir |
| [REA](https://github.com/morluto/rea) | Binary, .NET, Electron ve runtime analizi | Kullanıcı MCP kaydı |
| [replica-skill](https://github.com/Jakeschincariol/replica-skill) | Tasarım, mimari ve test iş akışları | `skills`; onaylı paket kurulumu |
| [OpenJarvis](https://github.com/open-jarvis/OpenJarvis) | Yerel ajan platformu | `openjarvis`; servis ayrıca başlatılır |
| [Build Your Own X](https://github.com/codecrafters-io/build-your-own-x) | Eğitim ve öğrenme planı | `byox` |
| [graphify](https://github.com/safishamsi/graphify) | Bilgi grafiği ve ilişki sorgusu | `graphify`; önceden üretilmiş graf gerekir |
| [Playwright MCP](https://github.com/microsoft/playwright-mcp) | Tarayıcı otomasyonu ve akış testi | İsteğe bağlı MCP |
| [Chrome DevTools MCP](https://github.com/ChromeDevTools/chrome-devtools-mcp) | Performans, ağ, konsol | İsteğe bağlı MCP |
| [Context7](https://github.com/upstash/context7) | Güncel/sürüme özel dokümantasyon | İsteğe bağlı haricî MCP |
| [Docker MCP Toolkit](https://docs.docker.com/ai/mcp-catalog-and-toolkit/) | Katalog ve konteynerli sunucu yönetimi | İsteğe bağlı; Docker izni gerekir |
| [Filesystem MCP](https://github.com/modelcontextprotocol/servers/tree/main/src/filesystem) | Sınırlı klasör erişimi | İsteğe bağlı referans sunucu |
| [Git MCP](https://github.com/modelcontextprotocol/servers/tree/main/src/git) | Yerel Git durumu ve diff | İsteğe bağlı referans sunucu |
| [Fetch MCP](https://github.com/modelcontextprotocol/servers/tree/main/src/fetch) | Web içeriğini Markdown olarak okuma | İsteğe bağlı referans sunucu |
| [Sequential Thinking MCP](https://github.com/modelcontextprotocol/servers/tree/main/src/sequentialthinking) | Plan adımları ve revizyon kaydı | İsteğe bağlı referans sunucu |
| [DeepPanda SQL / eski MCP'nin durumu](https://github.com/modelcontextprotocol/servers#archived) | SQLite inceleme ve onaylı yedek | Mevcut `database` eklentisi |

Araştırma notları:
- REA için resmî kaynak `morluto/rea`; benzer isimli depolar resmî dağıtım sayılmaz.
- MCP referans sunucuları üretime hazır ürün garantisi vermez. Eski SQLite MCP örneği arşivlenmiştir; mevcut salt-okunur SQL eklentisi korunur.
- Güncel Git/Fetch MCP sunucuları SDK 2.x ister; projenin `mcp<2` ortamına doğrudan kurulmaz. Ayrı F: ortamı ve protokol uyumluluk testi gerekir.
- Chrome DevTools kullanım istatistikleri ve CrUX erişimi için `--no-usage-statistics`, `--no-performance-crux` seçenekleri vardır. Tarayıcı araçlarında ayrı test profili kullan.
- graphify/replica upstream iş akışları Claude odaklıdır. DeepPanda'nın beceri metni uygulaması ve graf okuması, bütün upstream araçlarının otomatik taşındığı anlamına gelmez.

### Uzun işlemler ve zaman aşımı

Qt'nin normal istek süresi Ayarlar'dan yönetilir (varsayılan 600 sn). `multi_agent/run` için model kataloğu + beş ardışık model çağrısı nedeniyle varsayılan bekleme en az **3660 sn**, `ollama/pull` için **7260 sn** olur. Programatik açık `timeout` değeri önceliklidir. Web nginx yapılandırmasında da yalnızca bu iki uç noktanın okuma süreleri uzatılmıştır; sağlık/liste istekleri değişmez, bağlantı kurma sınırı 5 sn kalır.

Bağlantı ve yanıt zaman aşımı ayrı mesajlarla gösterilir. İstemcinin zaman aşımı sunucudaki işlemin iptal edildiğini kanıtlamaz; özellikle yazma/indirme işlemlerini durumlarını kontrol etmeden yeniden gönderme. Otomatik tekrar eklenmemiştir. Web ayarı için web imajının yeniden derlenmesi gerekir; mevcut konteyner kendiliğinden güncellenmez.

### F: üzerinde yerel MCP kurulumu

`tools/package.json` ve `tools/package-lock.json`, beş sunucunun sürümlerini sabitler. `setup-tools.ps1`, resmî SHA-256 ile doğrulanan **Node 24.22.2** paketini proje `.tools/runtime` alanında kullanır; sistem Node/Python kurulumunu değiştirmez. Npm önbelleği, home, geçici dosyalar, tarayıcı profilleri ve çıktılar proje `.tools` alanına yönlendirilir.

| Sunucu | Paket sürümü | Doğrulanan araç sayısı |
|---|---|---|
| Filesystem | `@modelcontextprotocol/server-filesystem@2.2.0` | 10, tamamı salt okunur |
| Sequential Thinking | `@modelcontextprotocol/server-sequential-thinking@2.1.1` | 1 |
| Playwright | `@playwright/mcp@0.0.84` | 25 |
| Chrome DevTools | `chrome-devtools-mcp@1.12.0` | 32 |
| REA | `rea-agents@6.8.0` | 229 |

Toplam **297 araç**, MCP `2025-11-25` protokolüyle gerçek `initialize` ve `tools/list` çağrılarına cevap verdi. Bu test tarayıcı açılması, native analiz motorlarının hazır olması veya Qt'nin Python MCP bağlantısının çalışması anlamına gelmez.

**Güncel durum:** Bir tekrar-kurulum denemesi sandbox `EPERM` hatasıyla yarım kalmıştı. Sandbox politikası güncellendikten sonra `.\setup-tools.ps1` 192 paketi kurdu ve beş sunucu yeniden 297 araç gösterdi. `.tools/mcp-servers.json` yayımlandı. `.\setup-tools.ps1 -VerifyOnly` 0 koduyla çıktı ve `.tools/mcp-verification.json`, `installation_valid: true` gösteriyor. Mevcut model/veritabanları ve ortak `mcp-servers.json` değiştirilmedi.

Kurulum betiği artık tekrar çalıştırmada tüm bağımlılık ağacını silen `npm ci` yerine kilit dosyasını kullanan `npm install` çalıştırır. Yapılandırma ancak protokol testi başarılı olduktan sonra yayımlanır; hata halinde host kaydı yayımlanmaz. VS Code ajan sandbox'ı açıksa proje kökü `readwritePaths` içinde olmalıdır. `settings.json` içinde Windows yollarındaki her `\` iki kez yazılmalıdır, örneğin `"F:\\DeepPanda Agentic Al"`.

```powershell
.\setup-tools.ps1
# Paket indirmeden, mevcut kurulumu ve stdio bağlantılarını kontrol et:
.\setup-tools.ps1 -VerifyOnly
```

Qt içinden aynı işlemler **Sistem → Yerel MCP araçlarını kur / doğrula** ile yapılır. Başarılı kurulumdan sonra **MCP / Copilot → Yapılandırmayı yeniden oku** kullanılır. Host kaydı `.tools/mcp-servers.json` içindedir; Docker API'nin ortak yapılandırmasına Windows yolları eklenmez. Kullanıcı tanımlı ek MCP dosyaları en son okunur ve otomatik kayıtları geçersiz kılabilir.

- Kurulum betikleri ve otomatik tarayıcı indirmeleri kapalıdır (`ignore-scripts=true`). Native REA bileşenleri ve tarayıcı gereksinimleri ayrıca kontrol edilir.
- Filesystem yalnızca `.tools/workspace` klasörünü salt okunur açar; tüm F: sürücüsünü veya proje sırlarını açmaz.
- Chrome kullanım istatistikleri/CrUX kapalıdır; Playwright ayrı geçici bağlam kullanır.
- İndirme 120 sn, npm işlemi 900 sn, her stdio denetimi 30 sn ile sınırlıdır. Aynı anda ikinci kurulum dosya kilidiyle engellenir.
- `.tools` ve `node_modules`, ajan çalışma alanı / kod grafı / tanılama taramalarından dışlanır.
- 12 Node testi ve 37 Python/Qt testi (+134 alt test) geçti. Erken hatalarda eski başarı raporunun geçersizleşmesi, bozuk kurulumun reddedilmesi, host kaydının kaldırılması, kurulum kilidinin bırakılması ve işlem ortamının geri yüklenmesi ayrıca doğrulandı. Sandbox güncellemesinden sonra canlı kurulum ve `-VerifyOnly` doğrulaması başarılı oldu.

## Entegrasyonlar

- **GitHub Copilot MCP araçları (`mcp`):** `mcp-servers.json` içindeki `github` (`https://api.githubcopilot.com/mcp/`, `GITHUB_TOKEN`) ve `graphify` sunucuları. API'de `servers`/`tools` salt-okunur, `call` onay ister. Qt istemcisi ayrıca VS Code'daki `rea`, `kaggle` ve diğer kullanıcı MCP sunucularını kullanır.
- **REA:** VS Code `mcp.json` içindeki `rea` (stdio, `npx rea-agents mcp`) sunucusu MCP sayfasından çalıştırılır; tersine mühendislik araçları bu bilgisayarda yürür.
- **replica-skill ve SKILL.md becerileri (`skills`):** `/data/skills` ve `/workspace/skills` altındaki `SKILL.md` paketlerini listeler, gösterir ve yerel Qwen ile uygular. `install` onaylı olarak GitHub arşivini indirir (en fazla 50 MB); önerilen kaynaklar `Jakeschincariol/replica-skill` ve `safishamsi/graphify`.
- **OpenJarvis (`openjarvis`):** OpenAI uyumlu yerel sunucuya bağlanır; mevcut **Sohbet** sağlayıcısında/araçlarında kullanılır, yeni sayfa gerekmez. Resmî `OpenJarvis[server]==1.0.4`, Windows Python 3.12 ile yalnız `.tools\venvs\openjarvis` ortamına kuruldu. `.\run-openjarvis.ps1`, `tools\openjarvis-local.toml` ile **yalnız `127.0.0.1:8010`** adresini dinler; Ollama `127.0.0.1:11435`, model `qwen3.6:latest`, araç çağırmayan `simple` ajanı kullanır. Dış analitik, yerel telemetri, izler ve ajan zamanlayıcısı kapalıdır; sağlayıcı anahtarları süreçten çıkarılır, OpenJarvis durumu/kimlik deposu `.tools\openjarvis-state` ile ayrılır. Kurulum gerekirse Python **3.10–3.13** ile `python -m venv .tools\venvs\openjarvis`, ardından `.\.tools\venvs\openjarvis\Scripts\python.exe -m pip install -r .\tools\requirements-openjarvis.txt` çalıştırın. Mevcut WSL Python 3.14 sürümü bu paketle uyumsuzdur; sistem Python'u değiştirilmedi. API adresi `OPENJARVIS_BASE_URL` (varsayılan `http://host.docker.internal:8010/v1`); gerçek Docker API → Windows loopback model listesi doğrulandı. Bu betik kurulum/model indirme veya otomatik Windows başlangıcı eklemez; konsolu kapatmak sunucuyu durdurur. Kimlik doğrulaması olmadan tüm ağ arayüzlerine açmayın.
- **Build Your Own X (`byox`):** `codecrafters-io/build-your-own-x` kataloğunu indirir, kategori/arama sunar ve seçilen eğitim için yerel Qwen ile adım planı çıkarır (`BYOX_SOURCE_URL`).
- **graphify (`graphify`):** mevcut `graphify-out/graph.json` dosyasını kullanır. Eklenti özet, sorgu, komşular, yol ve rapor eylemlerini salt-okunur sunar (`GRAPHIFY_GRAPH`). Güncel upstream README, Python/Claude Code ile `graphifyy` kurulumunu anlatıyor; `--platform copilot` desteği burada doğrulanmadı. Graf üreticisini ve veri aktarım izinlerini resmî kaynaktan ayrıca doğrula; paket/istemci uyumluluğu kontrol edilmeden proje ortamına kurma.
- **Yerel çoklu ajan (`multi_agent`):** Araçlar → Çoklu ajan bölümünde planlayıcı, bağlam araştırmacısı, geliştirici, test/inceleyici ve sentezleyici aşamalarını Qwen/Ollama ile çalıştırır. Aşamalar web araştırması, MCP/araç, dosya veya komut erişimine sahip değildir; bir defalık onay tüm çalışmayı başlatır ve her aşama yanıtı sonuçta gösterilir.
  Her aşamada gerçek `done=true` / `done_reason=stop`, yalnız `content` alanlı JSON ve en fazla 6000 karakter gerekir.
  Yarım, boş, geçersiz şemalı veya uzun yanıt sonraki aşamayı başlatmaz; çıktı sessizce kesilmez ve otomatik tekrar yoktur.
  Gerçek beş aşamalı yerel toplama fonksiyonu taslağı denemesi güncel denetimlerle 37,55 saniyede tamamlandı:
  plan/bağlam/sentez Qwen 2.5 Coder, taslak/inceleme Qwen 3.6. Bu, taslak üretme akışının kanıtıdır;
  önerilen kodun çalıştırıldığı, testlerinin geçtiği veya her istekte aynı kalite/sürenin sağlanacağı anlamına gelmez.
- **SQL (`database`):** yukarıdaki "Servis profilleri" bölümüne bakın.

### Gerçek entegrasyon ve kontrollü Windows kabulü

- GitHub MCP, mevcut `gh` oturumundan yalnız bellekte alınan kimlikle gerçek
  `initialize` / `tools/list` çağrılarını tamamladı: **49 araç**. Depo içeriği
  gönderilmedi, araç eylemi yürütülmedi, anahtar rapora yazılmadı.
- graphify'da hem `graphify` Python modülü hem gerçek `graph.json` eksik.
  Sırf `python` bulunması sunucunun çalıştığını kanıtlamaz; gerçek MCP başlatma
  başarısızdır. Yanlış `--platform copilot` önerisi kaldırıldı;
  sohbet salt-okunur listesi gerçek **`query`** eylemiyle eşleştirildi.
  Claude Code/graf üretimi için kodu buluta gönderen bir kurulum yapılmadı.
- Piper/faster-whisper ve Türkçe ses dosyası yok; ffmpeg mevcut olsa da ses
  üretme/tanıma çalışıyor sayılmaz. Seçili `tr_TR-dfki-medium` model kartı veri
  kümesi lisansını **CC-BY-NC-SA 4.0** olarak bildirir; dağıtım/kullanım şartları
  değerlendirilmeden model indirilmedi. Otomatik Whisper indirme kapalı kaldı.
- Gerçek Windows kaydında yalnız benzersiz, daha önce var olmayan geçici HKCU
  anahtarında `REG_SZ`, `REG_EXPAND_SZ`, `REG_DWORD`, `REG_QWORD`, `REG_MULTI_SZ`
  yazma/silme/geri yükleme/geri alma geçti; anahtar tamamen temizlendi.
  Aygıt/sürücü/port sorguları salt-okunur çalıştı. Yönetici yetkisi verilmedi,
  mevcut ayarlar ve donanım değiştirilmedi. Kritik aygıt, imza, kullanımda sürücü,
  dışa aktarılmadan silmeme dalları **6 test + 14 alt testte mock fixture** ile
  doğrulanır; bunlar gerçek sürücü kaldırma denemesi diye sunulmaz.

İlk durum/Windows/MCP kanıtı
`data\program-builds\remaining-capabilities-acceptance.json`, sonraki OpenJarvis
kanıtı `data\program-builds\openjarvis-local-acceptance.json` içindedir.
OpenJarvis gerçek Docker API sohbetinde yerel Qwen3.6'dan tam
`OPENJARVIS_LOCAL_OK` yanıtını verdi. Bu yalnız sabit kısa bağlantı testidir;
araçlı ajan/yük/performans kabulü değildir. Detached çalıştırma bu oturumun
araç ortamında iki kez çıkış1 verdi; bounded doğrulama sunucusu test sonunda
durduruldu. Kurulum/yapılandırma kalıcıdır; kullanmak için
`.\run-openjarvis.ps1` konsolunu açık tutun. Çalışan kalıcı servis veya Windows
oturum açılışında otomatik başlatma var diye raporlanmaz.
Cline ACP oturumu/model listesi ayrı olarak çalışmıştır; gerçek sağlayıcı yanıtı
hesap bakiyesinde engellidir. Ödeme/hesap değişikliği otomatik yapılmaz.

## İsteğe bağlı FreeLLMAPI chat gateway

FreeLLMAPI MIT lisanslı resmi image olarak ayrı container'da, yalnızca `127.0.0.1:3001` üzerinde çalışır. İlk anahtar kurulumu ve chat yönlendirmesi varsayılan olarak kapalıdır. Yerel encryption key dosyasını oluşturup gateway'i başlat:

```powershell
.\setup_freellmapi.ps1
docker compose up -d freellmapi
```

`http://127.0.0.1:3001` adresinde ilk kurulumu tamamla, Keys sayfasından kullanacağın provider key'lerini ekle ve unified API key oluştur. AI-Next için `.ai-next-cloud.env.example` dosyasını `.ai-next-cloud.env` olarak kopyala; unified key'i bu yerel dosyaya gir ve `FREELLMAPI_CHAT_ENABLED=true` yap. Ardından API container'ını yenile:

```powershell
Copy-Item .ai-next-cloud.env.example .ai-next-cloud.env
docker compose up -d api
```

Yalnızca `/api/chat` completion metni ve sohbet geçmişi gateway'e gönderilir. Intent sınıflandırması Ollama'da kalır; görev planı, kod önerisi, araştırma, belge ve statik analiz yolları gateway'e yönlendirilmez. Açıkça yerel model seçilirse yerel Ollama kullanılır. Provider key'leri ve FreeLLMAPI encryption key gitignored yerel dosyalardadır; encryption key'i yedekle, kaybolursa saklanan provider key'leri çözülemez. Free-tier kota, SLA ve her provider'ın kullanım şartları geçerlidir.

## Çevrim dışı Docker paketi

Windows x64 kaynak makinede `packaging/offline/Build-OfflineBundle.ps1 -PauseServices` beş Linux/amd64 image’ını, beş Ollama modelini ve `ai_data`, `qdrant_data`, `redis_data` dahil dört named volume’u tek taşınabilir klasöre alır. Varsayılan çıktı `%USERPROFILE%\Desktop\DeepPanda-Offline-Portable`; tutarlı veritabanı snapshot’ı için çalışan servisler paketleme sırasında durdurulur ve script sonunda yeniden başlatılır. Paket yaklaşık 50–60 GB olabilir.

Hedef makinede Docker Desktop, WSL 2 Linux container desteği, Docker Compose v2.20+ ve yeterli Docker storage gerekir; Docker Desktop pakete dahil değildir. Klasör kopyalanıp açıldıktan sonra `Install-OfflineBundle.ps1` çalıştırılır. Installer SHA-256 manifestini doğrular, image’ları `docker load` ile yükler, modelleri/verileri volume’lara geri koyar ve image pull/build yapmadan servisleri başlatır. Mevcut hedef volume’ları bulursa üzerine yazmaz. Durdurmak için `Remove-OfflineBundle.ps1`, volume’ları da silmek için ayrıca `-DeleteData` kullanılır.

Paket yerel model ağırlıklarını, indeksleri ve veritabanlarını içerir; aktarırken bu klasörü hassas veri kabul edin. Paket şifrelenmez. Ayrıntılar: [offline paket talimatları](packaging/offline/README-OFFLINE.md).

## Otonom hata analizi

Arayüz açıldığında `diagnostics` eklentisi mount edilen AI-Next workspace'ini salt okunur tarar; `Hata tara` ile yeniden çalıştırılabilir. Python AST/Ruff ve JSON/TOML/YAML sözdizimi denetlenir. `.env`, model/runtime paketleri, sanal ortamlar, bağımlılık, build/cache dizinleri ve sembolik bağlantılar atlanır. Birleştirme sonrası `data`, `runtimes`, `_tmp`, `_arsiv` ve `.tools` dizinleri tanılama, kod grafı ve workspace taramalarından da dışlanır. Sınırlar: dosya başına 1 MB, toplam 100 MB, 5000 dosya ve 120 saniye. Rapor yalnızca bulgu, yol ve satır numarası döndürür; kodu değiştirmez, komut çalıştırmaz veya ağa çıkmaz.

## Eklenti ekleme

Her eklenti `PluginManifest` ve `invoke(action, payload)` sözleşmesini uygular. Eklenti kaydı `create_app` içindeki gateway kurulumunda yapılır; route'lar ve diğer eklentiler doğrudan birbirini çağırmaz. Yeni eylemler gateway üzerinden geçmeli ve ilerideki onay/izin politikasına burada bağlanmalıdır.

## Workspace araçları

`workspace` plugin'i `list`, `read`, `preview_write`, `write`, `rollback` ve `run` eylemlerini verir. Mutlak/kaçış yolları, symlink'ler, `.env`, `.env.*` gizli dosyaları, `.env` ile biten adlar (örneğin `.freellmapi.env`, `.ai-next-cloud.env`), sanal ortamlar, `node_modules`, model/runtime ve build/cache klasörleri dışarıda kalır. `.env.example` ve `.ai-next-cloud.env.example` gibi örnekler erişilebilir kalır. `data`, `runtimes`, `_tmp`, `_arsiv` ve `.tools` yolları listeleme ve dosya erişiminden dışlanır. `write`, `rollback` ve `run` payload'ı açık `approved: true` olmadan reddedilir. Var olan dosya değiştirilmeden önce `/data/workspace-backups` altında yedeklenir; komutlar `shell=False`, PATH allowlist'i ve timeout ile çalışır. Analiz eklentileri dosya değiştirmez.

## Yerel hafıza

`memory` eklentisi onaylı `remember`, filtrelenebilir `search` ve `timeline`, `taxonomy`, `export`, `import`, `preview_source` ve `delete_source` eylemlerini sunar. Panelde proje/kategori/kaynak filtresi, taxonomy görünümü ve JSON dışa/içe aktarımı vardır. Import tekrar kayıtları atlar; dosya 10 MB ve 5.000 notla sınırlıdır. Kaynak silme öncesi kayıtlar versioned JSON backup'a yazılır; backup aynı import akışıyla geri yüklenebilir. Yazma, import, export ve silme açık onay gerektirir. SQLite dosyası Docker'da ayrı `ai_data` volume'unda `/data/memory.db` olarak kalır; model ağırlıklarından ve koddan ayrıdır. Embedding tabanlı anlamsal arama henüz yoktur.

## Belgeler

`Belgeler` panelinden PDF, DOCX, PPTX, XLSX, XLSM, TXT, MD, PY, JSON, TS ve TSX dosyaları açık kullanıcı onayıyla yerel indekse eklenebilir. Upload sınırı 20 MB; çıkarılan metin `/data` volume'unda indekslenir ve arama sonuçları kaynak karakter aralığıyla birlikte gösterilir. Metin önizlemesi 50.000 karakterle sınırlıdır; dosya indirme yalnızca indekslenmiş document ID üzerinden yapılır. Liste ve arama sonuçlarından açık onayla belge ve indeks kayıtları kalıcı silinebilir. Belge içeriği sohbet hafızasına otomatik yazılmaz; zengin PDF/görsel önizlemesi yoktur.

## Görev planları

`Görevler` paneli seçili yerel modelden taslak adımlar alabilir; taslak kullanıcı tarafından düzenlenip açıkça kaydedilene kadar kalıcı olmaz. Aktif adımda seçilen tek workspace dosyası ve isteğe bağlı en fazla 3 bağlam dosyası yerel modele verilip 1-based satır aralığı için tek değişiklik önerilebilir; toplam kaynak bağlamı 30.000 karakter, JSON çıktı bütçesi 4.096 token ile sınırlıdır. Backend önerilen özgün satırların hedef dosyada belirtilen yerde birebir eşleştiğini doğrular ve değişikliği kendisi uygular. Öneri yalnızca editöre gelir; diff önizleme ve ayrı yazma onayı gerekir. Model dosya yazamaz veya komut çalıştıramaz. Plan onaylanmadan adım ilerletilemez; her adım durumu değişikliği ayrıca açık onay ister. Onaylı yazma backup ID'si audit geçmişine bağlanır ve kullanıcı onayıyla geri alınabilir. Allowlist içindeki test komutları kullanıcı onayıyla, `shell=False` ve sınırlı timeout ile çalışır; sonuç ve sınırlı çıktı audit geçmişine yazılır. `Görevi kanıta göre doğrula`, adımların tamamlandığını ve kod görevinde son yazım/geri alma işleminden sonra başarılı bir test kaydı bulunduğunu salt-okunur denetler; testleri yeniden çalıştırmaz veya kaydedilmiş sonucu bağımsız olarak kanıtladığını iddia etmez.

## Arka plan işleri

`jobs` eklentisi kalıcı SQLite state ve event geçmişi, worker claim, monotonik progress, cooperative cancel, açık onayla retry ve stale-worker recovery sağlar. `İşler` paneli mevcut işleri ve sonuçlarını gösterir. Public URL araştırması bu çekirdeğin ilk worker’ıdır; medya worker’ı henüz bağlı değildir. Job oluşturmak kendi başına iş başlatmaz. Stale recovery açık onay ister ve otomatik retry yapmaz.

## Public URL araştırması

`Araştırma` paneli opt-in DuckDuckGo araması yapar; sorgu DuckDuckGo’ya iletilir ve bulunan URL ancak kullanıcı “Kaynaklara ekle” seçerse araştırmaya girer. Ayrıca elle 1–5 public HTTP(S) URL veya açık onayla 1–3 `github.com/owner/repository` README’si araştırılabilir. Repository clone edilmez ve kod çalıştırılmaz. Başlamadan önce onay alınır; private/local DNS hedefleri ve private adrese yönlendirmeler engellenir, environment proxy kullanılmaz, kaynak response’u 1 MB ve alıntı 4.000 karakterle sınırlıdır. Kaynak metni güvenilmeyen veri olarak yerel modele gönderilir; atıflı özet ve progress `İşler` panelinde saklanır. Başarılı sonuç, Job Merkezi’nden ayrıca onaylanarak hafızaya bir kez kaydedilebilir; otomatik kayıt yoktur.

İsteğe bağlı Yandex Search API için `YANDEX_SEARCH_API_KEY`, `YANDEX_FOLDER_ID`, `YANDEX_SEARCH_TYPE` ve `WEB_SEARCH_PROVIDER` container environment’ından okunur. `WEB_SEARCH_PROVIDER=auto` (varsayılan), iki credential da varsa Yandex’i, yoksa DuckDuckGo’yu seçer. Credential değerlerini kaynak dosyalara eklemeyin.

## Public repo takibi

`Araştırma` panelindeki allowlist yalnızca `owner/repository` biçiminde public GitHub depolarını tutar. Ekleme, metadata kontrolü, README/seçilmiş dosya indeksleme ve listeden çıkarma ayrı kullanıcı onayı ister. Metadata kontrolü elle başlatılır; yalnızca son release ve commit bilgisi okunur. README tek dosya ve 1 MB ile sınırlıdır. Kullanıcı ayrıca en fazla 5 normalize repo-relative text/source path seçebilir; dosya başına 1 MB, toplam 3 MB sınırı vardır ve desteklenmeyen/binary dosyalar reddedilir. İçerik kaynak URL/hash’iyle belge indeksine yazılır, aynı GitHub blob’u tekrar indekslenmez. Clone, otomatik dosya keşfi ve kod çalıştırma yapılmaz. Repo başına 60 saniye bekleme ve saatte toplam 20 yerel istek sınırı SQLite’ta kalıcıdır; GitHub’ın kendi rate limit yanıtları da gösterilir. Webhook veya otomatik arka plan taraması yoktur.

Browser snapshot için Playwright Chromium kullanılır. Varsayılan host allowlist `localhost`, `127.0.0.1`, `::1`, Compose içi `web` ve `host.docker.internal`’dır. Ek host gerekiyorsa `BROWSER_ALLOWED_HOSTS` içinde tam host adı açıkça yapılandırılmalıdır. Snapshot GET-only’dir; JavaScript, form/etkileşim, download ve allowlist dışı request’ler kapalıdır.

## Yerel kod grafı

`codegraph` eklentisi Python dosyalarını AST ile parse eder; modül, sınıf, fonksiyon, import ve statik çağrı ilişkilerini çıkarıp `/data/code_graph.json` içinde saklar. `build`, `search` ve `path` eylemleri merkezî gateway'den çağrılır. Kaynak kod çalıştırılmaz; dinamik dispatch ve çözümlenemeyen çağrılar bilinmeyen kalır. İlk sürüm Python-only'dir.

## Kaynaklı statik analiz

Allowlist’teki repo snapshot’ları ve diğer indekslenmiş text/source belgeleri `analysis` LangGraph akışıyla açık onaydan sonra incelenebilir. Workflow belgeyi sınırlandırılmış önizlemeyle okur, yalnızca kurulu local Ollama modelini çağırır ve kaynak dosya/URL ile doğrulanmış birebir line evidence döndürür. Belge içeriği güvenilmeyen veri sayılır; workflow kod çalıştırmaz, URL açmaz, exploit adımı üretmez ve raporu otomatik kaydetmez.

`knowledge` eklentisi aynı onaylı belge snapshot’larını `nomic-embed-text:latest` ile 768 boyutlu chunk’lara gömer ve Qdrant’ta kaynak URL, blob SHA, belge ID’si ve karakter aralıklarıyla saklar. `Araştırma` panelinden açık onayla indexleme ve vector delete yapılır; anlamsal arama salt-okunurdur. Aynı belge yeniden indexlenince önceki Qdrant point’leri değiştirilir, duplicate birikmez; document index’i vector delete işleminden etkilenmez.

## Çevrim dışı statik binary analizi

Araştırma paneli kullanıcı tarafından seçilen PE/ELF/Mach-O dosyasını açık onaydan sonra yerel LIEF ve Capstone ile inceler; upload 10 MB, executable section disassembly 256 KB/1.000 instruction, function/export listeleri 500 kayıt ve printable string listesi 500 kayıtla sınırlıdır. x86, x86-64 ve ARM64 instruction decoding desteklenir; diğer mimariler için metadata ve strings döner. Disassembly mümkün olduğunda entrypoint’ten başlar. Sonuçta format/header/section/import bilgisi, bulunan function/export kayıtları, adresli disassembly ve ASCII/UTF-16 stringler gösterilir. Çıktı truncation durumunu belirtir. Binary hiçbir aşamada çalıştırılmaz; decompiler, control-flow graph, dynamic analysis, exploit üretimi veya otomatik hedef taraması yoktur.

Ayrı PE odaklı arayüz `/pe-lab.html` adresinde sunulur. Tek örnek seçimi, onay, instruction sayfalama, string filtreleme, import sembollerini açma ve JSON raporu dışa aktarma desteklenir; istekler yalnızca aynı makinedeki AI-Next API’sine gider.

## Çalışma modları

`workflows` plugin kataloğu `standard`, `plan`, `debug`, `review`, `audit` ve `minimal` modlarını sunar. Sohbet seçilen modun talimatını sistem mesajı olarak modele iletir; yeni modlar açıkça katalogda kayıtlı olmalıdır. Bu talimatlar bu proje için özgün yazılmıştır; üçüncü taraf beceri metinleri kopyalanmaz.

Her chat isteği yanıt modelinden önce yerel `intent_router` ile `answer`, `plan`, `research`, `learn` veya `action_request` olarak sınıflandırılır. Örtüşmede öncelik: gerçek eylem isteği, dış kaynak araştırması, açıkça istenen hafıza kaydı, yürütmesiz plan, sonra doğrudan yanıt. Intent, güven puanı ve sonraki adım önerisi sohbet yanıtıyla birlikte gösterilir. Sınıflandırmanın kendisi eylem veya hafıza yazması başlatmaz. Qt'nin **Ajan** modu ayrı, onaylı araç yürütücüsünü kullanır; **Sor/Plan** otomatik araçları ve hafıza önerisi yazmasını kapatır. İstemciden zaten araç sonucu geldiyse backend aynı aracı tekrar çağırmaz. `mode` belirtmeyen eski API istemcilerinin mevcut davranışı korunur.

Intent sınıflandırmasını 27 örnekli, örtüşen/olumsuz istekleri de içeren sabit benchmark ile değerlendirmek için API container'ında şunu çalıştır:

```powershell
docker compose exec -T api python -m app.intent_eval --model qwen2.5-coder:7b
```

JSON raporu accuracy, macro-F1, Brier score, expected calibration error, confidence bantları, sınıf karışıklık matrisi ve örnek bazlı sonuçları içerir. `--limit N` hızlı smoke test, `--output /data/intent-eval/report.json` rapor saklama, `--min-accuracy 0.8` eşik kontrolü içindir. Set küçük ve el yapımıdır; metrikler tanısaldır, istatistiksel güvence değildir. Runner yalnızca `ollama` ve `intent_router` eklentilerini kaydeder; hafızaya yazma ve araç çalıştırma yapmaz.

Kurulu yerel modelleri konu bazında karşılaştırmak ve embedding sağlığını ayrı ölçmek için:

```powershell
docker compose exec -T api python -m app.model_eval --output /data/model-capability-report.json --routing-output /workspace/model-area-priorities.json
```

Evaluator modelleri sırayla ve süre sınırlarıyla sınar; buluta gitmez, model indirmez. Embedding modeli sohbet sıralamasına alınmaz. Kod önerileri çalıştırılmaz; AST ve sabit ölçütlerle incelenir. Rapor küçük deterministik fixture'lara göre sıralamadır; genel zekâ veya kapsamlı kod kalitesi garantisi değildir. `--model <model-adi>` tek model, `--limit N` alan başına ilk N örnek içindir. Routing çıktısı `/workspace/model-area-priorities.json` yolundan okunur. Otomatik seçim intent, yanıt, planlama, kaynaklı çıkarım, öğrenme ve kod değişikliği alanlarını kullanır; açık model seçimi korunur. Ölçülmüş profiller varsa kurulu olmayan, digest'i değişen veya eşik altında kalan adaylar atlanır; uygun aday yoksa sessizce başka modele düşmek yerine açık hata verilir. `MODEL_ROUTING_PREFERENCES` dosya yolunu belirler.

**7 Kasım 2026 gerçek yerel ölçümü:** beş sohbet modelinde 140 kontrol ve Nomic'te iki embedding partisi tamamlandı; timeout olmadı. [Ayrıntılı rapor](data/model-evaluations/2026-11-07-local-all.json) ve [etkin öncelikler](model-area-priorities.json) aynı köktedir. Skorlar aşağıdaki küçük görev setlerine aittir:

| Model | Niyet | Yanıt | Plan | Kaynak | Öğrenme | Kod |
|---|---:|---:|---:|---:|---:|---:|
| qwen2.5-coder:7b | 1 | 1 | 1 | 1 | 1 | 0,667 |
| deepseek-coder:6.7b | 0,6 | 0,667 | 0,667 | 0,667 | 0,667 | 1 |
| gemma:7b | 0,4 | 0,333 | 1 | 1 | 0,667 | 0,667 |
| qwen3.8:latest | 1 | 1 | 1 | 1 | 1 | 0,667 |
| qwen3.6:latest | 1 | 0,667 | 1 | 1 | 1 | 1 |

Nomic 768 boyutlu embedding üretti. Skor ve ölçülen gecikme sıralaması sonucunda **niyet/yanıt/plan/kaynak için Qwen 2.5**, **öğrenme/kod için Qwen 3.6** öne alındı. Soğuk model yüklemesi 43,5 saniyeye ulaşabildi. Çoklu ajan rol kataloğu alan ve kullanılabilir model önceliklerini döndürür; planlayıcı/bağlam/sentez Qwen 2.5, geliştirici/inceleyici Qwen 3.6 önceliğini kullanır. Bu model karşılaştırması tek başına beş aşamalı akış kanıtı değildir; sonraki gerçek uçtan uca deneme yukarıdaki çoklu ajan bölümünde ayrıca kaydedilmiştir.

2 Kasım tarihli eski host ölçümü [CAPABILITY_COMPARISON.md](CAPABILITY_COMPARISON.md) içinde tarihsel kayıttır; etkin Docker sıralaması yukarıdaki yeni ölçümdür.

## Sonraki entegrasyonlar

Eski LocalQwenAgent ile AI-Next arasındaki tam karşılaştırma ve öncelik sırası [CAPABILITY_COMPARISON.md](CAPABILITY_COMPARISON.md) içindedir. Yakın sıradaki işler media job consumer’ları, embedding tabanlı anlamsal bellek araması, runtime profilleri, rich media preview ve portable Windows pakettir. GitHub README araştırması ve onaylı research-memory kaydı uygulanmıştır; repository code analysis henüz yoktur.

## Test

```powershell
.\.venv\Scripts\python.exe .\backend\run_tests.py
# Yalnızca seçili testler:
.\.venv\Scripts\python.exe .\backend\run_tests.py --timeout 120 -- -q .\backend\tests\test_multi_agent.py
# Qt bağımlılıklarıyla masaüstü regresyonları:
.\.venv\Scripts\python.exe .\backend\run_tests.py --timeout 120 -- -q .\desktop\tests .\backend\tests\test_desktop_api.py .\backend\tests\test_test_runner.py
# Backend ve Qt birlikte:
$env:QT_QPA_PLATFORM='offscreen'
.\.venv\Scripts\python.exe .\backend\run_tests.py -- .\backend\tests .\desktop\tests -q
Remove-Item Env:\QT_QPA_PLATFORM
```

Çalıştırıcı önce 10 sn ile sınırlı bir `asyncio` açılış kontrolü, ardından varsayılan 300 sn toplam süre sınırıyla pytest çalıştırır. Takılan alt süreç durdurulur, zaman aşımı **124** çıkış koduyla bildirilir; pytest hata kodları korunur. `--preflight-timeout` ve `--timeout` ile süreler değiştirilebilir. Geçici dosyalar/önbellek proje içindeki `_tmp` altında kalır. Pytest ve ilgili backend/desktop bağımlılıkları proje `.venv` ortamında kurulu olmalıdır; çalıştırıcı paket kurmaz.

Windows'ta stack trace `socket._fallback_socketpair → accept` gösteriyorsa test gövdesinden önce yerel loopback bağlantısı takılmıştır. Bu durum bekleme süresini büyüterek çözülmez; çalışma ortamının sandbox/firewall loopback izinleri düzeltilmelidir. Çalıştırıcı izin değiştirmez ve başarısız ön kontrolden sonra testleri geçti saymaz.

Birleşik sohbetin önceki regresyonu: **316 Python/Qt testi ve 265 alt test** geçti; değişen sohbet/routing kapsamındaki Ruff kontrolleri temiz. Önceki birleştirme kontrolünde **12 Node testi** ve beş MCP sunucusunda **297 araç keşfi** de başarılıydı. Yeni canlı ek kontrolü metin, Dockerfile, DOCX, PNG OCR, ZIP envanteri, SQLite şeması ve onaylı statik ELF analizini doğruladı; yerel konuşma modeli bulunmadığı açıkça raporlandı. Gerçek dosya bağlamından beklenen işaret, gerçek tokenlar ve kaydedilmiş iki mesaj doğrulandı. Pylance istekleri zaman aşımına uğradığından editör tanı temizliği iddia edilmiyor; doğrulama çalıştırılmış test/build ve canlı sonuçlara dayanır. Önceden mevcut genel lint bulguları ve isteğe bağlı harici hesap/WSL entegrasyonları ayrı kapsamdadır.

Birleşik sohbet dağıtımının uçtan uca kontrolü de geçti: ajan gerçek `ollama.models` çağrısını yaptı ve yanıt modelinde özetledi; aynı çağrı tekrar yürütülmedi. Yazmanın reddedilmesi, diff/hash ile onaylı yazılması ve geri alınması doğrulandı. Gerçek ilk token sonrasında kesilen akış oturuma yarım tur kaydetmedi. Native Windows Qt'de beş sohbet profili, 107 form, gerçek gönderim, ekrandaki `4` yanıtı ve iki kayıtlı mesaj kontrol edildi; güncel normal uygulama açık bırakıldı. Yalnız test oturumları/geçici dosyaları temizlendi. Altı modelin ad/digest/boyut değerleri, mevcut named volume'lar, şifreleme anahtarı ve 603/776 eski hafıza kayıt/parça sayıları yeniden doğrulandı.

**Windows host sonrası son doğrulama: 337 Python/Qt testi + 356 alt test, 12 Node testi; değişen kapsamda Ruff, compileall ve diff kontrolü başarılı.** Gerçek Windows envanterleri, ayrı HKCU test değerlerinde tür/yazma/silme/geri alma ve boş anahtar temizliği geçti. Native Qt'de 131 form, gerçek USB sonucu, varsayılan Vazgeç/onay pencereleri, reddedilen yazmanın etkisizliği, onaylı yazma ve CRLF'yi aynen geri alma, veri göndermeyen yerel TCP bağlantısı doğrulandı. Genel DNS/TCP 443 bağlantısı da başarılıydı. Gerçek ajan `windows_host.devices` seçip çalıştırdı; yinelenen çağrıyı engelledi, 92 token ve iki kayıtlı mesaj üretti. Test oturumları temizlendi. Normal başlatmada test ortamının maskelediği backend import sırası düzeltildi ve ayrı temiz süreç regresyonuyla korundu. API/web güncellendi; HTTP host değişikliğini 503 ile reddetti, web Qt gerekliliğini gösterdi. Altı model/veri/anahtar korunumu tekrar geçti; normal Qt yanıt verir durumda açık bırakıldı. **Gerçek aygıt devre dışı bırakma, sürücü kurma/kaldırma veya keyfi kayıt defteri onarımı test amacıyla yapılmadı.**