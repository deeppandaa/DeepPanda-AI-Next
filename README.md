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

Docker Compose kurulu makinede bu dizinde:

```powershell
docker compose up --build -d
```

Ardından Qwen modelini açıkça indir:

```powershell
docker compose exec ollama ollama pull qwen2.5-coder:7b
```

Model indirme çok sayıda GB yer kullanır ve yalnızca bu komutla başlar. Ollama aynı anda tek model yüklü tutar. Varsayılan yerel beyin **Qwen 2.5 Coder 7B**'dir (`OLLAMA_MODEL`, `model-area-priorities.json`); Qwen 3.6 artık kullanılmaz. Tüm alanları tek bir Qwen modeline sabitlemek için `.env` içinde `DEEPPANDA_BRAIN_MODEL=qwen2.5-coder:7b` verilebilir. API health kontrolü `http://127.0.0.1:8787/api/health` adresindedir; web arayüzü yalnızca istenirse açılır (aşağıdaki "Servis profilleri" bölümüne bakın).

## Servis profilleri

Hazır ayarlar `.env.example` içindedir; gizli değerler için `Copy-Item .env.example .env` ile kopyalayıp `.env` dosyasını düzenle (commit edilmez). Compose proje adı `deeppanda-ai-next` olarak sabittir, böylece mevcut `ai_data`, `ollama_data`, `qdrant_data`, `redis_data` volume'ları korunur.

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

Script ilk çalıştırmada proje içinde `.venv` oluşturur, `desktop/requirements.txt` (PySide6, httpx, mcp) paketlerini kurar ve geçici/önbellek dosyalarını proje klasöründe tutar. Ayarlar `desktop/settings.ini` dosyasına yazılır (gitignored).

- **Sohbet:** oturum listesi, model seçimi (otomatik, yerel Qwen/Ollama modelleri, OpenJarvis, FreeLLMAPI, bulut sağlayıcıları), iş akışı modu, Markdown yanıtlar, "Başka yapay zekâya sor", bulut anahtarı istenirse tek pencereden kaydetme. `Ctrl+Enter` gönderir, `Ctrl+N` yeni sohbet açar.
- **Araçlar:** web arayüzündeki tüm araç formları (`desktop/tool_forms.json`, `frontend/tools.js` dosyasından `node desktop/sync_tool_forms.mjs` ile üretilir) ve hafıza, belgeler, görevler, çalışma alanı, araştırma, repo izleme, bulut, beceriler, OpenJarvis, Build Your Own X, graphify formları; aramalı ağaç ve "Gelişmiş" bölümünde herhangi bir eklenti eylemini JSON ile çalıştırma.
- **İşler:** arka plan işleri, durum filtresi, ayrıntı, iptal, yeniden deneme ve takılı işleri kurtarma.
- **Veritabanı:** veritabanı/tablo gezgini, salt-okunur SQL editörü, bütünlük kontrolü, yedek ve gerekirse SQL yöneticisini başlatıp açma.
- **MCP / Copilot:** VS Code/Copilot `mcp.json` ve proje `mcp-servers.json` sunucularını listeler, araçlarını getirir ve bu bilgisayarda çalıştırır. `GITHUB_TOKEN` yoksa `gh auth token` yalnızca istemci süreci için alınır.
- **Sistem:** API, Ollama/Qwen 2.5, OpenJarvis, graphify, SQL yöneticisi ve web durumu; yığını başlatma, konteyner durumu, API günlükleri, Qwen 2.5 indirme, API'yi yeniden derleme, web arayüzünü açma ve tanılama taraması.

Onay gerektiren işlemler yalnızca bir kez "Evet, devam et / Vazgeç" penceresiyle sorulur; salt-okunur işlemler soru sormaz.

## Entegrasyonlar

- **GitHub Copilot MCP araçları (`mcp`):** `mcp-servers.json` içindeki `github` (`https://api.githubcopilot.com/mcp/`, `GITHUB_TOKEN`) ve `graphify` sunucuları. API'de `servers`/`tools` salt-okunur, `call` onay ister. Qt istemcisi ayrıca VS Code'daki `rea`, `kaggle` ve diğer kullanıcı MCP sunucularını kullanır.
- **REA:** VS Code `mcp.json` içindeki `rea` (stdio, `npx rea-agents mcp`) sunucusu MCP sayfasından çalıştırılır; tersine mühendislik araçları bu bilgisayarda yürür.
- **replica-skill ve SKILL.md becerileri (`skills`):** `/data/skills` ve `/workspace/skills` altındaki `SKILL.md` paketlerini listeler, gösterir ve yerel Qwen ile uygular. `install` onaylı olarak GitHub arşivini indirir (en fazla 50 MB); önerilen kaynaklar `Jakeschincariol/replica-skill` ve `safishamsi/graphify`.
- **OpenJarvis (`openjarvis`):** OpenAI uyumlu `jarvis serve` sunucusuna bağlanır. WSL Ubuntu içinde `jarvis serve --host 0.0.0.0 --port 8010 -e ollama -m qwen2.5-coder:7b`; adres `OPENJARVIS_BASE_URL` (varsayılan `http://host.docker.internal:8010/v1`).
- **Build Your Own X (`byox`):** `codecrafters-io/build-your-own-x` kataloğunu indirir, kategori/arama sunar ve seçilen eğitim için yerel Qwen ile adım planı çıkarır (`BYOX_SOURCE_URL`).
- **graphify (`graphify`):** `pip install graphifyy`, `graphify install --platform copilot`, ardından Copilot CLI'da `/graphify .` ile `graphify-out/graph.json` üretilir. Eklenti özet, sorgu, komşular, yol ve rapor eylemlerini salt-okunur sunar (`GRAPHIFY_GRAPH`).
- **SQL (`database`):** yukarıdaki "Servis profilleri" bölümüne bakın.

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

Arayüz açıldığında `diagnostics` eklentisi mount edilen AI-Next workspace'ini salt okunur tarar; `Hata tara` ile yeniden çalıştırılabilir. Python AST/Ruff ve JSON/TOML/YAML sözdizimi denetlenir. `.env`, model/runtime paketleri, sanal ortamlar, bağımlılık, build/cache dizinleri ve sembolik bağlantılar atlanır. Sınırlar: dosya başına 1 MB, toplam 100 MB, 5000 dosya ve 120 saniye. Rapor yalnızca bulgu, yol ve satır numarası döndürür; kodu değiştirmez, komut çalıştırmaz veya ağa çıkmaz.

## Eklenti ekleme

Her eklenti `PluginManifest` ve `invoke(action, payload)` sözleşmesini uygular. Eklenti kaydı `create_app` içindeki gateway kurulumunda yapılır; route'lar ve diğer eklentiler doğrudan birbirini çağırmaz. Yeni eylemler gateway üzerinden geçmeli ve ilerideki onay/izin politikasına burada bağlanmalıdır.

## Workspace araçları

`workspace` plugin'i `list`, `read`, `preview_write`, `write`, `rollback` ve `run` eylemlerini verir. Mutlak/kaçış yolları, symlink'ler, `.env`, sanal ortamlar, `node_modules`, model/runtime ve build/cache klasörleri dışarıda kalır. `write`, `rollback` ve `run` payload'ı açık `approved: true` olmadan reddedilir. Var olan dosya değiştirilmeden önce `/data/workspace-backups` altında yedeklenir; komutlar `shell=False`, PATH allowlist'i ve timeout ile çalışır. Analiz eklentileri dosya değiştirmez.

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

Her chat isteği yanıt modelinden önce yerel `intent_router` ile `answer`, `plan`, `research`, `learn` veya `action_request` olarak sınıflandırılır. Örtüşmede öncelik: gerçek eylem isteği, dış kaynak araştırması, açıkça istenen hafıza kaydı, yürütmesiz plan, sonra doğrudan yanıt. Intent, güven puanı ve sonraki adım önerisi sohbet yanıtıyla birlikte gösterilir. Router kullanılamazsa normal sohbet devam eder. Sınıflandırma ek bir yerel model çağrısıdır; araştırma, dosya değişikliği, komut çalıştırma veya hafızaya yazma başlatmaz. `plan` ve `action_request` sonuçlarında kullanıcı isteği mevcut Görevler taslak formuna aktarabilir; taslak ayrıca üretilir ve kullanıcı kaydetmeden kalıcı olmaz. `learn` sonucu yalnızca düzenlenebilir not taslağıdır; kullanıcı checkbox ve ayrı onayla kaydedebilir. Araştırma ve diğer eylemler otomatik dispatch edilmez.

Intent sınıflandırmasını 27 örnekli, örtüşen/olumsuz istekleri de içeren sabit benchmark ile değerlendirmek için API container'ında şunu çalıştır:

```powershell
docker compose exec -T api python -m app.intent_eval --model qwen2.5-coder:7b
```

JSON raporu accuracy, macro-F1, Brier score, expected calibration error, confidence bantları, sınıf karışıklık matrisi ve örnek bazlı sonuçları içerir. `--limit N` hızlı smoke test, `--output /data/intent-eval/report.json` rapor saklama, `--min-accuracy 0.8` eşik kontrolü içindir. Set küçük ve el yapımıdır; metrikler tanısaldır, istatistiksel güvence değildir. Runner yalnızca `ollama` ve `intent_router` eklentilerini kaydeder; hafızaya yazma ve araç çalıştırma yapmaz.

Kurulu tüm local chat modellerini yanıt, planning, kaynaklı çıkarım, learning önerisi ve güvenli code-patch önerisi alanlarında karşılaştırmak için:

```powershell
docker compose exec -T api python -m app.model_eval --output /data/model-capability-report.json --routing-output /workspace/model-area-priorities.json
```

Evaluator embedding/cloud modellerini atlar; task draft endpoint'ini ve `TaskAssistantPlugin`'in yazmayan proposal yolunu kullanır. Kod önerileri çalıştırılmaz; yalnızca kaynak aralığı, Python syntax ve sabit kavram ölçütleri kontrol edilir. Rapor küçük deterministik fixture'lara göre sıralamadır; genel zekâ/safety veya bağımsız model kalitesi garantisi değildir. `--model <model-adi>` tek model, `--limit N` tüm alanlarda ilk N örnek için smoke test içindir. Rapor `/data` içinde kalır; routing çıktısı Compose API tarafından `/workspace/model-area-priorities.json` yolundan okunur ve yeniden benchmark edildiğinde güncellenir. Otomatik seçim intent için `intent`, chat cevabı için sınıflandırılan alana, görev planı için `planning`, patch önerisi için `code_change` listesini kullanır; kullanıcı model seçerse bu seçim önceliklidir. Kurulu olmayan adaylar atlanıp listedeki sonraki modele geçilir; liste eşleşmezse Ollama varsayılanı kullanılır. `MODEL_ROUTING_PREFERENCES` ile dosya yolu değiştirilebilir.

2026-11-02 ölçümü host Ollama'da dört chat modelini karşılaştırdı; sonuçlar ve seçili alan öncelikleri [CAPABILITY_COMPARISON.md](CAPABILITY_COMPARISON.md) içinde. Compose Ollama kendi `ollama_data` volume'unu kullanır; host'ta indirilen modeller bu volume'da otomatik görünmez. Aynı önceliklerin container'da kullanılması için tercih edilen modellerin Compose Ollama kataloğunda kurulu olması gerekir; bulunmayanlar otomatik olarak atlanır.

## Sonraki entegrasyonlar

Eski LocalQwenAgent ile AI-Next arasındaki tam karşılaştırma ve öncelik sırası [CAPABILITY_COMPARISON.md](CAPABILITY_COMPARISON.md) içindedir. Yakın sıradaki işler media job consumer’ları, embedding tabanlı anlamsal bellek araması, runtime profilleri, rich media preview ve portable Windows pakettir. GitHub README araştırması ve onaylı research-memory kaydı uygulanmıştır; repository code analysis henüz yoktur.

## Test

```powershell
Push-Location backend
python -m pip install pytest
python -m pytest -q
Pop-Location
```

`test_integrations.py` pytest kullanır; diğer testler `unittest` uyumludur.