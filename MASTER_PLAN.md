# DeepPanda AI Next — Ana Plan ve Durum

Son güncelleme: 10 Kasım 2026. Bu dosya kaybolan `MASTER_PLAN.md` dosyasının yerine yazıldı. Neyin yapıldığını, nerede kalındığını ve son kontrolün nasıl yapılacağını anlatır.

## 1. Hedef

- Kurtarılan DeepPanda AI Next projesini `F:\DeepPanda Agentic Al` altında yeniden kurmak. Ölçümlü yerel yönlendirme: genel yanıt/plan/kaynak Qwen 2.5; kod/öğrenme Qwen 3.6.
- Temel eklentiler: GitHub Copilot MCP araçları, REA, replica-skill, OpenJarvis, Build Your Own X, graphify.
- Docker yığını: API, Ollama, FreeLLMAPI, Redis, Qdrant, SQL yöneticisi. Web arayüzü yalnızca istenirse açılır.
- Günlük kullanım için **Qt kontrol merkezi**. Sade olacak, web arayüzünün tüm özelliklerini içerecek ve onay pencereleri en aza inecek.
- Projeye ait çalışma zamanları, paketler ve önbellekler proje kökünde kalacak. Windows, sürücü, Docker/WSL ve kullanıcı hesabı gibi ortak altyapı taşınmaz; işletim sisteminin kendi kayıt/önbellek yazmaları için mutlak sıfır C: yazması garantisi verilmez.

## 2. Konumlar

| Ne | Nerede |
|---|---|
| Proje (git deposu) | `F:\DeepPanda Agentic Al` |
| Python ortamı, pip önbelleği, geçici dosyalar | `F:\DeepPanda Agentic Al\.venv`, `_tmp` (gitignored) |
| Sistem Python'undan bağımsız yerel Python | `runtimes\python-3.12.10\tools\python.exe`; `setup-python.ps1` ve `tools\python-runtime.json` |
| Qt istemci ayarları | `F:\DeepPanda Agentic Al\desktop\settings.ini` (gitignored) |
| Taşınabilir Node, araç önbelleği/profilleri, stdio raporu | `F:\DeepPanda Agentic Al\.tools` (gitignored) |
| Sabitlenmiş araç paketleri / bağımlılıklar | `tools/package.json`, `tools/package-lock.json` / `tools/node_modules` (kurulu; bağımlılıklar gitignored) |
| API host bağlantıları | Proje kökü → `/workspace`, `models` → `/models`, `runtimes` → `/runtimes` |
| Gizli ortam dosyaları | Kök `.env`, `.ai-next-cloud.env`, `.freellmapi.env` (gitignored; mevcut anahtar korundu) |
| Geçiş yedekleri ve geri dönüş bilgileri | `data\backups\consolidation-20261107-2150` (gitignored; hassas yapılandırma içerir) |
| Docker Desktop veri diski | `F:\DeepPanda-Docker-Data`; VM diskleri doğrulandı, diğer projelerle ortak olduğundan taşınmadı |
| Tamamlanan ayrı test ortamı | `_tmp\live-check-20261107`; servisleri ve Qt önizlemesi kapatıldı, `18787`/`18788` artık kullanılmıyor |
| Korunan eski klasörler | `F:\DeepPanda-Proje` (silinmedi; aşağıdaki "Silme" bölümüne bakın) |

## 3. Yapılanlar

| # | İş | Durum |
|---|---|---|
| 1 | Docker sohbet özeti kurtarıldı, proje `F:\DeepPanda Agentic Al` altına alındı, `git init` ile başlangıç commit'i (`09e228d`) atıldı | ✅ |
| 2 | Genel varsayılan Qwen 2.5 Coder 7B; altı kurulu model korunarak ölçüldü, kod/öğrenme önceliği Qwen 3.6 oldu | ✅ |
| 3 | `requires_local_tools` yönlendirmesi (yerel veri gerekiyorsa salt-okunur araç döngüsü) kurtarılan kodda mevcut ve testli | ✅ |
| 4 | Yeni eklentiler: `mcp` (GitHub Copilot MCP köprüsü), `skills` (replica-skill / SKILL.md), `openjarvis`, `byox`, `graphify`, `database` (SQL); ortak hata eşlemesi `integration_errors` (403/404/503) | ✅ |
| 5 | Backend ve Qt son doğrulama: **337 test + 356 alt test**, **12 Node testi** geçti | ✅ |
| 6 | `docker-compose.yml`: sabit proje adı (`deeppanda-ai-next`, mevcut volume'lar korunur), API healthcheck, Ollama `127.0.0.1:11435`, `web` ve `manager` profilleri, `db-manager` (sqlite-web, varsayılan salt-okunur, isteğe bağlı parola), tüm portlar `.env` ile ayarlanabilir; `docker compose config` doğrulandı | ✅ |
| 7 | `.env.example` (tüm ayarlar Türkçe açıklamalı), `mcp-servers.json` (github + graphify), `docker-compose.models.yml` (mevcut model klasörünü bağlama) | ✅ |
| 8 | **Qt kontrol merkezi** (`desktop/`, `run-desktop.ps1`): Sohbet, Araçlar (131 form), Gelişmiş araçlar, İşler, Veritabanı, MCP / Copilot, Sistem, Ayarlar | ✅ |
| 9 | 107 form ve 8 Qt sayfası hazır; native Windows Qt, gerçek kök ayarları, canlı API/model listesi ve mevcut oturumlar doğrulandı; test webinden ve taşınan canlı API'den Qwen yanıtı alındı | ✅ temel canlı akış / isteğe bağlı entegrasyonlar ayrı kapsam |
| 10 | README: servis profilleri, Qt kontrol merkezi, entegrasyonlar, test komutu | ✅ |
| 11 | Canlı Docker yığınını yeni klasöre taşıma ve API/web imajlarını yeniden derleme | ✅ yedi servis tek kökten çalışıyor; volume, şifreleme anahtarı, altı model ve eski hafıza doğrulandı |
| 12 | `F:\DeepPanda-Proje` silme | Kapsam dışı: geri dönüş için korundu; silme ayrı açık onay gerektirir |
| 13 | Yerel çoklu ajan: planlayıcı → bağlam araştırmacısı → geliştirici → test/inceleyici → sentezleyici | ✅ kod/test eklendi ve test paketi geçti; canlı model testi bekliyor |
| 14 | Gemini, Kimi, GPT, Claude ve ek bulut sağlayıcıları; açık seçim ve anahtar yönetimi | ✅ `cloud_providers` ve Qt sağlayıcı/danışma formları mevcut |
| 15 | Redis tabanlı iş kuyruğuna geçiş | ⏳ araştırma/taşıma kararı gerekir; mevcut SQLite `jobs.db` dayanıklılığı korunuyor |
| 16 | Projeyi D:'ye taşıma | ⏳ açık kullanıcı onayı ve F:'de doğrulanmış yedek gerekir |
| 17 | Süre sınırlı test çalıştırıcısı: asyncio ön kontrolü, toplam pytest süresi, açık hata ve 124 zaman aşımı çıkışı | ✅ gerçek takılma 3,11 sn'de sonlandırıldı |
| 18 | Qt/web uzun işlem süreleri: çoklu ajan 3660 sn, model indirme 7260 sn; bağlantı/yanıt hataları ayrıldı; otomatik tekrar yok | ✅ sözleşme testleri, test imajı ve `nginx -t` geçti; uzun süreli uçtan uca çağrı ayrıca gerekli |
| 19 | Resmî kaynaklardan araştırılmış 15 araçlık gelişmiş katalog: arama, filtre, gereksinim, izin sınırı, kaynak ve ilgili ekrana geçiş | ✅ / gerçek yerel kurulum durumu bölüm 11'de |
| 20 | F: üzerinde SHA-256 doğrulanmış taşınabilir Node 24.22.2; beş MCP paket sürümü ve lockfile | ✅ |
| 21 | Beş yerel MCP: sandbox güncellemesinden sonra yeniden kuruldu; 192 paket, 297 araç, `-VerifyOnly` çıkış 0, `installation_valid=true` | ✅ stdio keşfi / tarayıcı-native görevleri ayrıca test edilecek |
| 22 | Qt Sistem'de onaylı yerel araç kur/doğrula düğmeleri, ayrı host MCP kaydı, başarısız kurulumun yayımlanmaması | ✅ kod/test hazır |
| 23 | Kök altında toplanan gizli ortam dosyaları, yedekler ve runtime dizinlerini workspace/tarama araçlarından dışlama | ✅ önce hata üretildi; regresyon ve dağıtılmış API reddetme kontrolleri geçti |
| 24 | SQL yöneticisi | ✅ `127.0.0.1:8789`, mevcut altı SQLite dosyası, gerçek süreçte `-r` salt-okunur bayrağı doğrulandı |
| 25 | Altı modelin gerçek yerel ölçümü, sağlıklı/digest uyumlu konu sıralaması, çoklu ajan rol öncelikleri | ✅ 140 sohbet kontrolü + iki embedding partisi; yeni indirme/bulut çağrısı yok |
| 26 | Özgün VS Code benzeri Qt sohbeti: modlar, ekler, araç/MCP çekmecesi, token akışı, durdurma, diff/onay/geri alma | ✅ regresyonlar geçti; kapsam ve sınırlar README'de |
| 27 | 24 Windows host aracı: proje dışı dosya, USB/PnP/COM/DCOM, sürücü, hedefli kayıt değeri ve DNS/TCP; yerel Qt yürütmesi, önizleme/onay, yedek/geri alma | ✅ 337 test, native Qt ve gerçek ajan doğrulandı; gerçek donanım değişiklikleri test için çalıştırılmaz |

## 4. Mimari özeti

- **API** (FastAPI, `127.0.0.1:8787`): sunucu özellikleri `PluginGateway` üzerinden çalışır. Onay gerektiren eylemler `approved=true` olmadan 403 döner. `windows_host` burada yalnız erişim durumu bildirir; Windows işlemlerini reddeder.
- **Eklentiler (40):** hafıza, belgeler, bilgi, görevler, işler, çalışma alanı, kod grafı, tanılama, araştırma, tarayıcı, binary analiz, repo izleme, bulut sağlayıcıları, FreeLLMAPI, Ollama, oturumlar, iş akışları, lisans, rapor, ses, OCR, medya, değerlendirme, Instagram, prompt kitaplığı ve eklenen `mcp`, `skills`, `openjarvis`, `byox`, `graphify`, `database`, `multi_agent`, `windows_host`.
- **Qt istemcisi** sunucu özellikleri için HTTP kullanır. Windows host araçlarını ve MCP araçlarını doğrudan bu bilgisayarda çalıştırır. Yeni ayrıcalıklı HTTP köprüsü yoktur. Docker komutlarını proje klasöründe yürütür.
- **Onay akışı:** otomatik ajan yalnızca açık salt-okunur API listesini sormadan çalıştırır. Diğer işlemler ve bütün MCP çağrıları onay ister; workspace yazması diff ve hash korumalıdır. Mevcut manuel formların politikaları korunur.
- **Çoklu ajan sınırı:** beş aşama yalnızca kurulu yerel Ollama modelini kullanır. Rol talimatları hiçbir aşamaya araç, ağ veya dosya yetkisi vermez; bir aşama başarısızsa sonraki aşamalar çalışmaz.

## 5. Varsayımlar

- "SQL ve manager" şu anlama alındı: `/data` altındaki SQLite veritabanları (`memory.db`, `tasks.db`, `jobs.db`, ...) ve web tabanlı **sqlite-web** yöneticisi (`127.0.0.1:8789`). Portainer veya Docker MCP Toolkit kastedildiyse ayrıca eklenebilir.
- API'ye `REDIS_URL` veriliyor, ancak backend henüz Redis kullanmıyor (iş kuyruğu SQLite `jobs.db`). Redis'e geçiş ayrı tasarım ve geçiş işi olarak kaldı; mevcut iş verisi taşınmadı.
- OpenJarvis WSL Ubuntu'da çalışır ve Docker'dan `host.docker.internal:8010` adresiyle erişilir. WSL→Windows erişimi henüz doğrulanmadı.
- GitHub Copilot MCP için `GITHUB_TOKEN` gerekir. Qt istemcisi token yoksa `gh auth token` ile yalnızca kendi süreci için alır.

## 6. Çözülen engeller ve kalan sınırlar

- **Docker erişimi ve Compose sahipliği düzeltildi.** API, web, FreeLLMAPI, Redis, Qdrant, Ollama ve SQL yöneticisi `F:\DeepPanda Agentic Al\docker-compose.yml` üzerinden çalışıyor. Tek kökten tekrar `up --wait` çağrısı mevcut yedi servisi yeniden oluşturmadan başarılı oldu.
- **Etkin uygulama host yolları birleştirildi.** API artık eski proje yerine yeni kökü, `models` ve `runtimes` alt klasörlerini bağlıyor. Boş eski model/runtime dizinlerine bağımlılık kalmadı. Modeller ve veritabanları aynı beş named volume'dadır; diğer projeleri de içeren `F:\DeepPanda-Docker-Data` ortak altyapı istisnasıdır.
- **Korumalı geçiş tamamlandı.** Dört veri volume'u durdurulmuş servislerden yedeklendi ve SHA-256 doğrulandı; 51 GB model volume'u kopyalanmadan korundu. Eski API/Ollama konteynerleri durdurulmuş geri dönüş kopyaları olarak saklandı. Diğer eski klasörler silinmedi (bölüm 13).
- **FreeLLMAPI şifreleme anahtarı ve özgün API ayarları korundu.** Yalnız Qwen varsayılanları bilinçli olarak `qwen2.5-coder:7b` yapıldı. Yeni kurulum anahtarı yalnız ayrı test ortamında üretildi; canlı verinin anahtarı değiştirilmedi.
- **Son Python/Qt doğrulaması: 337 test + 356 alt test; 12 Node testi.** Host testleri sahipli geçici dosyalar ve ayrı HKCU test anahtarları kullanıp temizler; gerçek aygıt/sürücü değişiklikleri mock edilir. Önceki birleştirmede 297 araçlık MCP keşfi de başarılıdır.
- **Lint sınırı:** son değişen Python dosyalarında `diagnostics.py` için `I001`; `workspace.py` için `SIM102`, `FURB188`, `TRY004` bulguları HEAD ile aynıdır. İlgisiz exception davranışı değiştirilmedi; tam lint temizliği iddia edilmiyor. Canlı API imajında Ruff yok; tanılama bunu `RUFF-UNAVAILABLE` olarak bildirir, sözdizimi kontrolü ayrı çalışır.
- Pylance aracı çalışma alanı kökü bildirmiyor ve C: genel Python'u gösteriyor; `reportMissingImports` uyarıları bu bağlamda sürüyor. Yorumlayıcı güncelleme aracı başarı bildirse de yeniden sorguda seçim değişmedi. F: üzerindeki `.vscode/settings.json` proje `.venv` ve backend yolunu tanımlar; editör seçimi ayrıca doğrulanmalı. Qt testleri gerçekten F: `.venv` ile geçti; editörün aynı ortamı kullandığı iddia edilmiyor.
- Önceki sandbox kısıtında VS Code kullanıcı `mcp.json` dosyası okunamıyordu. Qt istemcisi böyle bir durumda uyarı gösterip proje sunucularıyla devam eder; bunu tüm MCP araçlarının bağlı olduğu şeklinde yorumlama.
- graphify grafiği henüz üretilmedi (`graphify-out/graph.json` yok). Güncel upstream README Claude Code akışını anlatıyor; önceki `--platform copilot` kurulum önerisi doğrulanmadığı için otomatik kurulum talimatından çıkarıldı.
- Yeni API/web imajları canlıya alındı; `nginx -t`, proxy sağlık kontrolü ve Qwen sohbeti geçti. 3660/7260 saniyelik uzun işlem sınırları yalnız sözleşme testleriyle doğrulandı; beş aşamalı uzun model akışı bu birleştirmenin kapsamı değildir.
- ~~Yerel araç tekrar kurulumunda `tools\node_modules` için sandbox `EPERM`~~ — **çözüldü.** Kullanıcı sohbetin altındaki `Permission` menüsünde terminal sandbox iznini güncelledikten sonra `.\setup-tools.ps1` başarıyla tamamlandı (bkz. bölüm 11).

### Çözülen Docker sohbet izni

Docker erişim engelinin nedeni global VS Code Ayarları değil, **bu sohbetin altındaki `Permission` menüsündeki sohbet-başı terminal sandbox izniydi**. Bu menüden izin güncellendikten sonra `docker version`, container/mount/volume incelemesi ve yerel API sağlık kontrolü başarılı oldu. `C:\Users\emre\.docker` dosya yolu ayarları named pipe erişimini çözmedi; başka sohbetlerde bu izin ayrı seçilebilir. Önce ayrı ortamda test, ardından yedekli canlı geçiş tamamlandı.

## 7. Son kontrol tarifi

Proje klasöründe PowerShell aç (`F:\DeepPanda Agentic Al`).

1. **Ayar dosyaları:** bu makinede `.env`, `.ai-next-cloud.env` ve `.freellmapi.env` hazırdır. Örnek dosyaları üzerlerine kopyalama ve FreeLLMAPI anahtarını yeniden üretme.
2. **Mevcut model konumunu koru:** modeller `deeppanda-ai-next_ollama_data` named volume'unda (`/root/.ollama`, yaklaşık 51 GB); host `models` ve `runtimes` klasörleri boş. Qwen 2.5 Coder 7B kurulu. `down -v` kullanma; host model dizini varmış gibi `.env` ayarı ekleme.
3. **Tamamlanmış yığını tekrar başlat:**
   ```powershell
   docker compose config --quiet
   docker compose --profile web --profile manager up -d --no-build --wait
   docker compose --profile web --profile manager ps
   ```
   Kod değişirse önce `docker compose --profile web build api web` çalıştır, sonra aynı `up` komutunu kullan. API yeniden oluşturulduğunda nginx'in yeni adresi çözmesi için `docker compose restart web` çalıştır. Mevcut volume'lar ve anahtar dosyaları korunur.
4. **Qwen 2.5:** `docker compose exec ollama ollama list`. Model yoksa `docker compose exec ollama ollama pull qwen2.5-coder:7b` çalıştır.
5. **Sağlık:** tarayıcıda veya `curl` ile `http://127.0.0.1:8787/api/health` adresi `{"status":"ok"}` dönmeli.
6. **SQL yöneticisi:** `docker compose --profile manager up -d db-manager` çalıştır, ardından `http://127.0.0.1:8789` adresini aç.
7. **Qt kontrol merkezi:** `.\run-desktop.ps1` çalıştır ve sayfaları sırayla dene:
   - Sohbet: "Merhaba" yaz ve Qwen 2.5 yanıtı gel.
   - Araçlar: Hafıza → Ara.
   - Gelişmiş araçlar: 15 kayıt görünmeli; kategori/yetenek filtresini dene. graphify/replica seçimi ilgili araç formuna, Chrome/Playwright seçimi MCP sayfasına götürmeli. "API'de kayıtlı" ile "MCP'de doğrula" birbirinden ayrıdır.
   - Veritabanı: `memory.db` → `SELECT count(*) FROM memories`.
   - MCP / Copilot: `rea` ve `github` sunucularını seç → Araçları getir.
   - Sistem: Durumu yenile; tüm kartlar yeşil olmalı (OpenJarvis/graphify isteğe bağlı).
8. **OpenJarvis (isteğe bağlı):** WSL Ubuntu'da `jarvis serve --host 0.0.0.0 --port 8010 -e ollama -m qwen2.5-coder:7b` çalıştır. Ardından Qt'de model listesinden "OpenJarvis" seçip bir mesaj gönder.
9. **graphify (isteğe bağlı):** Gelişmiş araçlar → graphify → Resmî kaynak üzerinden kurulu sürümün istemci desteğini ve veri aktarımını doğrula. Graf üretildikten sonra `graphify-out/graph.json` dosyasını Qt → Araçlar → graphify → Özet ile kontrol et. Claude/Copilot uyumluluğunu varsayarak paket kurma.
10. **Web:** bu kurulumda açık; `http://127.0.0.1:8788` adresini kullan. Günlük kullanım için zorunlu değildir.
11. **Süre sınırlı test:** `.\.venv\Scripts\python.exe .\backend\run_tests.py -- backend\tests desktop\tests -q` çalıştır; başsız Qt için `QT_QPA_PLATFORM=offscreen` ayarlanabilir. Ön kontrol 10 sn, pytest 300 sn ile sınırlıdır. 124 çıkışı başarı değildir.

## 8. Silme (onay gerektirir)

Geçiş doğrulandı; aşağıdakiler yine de geri dönüş için korundu. Silme bu işin parçası değildir ve ayrı açık onay gerekir:

- `F:\DeepPanda-Proje\DeepPanda-AI-Next`: kurtarılmış 113 dosya. İçeriği bu projeye alındı; etkin uygulama konteynerleri artık buraya bağlı değil.
- `F:\DeepPanda-Proje\DeepPanda-AI`: boş `models` ve `AI-Runtimes` klasörleri.
- `F:\DeepPanda-Proje\_kurtarma-arsivi.zip`: kurtarma arşivi. İstenirse önce başka yere yedeklenebilir.

Kapsam dışı: `C:\Users\emre\Desktop\DeepPanda-Proje` bir junction değil. Yaklaşık 220 GB'lık ayrı ve gerçek bir klasör (LocalQwenAgent, GEMMA, Tools, yara ...). Bu çalışmada dokunulmadı; F:'ye taşınması ayrı bir iş ve onay gerektirir.

## 9. Sonraki yol haritası

1. **Birleştirme tamamlandı.** Günlük kullanımda kök Compose ve `run-desktop.ps1` kullanılır. Bölüm 13 geçiş kanıtı ve geri dönüş kaynaklarını kaydeder; taşıma adımlarını tekrar çalıştırma.
2. İstenirse `F:\DeepPanda-Proje` ve geri dönüş kaynakları için ayrı temizlik planı yapılabilir; silme için açık onay gerekir.
3. Redis tabanlı kuyruk için SQLite'ın kalıcı iş geçmişi ve kurtarma davranışını koruyan geçiş tasarla, test et ve yedekten sonra uygula. Bu sürümde Redis bağlantısı yapılandırılmış ama kullanılmıyor.
4. OpenJarvis/WSL erişimini ve graphify kurulum/graf üretimini kullanıcının makinesinde doğrula.
5. D:'ye taşıma yalnızca kullanıcı onayıyla ve F:'de SHA-256 doğrulanmış yedekle yapılacak.

## 10. Bu turda eklenen gelişmiş araçlar ve teslim durumu

- **Kod/depo:** GitHub MCP, Git MCP.
- **Analiz:** REA, graphify.
- **Tasarım/öğrenme:** replica-skill, Build Your Own X.
- **Yerel ajanlar:** OpenJarvis, Sequential Thinking MCP.
- **Tarayıcı/test:** Playwright MCP, Chrome DevTools MCP.
- **Araştırma:** Context7, Fetch MCP.
- **Altyapı/veri:** Docker MCP Toolkit, Filesystem MCP, DeepPanda SQL.

Liste ve kaynaklar [README](README.md#gelişmiş-araç-kataloğu) ile [katalog verisinde](desktop/tool_catalog.py) bulunur. Katalog [Qt sayfasına](desktop/page_catalog.py) bağlandı. Sonraki kullanıcı talebiyle beş yerel aracın kurulumuna başlandı (bölüm 11). Git/Fetch MCP'nin güncel SDK 2.x gereksinimi, projenin `mcp<2` bağımlılığıyla aynı ortama kurulmalarını engeller; ayrı F: ortamı gerekir. SQLite referans MCP'si arşivli olduğu için mevcut SQL eklentisi korundu. Chrome istatistik/CrUX seçenekleri ve REA'nın resmî deposu not edildi.

**Teslim durumu:** testten sonra tek köke geçiş ve canlı doğrulama tamamlandı. Yedi servis, Qwen sohbeti/SQLite kaydı, native Qt ve salt-okunur SQL yöneticisi çalışıyor; veri ve şifreleme anahtarı korunuyor (bölüm 13). Çoklu ajanın uzun beş aşamalı akışı, OpenJarvis/WSL, graphify üretimi ve harici hesap entegrasyonları ayrı, isteğe bağlı işlerdir.

## 11. Gerçek yerel araç kurulum turu

1. Sistem Node 20.18.1'in güncel paketlere yetmediği doğrulandı. Resmî Node 24.22.2 Windows x64 ZIP'i F:'ye indirildi; ZIP ve `node.exe` SHA-256 değerleri doğrulandı. Sistem kurulumu değiştirilmedi.
2. İlk `npm install` ile 193 paket F: proje alanına kuruldu. Beş sunucu gerçek stdio bağlantısında araç listeledi: Filesystem **10** (tamamı salt okunur), Sequential Thinking **1**, Playwright **25**, Chrome DevTools **32**, REA **229**. Hepsi `2025-11-25` protokolünü kabul etti; test süreçleri kapatıldı.
3. Tekrar kurulabilirlik testi için kullanılan `npm ci` mevcut yeni bağımlılıkları kaldırdı, sonra sandbox yazma engeline takıldı. Kurulum o anda eksik kaldı; önceki başarı gizlenmeden kaydedildi ve izin olmadan tekrar denenmedi (madde 7'de onarıldı).
4. Kurulum betiği `npm install` kullanacak şekilde düzeltildi. Ortak API yapılandırması korunur; yerel kayıt yalnız bütün protokol testleri geçince `.tools/mcp-servers.json` olarak yayımlanır. Başarısız kurulum sırasında host kaydı kaldırılmış ve rapor `installation_valid=false` olarak kaydedilmişti; madde 7'deki onarımdan sonra durum yeniden geçerlidir.
5. Qt Sistem'e tek onaylı kur/doğrula düğmeleri eklendi. `.tools` çalışma alanı, kod grafı ve tanılama taramalarından dışlandı. Npm kurulum betikleri, tarayıcı indirmeleri ve Chrome telemetrisi kapalı tutuldu.
6. **12 Node testi + 37 Python/Qt testi + 134 alt test geçti.** Takılan stdio çocuğu 200 ms test sınırında yaklaşık 226 ms'de durdu. Eksik kurulumun reddedilmesi, host kaydının kaldırılması, kurulum kilidinin bırakılması ve çağıranın ortam değişkenlerinin geri yüklenmesi gerçek çalıştırmayla doğrulandı. Erken checksum/manifest hatalarında eski başarı raporunun kalmaması ve sayfalı araç keşfi de test edildi. Pylance yeni Python test dosyası ve MCP ekranında sözdizimi hatası bulmadı. Hedefli Ruff kontrolü, `page_mcp.py` içinde HEAD'de de bulunan `TRY004` uyarısı hariç geçti; mevcut JSON hata yakalama davranışı değiştirilmedi.

7. **Sandbox güncellemesinden sonra canlı onarım başarılı.** Npm günlüğü 192 paket kurulduğunu gösteriyor. `.\setup-tools.ps1 -VerifyOnly` bağımsız olarak yeniden çalıştırıldı ve çıkış 0 verdi: Filesystem 10, Sequential Thinking 1, Playwright 25, Chrome DevTools 32, REA 229; toplam **297 araç**, protokol `2025-11-25`. `.tools\mcp-servers.json` varlığı ve rapordaki `installation_valid=true` değeri de ayrıca kontrol edildi. 12 Node testi yeniden geçti. Bu sonuç Docker, tam Python test paketi veya tarayıcı/native motorların gerçek görevleri için başarı anlamına gelmez.

**Sonraki işlem:** Qt'de **MCP / Copilot → Yapılandırmayı yeniden oku** ile yerel sunucuları listele. Beş sunucunun protokol kontrolü tekrar geçti; Filesystem için Python/Qt köprüsü üzerinden gerçek `list_allowed_directories` çağrısı da başarılı. Diğer MCP sunucularının tarayıcı/native görevleri, GitHub/Context7 hesap bağlantıları, ayrı Python Git/Fetch sunucuları, OpenJarvis ve graphify üretimi sonraki işlerdir.

## 12. Taşıma öncesi test ortamı (tamamlandı)

Kullanıcı önce çalıştırıp test etmeyi istedi. Canlı yığını değiştirmeden `deeppanda-verify-5542d1d9` adlı ayrı Compose projesi kuruldu. Aşağıdaki kayıt o aşamaya aittir; geçişten önce test servisleri ve Qt önizlemesi kapatıldı.

- Yapılandırma: `_tmp\live-check-20261107\compose.yml`; yeni API/web imaj etiketleri `verify-5542d1d9`. Mevcut `latest` etiketleri değiştirilmedi.
- API: `http://127.0.0.1:18787`; web: `http://127.0.0.1:18788`. FreeLLMAPI, Qdrant ve Redis ayrı test container'larıdır; host portu açılmaz.
- API verisi `_tmp\live-check-20261107\data` altındadır. Workspace salt-okunur bağlıdır. Model üretimi mevcut Ollama servisini kullanır; model indirme, ağırlık taşıma veya eski veritabanına yazma yapılmadı.
- Qt test başlatıcısı `_tmp\live-check-20261107\preview_desktop.py`; ayar kaydı da aynı test klasörüne gider. Sistem sayfasının proje yolu test Compose klasörüdür; gerçek yığını hedeflemez.
- **Geçen kontroller:** 214 Python/Qt testi + 134 alt test, 12 Node testi, 297 MCP aracı keşfi, gerçek Filesystem MCP çağrısı, API/web derlemesi, `nginx -t`, Redis PONG, Qdrant/FreeLLMAPI HTTP 200, 38 API eklentisi, SQLite bütünlüğü ve salt-okunur SQL/onay sınırları.
- Web arayüzünde Qwen 2.5'e `2 + 2` soruldu, tam `4` yanıtı alındı. İki mesaj SQLite oturumuna kaydedildi ve Qt oturum listesinde görüldü.
- Native Windows Qt platformunda 8 sayfa, 15 katalog kaydı, model listesi ve API bağlantısı doğrulandı (166 font). Offscreen ekran görüntüsündeki kutu karakterler native platformda yok; ilk inline kontrolün metin kodlaması sorunu ASCII-bağımsız durum kontrolüyle giderildi. Ürün kodunda değişiklik gerekmedi.
- API tanılamasında `RUFF-UNAVAILABLE` uyarısı var: imajda Ruff yok, Python sözdizimi tarandı fakat lint taraması yapılmadı. Harici hesap/WSL entegrasyonları ve uzun çoklu ajan görevleri bu temel testin kapsamına dahil değil.

`18787` ve `18788` test portları artık kullanılmıyor. Günlük kullanım gerçek kök ayarlarıyla `run-desktop.ps1` ve `8787`/`8788`/`8789` adresleridir; eski test başlatıcısını kullanma.

## 13. Tamamlanan birleştirme ve geri dönüş

- **Tek etkin uygulama kökü:** `F:\DeepPanda Agentic Al`. Yedi servisin Compose çalışma dizini bu köktür; aktif uygulama bind mount'ları da kökün altındadır. API/web bu kaynaklardan derlendi. Qt'nin kalıcı ayarları aynı kökü ve gerçek API/web/SQL adreslerini kullanır.
- **Depolama istisnası:** `deeppanda-ai-next_{ai_data,freellmapi_data,ollama_data,redis_data,qdrant_data}` volume'ları değişmedi. Altı modelin ad/digest/boyut değerleri birebir korundu. Docker Desktop'ın diğer iş yükleriyle ortak `F:\DeepPanda-Docker-Data` diski taşınmadı.
- **Yedek:** `data\backups\consolidation-20261107-2150`. Dört model dışı volume arşivi ve SHA-256 dosyaları, özgün konteyner/ortam anlık görüntüleri, veritabanı satır sayıları, `verification.json` ve `rollback-compose.json` bulunur. Bu klasör gizli anahtar içerir; gitignored'dur ve paylaşılmamalıdır.
- **Geri dönüş kaynakları:** eski API/Ollama konteynerleri `deeppanda-rollback-20261107-api` ve `deeppanda-rollback-20261107-ollama` olarak durduruldu; restart politikaları `no`. Özgün imajlar `deeppanda-rollback-<servis>:20261107` etiketleriyle tutuldu. Geri dönüş ayrı kontrollü işlem olmalıdır: eski ve yeni yığın aynı anda çalıştırılmaz, canlı volume'ların üzerine körlemesine arşiv açılmaz. Eski klasörler silinmedi.
- **Veri kanıtı:** API yeniden oluşturulduktan sonra SQLite bütünlüğü ve önceki tablo sayıları kontrol edildi; **603 legacy kayıt ve 776 legacy parça** aynen korundu. FreeLLMAPI'nin mevcut şifreleme anahtarı değişmedi; veritabanı bütünlüğü ve eski tablo sayıları da doğrulandı.
- **Canlı kanıt:** API/web proxy/FreeLLMAPI/SQL HTTP kontrolleri, Redis PONG, Qdrant ve `nginx -t` başarılı. SQL yöneticisinin gerçek komut satırında `-r` görüldü. Canlı Qwen sohbeti tam `4` verdi; iki mesaj SQLite'a kaydedildi. Yalnız bu kontrolün oluşturduğu test oturumu temizlendi, kullanıcı oturumları korundu.
- **Dosya sınırları:** `.freellmapi.env`, `.ai-next-cloud.env` ve özel `data`, `runtimes`, `_tmp`, `_arsiv`, `.tools` yolları workspace erişiminden dışlanır; çalışma dizinleri diagnostics/codegraph taramalarından da dışlanır. Örnek ortam dosyaları okunabilir kalır. Başarısız regresyon önce üretildi; düzeltme sonrası hedefli **20 test + 13 alt test** ve canlı HTTP 422 kontrolleri geçti.
- **Birleştirme aşaması testi:** tüm backend/Qt paketinde **215 test + 147 alt test** (12,79 sn). Native Qt gerçek ayarları, canlı API/Qwen kataloğu ve mevcut kullanıcı oturumlarıyla doğrulandı. Ruff'daki dört önceki bulgu bölüm 6'da kayıtlıdır; isteğe bağlı harici entegrasyonlar için başarı iddia edilmez.

Bu makinede salt doğrulamayı tekrar çalıştırmak için `.\.venv\Scripts\python.exe .\_tmp\consolidate-20261107\migrate.py verify` kullanılabilir. Tek seferlik `prepare`, `backup`, `deploy` aşamaları tamamlandı; yeniden çalıştırılmamalıdır.

## 14. Ölçümlü modeller ve birleşik sohbet

- **Kalıcı ölçüm:** `data\model-evaluations\2026-11-07-local-all.json`; etkin seçim `model-area-priorities.json`. Beş sohbet modeli yanıt verdi, Nomic 768 boyutlu embedding üretti. 140 sohbet kontrolü ve iki embedding partisi tamamlandı; bulut çağrısı/model indirme yapılmadı. Alan skorları ve sınırlar README'dedir.
- **Öncelikler:** niyet, yanıt, plan ve kaynak çıkarımı Qwen 2.5; öğrenme ve kod değişikliği Qwen 3.6. Çoklu ajan rol kataloğunun gerçek API yanıtında planlayıcı/bağlam/sentez ile geliştirici/inceleyici öncelikleri doğrulandı. Mevcut modeller ve açık model seçimi korunur; global beyin sabitlemesi kaldırıldı.
- **Yeni API:** `/api/chat/attachments/analyze`, `/api/chat/tool-plan`, `/api/chat/stream`. Ekler geçici/yerel işlenir; plan endpoint'i yalnızca önerir. Yerel akış gerçek Ollama tokenlarıdır. Eski istemcilerin `mode` belirtmeyen çağrıları uyumlu kalır.
- **Qt:** Ajan/Sor/Plan, dosya/klasör seçimi, sürükle-bırak, sohbet içindeki 107 form/MCP çekmecesi, araç izleri, onaylar, diff/hash korumalı yazma, son yazmayı geri alma, durdurma, arama/kopyala/düzenle/dışa aktar ve kısayollar. Eklerin ham verisi ve canlı araç izleri oturum geçmişine yazılmaz.
- **Gözlenen ve giderilen entegrasyon sorunları:** numaralı ek adları Dockerfile gibi uzantısız dosyaları bozuyordu; ayrı `label` ile özgün ad korundu. Araç grubu planlamasında modelin eylem argümanı uydurması, boş argüman şemasının yapılandırılmış çıktıya bağlanmasıyla önlendi. Tamamlanmış araç sonuçlarının sentezi kod modeli yerine yanıt alanına yönlendirildi.
- **REA sınırı:** VS Code 1.145.2 ve Copilot Chat 0.73.0 metadata incelemesi. Paket kanıtı `ev_fe7f4f965ea49ffc50b941fe62622680bdaae91b741046e6d211ecde7cef284c`; çekirdek yerelleştirme kanıtı `ev_f585e2e5d544101c55654fcefe25512c32338e1e014ad6f620655d0474460bd5`. Microsoft kodu/varlıkları kopyalanmadı; canlı VS Code ve bütün Copilot servisleriyle birebir eşdeğerlik iddiası yoktur.
- **Doğrulama:** 316 test + 265 alt test ve değişen kapsamda Ruff başarılı. Canlı metin/Dockerfile/DOCX/OCR/ZIP/SQLite/ELF yolları ile gerçek dosya bağlamından yanıt ve SQLite mesaj çifti doğrulandı. Yerel konuşma modeli mevcut olmadığından ses yolu açık `unavailable` döndürür; tüm harici entegrasyonların kimlik doğrulaması veya tüm MCP eylemleri test edilmiş değildir.
- **Tamamlanan canlı akış:** gerçek otomatik `ollama.models` ve Qwen 2.5 sentezi, yinelenen çağrının engellenmesi, yazma reddi/diff-hash onayı/rollback, gerçek token sonrası iptal ve yarım turun kaydedilmemesi. Native Qt'de gerçek gönderim ve `4` yanıtı görüldü; 107 form ve beş ölçümlü sohbet profili doğrulandı. Güncel normal Qt uygulaması yeniden açılıp yanıt verir durumda bırakıldı.
- **Kalıcılık:** API imajı yeniden derlenip dağıtıldı, web proxy yenilendi; diğer servisler ve korunan rollback kaynakları değiştirilmedi. Veri doğrulayıcı yeni boş beyin override politikasına uyarlandı. Altı model, volume eşlemeleri, şifreleme anahtarı, SQLite bütünlüğü ve 603/776 eski kayıt/parça korunumu tekrar geçti; test oturumları temizlendi.

## 15. Windows host araçları ve son doğrulama

- 24 yeni araç ve 131 Qt formu; 40 API eklentisi. Windows yürütmesi yalnız yerel Qt'de, HTTP tarafı non-executing manifest/status eklentisidir.
- USB/PnP/seri COM, sürücüler, DCOM/AppID/CLSID ve olay tanısı; onaylı proje dışı dosya, hedefli Software kayıt değeri, aygıt/sürücü yönetimi ve DNS/TCP testi. Korunan hedefler, admin gerekliliği ve geri alma sınırları README'de açıklanır.
- 10 dakikalık tek kullanımlık plan, değişmeyen hedef doğrulaması, varsayılan Vazgeç, kalıcı önceki değer ve günlük; rollback kaydı da önizlemeye bağlanır. Geri alma yalnız dosya/kayıt değeri kapsamındadır.
- **337 test + 356 alt test / 12 Node testi**; kapsamlı Ruff, compileall ve diff kontrolü geçti. Normal Qt başlangıcındaki import sırası problemi temiz alt süreç testiyle giderildi; launcher jsonschema bağımlılığını da denetler.
- Native Windows Qt'de gerçek USB envanteri, yazma reddi/onayı ve byte-korumalı geri alma, veri göndermeyen TCP kontrolü geçti. Ayrı HKCU test değerleri ve oluşturulan boş anahtarlar geri alındı. Genel DNS/TCP 443 bağlantısı doğrulandı.
- Gerçek ajan `windows_host.devices` seçip çalıştırdı; aynı çağrıyı yinelemedi, 92 token ve iki mesaj üretti. Yalnız sahipli test oturumları/dosyaları temizlendi.
- API/web dağıtıldı; HTTP host işlemini 503 ile reddetti, tarayıcı Qt gerekliliğini gösterdi. Altı model, veri volume'ları, anahtar ve 603/776 eski kayıt/parça korunumu geçti. Normal Qt açık ve yanıt verir durumda bırakıldı.
- Gerçek sürücü kurma/kaldırma, aygıtı devre dışı bırakma veya keyfi registry onarımı test edilmedi; bu dallar kontrollü mock testleriyle doğrulandı. Otomatik UAC/reboot, zorla paket kaldırma ve toplu registry temizliği yoktur.

## 16. Sohbette Qt, web ve MCP araçları

- Ajan, şeması bilinen web/Qt formları, Windows host, Qt veritabanı/işler işlemleri, görev taslağı ve yapılandırılmış MCP sunucularından göreve göre seçim yapabilir. Görev taslağı yalnız öneri üretir; görev kaydetmez veya çalıştırmaz. Parola isteyen formlar ve şeması bilinmeyen iç eylemler otomatik seçime açılmaz.
- Tamamlanan ve başarısız araç çıktıları sohbet içinde gösterilir ve yanıt modeline bağlam olarak verilir; bağlam kesilirse kullanıcı bilgilendirilir. Ham araç izleri gizlilik için geçmiş oturum yeniden açıldığında yüklenmez. API `system.hardware` Docker'da Linux ortamına, `windows_host` ise yerel Windows'a aittir.
- Salt-okunur izin listesi dışındaki işlemler ve tüm MCP çağrıları kullanıcı onayı ister. Windows değişiklikleri hedefe özgü önizleme ve tek kullanımlık onaylı planla yürütülür; genel host kabuğu otomatik ajana verilmez. Qt sistem sayfasının Docker durum komutu seçilebilir, API günlüklerini okumak onay gerektirir; yığın kurulumu/yeniden oluşturma ve pencere açma manuel kalır.
- MCP kataloğu şema ve boyut sınırlarına göre sayfalanır: gerçek REA kataloğundaki 229 araç beş sayfada sunuldu. Gerçek Sequential Thinking oturumunda aynı turdaki iki çağrı sırasıyla 1 ve 2 geçmiş girdisi döndürdü; oturum tur sonunda kapanır ve sonraki mesaja otomatik taşınmaz. Eksik/uyumsuz sunucular hata olarak gösterilir; isteğe bağlı graphify kendiliğinden kurulmaz.
- Gerçek model denemelerinde API donanımı için `system.hardware`, altı adımlı görev taslağı için `tasks.draft` ve Windows USB envanteri için `windows_host.devices` seçildi. USB filtresiyle 15 aygıt listelendi ve sonuç sohbet yanıtında görüldü. Test betiği her denemede ilk başarılı araçtan sonra planlamayı durdurdu; bu, modelin kendi kendine durmasını kanıtlamaz. Aygıt veya sürücü üzerinde gerçek değişiklik yapılmadı.
- Backend/Qt paketinde 364 test ve 487 alt test, ilgili Ruff kapsamı ve diff kontrolü geçti. Yerel CPU'daki üç canlı deneme yaklaşık 141, 172 ve 214 saniye sürdü; model yanlış araç seçebilir veya sonuçları hatalı yorumlayabilir. Araç çıktısı ve onay ayrıntıları kontrol edilmelidir.
- Güncel API imajı dağıtıldı, web proxy yenilendi; API, web ve proxy sağlık kontrolleri geçti. Dağıtılan kaynakların hash'leri, altı model, volume'lar, anahtar ve 603/776 eski kayıt/parça korundu. Dağıtım sonrası gerçek donanım çıktısından modelin CPU ve RAM değerlerini doğru özetlediği doğrulandı; yalnız teste ait sohbet oturumu silindi. Güncel normal Qt penceresi açık, API'ye bağlı ve yanıt verir durumda bırakıldı.

## 17. Masaüstü dosya ve pil programı denemesi

- Gerçek Qt sohbetinde onaylı `windows_host.directory_create` ile masaüstünde `DeepPanda_Ajan_Test` klasörü oluşturuldu; `windows_host.file_write` ile tek satırlık `deneme.txt` yazıldı ve içerik bağımsız doğrulandı. Kullanıcı istediği için klasör ve test dosyaları korunur.
- Kod denemesinde model, Windows masaüstü hedefini üç kez proje içi `toplama.py` olarak yazdı. Yalnız bu testin oluşturduğu dosya, üç yedeğin hedefi ve hash zinciri doğrulanarak geri alındı. Linux workspace artık Windows mutlak/sürücü yollarını ve belirsiz ters eğik çizgileri reddeder; Qt ajanı istekteki mutlak Windows yolunu aynı sonlu göreli workspace hedefiyle değiştirmeyi durdurur.
- Model aynı dosyayı bir turda tekrar tekrar yazıp doğrulanmış içeriği bozmayı da önerdi. Qt ajanı artık aynı araç ve hedef için tur başına yalnız bir başarılı yazmaya izin verir; sonraki değişiklik yeni mesaj ve yeni onay gerektirir. Farklı dosyalar için ayrı yazma işlemleri korunur. Bu korumalar tüm olası yanlış hedefleri veya hatalı kodu tespit etmez.
- Pil denemesinde Qwen 2.5'in bağımsız ürettiği Python kodu yanlış `powercfg` komutları içerdi; sonraki düzeltme önizlemesi de güvenli geri yükleme sağlamadığından reddedildi. Qwen 3.6 ile ayrı bir araç-planı denemesi geçersiz JSON döndürdü. Doğrulanan Python kodu dışarıda hazırlandı ve Qt ajanına hedefe özel diff onayıyla yazdırıldı; ajanın daha sonraki bozuk ikinci yazma önerisi reddedildi.
- Yazılan `pil_ayari_test.py` yedi sahte komut/arıza/eşzamanlı değişiklik senaryosundan geçti. Ajan programı çalıştırması istendiğinde yalnız dosyayı okudu; Windows'ta genel Python yürütme aracı bulunmadığı için kendi başına çalıştırmadı. Program kullanıcı isteği doğrultusunda ayrı olarak elle çalıştırıldı: pilde ekran kapanma değeri **0 → 600 → 0 saniye** bağımsız gözlendi, AC değeri 0 kaldı ve özgün güç planı korundu. Bu sonuç ajanın bağımsız kod üretip çalıştırabildiği anlamına gelmez.
- **2026-11-10 yeniden kabulü:** aynı masaüstü dosyası SHA-256 `e56bc2ecb5d444c206b2f54e359956f0e718a13a78d9088fe1002abc89f88dbb` ile doğrulandı. Gerçek çalıştırma sırasında bağımsız sorgu DC **0 → 600 → 0**, AC sürekli 0 gözledi; işlem exit 0, stderr boş, aktif plan ve bütün `powercfg /query` çıktısı önce/sonra aynı kaldı. Ardından gerçek yerel Qwen3.6 yalnız `windows_host.python_run` şemasından doğru dosya/argümansız/30 saniyelik çağrı üretti; gerçek `ChatAgent._api_action` önizleme ve yalnız bu dosyaya sınırlı harness onayıyla çalıştırdı (`operation_id=43fc8488c24744838ee3eb451f69f4b5`). İkinci çalışma da exit 0; bütün güç ayarları ve kaynak hash'i aynı kaldı. Bu kontrollü model-planı/ajan-yürütme kabulüdür; tek kesintisiz Qt sohbeti veya modelin bağımsız pil kodu üretimi değildir. Dosya konsol testidir, GUI penceresi yoktur; kalıcı ayar değişikliği bırakılmadı.
- **Modelin yazdığı grafik pil paneli (kısmi kabul):** kullanıcı grafik tasarımı kurulu yapay zekanın yapmasını istedi. Kod asistanının başlattığı iki yeni panel dosyası çalıştırılmadan kaldırıldı. Gerçek yerel `qwen3.6:latest`, ayrı [battery_gui](projects/battery_gui/README.md) projesinin dört dosyasını yazdı (`c21dcedfbd5746d885ac881badd5c2bd`); ilk ayrı üretim denemesi sözdizimi denetiminde reddedilmişti. Native API hatası ve başarısız testler modele geri verildi; dört ayrı model güncellemesi yapıldı. Bu, otomatik iki-onarımlı ajan döngüsü değil, açıkça yönlendirilen manuel model-planlama deneyidir; uygulama kaynaklarına kod asistanı elle düzeltme uygulamadı. Mevcut `.venv` PySide6 ortamı kullanıldı, yeni paket indirilmedi.
- **Grafik panelde gerçek doğrulama:** Windows `GetSystemPowerStatus` ile %100 / AC gücü okundu; 800×640 yerel pencere render edildi, Yenile düğmesi ve 5 saniyelik timer doğrulandı. Bilinmeyen yüzde UI'da `--`/boş bar, okuma hatası inline hata olarak gösterildi. Koyu lacivert/yeşil tasarımın ekran görüntüsü incelendi, ardından kullanıcıya görünen `DeepPanda Pil Paneli` penceresi açılıp yanıt verir durumda doğrulandı. Panel yalnız izler, hiçbir güç ayarı değiştirmez; eski pil ayarı konsol dosyası korundu.
- **Açık hata / dürüst sınır:** modelin dokuz testinin sekizi geçti; `test_unknown_percent` hâlâ başarısız: yüzde bilinmiyorken kaynak AC ise etiket `Bilinmiyor` yerine `AC Gücü` kalıyor. Son iki model çağrısında test dosyası değiştirilmedi. Bu demo genel kabulü geçmiş, üretime hazır veya tamamen bağımsız onarım başarısı sayılmaz; hata kullanıcıya açıkça bildirildi. Üretim/onarım istemleri ve işlem kimlikleri yerel `data\program-builds\battery-gui-generation.json` içinde tutulur. Yeniden açmak için kökten `.\.venv\Scripts\python.exe -B .\projects\battery_gui\app.py`; test için `.\.venv\Scripts\python.exe -B -m unittest discover -s .\projects\battery_gui -p "test_*.py" -v`.
- **Sonraki çoklu yerel model onarımı — kalan hata kapandı:** kullanıcı hatayı modelin bulmasını/düzeltmesini, tekrar test ve farklı ajan görüşü istedi. Qwen3.6 ve Qwen2.5 Coder 7B, aynı gerçek başarısız test ve tam kaynak bağlamından, birbirlerinin raporunu görmeden salt-okunur teşhis üretti. İkisi de yüzde 255'te etiket dalının eksik olduğunu belirledi. Bu raporlar tavsiye olarak gerçek `ChatAgent` test → güncelleme → test döngüsüne verildi; iki onarım üst sınırı ve test değiştirme/no-op engeli korundu. İlk test `a58f16a12fb2490db5f8eb8b2d9ae2d4`: 9 test/1 hata; modelin tek `battery.py` güncellemesi `bb5d70d2d7f441a785555950d34a79b9`; yeniden test `ed4e1847400e4483ae513e340bb9a5db`: 9/9 geçti. Uygulama koduna kod asistanı elle müdahale etmedi.
- **İki ayrı tekrar ve bağımsız kontrol:** sonraki `project_test` işlemleri `2b3dec0d1283481784d48bb9b36b5ed0` ve `6457a48fd7694319a0ba0db751e53f7b` da 9/9 geçti. Test dosyası SHA-256 `1188939263228b37d1bc27399dd577f51bd5df166b31fcaf0a6c11773132fd65` bütün akışta aynı kaldı. Bağımsız sekiz bilinmeyen-yüzde birleşimi, native başarısızlıkta OSError, 12 bayt Windows yapı boyutu ve gerçek Qt'de bilinmeyen yüzde/durum, inline okuma hatası ve Yenile kontrolü geçti; gerçek okuma %100/AC. Kaynak hash'leri kontroller sırasında değişmedi. Eski yalnız bu demo penceresi normal kapatılıp düzeltilmiş sürüm kullanıcıya tekrar açıldı; ana asistan penceresi korunur.
- **Ajan görüşü kanıt değildir:** Qwen2.5'in son tekrar incelemesi kendi içinde çelişkili bir öneri verdi; aynı testlerin geçmesi ve bağımsız davranış kontrolleriyle desteklenmediği için değişiklik uygulanmadı. Ön teşhisler + iki model görüşü ve testler kaydedildi: `data\program-builds\battery-gui-multiagent-repair.json`. Bu, mevcut yerel modellerle kontrollü orchestration/harness kabulüdür; her Qt turunda otomatik çoklu model hakemliği kalıcı olarak entegre edilmiş değildir. Yeni temel bağımlılık/bulut çağrısı, test zayıflatma veya güç ayarı değişikliği yapılmadı. Önceki 8/9 açık hata kaydı bu yeni kabul ile kapanmıştır; bütün donanım durumlarının kusursuzluğu iddia edilmez.
- İlgili tüm backend/Qt paketinde **379 test + 499 alt test** geçti; hedefli Ruff ve diff kontrolü başarılıdır. `workspace.py` içindeki üç önceden mevcut Ruff bulgusu bu kontrolde hariç tutuldu. Gerçek sürücü, aygıt veya kayıt defteri değişikliği bu denemede yapılmadı.

## 18. 10 Kasım görev listesi ve tek kök çalışması

Bu listenin ilk teslim dilimi tek kök/bağımlılık birleştirmesidir. Sonraki maddeler planlanmış ayrı uygulama işleri olarak açık kalır; yalnız menü/form bulunması tamamlandıkları anlamına gelmez.

### A — Önce tek kök ve bağımlılıklar

- [x] Etkin kökü, Docker mount'larını, Qt ayarını ve dış Python/GPU test yollarını incele. Etkin kaynak kökü zaten `F:\DeepPanda Agentic Al`; yeni bir iç içe proje kopyası oluşturulmadı.
- [x] Python 3.12.10 çalışma zamanını SHA-256 sabitlenmiş resmî Microsoft NuGet paketinden `runtimes` altına al; mevcut `.venv` paketlerini koruyarak C: Python bağımlılığını kaldır.
- [x] Python/Qt ve GPU başlatıcılarını proje içi runtime, paket, pip/model/GPU önbellekleri ve geçici dizinlere bağla. Kullanıcı profili/global PATH değiştirilmez.
- [x] Önceki C: geçici GPU testini proje içindeki `tools\gpu-benchmark.py`, ayrı paket manifesti ve `.tools\venvs\gpu-benchmark` ortamından çalıştırılabilir hale getir.
- [x] Eski `F:\DeepPanda-Proje` kökünü `_arsiv\legacy-20261110` altına kopyala; **114 dosyanın** tamamını SHA-256 ve adet karşılaştırmasıyla doğrula. Kaynak silinmedi, geri dönüş korunur.
- [x] Beş yerel MCP sunucusunu proje içinden doğrula: **297 araç** keşfedildi. Bu yalnız protokol/araç listesi kontrolüdür, her aracın bütün eylemleri test edilmiş değildir.
- [x] Yeni kök düzeninde başlatma/regresyon/veri koruma kontrollerini tamamla ve sonucu kaydet.

**A dilimi doğrulaması:** yeni yerel Python ile **379 test + 499 alt test**, yerel araç/ortam korumaları için **16 Node testi** geçti. Boş bir test sanal ortamı sistem Python'u olmadan oluşturuldu; pip/SSL/SQLite çalıştı ve test ortamı temizlendi. Gerçek `run-desktop.ps1` başlatıcısından açılan **DeepPanda Kontrol Merkezi** yanıt verdi; çalışan gerçek Qt sürecinin `runtimes\python-3.12.10\tools\python.exe` olduğu ve normal kapanışta başlatıcı çıkışının **0** olduğu doğrulandı. Test penceresi açık bırakılmadı. Lint, dört PowerShell betiğinin sözdizimi ve diff kontrolü geçti. Pylance MCP bağlantısı başlatılamadığı için editör doğrulaması yapılamadı; Python sözdizimi yerel yorumlayıcıyla ayrıca kontrol edildi.

Canlı veri doğrulayıcı **altı kurulu modelin**, aynı volume'ların/şifreleme anahtarının, SQLite bütünlüğünün ve **603 kayıt / 776 parçanın** korunduğunu doğruladı; API/web/SQL HTTP kontrolleri geçti. Ortak Docker diskine veya canlı servislere taşıma/yeniden oluşturma yapılmadı. C: üzerindeki yalnız bize ait geçici `dp_gpu_bench` ortamı, proje içindeki karşılığı çalıştıktan ve özgün betiği `data\backups\consolidation-20261110` altına hash doğrulamasıyla alındıktan sonra temizlendi. Kullanıcının genel Python'u/pip önbelleği ve masaüstü test dosyaları silinmedi.

### B — Birleştirmeden sonra, uygulama sırası

| ID | Görev | Tamamlanma ölçütü | Durum / bağımlılık |
|---|---|---|---|
| B1 | Ollama GPU bağlantısı ve ölçüm | Gerçek sohbet/model yükünde GPU erişimi, VRAM kullanımı ve süre/token hızı doğrulansın; CPU/GPU ile unlock etkisi ayrı raporlansın | Tamamlandı; aynı model/istemle CPU 11,686 → GPU 50,149 token/sn, 100% GPU; unlock A/B değil |
| B2 | Onaylı Windows kod çalıştırma | Dosya/hash/yorumlayıcı/argüman önizlemesi, işlem başına onay, süre/çıktı sınırı ve hata bildirimi; gerçek zararsız programın çıktısı doğrulansın | Temel yürütme ve sohbetten Python süreç ağacı iptali tamam; gerçek ajan stdout VERIFIED_SUM=42, exit 0; kalıcı GUI başlatma kapsam dışı, paket kurulumu ayrı C2 aracı |
| B3 | Ajan güvenilirliği | Yanlış yol/araç, geçersiz JSON, hatalı kod ve kanıtsız başarı için yeniden üretim, regresyon ve gerçek sohbet testleri | Temel korumalar, ayrı Qwen3.6 onarımı ve tek Qt sohbet turunda tariften konsol programı → ZIP teslimi doğrulandı; genel güvenilirlik açık |
| B4 | Beş aşamalı çoklu ajan | Bütün aşamalar gerçek yerel modelle bitsin; üretilen çıktı ve hata halinde duruş doğrulansın | Temel kabul geçti: gerçek beş aşama ve final yanıt; hata duruşu fixture regresyonuyla doğrulandı. Araçsız taslak akışıdır; B3/C5 bağımsız kod düzeltme başarısı değildir |
| B5 | İsteğe bağlı entegrasyonlar | OpenJarvis/WSL, graphify, ses modeli ve yetkili MCP araçları ayrı ayrı denensin; eksik hesap/paket açıkça işaretlensin | Gerçek GitHub MCP initialize/49 araç başarılı; OpenJarvis izole Windows Python 3.12 ile kuruldu ve Docker API model listesi geçti. graphify modülü/grafı ve ses paketleri/modeli yok; lisans/veri aktarımı sınırları nedeniyle bunlar çalışıyor sayılmaz |
| B6 | Kontrollü Windows yönetim testleri | Kritik olmayan izole hedeflerde kayıt/aygıt/sürücü akışı; gerçek tehlikeli değişiklik gerektiren dallar mock olarak açıkça ayrılsın | Sınırlı kabul tamam: benzersiz HKCU hedefinde beş tip set/delete/rollback ve tam temizlik; gerçek aygıt/sürücü/port sorguları salt okunur. Donanım değiştiren dallar mock olarak ayrıdır; sırf test için donanım bozulmadı |
| B7 | Sohbet sürekliliği ve VS Code farkları | Ek/araç izi saklamada gizlilik ve açık tercih; MCP oturum sürekliliği ve mevcut özellik farkları açıkça tanımlansın/test edilsin | Temel kabul tamam: ayrı onaylı ek yolları, sınırlı ad/durum özetleri ve aynı açık sohbette sınırlı canlı MCP; ham iz/çıktı kalıcılığı, uygulamalar arası canlı durum ve bütün VS Code özellikleri kapsam dışı |

### C — Tarif veya hazır koddan çalışan program üretme

Hedef: tarif/kod → kabul ölçütleri → proje dosyaları → yalıtılmış bağımlılıklar → onaylı çalıştırma → test/hata düzeltme → doğrulanmış teslim. Temel Python akışı uygulanmıştır; bağımsız model başarısı ve paketleme aşağıda ayrıca ayrılır.

| ID | Görev | Tamamlanma ölçütü | Bağımlılık |
|---|---|---|---|
| C1 | Onaylı proje alanı ve çok dosyalı üretim | Kullanıcının hedefini koruyan yeni proje klasörü, açık kabul ölçütleri, kaynak/test/README dosyaları; mevcut içerik sessizce ezilmez | A |
| C2 | Projeye özel bağımlılık ortamı | Üretilen programın ayrı `.venv`/manifesti, kök içi paket önbelleği, açık kurulum/ağ onayı; asistanın ortamı kirletilmez | C1, B2 |
| C3 | Çalıştır-test-düzelt döngüsü | Gerçek çıkış kodlu sözdizimi/build/birim/smoke testleri; sınırlı düzeltme, iptal ve açık başarısızlık; model beyanıyla başarı sayılmaz | C2, B3 |
| C4 | İsteğe bağlı uygulama paketleme | Açık istekle Windows `.exe` gibi çıktı; araç/lisans/bağımlılık kontrolü, ayrı çıktı klasörü ve açılış testi | C3; temel Python konsol/onedir kabulü geçti, aşağıdaki sınırlar geçerli |
| C5 | Gerçek sohbet kabul denemesi | Yalnız tariften küçük SQLite stok uygulaması: çok dosya, test, kontrollü hata düzeltme ve teslim bağlantıları; asistanın elle tamamladığı kısımlar ayrıca belirtilir | SQLite stok çekirdek kabulü geçti: model kodu + 14 test + çıkarılan EXE'de 16 kontrol. Onarım ayrı örnekte geçti. Yeni JSON sayı konsol projesinde tek native Qt turu → 8 test iki kez → ZIP → çıkarılan EXE 43 kontrol geçti; SQLite denemesinin kendisi tek-tur diye sunulmaz |

Uygulama sırası A → B1 → B2/B3 ve C1–C3 → C5 kabul denemesi olarak izlendi. B4, B7 ve isteğe bağlı C4'ün aşağıda sınırlanan temel kabulleri de geçti. Sonraki C5 kabullerinde modelin uygulama koduna elle müdahale olmadan kaynak → test → EXE/ZIP doğrulandı; JSON sayı konsol projesinde aynı yol tek native Qt Sohbet turunda da geçti. B5/B6 ve genel ajan güvenilirliği açık kalır. Her dilimin durumu ve kanıtı ayrıca kaydedilir. Her dil/program türü için kusursuz otomatik üretim garantisi verilmez.

### C1–C3 uygulama ve C5 kabul sonucu

- **C1 tamam:** `project_create` ve `project_update`; yeni, sahiplik kayıtlı `projects\<ad>` alanında çok dosya, Python sözdizimi, test/README şartı, bütün ağaç hash'i, ayrı diff/onay ve eski dosya baytlarının kaydı. Mevcut klasör sessizce sahiplenilmez; otomatik proje geri alma yoktur.
- **C2 temel akış tamam:** `.tools\venvs\program-<ad>` ayrı ortamı, sabit PyPI/wheel ve açık doğrudan sürüm şartı. Gerçek `six==1.17.0` gereksinim manifestli geçici projede kuruldu, ayrı yorumlayıcıyla içe aktarıldı ve unittest geçti; test projesi/ortamı temizlendi. Paket/freeze çıktısı sahiplik kaydına yazılır. Transitif hash lock garantisi yoktur.
- **C3 temel Python/unittest akışı tamam:** genel üç/program sekiz adım, en fazla iki onaylı düzeltme; arada güncelleme olmadan başarısız test tekrar edilmez. Aşama şeması tek projeye daraltılır. Hata traceback/kaynakları yerel modele verilir; büyük çıktıda yapılandırılmış test kanıtı korunur. Sıfır test/tamamı skipped başarısızdır. Sohbetten yerel Python/test/ortam süreç ağacı iptali eklendi; diğer araçlar için anında iptal, kalıcı GUI ve diğer dil build'leri kapsam dışıdır.
- **İlk C5 denemesi bağımsız geçmedi:** Qwen 2.5 Coder 7B tariften `stok_demo` için üç dosya oluşturdu; aynı ürünü tekrar ekleme testi gerçek `5 != 15` hatasını yakaladı. Gerçek sohbet tekrarlarında model yalnız biçim/README değiştirdi veya `None` sözleşmesini bozan değişiklik önerdi; uygun olmayan öneriler reddedildi. Kurulu DeepSeek Coder 6.7B ile tek alternatif deneme de yalnız biçim değişikliği önerdi. Bu denemeler bağımsız program üretme/düzeltme başarısı olarak sayılmaz; sonraki ayrı Qwen3.6 kabulü aşağıdadır.
- **Teslim örneği çalışıyor, ancak insan/asistan müdahaleli:** SQL upsert toplamayı kod asistanı düzeltti; modelin test beklentileri zayıflatılmadı. Sonraki gerçek `project_test` dört testi geçti (`operation_id=4ae77d71054043ddbe5fbd462d10538d`). Ayrı smoke kontrolü toplama, sıfır/negatif miktar, bulunamayan ürün, SQL özel karakterleri ve yeniden açınca kalıcılığı doğruladı. Bu ayrım örneğin README'sinde de yazılıdır.
- **Son doğrulama:** 408 test + 543 alt test, 16 Node testi, ilgili Ruff ve diff kontrolü geçti. Native Qt penceresi gerçekten gösterildi ve normal kapandı; 137 form / 30 host aracı ve API'nin host yürütmesini HTTP 503 ile reddettiği doğrulandı. Altı model/volume/anahtar, SQLite bütünlüğü ve 603 kayıt / 776 parça korundu. C4 ve B4–B7 hâlâ ayrı açık işlerdir.

### C3 gerçek kanıtlı yerel model düzeltmesi

- **Kök neden doğrulandı:** uzun `project_test` sonucunun sohbet için 5.000 karaktere kısaltılması, `source_files` alanını yapılandırılmış düzeltme girdisinden düşürüyordu. Otomatik düzeltici artık son ham başarısız sonuçtan ayrı kaynak/test özeti ve traceback bağlamı kurar; görüntüleme/son yanıt hâlâ kısadır. Kaynaklar yeniden kısaltılmaz; stdout 4.000/stderr 12.000 karakterle açık kesilme işaretli, toplam JSON en fazla 48.000 karakterdir. Büyük JSON açık hatayla durur. Kabul istemi ayrı 12.000 karakterlik alıntıdır.
- **Yazmadan önce koruma:** yalnız son kanıtta kesilmemiş içeriği olan mevcut uygulama `.py` dosyası; `test*`, `*_test.py`, `test/tests` klasörleri, README/yeni dosya, çift hedef, bozuk Python ve AST'si değişmeyen yorum/biçim önerileri reddedilir. Hata sohbet izinde görünür; başarısız öneri onaya/host yazmasına gitmez. Manuel istenen `project_update` test düzenlemeye devam edebilir. Her gerçek test/yazma ayrı onaylıdır; iki düzeltme sınırı değişmedi. Bu yapısal kontrol, zararlı kod için sandbox veya anlamsal doğruluk garantisi değildir.
- **Gerçek yerel model kanıtı:** [repair_acceptance](projects/repair_acceptance/README.md) ayrı sahiplik kayıtlı projedir; kod asistanı stok örneğindeki toplama ifadesini bilinçli bozdu ve altı sabit testi hazırladı. Gerçek `qwen3.6:latest` + API/Qt ajanı + Windows host hattında test → model güncellemesi → test, 66,14 saniye sürdü. İlk işlem `452cbfa74bb04c11bd2882fc010493ec`: 6 test, 2 başarısız. Model yalnız `inventory.py` dosyasını `7adfe9bab265441d919464a1ebdc7453` ile düzeltti; son test `480dc84457264dfb9e78b21342d5786f`: 6 test, 0 hata. İki test ve tek yazma ayrı, yalnız bu projeye sınırlı harness onayı aldı; bulut/anahtar kullanılmadı.
- **Testler zayıflatılmadı:** test dosyası önce/sonra byte hash'i `645dda8486602094db44b37d9f9a796f2763d4f5d7f02a89cfd3ce2423e474e9`; tekrar ekleme, sıfır/negatif miktar, bulunamayan ürün, SQL özel karakterleri ve yeniden açınca kalıcılık aynı altı testle doğrulandı. Düzeltmeye kod asistanı elle müdahale etmedi. Başlangıç kodu/testler insan-asistan hazırlığıdır; bu sınırlı model onarım başarısı, tariften sıfırdan bağımsız üretim/teslim C5 kabulü değildir.
- **Bağımsız ek kontrol:** model turunda verilmeyen 75 farklı miktarlı ekleme / 7 ürün için toplamlar ve veritabanı yeniden açılınca kalıcılık geçti; bütün kaynak ağacı önce/sonra aynı kaldı, sabit test SHA-256'sı tekrar doğrulandı.
- **Regresyon:** 531 test + 609 alt test ve ilgili Ruff geçti; yeni 7 test uzun ham kanıt, gerçek planner istek bütçesi, test/README/no-op reddi, tam olmayan kaynak ve manuel test güncellemesi ayrımını kapsar. Yeni yardımcıda Pylance tanısı yoktur; `chat_agent.py` sorgusu workspace import çözümleme (`reportMissingImports`) ve mevcut MCP `session` için `reportPossiblyUnboundVariable` bildirdi; bu dosya için temiz editör denetimi iddia edilmez. Kullanıcının açık Qt penceresi yeniden başlatılmadı; yeni korumalar sonraki Qt açılışında yüklenir.

### C3 kalıcı ikinci yerel ajan / çift test entegrasyonu

- **Kalıcı uygulama:** Qt `Settings.program_review_model` ve Ayarlar sayfasına model alanı eklendi. Varsayılan boş/kapalı; bu kurulumda kullanıcı isteğiyle `qwen2.5-coder:7b` kaydedildi. Başarısız `project_test` sonrasında mevcut `ChatAgent` onarım döngüsü, ayrı modelle sınırlı/şemalı salt-okunur kök neden/öneri/kontrol raporu alır, sohbet araç izine ekler ve asıl modele yalnız doğrulanması gereken tavsiye olarak verir. Kaynak/traceback ayrı tam kanıt bağlamında kalır. İkinci model yazma, yürütme veya onay yetkisi kazanmaz.
- **Sınırlar:** açık birincil yerel model seçilmelidir; ikinci model farklı ve kurulu olmalıdır. Bulut/aynı/eksik model, geçersiz rapor veya API hatası görünür duruş üretir; indirme/sessiz alternatif yoktur. Aynı projede en fazla iki onarım ve iki inceleme; test/README/no-op koruması ve her yazma/test için ayrı onay korunur. İptal sonrası yeni çağrı yoktur; sürmekte olan HTTP model isteğinin sunucuda anında sonlanması garanti değildir.
- **Gerçek çift test:** özellik açıkken ilk başarılı testten sonra model planlamasına gerek olmadan aynı hedef/argümanlarla ayrı onaylı ikinci `project_test` yapılır. İkinci test reddi/hatası/başarısızlığı doğrulanmış başarıyı engeller. İlk test doğrudan geçerse teşhis çağrısı gerekmez. Sekiz planlama/eylem turuna ek en fazla iki inceleme ve bir doğrulama testi vardır. Model raporu kabul testi yerine geçmez.
- **Süre ve kullanıcı verileri:** kayıtlı istemci beklemesi 600 → 660 saniye; Ollama backend'in 600 saniyelik sınırı değiştirilmedi. Bunlar çağrı başına sınırdır; bütün turun tek toplam deadline'ı değildir. Host test/çalıştırma süreleri ve iptal korunur. Yalnız bu iki QSettings anahtarı değişti; sağlayıcı anahtarlarına dokunulmadı. Açık ana Qt/giriş alanları yeniden başlatılmadı; yeni kod/tercihler sonraki açılışta yüklenir. Gerçek ayrı Qt Ayarlar penceresinde kaydedilen model ve 660 saniye yüklendiği doğrulandı.
- **Regresyon:** son tam paket 541 test + 614 alt test, ilgili Ruff geçti. İncelemeci modeli/ayar roundtrip, UI, hatalı şema, otomatik birincilin kendini inceleyememesi, iptal, iki onarımda duruş, ikinci test başarısızlığı/reddi ve eski varsayılan kapalı davranış kapsanır. Pylance değişen üç üretim yüzeyinde (ajan, yardımcı, ayarlar sayfası) tanı döndürmedi.

### C5 daha özgül görev — model uygulaması, bağımsız gözlem, açık başarısızlık

- **Görev:** yeni [invoice_audit](projects/invoice_audit/README.md): yalnız standart kütüphane ile CSV fatura denetimi; kesin kuruş hesabı, paid/refunded, boşluk temizliği, aynı/çelişkili kimlik, hatalı tutar/başlık, BOM/Unicode ve tam JSON sözleşmesi. Yerel Qwen3.6 uygulamayı, testleri ve README'yi tariften yazdı; kod asistanı uygulama çözümü/fix kodu vermedi. Oluşturma `2332dc742b3b447cb3ca8d7a8172467c`, ortam `e818b3261cd84ea09ddd52fcedb522b2`; paket indirme/bulut/özel veri yok.
- **Kendi testleri yeterli değildi:** gerçek ajan üretim → ortam → test akışını yürüttü; 12 test `5b86681733264464acc82de17733cbb2` ve otomatik ayrı onaylı doğrulama `133720d6fa974babbe0bc5c1c3aef041` ile geçti. Buna rağmen bağımsız 15 kesin giriş/çıkış kontrolünden yalnız 12'si geçti: normalize edilmiş aynı kimlik hatalı çatışma, üç ondalıklı tutarın kabulü, başlıksız boş dosyanın başarı sayılması.
- **Test üretimi de gözlemlendi:** ikinci yerel model Qwen2.5'e yalnız gereksinim ve gözlenen giriş/beklenen çıktı verildi; ilk test önerisi bozuk quoting ile yazılmadan reddedildi. Sonraki önerisi eksik `sys` ve olmayan fixture dosyaları içeriyordu, kabul kanıtı sayılmadı. Qwen3.6 test kurulum hataları ile gereksinimlerden geçerli üç ek regresyon testi yazdı (`37516e80dbcc4c468b092ebac38e635a`). Kod asistanı test veya uygulama çözüm kodunu elle yazmadı; gözlem, görev/fixture geri bildirimi ve ayrı hedefli onayları yönetti.
- **Entegre onarımın gerçek sonucu:** ilk 15 test `2a29e58658f74b53a1f43813fa3ea348` ile üç başarısız; ikinci yerel ajan raporu sonrası Qwen3.6 `4a387147047747c5b46336c637110fb7` ile yalnız uygulamayı güncelledi, `20f609d8f0844b8b9c68cd2d55f4d9c1` iki başarısız kaldı. Yeni bağımsız görüş sonrası ikinci güncelleme `0eb3a09f05344c2b9fefd7c9fe3f38ee`; test `c65dc3df8cb64732b7af0f16f9c23422` bir başarısız kaldı. Sistem üçüncü inceleme/yazma yapmadan sınırda durdu; yanlış başarı vermedi. Bağımsız 15 davranış kontrolü de 14/15 oldu. Kalan hata aynı normalize faturanın çatışma sayılmasıdır; elle tamamlanmadı, paketlenmedi.
- **Sabit test kanıtı:** onarım boyunca `test_audit.py` SHA-256 `3fdc41e6c47d717b03ed7820600069e029ada535aff6ae71e0a7af06ea7e1b83`, `test_acceptance.py` `edf78fddbf9fcfbafd17ff2e5e290617f240b73d0b518e3e10b261d68f64ab27` değişmedi. İstemler, çağrı/onay izi ve bağımsız girdiler/sonuçlar yerel `data\program-builds\invoice-autonomous-acceptance.json` içinde tutulur.
- **İlk turun sonucu:** kalıcı ikinci-ajan/çift-test entegrasyonu doğrulandı; bu aşamada daha karmaşık görevin tam kabulü **geçmedi**. Testler gevşetilmedi ve kod asistanı uygulamayı elle düzeltmedi. İki-onarım sınırı korundu. Kullanıcının sonraki açık teşhis/düzeltme isteğiyle bulunan altyapı sorunları ve doğrulanan yeni sonuç aşağıdaki bölümde ayrı kaydedilmiştir. Tek Qt mesajında native UI kabulü ve bütün görevlerde bağımsız başarı açık kalır.

### C3/C5 kalan hatanın kanıtlı teşhisi ve onarım altyapısı

- **Uygulama hatası gözlendi:** runtime yerellerinde mevcut satır `('1','A','1.00','paid')`, daha önce `seen_ids` içine saklanan ham satır `(' 1 ',' A ',' 1.00 ',' paid ')` idi. Aynı fatura farklı temsillerle karşılaştırılıyordu. Kaynak kesilmesi ilk teşhisin nedeni olarak kanıtlanmadı; modelin iç düşüncesi hakkında iddia yoktur.
- **İnceleme boşluğu kapatıldı:** önceki genel/yanlış raporlar kaynak kanıtı gerektirmiyordu. Artık rapor 1–4 birebir alıntı içermeli; her alıntının tam ve kesilmemiş gerçek dosyada varlığı doğrulanır. Geçersiz alıntı raporu hata olarak araç izinde tutulur, yazma yapılmaz. Kaynak eşleşmesi semantik doğruluk garantisi değildir.
- **Test ve onarım kanıtı:** test runner, en fazla sekiz hata için kimlik/tür/traceback ve kesinti/atlanma işaretleri üretir (10.000 JSON karakteri). Aynı turdaki önceki onaylı onarımların sınırlı diff/test durumu sonraki isteme eklenir. Test koruması, ayrı onay ve iki onarım sınırı değişmedi; toplam 48.000 karakter aşımı açık duruştur.
- **Ayrı gerçek aktarım hatası bulundu:** kurulu `qwen3.8:latest` ile açık deneyde kaynak-alıntılı öneri üretildi, ancak birincil Qwen3.6 yanıtı geçersiz JSON oldu. Değişmeden kalan kaynak ve doğrulanmış raporla yapılan tek metadata tanı tekrarında Ollama `prompt_eval_count=7053`, `eval_count=1138`, `done_reason=length` döndürdü; toplam 8191, eski 8192 bağlamı tüketti. Bu örnekte çıktı tam dosyanın ortasında kesilmişti; genel JSON hatası gerçek nedeni gizliyordu. Bu tanı tekrarında yeni inceleme üretilmedi; mevcut doğrulanmış rapor kullanıldı, hiçbir uygulama yazması gerçekleşmedi.
- **Kalıcı düzeltme:** argüman planlaması 16.384 token bağlama çıkarıldı; çıktı üst sınırı 4.096 olarak kaldı. Boş argümanlı grup seçimi 8.192/256 kalır. `done_reason=length` artık JSON parse edilmeden açık bütçe/kesilme hatasıdır; geçerli JSON görünse de reddedilir. Süre uzatmak bu token sorununu çözmez. Yalnız API imajı yeniden oluşturulup API servisi güncellendi; sağlık ve konteynerde yeni kod doğrulandı. Kullanıcının açık Qt/girişleri yeniden başlatılmadı.
- **Deney ayrımı:** eski Qwen2.5 inceleme denemesi yeni kaynak doğrulamasını geçmedi. Daha güçlü kurulu incelemeciyle deney açıkça yapıldı; sessiz model değiştirme veya otomatik fallback eklenmedi. Gerçek başarı doğrulanınca yalnız QSettings `program_review_model` anahtarı `qwen3.8:latest` olarak güncellendi; 660 saniye ve diğer ayarlar korundu. Açık Qt yeni kod/tercihi sonraki açılışta yükler.
- **Yerel kanıt:** `data\program-builds\invoice-grounded-repair.json` geçmiş başarısız denemeleri, gerçek raporları ve onayları; `invoice-planner-response-diagnostic.json` gerçek kesilmiş yanıt/metadata'yı korur. Uygulama düzeltmesini kod asistanı yazmadı veya birincil modele somut çözüm ipucu vermedi.
- **Gerçek model-only sonuç:** API güncellemesi sonrası yeni gerçek Qwen3.8 kaynak-alıntılı incelemesi ve Qwen3.6 uygulama güncellemesi `9bca12fed52d425b9fcac69dd26bba12` ile kalan hata düzeldi. Değişmeyen 15 test ayrı onaylı `03aa1e3dd98a462bbd65d9390134819c` ve `251b3b57fab641888de3e7168b23b78f` ile geçti (0 failure/error/skip). Önceki 15 kesin CLI girdi/çıktısı ve 60 ek normalize alan/status/sıra kombinasyonu 75/75 geçti. Test hash'leri önceki bölümle aynı; uygulama elle düzeltilmedi, testler gevşetilmedi, paketlenmedi.
- **Regresyon ve sınır:** 547 test + 616 alt test, ilgili Ruff ve diff kontrolü geçti; alıntı reddi/rapor kaydı, önceki diff aktarımı, uzun Unicode traceback bütçesi, iki onarım sınırı ve geçerli JSON görünse de kesilmiş planner yanıtı kapsanır. Pylance son sorguda yardımcı/proje dosyalarında tanı döndürmedi; ajan/backend sorgusu mevcut workspace import çözümleme (`reportMissingImports` / `reportMissingModuleSource`) ve mevcut MCP `session` için `reportPossiblyUnboundVariable` bildirdi. Bu iki dosya için temiz editör denetimi iddia edilmez. Tek native Qt mesajı kabulü ve bütün görevlerde otomatik güvenilirlik açık kalır.

### C5 gerçek Qt tek-mesaj denemesi — yanlış test beklentisi ve son yanıt bütçesi

- **Gerçek native akış:** mevcut ana Qt PID 18300 ve pil paneli PID 22948 korunarak ayrı görünür üretim `ChatPage` açıldı. QTest gerçek Gönder düğmesine bir kez ve yalnız hedef projeye ait native onay düğmelerine bastı; API/model/ChatAgent/arka plan işçisi/onay penceresi mock edilmedi. Tariften yerel Qwen3.6 [qt_time_report](projects/qt_time_report/README.md) uygulamasını, sekiz testi ve README'yi oluşturdu (`92dd10e6b8104f78b54262645408dbe9`); ağsız ortam `26eb715f8ddc456c9e0cbaea626d3b8b`.
- **Yeni gerçek bulgu:** ilk sekiz testten ikisi başarısızdı. Qwen3.8 bağımsız kaynak-alıntılı raporu iki farklı durumu ayırdı: Unicode `\d` ile ASCII dışı rakamların kabulü gerçek uygulama hatası; `01:30 + 02:45` için 150 bekleyen test ise yanlış (doğru toplam 255). Qwen3.6 yalnız uygulamadaki Unicode kontrolünü `9c8e844add854e0babbe6f15e033a904` ile düzeltti; testler değişmedi, 7/8 kaldı. İkinci inceleme de yanlış test beklentisini teşhis etti. Kod asistanı uygulama veya test çözümü yazmadı.
- **Yanlış teste uydurma engeli:** önceki rapor bunu metinde söylese de akış tekrar uygulama onarımı istiyordu. İncelemeci artık ilk kabul gereksinimlerini de görür ve zorunlu `test_conflicts` alanında somut test/sözleşme çelişkisini bildirir. Kaynak-alıntılı böyle rapordan sonra birincil modele düzeltme çağrısı/yazma yapılmadan açık hatayla durulur; testler otomatik değiştirilmez. Bu semantik model görüşüdür, bütün yanlış testleri yakalama garantisi değildir.
- **Native koruma kabulü:** yeni gerçek Qt turunda `bb595318f2f3411d89bd477e3bee3ab6` testi, Qwen3.8'in doğru test kimliği/hesabı/kaynak alıntısı ile çelişki raporu ve yalnız bir test onayı gözlendi; uygulama/test yazması yapılmadı. Değişmeyen uygulama için bağımsız tam CLI sözleşmesi kontrolleri 31/31 geçti; bu, yanlış self-test'in geçmesi veya tam teslim sayılmadı.
- **Ayrı son-yanıt hatası kanıtı:** ilk native tur sonunda `502 Model provider returned no chat content` alındı, son yanıt/sohbet kaydı oluşmadı. Aynı araç kanıtıyla gerçek backend/Ollama çağrısına yalnız gözlemci eklenen bir tanı tekrarında son normal-chat yanıtı `prompt_eval_count=2675`, `eval_count=1421`, `done_reason=length`, boş content döndürdü: eski varsayılan 4096 bağlamı doluyordu. Önceden düzeltilen 16K yalnız JSON planlayıcıdaydı, son metin çağrısına uygulanmıyordu.
- **Kalıcı son-yanıt düzeltmesi:** yalnız araç sonuçlu yerel ajan özetlemesinde 16.384 bağlam / 4.096 çıktı / `think=false` açıkça gönderilir. Ollama adaptörü mevcut bounded seçeneklerini normal ve akışlı chat'te de iletir. Sıradan sohbetin varsayılanları, bulut ve FreeLLMAPI değişmez. Yerel `done_reason=length`, içeriği kısmen varsa da açık bütçe hatasıdır; başarılı sohbet diye kaydedilmez. API tek başına yeniden build/deploy edildi ve sağlık doğrulandı.
- **Kanıtlar:** yerel `data\program-builds\native-chat-acceptance.json`, `native-conflict-acceptance.json`, `native-time-independent.json`, `native-completion-diagnostic.json`. İlk kabul koşusunun gözlemci stdout'u Unicode yazdırırken hata verdi; sinyal verisi JSON raporunda korunmuştu, üretim akışı etkilenmedi. Sonraki gözlemcide UTF-8 açık ayarlanarak giderildi.
- **Düzeltme sonrası gerçek native sonuç:** `58fc126684c34c7189708193dcc30fb7` testi ve yeni Qwen3.8 çelişki raporu sonrası hiçbir yazma yapılmadı; Qwen3.6 son Türkçe açıklamayı üretti. Qt doğru **BAŞARISIZ / doğrulanamadı** önekini gösterdi, sohbet `63b30c00-48d6-4948-8e0b-33d1b1db05c4` olarak kaydedildi; API'den aynı iki kullanıcı/asistan mesajı geri okundu. Bu, yanlış testte güvenli duruş + son yanıt/süreklilik kabulüdür; sıfırdan üretilen programın tamamlanmış başarılı teslimi değildir. `native-conflict-after-budget.json` içinde saklanır.
- **Test koruması ve regresyon:** ilk native oluşturma onayındaki diff'ten yeniden hesaplanan `test_app.py` SHA-256 `e6b8397f73cc5d387f1f3b1a4ea24972db68f00a51f07f94a50f5ce18d066929` mevcut baytlarla aynıdır. Son tam baseline **550 test + 619 alt test** geçti; ilgili üretim/yeni test Ruff kontrolleri geçti. Daha önceki `test_ollama.py` fake sınıflarında bulunan `PYI034`/`RUF012` uyarıları değiştirilmedi; yalnız o dosyanın scoped lint'inde hariç tutuldu. Diff whitespace kontrolü ve Ollama yardımcı Pylance tanısı temizdir.
- **Başarılı native yol da doğrulandı:** mevcut model üretimi `invoice_audit`, gerçek Qt sayfasında tek mesajdan `b746087be0514eb59b4bdf844178d2fd` ve `7e353cdd8f684dc4b377fa8c52dff1e2` ayrı native onaylarıyla iki kez 15/15 geçti. Yeni son yanıt çağrısı tamamlandı; Qt **GEÇTİ** önekini gösterdi, sohbet `2d0fbbca-86ed-4c1b-a39a-2a06c28aec04` olarak kaydedilip API'den geri okundu. Bu turda dosya/ortam değişikliği veya incelemeci çağrısı gerekmedi. `native-invoice-success.json` kanıtıdır. Bu mevcut projeyi test etme kabulüdür; sıfırdan üretim → kusursuz testler → paket tesliminin tek native mesajda başarısı olarak sunulmaz.

### C3/C5 başarı kanıtı ve kaynak bütünlüğü sıkılaştırması

- **Önce yeniden üretildi:** önceki turdan kalan test/paket sonuçları ve adı benzer MCP sonuçları güncel doğrulanmış başarı sayılabiliyordu. Gerçek unittest sırasında uygulama/test dosyası değiştirme, ekleme ve silme de ham test özeti başarılıysa kabul ediliyordu. Yeni regresyonlar düzeltmeden önce başarısız oldu; yalnız kanıtlanan bu yollar değiştirildi.
- **Güncel ve doğru araç kökeni:** test/paket başarı öneki yalnız bu turdaki tam kanonik Windows host API araç adlarıyla üretilir. Eski sonuçlar model bağlamında kalabilir ama güncel başarıyı onaylayamaz; benzer MCP adları reddedilir. Doğrulama, model için son sekize indirilen bağlamdan ayrı güncel-tur sonuçlarını kullanır.
- **Kaynak bütünlüğü:** `project_test` ve `project_package`, işlem öncesi/sonrası tüm `.py` yollarının SHA-256/boyut kayıtlarını karşılaştırır. Değişiklik ham testler geçse bile genel başarıyı geçersiz kılar; testte inceleme/onarım çağrısı yapılmadan durulur, paketlemede `create_delivery` çağrılmaz. En fazla sekiz değişen yol ve açık atlanma sayısı ile `integrity_error`, uzun çıktıda da korunur; onay önizlemesi kapsam uyarısını gösterir. Otomatik geri alma yoktur, kısmi çıktılar kalır. Bu snapshot karşılaştırması sandbox/sürekli izleme değildir; Python dışı dosyaları ve işlem içinde değiştirilip geri alınan kaynakları garanti etmez.
- **İncelemeci iddiaları:** her `test_conflicts` kimliği gerçek güncel `failure_details` listesinde olmalı, tekrarsız olmalı ve ilgili test modülünün tam kaynağından doğrulanmış alıntıya bağlanmalıdır. Uydurma kimlik, tekrar ve yalnız uygulama alıntısı yazmadan reddedilir; iç içe test modülleri/Windows dosya adı harf farklılıkları kapsanır. Bu bağlama denetimi model yorumunun anlamsal doğruluğunu kanıtlamaz.
- **Gerçek değişmeyen proje kabulü:** üretim `ChatAgent` + gerçek API/Ollama/Windows host hattında Qwen3.6 `invoice_audit` projesini iki ayrı dar kapsamlı harness onayıyla 15/15 test etti: `e9d83b735e2846ada1bc83330bbdca87`, `a8cec4fbfff044b0a1fca58977774c03`. Her iki yeni `source_integrity.unchanged=true`; uygulama/test SHA-256 kayıtları önce/sonra aynı. Bu yeni native UI denemesi değil, gerçek ajan/host regresyon kabulüdür.
- **Gerçek yanlış-test duruşu:** `qt_time_report` testi `b42598edfa414d37923db54fad404f3c` yine 7/8 kaldı. Gerçek Qwen3.8 raporu `test_app.TestApp.test_valid_input` ve test kaynak alıntısıyla 150 yerine 255 gerektiğini açıkladı; yeni kimlik/modül doğrulaması geçti. Bir test onayı dışında yazma/onarım yapılmadı; son yanıt başarısızlığı doğru bildirdi. İki proje için kaynak hash'leri değişmedi, ana Qt PID 18300 açık kaldı. Yerel kanıt `data\program-builds\reliability-hardening-acceptance.json` içindedir.
- **Regresyon:** son tam backend/desktop koşusu **557 test + 632 alt test** geçti; değişen beş Python dosyasında Ruff temizdir. Eski/benzer araç sonucu reddi, gerçek test sırasında kaynak ekleme/silme/değiştirme, paketlemede ZIP çağrısının engellenmesi, onarımdan önce duruş, uzun çıktıda hata kanıtı, açık atlanma sayısı ve iç içe test kimliği/alıntı eşleştirmesi kapsanır. `program_projects.py` ve `program_repair.py` için Pylance tanısı yoktur. Geçici kabul betiği temizlendi; uygulama/test kaynakları elle değiştirilmedi.
- **Sınır:** sıfır hata veya bütün programların güvenilir üretimi iddia edilmez; sıfırdan başarılı tek native mesaj → paket teslimi kabulü açık kalır. Açık Qt yeniden başlatılmadı; yeni masaüstü kodu sonraki açılışta yüklenir.

### C5 aynı kontrol merkezi Sohbet sayfasında tek-tur üretim ve ZIP teslimi

- **Eksik yol önce kanıtlandı:** mesaj aynı turda `project_package` istese de başarılı `project_test` / ikinci test ardından ajan koşulsuz duruyordu. Yeni regresyon 4 yerine 2 host çağrısı gözleyerek başarısız oldu. Ayrı bir arayüz/ajan sayfası eklenmedi; mevcut `ChatPage` → `ChatAgent` yolu düzeltildi.
- **Kalıcı ve sınırlı devam:** ilk araç oluşturma/güncelleme/ortam/test iken açık `then project_package` / `sonra project_package` / `ardından project_package` sırası istenirse sabit PyInstaller sürümü ilk testten önce ayrı onaylı proje ortamına dahil edilir. Paket listesinin bunu içermesi hem planner şemasında hem host çağrısından önce denetlenir. Ortam başarısızsa, test/ikinci test başarısız veya reddedilmişse paketleme yoktur. Paketlemeden yalnız söz etmek/reddetmek otomatik kurulum başlatmaz. Aynı proje, sekiz eylem, iki onarım ve her gerçek işlem için ayrı onay korunur; doğrudan paketleme ve yalnız test isteminin davranışı korunur.
- **Gerçek native kabul:** üretim `MainWindow` içindeki mevcut `ChatPage`, gerçek QTest Gönder/onay düğmeleri, arka plan işçisi, API/Ollama ve Windows host kullanıldı; agent/API/model mock veya override edilmedi. Qwen3.6 yalnız tariften `qt_number_report` uygulamasını, sekiz unittest testini ve README'yi yazdı; kod asistanı uygulama/test çözümü vermedi veya dosyaları düzeltmedi. Ana Qt PID 18300 kapatılmadı; kabul için güncel üretim kontrol merkezi penceresi kullanılıp iş sonunda kapatıldı. Bu yeni bir ürün bölümü değildir; açık eski pencere yeni masaüstü kodunu sonraki açılışta yükler.
- **Tek Gönder, beş onay:** oluşturma `ad2e93d55dbd48a8aa969751aa1d38b7`, ardından ortam, iki ayrı test ve paketleme. Her test 8/8 geçti; paketleme testleri tekrar çalıştırdı, `--help` açılışı 0 çıktı ve kaynak bütünlüğü doğrulandı. Hiçbir uygulama/test onarımı gerekmedi; Qwen3.8 hata incelemecisi ayarı açık, başarılı yolda teşhis çağrısı beklenmez. Son model yanıtı tamamlandı; sohbet `a9ad786d-aedc-47d4-b0ad-70d4cb7d6b2e` API'den iki gerçek kullanıcı/asistan mesajıyla geri okundu.
- **Teslim ve bağımsız kontrol:** `data\program-builds\qt_number_report\8a1ab431c0da438586dbfe75b482a7e6\qt_number_report-windows.zip`; SHA-256 `f092814f5f4b98b2ffa77f6ffca84756e40135066c5de08528e7f35b44a7677e`. ZIP CRC/tam manifest listesi/boyut/hash'leri doğrulandı. Ayrı geçici klasöre çıkarılan EXE, çocuk PATH'inde Python klasörü olmadan 25 sabit/seeded geçerli tam JSON çıktısı + 15 geçersiz JSON/değer + eksik dosya/argüman + yardım olmak üzere **43/43** kontrolü geçti. Üretim diff'inden çıkarılan iki Python dosyası hash'i teslim/kabul sonunda aynıdır; geçici çıkarma klasörü temizlendi.
- **Gözlemci hatası ayrımı:** ilk harness yanlışlıkla UI'deki bütün `page.messages` uzunluğunu 2 bekliyordu; gerçekte kullanıcı + beş araç izi + asistan vardı. Bu yalnız gözlemci assert hatasıydı; son Türkçe yanıt, paket ve kalıcı sohbet zaten oluşmuştu. Değişmeyen native kayıt doğrulanarak bir kullanıcı/bir asistan + beş araç izi ve API'deki iki diyalog mesajı ayrıldı; yeni model turu, yeniden üretim veya dosya değiştirerek geçirme yapılmadı. Açıklaması `data\program-builds\native-single-chat-delivery.json` içindedir; `.png` gerçek kontrol merkezi sonucunu gösterir.
- **Sonuç/sınır:** bu örnek için sıfırdan tek native tur → model testleri → EXE/ZIP kabulü artık geçti. Önceki süre programının yanlış testi değiştirilmedi ve 7/8 durumu geçmiş kanıt olarak korunur. Genel otomatik güvenilirlik, her tarif/model, GUI kalitesi, temiz başka PC, imzalama veya lisans uygunluğu tamamlanmış sayılmaz; sıfır hata iddiası yoktur.
- **Regresyon:** son tam backend/desktop koşusu **562 test + 638 alt test** geçti; değişen ajan/test dosyalarında Ruff ve `chat_agent.py` Pylance tanısı temizdir. Tek-tur teslim, ortam hatası/ikinci test hatası/onay reddinde duruş, sabit paketleyici zorunluluğu, paketlemeyi yalnız anma/reddetmede kurulum olmaması ve iki onarım sonrası sekiz adımda teslim kapsanır.

### C5 tariften model kodu ve doğrulanmış CLI teslimi

- **Üretim:** gerçek yerel `qwen3.6:latest`, açık Python/SQLite API ve CLI sözleşmesini tarif eden istemden yeni [stock_generated](projects/stock_generated/README.md) projesini oluşturdu: `inventory.py`, `app.py`, `test_inventory.py`, `README.md`. İstem kaynak kod içermiyordu; planner gerçek API araç şemasıyla çağrıldı, dosyalar `project_create` ayrı host onayı `a72e797408674a1d829c294cd012f2a6` ile yazıldı. Kod çalıştırılmadan incelendi; ağ/bulut/anahtar kullanılmadı. Uygulama ve modelin test/README dosyaları sonradan elle değiştirilmedi.
- **Aşamalı gerçek kabul:** ayrı onaylı temel ortam → gerçek `ChatAgent` test hattı; modelin altı testi ilk seferde geçti (`0e58fcaa561d4f649c9213e64587f83e`). Sonradan kod asistanının hazırladığı sabit `test_acceptance.py`, ayrı `project_update` onayı `8f3f30687cfe4da5b78183218a087a80` ile eklendi. Model bu sekiz testin içeriğini üretim sırasında görmedi. İkinci test `b10b296872ba41eda79de7574193d2a6`: 14 test, 0 hata/atlanan. API'de 75 toplama/7 ürün, negatifte değişmeme, CLI'de tam JSON alanları/değerleri, sıfır, eksik ürün, SQL özel/Unicode adları, geçersiz tamsayı, ayrı veritabanı ve yeniden açınca kalıcılık kapsandı.
- **Yakalanıp düzeltilen araç hatası:** modelin CLI testleri yeni Python alt süreci açınca üst sürecin `-B` bayrağı miras kalmıyordu; `inventory.cpython-312.pyc` oluşması sonraki snapshot'ı engelledi. Gerçek yeni regresyon önce bu hatayla düştü; `project_test` ortamına paketlemedeki gibi `PYTHONDONTWRITEBYTECODE=1` eklenince geçti. Yalnız bu kabulün bilinen tek `.pyc` dosyası ve boş önbellek klasörü temizlendi. Bu araç düzeltmesidir, model uygulama kodunun elle tamamlanması değildir.
- **Teslim:** ayrı `project_environment` paket/ağ onayı `7804e2c3057743b986f09cafa4ecec5d` ile `pyinstaller==6.16.0`; ardından `project_package` `a65073ae1a1f45a5a68b991c9cb8e59f`. Güncel 14 test, build, `--db :memory: get absent` sonlu açılışı ve ZIP doğrulaması geçti. Arşiv: `data\program-builds\stock_generated\2dfa413e64aa415e9b3d37ef71f8d206\stock_generated-windows.zip`; 18.872.857 bayt, manifestte 15 dosya. SHA-256 `5ba0a61d5e4ab68c36dc49b90e3df8ea9e44eb86aab9c590de5bdfdfdce63ece`.
- **Çıkarılan EXE:** ZIP CRC/tam dosya listesi/boyut/SHA-256 tekrar doğrulandı; geçici ayrı klasöre çıkarılan EXE, çocuk PATH'inde Python bulunmadan 16 tam çıktı/çıkış kodu kontrolünü geçti. Tekrar toplama, sıfır/negatif, eksik ürün, ondalık girdi reddi, SQL özel/Unicode adları, kalıcılık ve ayrı DB kontrol edildi. Dört model dosyasının hash'leri üretim sonrası kabulden teslim sonuna aynı kaldı; bağımsız test dosyası da değişmedi. Ayrıntılı yerel kanıt `data\program-builds\stock-generated-acceptance.json` içinde tutulur.
- **Regresyon ve sınır:** 532 test + 609 alt test, ilgili Ruff geçti; değişen üretim dosyasında Pylance tanısı yoktur. Bu tek Windows makinesinde aşamalı harness + gerçek API/ajan/host kabulüdür; tek Qt mesajında kesintisiz otomasyon/native UI kabulü değildir. Başlangıç uygulamasını model yazdı, istem/test onayları/bağımsız kabul testleri/paketleme ve çıktı doğrulamasını kod asistanı yürüttü. Bu örnekte uygulama onarımı gerekmedi; onarım ayrı `repair_acceptance` örneğinde doğrulanmıştır. Bütün modeller/istemler, temiz başka PC, GUI, imzalama/lisans uygunluğu veya kusursuz yazılım garantisi değildir. Kullanıcının açık Qt penceresi korunmuştur.

### C4 temel Windows konsol paketleme kabulü

- `project_package` Qt host formuna/ajan şemasına ayrı onaylı değişiklik olarak bağlandı. Normal test akışı otomatik paketlemez. Yönetici Qt, sahipsiz proje, eksik ortam, proje dışı/eksik/Python olmayan giriş noktası reddedilir. Dosya ağacı/hash yarış kontrolü korunur.
- `pyinstaller==6.16.0` yalnız projeye özel ortamda ayrı `project_environment` paket/ağ onayıyla kurulur. Paketleme kendi kendine kurulum/indirme yapmaz; kurulu sürümü kontrol eder ve paket/sürüm/lisans metadata envanteri yazar. Metadata hukuki uygunluk onayı veya tam transitif lisans doğrulaması değildir; dağıtmadan gerçek lisanslar incelenmelidir.
- Güncel unittest → konsol/onedir build → sonlu CLI açılışı aynı süre/Windows Job Object ağacı içindedir. Test yok/tamamı skipped/başarısız test build'i durdurur. Sonraki gerçek EXE/rapor, sıfır açılış kodu, tamamlanmış ve iptal edilmemiş süreç başarı şartıdır. Sonuçta EXE yolu/hash ve yapılandırılmış kanıt uzun çıktıda da korunur.
- Her deneme ayrı `data\program-builds\<ad>\<benzersiz-kimlik>` altında kalır; kaynak/spec/build dosyaları karıştırılmaz. Gerçek denemede alt unittest sürecinin `__pycache__` oluşturduğu görüldü; `-B` ve alt süreçlere `PYTHONDONTWRITEBYTECODE` eklenerek kaynak ağacının değişmemesi tekrar doğrulandı. Testte oluşmuş yalnız bilinen iki bytecode dosyası ve boş klasörü temizlendi.
- **Gerçek kanıt:** elle yazılmış [exe_smoke_demo](projects/exe_smoke_demo/README.md) iki unittest'i geçti; EXE `--self-test` ile `EXE_SUM=42` yazıp exit 0 verdi. Başarılı işlem `0b5b952f7c9f4b86834211619012adc3`, çıktı `data\program-builds\exe_smoke_demo\2112c09aa2134f21acc1f4ca1881efb6\dist\exe_smoke_demo\exe_smoke_demo.exe`. EXE SHA-256 ve bağımlılık raporu doğrulandı; kaynak ağacı aynı kaldı. Eksik PyInstaller'ın başarısız sayılması, bozuk kaynak/testin build'i durdurması, gerçek bir saniyelik timeout ve gerçek iptal ayrıca doğrulandı; kaynak sonra kendi onaylı güncellemesiyle eski haline getirildi.
- **Native Qt:** yeni paketleme formu gerçekten açıldı; giriş/argüman/180 saniye payload'ı ve ortak onay hattına yönlenmesi, ajan şeması ve salt-okunur otomatik izin listesinde olmaması doğrulandı. Host form sayısı 31 oldu. Mevcut kullanıcı penceresi/giriş alanları korunur, yeni özellik sonraki Qt açılışında yüklenir.
- **Regresyon:** 490 test + 598 alt test, ilgili Ruff, editör hata kontrolü ve diff kontrolü geçti. Başarısız manuel host paket/test sonucunun formda veya sohbet/kalıcı özette başarı etiketi almaması da düzeltildi ve test edildi. Dosya bulunmaması, yanlış giriş, onay reddi, benzersiz çıktı, eksik paket, uzun kanıt, başarısız açılış, timeout, iptal ve ajan başarı/başarısızlık raporu kapsanır. Pylance dosya sözdizimi aracı yeni dosyayı kullanıcı dosyası olarak bulamadı; ayrı editör sorun sorgusu değişen dört üretim dosyasında hata bildirmedi, yürütme testleri geçti.
- **Sınır:** bu temel Python konsol/onedir kabulüdür; bütün klasör birlikte taşınır. Kalıcı GUI, özel veri/hook/spec, tek dosya, imza/kurulum sihirbazı ve diğer diller açık kapsam dışıdır. Build hook/test/EXE kullanıcı yetkisiyle çalışır; sandbox/ağ izolasyonu değildir. Kısmi çıktı ve yan etkiler iptalde geri alınmaz. Elle yazılan örnek C5 bağımsız model başarısı sayılmaz; B7 canlı MCP sürekliliği de açık kalır.

### C4 doğrulanmış taşınabilir ZIP teslimi

- Mevcut ayrı onaylı `project_package` sonuna ZIP teslimi bağlandı; yeni otomatik kurulum/çalıştırma izni yoktur. Başarılı onedir uygulamanın tüm dosyaları, bağımlılık raporu ve göreli yol/boyut/SHA-256 listesi tek ZIP'te toplanır. Work/spec/kaynak/işlem logları ve geliştirme ortamı dışarıda kalır; uygulama içine gömülen veri/metadata paylaşmadan incelenmelidir.
- 5000 dosya/dizin ve toplam 512 MiB kaynak sınırı, akış halinde okuma/hash ve ZIP içinden tekrar hash doğrulaması vardır. ZIP yeniden sıkıştırılmadan yazılır; sessiz kesme yoktur. Link/junction/hardlink reddedilir. Mevcut arşiv sessizce ezilmez; dosya değişirse hata döner. SHA-256 imza/özgünlük/zararsızlık veya lisans uygunluğu kanıtı değildir.
- Aynı toplam paketleme süresi ve iptal koşulu ZIP aşamasını da kapsar; kısmi ZIP temizlenir. ZIP başarısız/iptal/zaman aşımı ise EXE üretilmiş olsa bile paketleme başarılı raporlanmaz. Arşiv yolu/hash ve liste yolu uzun model bağlamında yapılandırılmış olarak korunur.
- **Gerçek kanıt:** `operation_id=0a70a34da15d461dad056dd5ee4cf26e`, `data\program-builds\exe_smoke_demo\9f75963422bd43a39b379e8cd67ed6ce\exe_smoke_demo-windows.zip`, 17.119.165 bayt. SHA-256 `d33ecfaa15cb6428f4c9f8a4e5cffcec8f11ce5f8c38fe6b550d8ae5b049e6ee`; 13 dosya listesi ve bütün hash'ler doğrulandı. Bağımsız geçici klasöre çıkarılan EXE, çocuk PATH'inde Python olmadan `EXE_SUM=42`, exit 0 verdi; kaynak ağacı aynı kaldı. Aynı Windows makinesinde yapılan testtir, temiz başka makine kabulü değildir; örnek elle yazılmış olduğundan C5 bağımsız model başarısı sayılmaz.
- **Regresyon:** 524 test + 598 alt test, ilgili Ruff ve diff kontrolü geçti; Pylance iki üretim dosyasında hata döndürmedi. Tam ZIP listesi/hash/boyut, özel log/kaynak dışlama, tam byte sınırı ve aşım reddi, link/hardlink, bozuk hash/CRC, iptal ve ZIP süre aşımı testleri var. Gerçek Qt formunda teslim JSON'u ve sohbetin kısaltılmış araç kanıtında arşiv yolu/hash'in korunduğu doğrulandı; dosya kendiliğinden açılmadı/yüklenmedi. Kullanıcı penceresi korunur, yeni özellik sonraki Qt açılışında yüklenir.

### Cline hesabı / Qt bağlantısı

- Resmî Windows x64 Cline CLI **3.0.74**, sabit `tools\cline\package-lock.json` ve npm integrity doğrulamasıyla `.tools\cline` içine kuruldu. `setup-cline.ps1` proje Node hash'ini ve gerçek CLI sürümünü doğrular; global kurulum yapılmaz.
- Qt model listesine **Cline (hesabım / ACP)**, ayrı resmî hesap giriş terminali, çalışma klasörü seçimi ve Sistem sayfasına kur/doğrula düğmesi eklendi. Mevcut VS Code hesabının gizli verileri kopyalanmaz; profil `.tools\cline-state` içindedir.
- ACP 1 akışı, metin/araç izi, tek çağrılık izin, Plan/Act ve ortak sohbet kaydı bağlandı. `--auto-approve false` sabittir; kalıcı izin verilmez. Bulut/klasör/geçmiş aktarımı her turda ayrıca onaylanır; ekler ve manuel araç sonuçları sessizce gönderilmez. İptal/süre/çıktı sınırı ve Windows Job Object temizliği uygulanır. Cline sandbox değildir.
- **Gerçek kanıt:** CLI `--version` 3.0.74; native binary ile istem/kimlik bilgisi göndermeden ACP el sıkışması geçti. Native Qt'de Cline seçeneği ve giriş kontrolleri gerçekten görünür oldu, pencere normal kapandı. Yetki/ret/mod/araç sonucu/iptal/hata/geçmiş uçları yerel ACP fixture'ıyla doğrulandı. Son tam paket **426 test + 548 alt test**, **16 Node testi**, ilgili Ruff, PowerShell sözdizimi ve diff kontrolü geçti.
- **Kullanıcı adımı / doğrulanmayan:** sonraki kontrolde oturum hazır hale geldi; gerçek model yanıtı aşağıda açıklanan bakiye engeli nedeniyle doğrulanmadı. Giriş gerekirse **Cline hesabını bağla** düğmesini kullanın; bakiye/faturalandırma işlemleri kullanıcı tarafından resmî Cline arayüzünde yapılır. Bu entegrasyon C5'in bağımsız yerel model kabulünü veya diğer açık işleri tamamlandı yapmaz.

### Cline genişletme ve gerçek oturum kontrolü

- Sohbete **Cline bağlantısını doğrula** eklendi: gerçek ACP el sıkışması → `session/new` → yalnız model kataloğu. Bu kontrol model istemi/geçmiş göndermez; araç izinlerini reddeder, iptal edilebilir ve sohbet mesajı oluşturmaz. Kurulum, oturum hazırlığı ve gerçek model yanıtı ayrı durumlar olarak gösterilir.
- Qt içinden açık Cline model seçimi eklendi. Modern ACP `session/set_config_option` yalnız model kategorisi için; eski `session/set_model` yolu da desteklenir. Gruplu modeller açılır; geçersiz/yinelenen kimlikler reddedilir. Model yeni oturum kataloğunda bulunmazsa veya modern seçim onayı eşleşmezse istem gönderilmez; sessiz model değiştirme yoktur. Otomatik izin/diğer özel yapılandırmalar açılmaz.
- Klasör ve model tercihi yerel Qt INI ayarında hatırlanır; genel Ayarlar ekranı bunları kaybedecek yeni bir nesne üretmez. Kimlik bilgileri ayrı Cline profilinde kalır; bu işte okunmadı/kopyalanmadı. Tamamlanmış gerçek yanıtta Cline'ın seçili modeli metadata'ya ve doğrulama etiketine eklenir.
- **Önceki deneme:** `session/new -32000` sonrasında resmî giriş konsolu açılmıştı; o hata tek başına “yanlış şifre” olarak yorumlanmadı. **Güncel gerçek sonuç:** `session/new` başarılı, 307 model katalogda var. Varsayılan model ve açıkça seçilmiş `recursive/flint-v1.0:free` ile boş klasörde, geçmişsiz/izinsiz kısa yanıt girişimleri `session/prompt -32603` verdi; sağlayıcının `insufficient balance` sinyali tespit edildi. Oturum hazır fakat gerçek model yanıtı/bakiye erişimi doğrulanmış değil. Ücretsiz model etiketi bu engeli aşmadı; başka modellerle otomatik deneme/ödeme yapılmadı.
- **Regresyon:** 440 test + 557 alt test, ilgili Ruff ve diff kontrolü geçti; gerçek native Qt genişletilmiş kontrolleri göründü ve test penceresi normal kapandı. Pylance dosya sözdizimi temiz; `_cline_turn` için çözülen çağrı uyumlu, `ClineClient.run` için araç çağrı sitesi çözemedi. Pylance ortamında `desktop.*` importları `reportMissingImports` verdi; editör tip kontrolünün tamamen geçtiği söylenmez. Gerçek terminal testleri proje ortamında geçti.
- **Kısa yanıt testi ve güvenli hata ayrımı:** Qt'ye **Cline kısa yanıt testi** eklendi. Açık onayla seçili modele sabit istem; boş geçici klasör, geçmiş/ek yok, bütün araç izinleri ret; tam `CLINE_CONNECTION_OK`, tamamlanmış tur ve araç çağrısı olmaması şartı. İptal/hata veya farklı çıktı başarı sayılmaz; ortak sohbete kaydedilmez. Ham sağlayıcı hatası/kimlik bilgisi gösterilmeden bilinen bakiye/giriş sinyalleri sabit Türkçe yönlendirmeye çevrilir; bilinmeyen hatada kod/aşama korunur.
- Açık hesap adımı: resmî Cline üzerinden kredi ve kişisel/kurum faturalandırma seçimini kontrol et → **Cline kısa yanıt testi**. Hesap engeli giderilmeden kaynak kodunu buluta göndererek kabul testi yapılmaz. Bu engel yerel Ollama akışını değiştirmez.
- **Güncel regresyon:** 446 test + 565 alt test, ilgili Ruff ve diff kontrolü geçti. Gerçek native Qt penceresinde yeni kısa yanıt testi ve Cline kontrolleri görünür/etkin doğrulandı; test penceresi normal kapandı. Pylance sohbet dosyası sözdizimi temiz; yeni `cline.py` dosyası Pylance tarafından bulunamadığı için onun editör analizi doğrulanmış sayılmadı; gerçek Python testleri geçti.

### NVIDIA NIM sağlayıcısı

- Mevcut bulut sağlayıcı sözleşmesine `nvidia` eklendi: resmî `https://integrate.api.nvidia.com/v1`, varsayılan `meta/llama-3.1-8b-instruct`; `cloud:nvidia` açık seçimi ve “nvidia'ya sor / nim kullan” yönlendirmesi. Katalog, anahtar saklama/silme, modeller, sohbet ve çoklu danışma aynı mekanizmayı kullanır. Otomatik yerel seçim NVIDIA'ya geçmez; ücretsiz erişim iddiası yoktur.
- Qt Ayarlar'a NVIDIA Build bağlantısı, maskeli anahtar, model seçimi, onaylı kayıt/katalog ve sabit kısa yanıt testi eklendi. Anahtar Qt INI/sohbete yazılmaz; mevcut API sunucusunun sağlayıcı deposunda kalır (şifreli kasa değildir). Anahtar/model kaydı yanıt doğrulaması sayılmaz. Test geçmişsiz/dosyasız/araçsızdır; tam sabit çıktı ve `stop` bitişi şarttır. Genel bulut bağlam/araç onayları korunur.
- Ek SDK/bağımlılık veya yeni anahtar dosyası oluşturulmadı; `.ai-next-cloud.env.example` yalnız boş NVIDIA örneklerini içerir. Mevcut gizli dosyalar/VS Code/Cline sırları okunmadı veya taşınmadı.
- Gerçek hesap doğrulaması kullanıcı anahtarını maskeli alana kaydettikten sonra yapılabilir; anahtarsız NVIDIA yanıtı başarılı gösterilmez.
- **Doğrulama:** 457 test + 574 alt test, ilgili Ruff ve diff kontrolü geçti. Mock HTTP testleri resmî NVIDIA adresi/Bearer başlığı/model gövdesi, katalog, eksik anahtar, 401/403/402/429/500 ve anahtar kaldırmayı doğruladı. Qt testleri maskeli alan, ret, geçmişsiz sabit test ve mükerrer ücretli isteğin engellenmesini kapsıyor. Yalnız API servisi yeniden build edildi; canlı katalog 13 → 14 sağlayıcı ve `nvidia` döndürüyor, eksik anahtar `auth_required`, kayıtlı sağlayıcı sayısı 0 olarak korundu. `/data` hâlâ `deeppanda-ai-next_ai_data`; volume silinmedi/taşınmadı. Gerçek native Qt'de NVIDIA ayar alanları ve sohbet model girdisi görüldü.

### Sohbetten Python süreç iptali

- Durdur/Esc sinyali artık Qt ajanı → yalnız yerel `DesktopApiClient.host_action` → WindowsHost → `python_run` / `project_environment` / `project_test` → yürütücüye aktarılır. HTTP payload'una veya model argümanlarına iptal nesnesi eklenmez; önizleme ve tek kullanımlık onay koşulları korunur. Diğer araçlar mevcut senkron davranışını sürdürür.
- Yürütücü yaklaşık 100 ms denetim aralığıyla iptali kontrol eder; Job Object kapandıktan ve ana süreç/okuyucular bittikten sonra döner. Başlatmadan önce veya Job Object ataması sırasında iptal edilirse kullanıcı kodu serbest bırakılmaz. İptal başarı/zaman aşımı değildir: işlem kaydı `cancelled`, stdout/stderr korunur; test `passed=false`, ortam `environment_ready=false`. Otomatik tekrar/düzeltme başlatılmaz. Dosyalar ve kısmi ortam kurulumu geri alınmaz; manuel araç formlarında ayrı durdurma henüz yoktur.
- **Gerçek kanıt:** Windows ana/çocuk süreç testi iptal sonrasında gecikmeli dosya yazımının gerçekleşmediğini ve çocuğun sonlandığını doğruladı. Gerçek unittest ve sanal ortam oluşturma sırasında iptal edildi; test scratch temizlendi, yarım ortam başarı olarak kaydedilmedi. Native Qt'de gerçek Durdur düğmesi çalışan ajan/host çağrısında tıklandı: çıktı korundu, kayıt `cancelled`, arayüz yeniden kullanılabilir, çocuk dosya yazmadı; tıklamadan temizliğe 2 saniyeden kısa sınır doğrulandı. Bu genel gecikme garantisi değildir.
- **Regresyon:** 465 test + 577 alt test, ilgili Ruff ve diff kontrolü geçti. Pylance imza kontrolü yürütücü için çağrı sitesi çözemedi; editör tip doğrulaması iddia edilmedi, gerçek testler proje yorumlayıcısında geçti. C5 bağımsız model başarısı, paketleme ve B4–B7 ayrı açık kalır.

### B4 gerçek çoklu ajan kabulü ve yanıt doğrulaması

- Mevcut altı Ollama modeli indirimsiz/hesapsız kullanıldı. Otomatik alan yönlendirmesi planlayıcı/bağlam/sentez için `qwen2.5-coder:7b`, geliştirici/inceleyici için `qwen3.6:latest` seçti. Basit toplama fonksiyonu taslağı isteği gerçek HTTP akışında beş aşama ve sentez yanıtıyla önce 106,25 saniyede, güncel sıkı kontrollerden sonra 37,55 saniyede tamamlandı; bu süreler performans garantisi değildir.
- Eksik `done`, `done=false`, kesilmiş yanıt, fazladan JSON alanı ve 6000 karakter üzerindeki aşama çıktıları artık açık hatayla durur. Eski sessiz karakter kesme kaldırıldı. Bu değişiklikler öncesinde üç hata sınıfı başarısız regresyonla yeniden üretildi; düzeltmeden sonra bütün geçersiz durumlarda sonraki aşamaların çağrılmadığı test edildi. Üçüncü aşama sağlayıcı hatasında duruş da fixture testindedir; canlı sağlayıcı kasıtlı bozulmadı.
- Yalnız API servisi rebuild edildi; gerçek güncel HTTP denemesi `status=completed`, `local_only=true`, beş sıralı/dolu aşama, doğru rol modelleri ve son aşamayla aynı final yanıtı doğruladı. Açık onay olmadan HTTP 403 alındı. Modelden dosya/komut çalıştırması istenmedi; `tools_used=[]`. Kaynak proje/anahtarlar buluta gönderilmedi.
- **Regresyon:** 466 test + 585 alt test, ilgili Ruff ve diff kontrolü geçti. Bu sınırlı taslak kabulü tamamlandı; C5 bağımsız kod üretme/düzeltme, C4 paketleme ve B7 sohbet sürekliliği ayrı açık işlerdir.

### B7 yerel ek yolu sürekliliği

- Sohbete varsayılan kapalı, ayrı gizlilik onaylı **Bu sohbetin ek yollarını bu bilgisayarda hatırla** seçeneği eklendi. Kayıt yalnız yol referanslarıdır; dosya içeriği, araç sonucu/izi, kimlik bilgisi veya canlı MCP oturumu saklanmaz. Yollar API adresi ve oturum kimliğiyle ayrılır, sabit boyut/32 ek sınırı ve atomik yazma kullanılır; kayıt `data\chat-continuity` altında kalır.
- Yeni sohbette tercih kapalıdır; mevcut sohbetin tercihi ve yolları yeniden açılınca geri yüklenir. Yollar tekrar doğrulanır; kayıp/özel/link yolları uyarıyla atlanır, içerik ancak Gönder sırasında güncel sürümden okunur. Kaydı bozmak sohbet mesajlarının yüklenmesini engellemez; hata gizlenmez. İşareti kaldırma ve sohbet silme yerel kaydı siler; kaynak dosyalara dokunmaz.
- Sohbet değişiminde eski araç izi/bağlamı ve geri alma hedefi temizlenir; önceki soru/yanıt düğmeleri açılan sohbetten yeniden kurulur. Bulut aktarımı onayı, Cline/OpenJarvis ek kısıtları ve aktif turda oturum değiştirememe davranışı korunur.
- **Kanıt:** 474 test + 585 alt test, ilgili Ruff ve diff kontrolü geçti. Gerçek native Qt penceresinde varsayılan kapalı tercih → onaylı kayıt → yeni sohbet → eski sohbetin yollarını geri yükleme → işareti kaldırıp silme doğrulandı; dosya içeriğinin kayıtta olmadığı kontrol edildi. Testler API/oturum ayrımı, bozuk/kayıp/özel yol, disk hatası, ek kaldırma ve sohbet silmeyi kapsıyor. Mevcut kullanıcı penceresi/giriş alanları kapatılmadı; yeni Qt kodu sonraki açılışta yüklenir.
- Bu dilimde B7 tamamen kapanmadı; araç özetleri aşağıdaki sonraki dilimde eklendi. Ham araç izi ve turlar arası canlı MCP oturumu, paketleme ve C5 bağımsız model kabulü açık kalır.

### B7 yerel araç adı/durum özetleri

- Ayrı, varsayılan kapalı açık onay yalnız bundan sonraki araç sonucu gösteriminden geçen ad/durum özetlerini saklar. Ek yolu tercihi bağımsızdır. Son 100 özet tutulur; çıkarılanların sayısı gösterilir. Bilinen anahtar/giriş işlemleri hariçtir; araç adlarının özel sunucu/işlem adı içerebileceği açıklanır. Bu tam Cline/sağlayıcı günlüğü veya genel sır ayıklayıcısı değildir.
- API/oturumla ayrılmış atomik `.tools.json` yalnız ad/durum, sürüm ve çıkarılan özet sayısı içerir. Ham çıktı/komut/argüman/anahtar/dosya içeriği/geri alma hedefi kaydedilmez. Yeni sohbette kimlik oluşunca yazılır; mevcut oturum olayları anında kaydeder, sonraki iptal tamamlanmış işlemi yok saymaz.
- Yeniden açılışta ayrı salt-gösterim bölümü kullanılır; model/araç bağlamı, izin, geri alma veya yeniden yürütme oluşturulmaz. Opt-out yalnız özetleri siler; sohbet silme iki yerel kaydı da temizlemeyi dener, hata görünürdür. Boyut/şema ve ad/durum sınırları doğrulanır.
- **Native Qt kanıtı:** gerçek pencere → onay → araç çıktısı gösterimi → yeni sohbet → eski sohbetin özetini yeniden açma → opt-out silme geçti. Ham çıktı kayıtta yok; geri yüklenmiş araç bağlamı boş ve model mesajları değişmedi. Mevcut kullanıcı penceresi/giriş alanları korunur, yeni özellik sonraki Qt açılışında yüklenir.
- **Regresyon:** 482 test + 585 alt test, ilgili Ruff ve diff kontrolü geçti. Varsayılan kapalı durumda/onay reddinde kayıt oluşmaması, ham çıktı/argüman gizliliği, API/oturum ayrımı, bozuk/büyük kayıt, son 100 sınırı, ayrı opt-out, ilk yanıt kimliği, sonraki iptal ve disk/silme hatası testleri kapsandı. B7'nin ham iz/MCP kısmı ve C4/C5 açık kalır.

### B7 aynı açık sohbette canlı MCP sürekliliği

- Ayrı, varsayılan kapalı **MCP oturumlarını bu açık sohbette mesajlar arasında tut** tercihi eklendi. Açık onay yalnız bağlantı ömrüne aittir; her araç çağrısı yine ayrı onay ister. Tercih/sunucu oturumu/çıktı diske kaydedilmez; mevcut yol/özet tercihleri ve API mesaj kaydı bağımsızdır. Sunucunun kendi veri saklama davranışı bu mekanizmayla denetlenmez.
- Yeni `ChatMcpRuntime` tek thread/async sahip görev üzerinde MCP bağlamlarını açar, aynı görevde tekrar kullanır ve kapatır. En fazla dört sunucu, son ajan araç turundan sonra 10 dakika boşta sınırı vardır. İlk keşfe kadar süreç başlatılmaz; kapanan/süresi dolan oturum sessizce yeniden başlatılmaz.
- Opt-out/yeni sohbet/sohbet açma/etkin sohbet silme/iptal/tur hatası/pencere kapanışı bağlantıları kapatır. Arayüz kapanışı bekler; kapanış hatası açık gösterilir ve geçiş durur. Başarısız kapanış eski runtime'ın yeni bir taneyle sessizce üzerine yazılmasına izin vermez. MCP hatası veya onay reddi bağlantıları temizler; çağrı otomatik tekrarlanmaz. API/proje/MCP yapılandırma değişiminde eski durum başka hedefte kullanılmaz; kimlik bilgisi değişmeden önce bağlantıların kapatılması gerektiği açıklanır.
- **Gerçek kanıt:** izole FastMCP stdio fixture'ında farklı `ChatAgent` örneklerinin iki mesajı aynı PID/sayaçla 1 → 2 döndü; yeni runtime 1'den başladı. Her çağrı ayrı onay istedi. Kapanıştan sonra gerçek Windows PID çıkışı, gerçek devam eden çağrı iptali, onay reddi, araç hatası, yapılandırma değişimi, dört sunucu sınırı ve kısa test saatiyle idle sonlanması doğrulandı. Varsayılan kapalı yolun her turda yeni sayaç 1 üretmesi korundu.
- **Native Qt:** görünür MainWindow'da onaylı tercih → Gönder ile iki gerçek MCP turu (1, 2) → Yeni sohbet ile kapatma → yeni oturumda 1 → pencere kapanırken canlı stdio oturumunu bırakma geçti. Üç çağrı için üç ayrı izin istendi; testin yerel store'unda JSON oluşmadı. Kullanıcının açık penceresi/giriş alanları korunur, yeni özellik sonraki Qt açılışında yüklenir.
- **Regresyon:** 511 test + 598 alt test, ilgili Ruff ve diff kontrolü geçti; son koşuda arka plan Qt sinyal hatası yoktu. Gerçek stdio sürecinin ani kapanması tek başarısız çağrı olarak raporlandı, tekrar edilmedi; hızlandırılmış idle sınırı gerçek PID'yi de kapattı. Sor modu canlı işçi başlatmadı, etkin sohbet silme kapanışı bekledi. Pylance tanı sorguları dört üretim dosyasında hata döndürmedi; imza uyumluluk aracı çağrı sitesi çözemedi, bu kontrol için ayrıca doğrulama iddia edilmedi.
- **Hata sonrası ayrım:** aynı turda yeniden bağlanma/çağrı tekrarı yoktur. Temizlenen bağlantılardan sonra tercih etkin kalmışsa kullanıcının yeni mesajı yeni bir keşif/bağlantı başlatabilir; önceki sunucu durumu sürmüş sayılmaz. Süresi dolmuş/kapanmış runtime yeniden onay ister.
- **Sınır:** yalnız birleşik sohbet ajanı; Cline/OpenJarvis/manuel MCP paneli ve bütün üçüncü taraf tarayıcı/uzak sunucu kalıcılıkları bu kabulün dışında. Uygulamalar arası canlı oturum, otomatik yeniden bağlanma ve ham araç çıktısı kalıcılığı yoktur. Kapanış uzak işlemleri, ayrı tarayıcıları veya yan etkileri geri almaz; sandbox değildir. C5 bağımsız yerel model kod düzeltme kabulü hâlâ açık.

### GPU ölçümü hakkında yeni gözlem

10 Kasım'da proje içindeki yeni ortamdan aynı sentetik Ada MMA testi çalıştı: FP16 toplama **57,87 TFLOPS**, FP32 toplama **29,07 TFLOPS**, oran **0,502**. 8 Kasım'daki yaklaşık 1,00 oranıyla aynı değil. Bu ölçüm unlock'ın şu anda etkin olmayabileceğine işaret eder, ancak yeniden başlatma/güç/ayar koşulları sabitlenmiş gerçek açık/kapalı karşılaştırması yapılmadı. Önceki “unlock kesin çalışıyor” ifadesi kontrollü A/B kanıtı olarak kabul edilmemelidir. İlk birleştirme diliminde GPU ayarı değiştirilmedi; sonraki B1 çalışmasında GPU tahsisi aşağıdaki gibi tamamlandı.

### B1/B2 uygulama ve kanıt

- Ollama'ya varsayılan `gpus: all` eklendi; GPU'suz makineler için açık `docker-compose.cpu.yml` opt-out'u var. Yalnız Ollama aynı imaj ve aynı volume ile yeniden oluşturuldu; model indirilmedi. Container içi `nvidia-smi` GPU'yu gördü.
- `tools\benchmark-ollama.py` aynı Qwen 2.5 Coder 7B digest'i, istem, seed 42, 4096 bağlam ve 128 token sınırıyla ısınmadan sonra üçer koşu ölçtü. Medyan CPU **11,686**, GPU **50,149 token/sn**, yaklaşık **4,29×**; `ollama ps` **100% GPU**, toplam GPU belleği yaklaşık **4997 MiB**. Ham raporlar `data\model-evaluations\2026-11-10-ollama-{cpu,gpu}.json` altındadır. Bu sonuç büyük Qwen 3.6'nın tamamen VRAM'e sığacağı veya unlock kazancı olduğu anlamına gelmez.
- Yerel Qt hostuna **26. araç `python_run`**, toplam **133 form** eklendi; API/HTTP eklentisi yürütme yapmaz. Sabit proje Python'u, kod/hash/argüman önizlemesi, tek kullanımlık onay, 1–120 sn süre ve stdout/stderr başına 32.000 bayt sınırı uygulanır. Onaydan sonra kaynak yeniden okunarak çalıştırılmaz; onaylanan baytlar yürütülür. Başlangıç kapısı Windows Job Object'e bağlanmadan kodu bırakmaz; timeout ve normal bitişte alt süreçler de kapatılır. Bu sandbox değildir; dosya/ağ/sistem yan etkileri geri alınmaz, imports/diğer dosyalar kaynak hash'inin kapsamında değildir. Yönetici Qt'de kapalıdır.
- Gerçek sohbet ajanı mevcut zararsız test programı için `windows_host.python_run` seçti; işletmen onay işlevi yalnız beklenen kaynak hash'i/hedef/argüman/süreyi kabul etti. Araç **stdout `VERIFIED_SUM=42`, exit 0** verdi ve yanıt bu gerçek sonucu kullandı. Model yine aynı çağrıyı önerdi; mevcut tekrar koruması engelledi. Bu, B3 güvenilirlik işinin hâlâ açık olduğunu gösterir. Programı bu denemede model üretmedi; C5 tariften program kabul testi henüz yapılmadı.
- Çalıştırma testleri gerçek Windows süreçleriyle onay reddi, sonradan değişen kaynak, sıfır olmayan çıkış, kesilmiş çıktı, timeout/alt süreç kapatma, normal bitişte arka plan süreci kapatma, Job atama hatasında kullanıcı kodunu hiç başlatmama ve literal argümanları kapsar. Genel paket kurulumu, asistan ortamını programa açma, anlık iptal ve kalıcı GUI başlatma eklenmedi.
- Son paket **391 test + 508 alt test**, **16 Node testi** ve değişen kapsamda Ruff/diff kontrolüyle geçti. Qt gerçek form kataloğu **133 form** ve `python_run` kaydını doğruladı. API imajı yeniden derlenip dağıtıldı, web proxy yenilendi; canlı HTTP `python_run` çağrısı beklendiği gibi **503** ile reddedildi. Veri doğrulayıcı altı modeli, aynı volume/anahtarı, SQLite bütünlüğünü ve **603 kayıt / 776 parçayı** korunmuş buldu. Tam tariften program üretme C1–C5 ve B3–B7 hâlâ açık; bunlar tamamlandı diye işaretlenmedi.

**Sınırlar:** ortak Docker diskini/volume'ları kopyalama veya taşıma, eski kaynakları silme, kullanıcı VS Code/kimlik bilgilerini projeye kopyalama ve işletim sistemi/NVIDIA araçlarını taşınabilirleştirme bu dilimin kapsamında değildir.

### B5/B6 ek kabul ve kaynak üretim bütçesi

- Gerçek GitHub MCP kimlik doğrulaması, `initialize` ve **49 araç** listesi geçti;
  kimlik yalnız bellekte kullanıldı, depo içeriği/araç çağrısı gönderilmedi.
  Windows tarafında benzersiz geçici HKCU anahtarında beş kayıt tipi
  set/delete/restore/rollback sonrası tamamen temizlendi. Gerçek aygıt/sürücü/port
  envanteri salt okunur çalıştı. Donanım değiştiren dallar **6 test + 14 alt testte
  mock** olarak ayrıldı; yetki yükseltme veya mevcut ayar değişikliği yapılmadı.
- graphify'da modül ve gerçek graf eksik; gerçek MCP başlatması başarısızdır.
  Yanlış Copilot kurulum önerisi kaldırıldı, gerçek salt-okunur `query` eylemi
  sohbet izin listesine bağlandı. Piper/faster-whisper ve Türkçe ses dosyası yok;
  veri kümesinin CC-BY-NC-SA 4.0 şartları değerlendirilmeden model indirilmedi.
  Bu eksikler çalışan entegrasyon diye işaretlenmedi; Cline bakiye engeli sürer.
- Resmî `OpenJarvis[server]==1.0.4` proje içi Windows Python 3.12 ortamına kuruldu;
  `pip check` geçti. Mevcut WSL Python 3.14 destek aralığının dışındadır.
  `run-openjarvis.ps1` / `tools\openjarvis-local.toml` yalnız loopback8010,
  Ollama11435, Qwen3.6 ve araç çağırmayan `simple` ajanını kullanır. Analitik,
  telemetri, izler ve ajan zamanlayıcısı kapalı; kimlik deposu ayrı proje
  dizinindedir, miras sağlayıcı anahtarları çıkarılır. Gerçek Docker API →
  Windows loopback model listesi geçti. İki detached araç başlatması çıkış1
  verdi ve port açılmadı; kalıcı servis çalışıyor diye kabul edilmedi.
- Gerçek GUI kaynak üretimi 4.096 çıktı token sınırında kesildi ve hiçbir dosya
  yazılmadan açık hata verdi. Yalnız `project_create/update` kaynak çağrıları
  **32.768 bağlam / 8.192 çıktı** bütçesine yükseltildi. Diğer argüman çağrıları
  16.384/4.096, grup seçimi8.192/256 ve son özet16.384/4.096 kaldı;
  24.000 karakter JSON ve uzunluk-duruş reddi kaldırılmadı.
- **Altyapı regresyonu:** tam **566 test + 638 alt test** geçti; son OpenJarvis
  rehber düzeltmesi dahil odaklı **128 test + 57 alt test**, yerel sağlayıcı
  etiketi için **56 test + 281 alt test** geçti. İlgili Ruff kontrolünde yalnız
  önceden var olan import/fixture uyarıları dışlandı. Pylance kaynak bütçesi,
  Ollama ve graphify dosyalarında tanı döndürmedi; OpenJarvis'te mevcut `app.*`
  importları için editör `reportMissingImports` verdi, gerçek backend testleri
  ve çalışan servis ithalleri geçti. Editörün tamamı temiz diye sunulmaz.

### Grafik arayüzlü yerel model kabulünün son durumu

- Mevcut üretim `MainWindow > Sohbet` içinde gerçek Gönder/onay düğmeleriyle
  Qwen3.6 yalnız kendisi `qt_expense_panel` uygulama/test/README dosyalarını yazdı.
  İlk **11 test iki kez** geçti; bağımsız GUI yalnız **16/26** idi. Ayrı model
  test düzeltmesi ve Qwen3.8 incelemeli onarımdan sonra **12 test iki kez**
  geçti fakat bağımsız kontrol hâlâ **22/29** idi. Modelin tema/düğme/uzunluk
  iddialarının gerçek kaynakla uyuşmadığı açıkça kaydedildi.
- Bir sonraki ayrı onaylı test güncellemesi altı gerçek regresyon ekledi:
  önceki **12 yöntem ve iddianın AST'si aynen** korundu, toplam18 oldu.
  Sonraki **iki onaylı uygulama onarımı** boyunca test hash'i onay diff'iyle
  birebir aynı kaldı: `744f48e6501a6d4046987b81bf035ea1017918ade9053a6c327a15313a86a465`.
  Kaynak bütünlüğü testlerin hiçbirinde değişmedi. Uygulama/testler Copilot
  tarafından elle tamamlanmadı.
- Gerçek native Qt bağımsız kontrolü artık **31/33**: Sil düğmesi gerçek
  tıklamayla siler, toplam425 olur, grafik yenilenir; seçimsiz silme veriyi ve
  çizimi korur; yinelemeler, geçersiz/Unicode girdiler, hata temizliği,
  gerçek lacivert/turkuaz piksel çizimi ve minimum boyutta görünürlük/çakışmama
  geçti. Ekran görüntüsü ayrıca incelendi. Kalan iki kontrol denemenin
  kaynak uzunluk sınırlarıdır: app6426 `<4300`, test6258 `<3100` koşulunu
  sağlamıyor.
- Modelin son suite'i **16/18** kaldı: uzunluk ve hex renkler doğru olduğu
  halde CSS'te `dark/navy/cyan` kelimelerini zorunlu sayan hatalı tema testi.
  İncelemeci bunu anlamsal çelişki olarak yakalayamadı; sırf kelimeleri yoruma
  ekleme önerisi uygulanmadı. İki onarım sınırı sonrası güvenli duruş ve
  başarısız test rozeti var; son model metni çözüm planını tekrar anlatıyor.
  **Grafikli tam kabul ve genel model güvenilirliği açık/engelli; tamamlandı
  işaretlenmedi.** Yeni ürün sayfası eklenmedi; bu örnekte paketleme istenmedi.
- Gerçek OpenJarvis sohbeti API eklentisinden yerel Qwen3.6 ile tam
  `OPENJARVIS_LOCAL_OK` döndü; yalnız sabit kısa istem gönderildi. Kuyruklu
  bu koşu207,69 sn sürdü, performans garantisi değildir. Detached ortam
  başlatması çalışmadığından bounded test sunucusu sonunda durduruldu;
  kalıcı kurulum `run-openjarvis.ps1` ile elle çalıştırılır, otomatik giriş
  servisi veya sürekli hazır bağlantı iddiası yoktur.
- Kalıcı kanıt: `data\program-builds\native-visual-contract-repair.json`,
  `visual-independent-final.json`/`.png`, `openjarvis-local-acceptance.json`
  ve `remaining-capabilities-final.json`. İlk başarısız/eksik kabul kayıtları
  korunur; sonraki sonuçlarla geriye dönük başarılı diye değiştirilmez.

### D — Kanıta dayalı gelişim sırası

| ID | İş | Kabul kapısı | Durum |
|---|---|---|---|
| D1 | İstekten ölçülebilir kabul listesi | İlk kullanıcı gereksinimleri korunur; her madde doğrulandı/başarısız/henüz doğrulanmadı olarak ayrı izlenir; modelin kendi seçtiği liste tam kapsam kanıtı değildir | Ölçüt taslağı hash'li özgün istekle bağlanır; incelemeci taslak dışındaki olası eksikleri özgün metinden birebir alıntılamaya çalışır. Kapsam durumu daima tavsiye niteliğinde; tamlık ve davranış kanıtı motoru sonraki iş |
| D2 | Bağımsız kabul ve testlerin doğruluğunu inceleme | Uygulamadan ayrı doğrulama, gerçek GUI etkileşimi/çıktı; yanlış test ayrı gerekçe ve onay olmadan değiştirilmez | `project_test` ilk 40 çalıştırılan/skipped test kimliğini ve liste kırpılmasını raporlar; başarılı koşum, test başına 2.000 satır sınırıyla test kimliği/dosya yolu eşleşmeli çalıştırılan satır izini de kaydeder. `test_linked`/`conflict` alıntısı başarılı son koşumun atlanmamış test kimliğini, kaynak dosyasıyla uyumu ve uygulamadaki fonksiyon/sınıf çağrısına bağlı, gerçekten değerlendirilen assertion'ı ister; assertion ile uygulama çağrısının ikisinin de izde bulunduğu doğrulanır. Sabit karşılaştırma dahil sabit doğrulukla geçebilen bariz vakumlu assertion'lar, bağımsız veya kısa devre/koşullu dalda kalan çağrı ve assertion'dan önce yeniden atanan sonuç kanıt sayılmaz; sabit boolean ifadeleriyle geçen `unittest.assertEqual/assertIs` ve başarısız `assertNotEqual/assertIsNot` kanıtları, yorum ve çağrılmayan iç yardımcı reddedilir. Bu yapısal bağ ve satır izi semantik doğruluk kanıtı değildir. Qt doğrulaması için pinli Python 3.12.10, `.venv` ve bağımlılıklar doğrulandı; repo başlatıcısının geçici OS kısayolu güvenlik politikasıyla engellendi, uygulama açılmadı. Katalogdaki kurulu `DeepPanda.exe` `İş Emirleri` ürünüdür ve kullanılmadı; packaged desktop exe yok. Gerçek uygulama GUI kabulü ve genel test denetimi açık |
| D3 | Kanıta bağlı sonuç ve sohbet sürekliliği | Test sonucu ile gereksinim kabulü ayrı; bilinmeyenler açık; aynı durum ilk yanıt ve yeniden açılan API sohbet kaydında korunur | İlk dilim uygulandı ve gerçek Qt/API kaydıyla doğrulandı; genel gereksinim motoru değildir |
| D4 | Sınıflandırılmış ve tekrarsız sınırlı onarım | Kaynak bütünlüğü/iptal/süre aşımı/assertion/test hatası mekanik olarak ayrılır; eldeki sınırlı kaynak kanıtında daha önce denenmiş AST-eşdeğer duruma dönüş yazmadan durur; iki onarım sınırı korunur | İlk dilim uygulandı ve birim + ajan entegrasyon testleri geçti; genel kök neden/ortam teşhisi değildir |
| D5 | Kalıcı regresyon havuzu | Her yeni bulunan hata önce başarısız testle üretilir; düzeltme sonrası hedefli ve gerekli kapsamda tam test; farklı görevlerde kabul ayrı raporlanır | API/kayıt/UI, bozuk/eski kanıt, onarım döngüsü, süre aşımı, uzun kabul-raporu oturum kaydı, davranış bağlantısı, gerçekten çalışmış test kimliği, sabit karşılaştırma dahil bariz vakumlu assertion, sabit booleanlı unittest karşılaştırmaları ve yeniden atamayla bağlantısı kesilen sonuç vakaları eklendi; en güncel birleşik backend + desktop koşumu 607 testi geçti |
| D6 | Daha güçlü çalıştırma izolasyonu | Windows GUI uyumu dahil ayrı kullanıcı/VM veya uygun konteyner, ağ/dosya/kimlik sınırları ve kaçış/temizlik testleri; açık çalışma modu ve gerçek izolasyon kanıtı | Python sonuçları ve kısaltılmış sohbet kanıtı `isolation_mode=windows_job_object_process_tree_lifetime_only` / `sandboxed=false` bildirir; çalışma modu şeffaflığı kısmi olarak tamamlandı. Gerçek dosya/ağ/kimlik izolasyonu ve kaçış testleri yok; mevcut Docker Desktop Linux modunda, Windows GUI kabuline uygun değil |

D1/D2/D6 tümü uygulanmış sayılmaz. D1 ve D3/D4/D5'in yukarıdaki ilk
dilimleri tamamlandı; bağımsız kabul incelemesi her ölçütü testle ilişkili,
eksik, çelişkili veya doğrulanamaz diye sınıflandırabilir ve özgün istekteki
olası eksikleri alıntılayabilir; bu model değerlendirmeleri gereksinim geçişi
değildir. Orijinal isteğin ölçüt listesiyle eksiksiz kapsandığını doğrulamak,
kriter başına gerçek/bağımsız davranış kanıtı toplamak, genel test denetimi ve
gerçek OS izolasyonu sonraki aşamalardır. Jarvis'e yeni yetki,
bulut aktarımı veya Windows güvenlik ayarı bu listeyle otomatik verilmez.

**D3/D4/D5 ilk dilimin kalıcı kanıtı:**
- En güncel birleşik backend + desktop regresyonu: **608 test geçti**,
  663 alt test, 126,06 saniye. Yeni çalıştırılan-satır kanıtı ayrıca hedefli
  regresyonda **76 test + 89 alt test** geçti; değişen Python dosyalarında
  Ruff, compileall ve diff kontrolleri temiz. Güncel API yeniden oluşturulup başlatıldı;
  `/api/health` yanıtı `status=ok`, `plugin_gateway=ready`.
- Mevcut üretim `MainWindow → Sohbet` üzerinden gerçek yerel model ve
  native onaylarla GUI görevine tekrar dönüldü. Ekrandaki son yanıt API'den
  geri okunan kayıtla birebir aynı; başarısız test hata durumunda ve
  gereksinimler **HENÜZ DOĞRULANMADI** olarak kaldı.
- Qwen3.6'nın ayrı onaylı uygulama/test güncellemesi 18 test adını korudu;
  yanlış `dark/navy/cyan` sözcük kontrolünü hex-renk kontrolüne çevirdi.
  Bu kendi başına gerçek çizim kabulü değildir. Kendi testleri **17/18**,
  ayrı gerçek GUI kontrolü **31/33**: uygulama 6836, test 6454 karakter,
  gereken sınırlar sırasıyla `<4300` ve `<3100`. Sıkıştırma isteğine rağmen
  dosyalar büyüdü; uygulamayı kod asistanı tamamlamadı.
- Qwen3.8 incelemecinin güncel kaynakta bulunmayan eski biçimli alıntıları
  kaynak kanıtı kontrolünde reddedildi; uygulama onarımı yazılmadı.
  Test dosyasının hash'i ilk testten inceleme sonuna kadar aynı kaldı.
  Tam başarı/paketleme ilanı yoktur. İlk başarısız kayıtlar korunur:
  `data\program-builds\native-evidence-reliability.json`/`.png` ve
  `visual-reliability-independent.json`/`.png`.
- **Ayrı rol karşılaştırması:** kayıtlı tercih değiştirilmeden bu deneme
  penceresinde Qwen3.8 geliştirici, Qwen3.6 incelemeci seçildi. Kaynaklar
  ilk isteğe gömülmek yerine mevcut dosya eki/gerçek `text.preview` hattıyla
  okundu. Qwen3.8 dosyaları 6191/6254 karaktere indirdi; iki sınır da
  hâlâ başarısızdır. Kendi testleri bu kez **16/18**: uzunluğa ek olarak
  yeni tema testi gösterilmemiş pencerenin paletini gri `(239,239,239)`
  ölçtü. Bu, görünür pencerenin çizim kabulü değildir; ayrı gerçek GUI
  kontrolü lacivert/turkuaz çizimi ve etkileşimleri yine **31/33** doğruladı.
  İncelemeci kaynak alıntılarını `...` ve yeniden biçimlenmiş satırlarla
  verdi; birebir alıntı koruması yine yazmadan durdurdu. Her iki rol
  dizilişi de tam kabul sağlamadı; test hash'i ve kayıt/UI eşitliği korundu.
  Kaydedilmiş incelemeci hâlâ `qwen3.8:latest`; sessiz kalıcı rol değişimi
  yoktur. Son durum **engelli**, paketleme yapılmadı; kanıtlar
  `native-evidence-role-swap.json`/`.png` ve
  `visual-reliability-role-swap.json`/`.png` aynı kanıt klasöründedir.

**D1 gereksinim taslağı dilimi (gerçek GUI/model başarısı iddiası değildir):**
- `project_create` önizlemesindeki model ölçüt taslağı onay sonrası proje
  kaydında korunur; oluşturma, ortam, test, güncelleme ve paketleme sonuçlarına
  ayrı metadata olarak taşınır.
  API, istemin UTF-8 SHA-256 parmak izini kaydeder ve en çok 32 satır ölçütü
  listeleyip her birini **HENÜZ DOĞRULANMADI** işaretler. Liste limiti aşılırsa
  kırpılma açık belirtilir; Sor/eski/benzer adlı araç sonucu taslağı terfi ettirmez.
- Özgün kullanıcı isteği mevcut oturum mesajında aynen saklanır; yeni API
  metadata alanında yalnız hash yer alır. Hash içeriğin veya kriterlerin
  eksiksizliğinin kanıtı değildir. Taslak modelin ürettiği/istemcinin bildirdiği
  veridir, ölçütler kendiliğinden onaylı gereksinim veya başarı değildir.
- API ve Qt kod regresyonu **607 test** ile doğrulandı; D1 hâlâ
  kısmi. Eksik/örtük gereksinimlerin otomatik keşfi, özgün metinle tamlık
  kıyası ve her kriteri bağımsız doğrulayacak kanıt akışı henüz yoktur.
- D2'nin ilk kod dilimi: başarılı test sonrası ayrı yerel incelemeci
  güncel proje kaynaklarını okur ve her ölçütü testle ilişkili/eksik/
  çelişkili/doğrulanamaz olarak, birebir kaynak alıntılarıyla raporlar.
  Hem testle ilişkili hem de testle çelişkili sınıflar güncel test dosyasından
  çalıştırılabilir assertion alıntısı ister.
  Hash-eşleşmeli özgün istekte ölçüt listesi dışında kalan olası gereksinimler
  ayrıca birebir alıntılanır; hash uyuşmazlığı veya kesilmiş istek kapsam
  iddiasını engeller.
  Test edilen Python kaynak bütünlüğü ve incelemeye sunulan dosyaların
  hash'leri eşleşmezse başarı düşürülür; eksik, kesilmiş veya uydurma
  alıntı raporu reddedilir. Test alıntısı çağrılmayan iç yardımcıdaki
  assertion'ı veya `with` dışında tek başına kullanılan `pytest.raises/warns`
  çağrısını kanıt saymaz. Bu rapor tavsiyedir;
  test koşumunun yerine geçmez ve hiçbir kriteri doğrulanmış yapmaz.
  Kaydedilmiş gerçek GUI denemesi kurulu istemcinin `WinError 10061`
  bağlantı hatasında kaldı; yeni GUI derlemesinin çalıştırılması henüz
  doğrulanmadı.
- İlgili testler: `test_program_verification_preserves_approved_criteria_as_unverified_items`,
  `test_program_verification_reuses_persisted_criteria_from_followup_project_test`,
  `test_package_only_turn_keeps_project_criteria_visible_but_unverified`,
  `test_unapproved_or_lookalike_criteria_are_not_promoted_to_program_checklist`,
  `test_program_checklist_caps_items_and_marks_truncation` ve
  `test_approved_create_criteria_reach_the_checklist_without_becoming_verified`.
