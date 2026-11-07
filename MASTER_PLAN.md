# DeepPanda AI Next — Ana Plan ve Durum

Son güncelleme: bu çalışma oturumu. Bu dosya kaybolan `MASTER_PLAN.md` dosyasının yerine yazıldı. Neyin yapıldığını, nerede kalındığını ve son kontrolün nasıl yapılacağını anlatır.

## 1. Hedef

- Kurtarılan DeepPanda AI Next projesini `F:\DeepPanda Agentic Al` altında yeniden kurmak. Yerel beyin **Qwen 2.5 Coder 7B**.
- Temel eklentiler: GitHub Copilot MCP araçları, REA, replica-skill, OpenJarvis, Build Your Own X, graphify.
- Docker yığını: API, Ollama, FreeLLMAPI, Redis, Qdrant, SQL yöneticisi. Web arayüzü yalnızca istenirse açılır.
- Günlük kullanım için **Qt kontrol merkezi**. Sade olacak, web arayüzünün tüm özelliklerini içerecek ve onay pencereleri en aza inecek.
- Her şey F: üzerinde kalacak; C:'ye kalıcı bir şey yazılmayacak.

## 2. Konumlar

| Ne | Nerede |
|---|---|
| Proje (git deposu) | `F:\DeepPanda Agentic Al` |
| Python ortamı, pip önbelleği, geçici dosyalar | `F:\DeepPanda Agentic Al\.venv`, `_tmp` (gitignored) |
| Qt istemci ayarları | `F:\DeepPanda Agentic Al\desktop\settings.ini` (gitignored) |
| Docker Desktop veri diski | `F:\DeepPanda-Docker-Data` (`disk`, `main`) |
| Eski kalıntılar (silinecek) | `F:\DeepPanda-Proje` (aşağıdaki "Silme" bölümüne bakın) |

## 3. Yapılanlar

| # | İş | Durum |
|---|---|---|
| 1 | Docker sohbet özeti kurtarıldı, proje `F:\DeepPanda Agentic Al` altına alındı, `git init` ile başlangıç commit'i (`09e228d`) atıldı | ✅ |
| 2 | Varsayılan model Qwen 2.5 Coder 7B (`OLLAMA_MODEL`, `model-area-priorities.json`, testler, değerlendirme vakaları); Qwen 3.6 kaldırıldı | ✅ |
| 3 | `requires_local_tools` yönlendirmesi (yerel veri gerekiyorsa salt-okunur araç döngüsü) kurtarılan kodda mevcut ve testli | ✅ |
| 4 | Yeni eklentiler: `mcp` (GitHub Copilot MCP köprüsü), `skills` (replica-skill / SKILL.md), `openjarvis`, `byox`, `graphify`, `database` (SQL); ortak hata eşlemesi `integration_errors` (403/404/503) | ✅ |
| 5 | `backend/tests/test_integrations.py` ve gateway testleri; tam paket **172 test geçti** | ✅ |
| 6 | `docker-compose.yml`: sabit proje adı (`deeppanda-ai-next`, mevcut volume'lar korunur), API healthcheck, Ollama `127.0.0.1:11435`, `web` ve `manager` profilleri, `db-manager` (sqlite-web, varsayılan salt-okunur, isteğe bağlı parola), tüm portlar `.env` ile ayarlanabilir; `docker compose config` doğrulandı | ✅ |
| 7 | `.env.example` (tüm ayarlar Türkçe açıklamalı), `mcp-servers.json` (github + graphify), `docker-compose.models.yml` (mevcut model klasörünü bağlama) | ✅ |
| 8 | **Qt kontrol merkezi** (`desktop/`, `run-desktop.ps1`): Sohbet, Araçlar (106 form), İşler, Veritabanı, MCP / Copilot, Sistem, Ayarlar | ✅ |
| 9 | Qt uçtan uca duman testi: 7 sayfa, 106 form, hafıza/görev/graphify/beceri/OpenJarvis/DB/MCP/Docker yolları; **0 hata** | ✅ |
| 10 | README: servis profilleri, Qt kontrol merkezi, entegrasyonlar, test komutu | ✅ |
| 11 | Canlı Docker yığınını yeni klasöre taşıma ve imajı yeniden derleme | ⏳ onay ve sandbox izni bekliyor |
| 12 | `F:\DeepPanda-Proje` silme | ⏳ taşıma doğrulandıktan sonra, onayla |

## 4. Mimari özeti

- **API** (FastAPI, `127.0.0.1:8787`): tüm özellikler `PluginGateway` üzerinden çalışır. Onay gerektiren eylemler `approved=true` olmadan 403 döner.
- **Eklentiler (37):** hafıza, belgeler, bilgi, görevler, işler, çalışma alanı, kod grafı, tanılama, araştırma, tarayıcı, binary analiz, repo izleme, bulut sağlayıcıları, FreeLLMAPI, Ollama, oturumlar, iş akışları, lisans, rapor, ses, OCR, medya, değerlendirme, Instagram, prompt kitaplığı ve yeni eklenen `mcp`, `skills`, `openjarvis`, `byox`, `graphify`, `database`.
- **Qt istemcisi** API ile HTTP üzerinden konuşur. MCP araçlarını (REA, Copilot GitHub, kaggle, graphify) doğrudan bu bilgisayarda çalıştırır. Docker komutlarını proje klasöründe yürütür.
- **Onay akışı:** salt-okunur işlemler hiç sormaz. Yazma/kurma/çalıştırma işlemleri tek bir "Evet, devam et / Vazgeç" penceresiyle sorulur.

## 5. Varsayımlar

- "SQL ve manager" şu anlama alındı: `/data` altındaki SQLite veritabanları (`memory.db`, `tasks.db`, `jobs.db`, ...) ve web tabanlı **sqlite-web** yöneticisi (`127.0.0.1:8789`). Portainer veya Docker MCP Toolkit kastedildiyse ayrıca eklenebilir.
- API'ye `REDIS_URL` veriliyor, ancak backend henüz Redis kullanmıyor (iş kuyruğu SQLite `jobs.db`).
- OpenJarvis WSL Ubuntu'da çalışır ve Docker'dan `host.docker.internal:8010` adresiyle erişilir. WSL→Windows erişimi henüz doğrulanmadı.
- GitHub Copilot MCP için `GITHUB_TOKEN` gerekir. Qt istemcisi token yoksa `gh auth token` ile yalnızca kendi süreci için alır.

## 6. Engeller

- Çalışma ortamının sandbox'ı Docker daemon'a (`npipe:////./pipe/docker_engine`) ve yerel TCP bağlantılarına izin vermiyor. Bu yüzden canlı yığın yeniden başlatılmadı ve imaj yeniden derlenmedi. Bunlar zaten açık onay gerektiriyor.
- Sandbox, VS Code kullanıcı `mcp.json` dosyasını okumaya izin vermiyor. Qt istemcisi bu durumda dosyayı atlayıp uyarı gösteriyor ve proje sunucularıyla devam ediyor. Normal kullanımda dosya okunur.
- graphify grafiği henüz üretilmedi (`graphify-out/graph.json` yok).

## 7. Son kontrol tarifi

Proje klasöründe PowerShell aç (`F:\DeepPanda Agentic Al`).

1. **Ayar dosyası:** `.env` yoksa `Copy-Item .env.example .env` çalıştır. İstersen `GITHUB_TOKEN`, `SQLITE_WEB_PASSWORD` ve `DB_MANAGER_MODE` değerlerini doldur.
2. **Modellerin yerini kontrol et:** `docker inspect deeppanda-ai-next-ollama-1 --format "{{json .Mounts}}"`. Modeller bir host klasöründeyse `.env` içine `OLLAMA_MODELS_HOST_DIR=<o klasör>` yaz. 3. adımda komutları `-f docker-compose.yml -f docker-compose.models.yml` ile çalıştır.
3. **Yığını yeni klasöre taşı (onaylı yeniden dağıtım):**
   ```powershell
   docker compose config --quiet
   docker compose build api
   docker compose up -d
   docker compose ps
   ```
   Proje adı aynı kaldığı için volume'lar (`ai_data` içindeki 603 hafıza kaydı dahil) korunur. Konteynerler yeni klasörü bağlayacak şekilde yeniden oluşturulur.
4. **Qwen 2.5:** `docker compose exec ollama ollama list`. Model yoksa `docker compose exec ollama ollama pull qwen2.5-coder:7b` çalıştır.
5. **Sağlık:** tarayıcıda veya `curl` ile `http://127.0.0.1:8787/api/health` adresi `{"status":"ok"}` dönmeli.
6. **SQL yöneticisi:** `docker compose --profile manager up -d db-manager` çalıştır, ardından `http://127.0.0.1:8789` adresini aç.
7. **Qt kontrol merkezi:** `.\run-desktop.ps1` çalıştır ve sayfaları sırayla dene:
   - Sohbet: "Merhaba" yaz ve Qwen 2.5 yanıtı gel.
   - Araçlar: Hafıza → Ara.
   - Veritabanı: `memory.db` → `SELECT count(*) FROM memories`.
   - MCP / Copilot: `rea` ve `github` sunucularını seç → Araçları getir.
   - Sistem: Durumu yenile; tüm kartlar yeşil olmalı (OpenJarvis/graphify isteğe bağlı).
8. **OpenJarvis (isteğe bağlı):** WSL Ubuntu'da `jarvis serve --host 0.0.0.0 --port 8010 -e ollama -m qwen2.5-coder:7b` çalıştır. Ardından Qt'de model listesinden "OpenJarvis" seçip bir mesaj gönder.
9. **graphify (isteğe bağlı):** `.\.venv\Scripts\python.exe -m pip install graphifyy` ve `graphify install --platform copilot` çalıştır. Copilot CLI'da `/graphify .` komutunu ver. Ardından Qt → Araçlar → graphify → Özet.
10. **Web (isteğe bağlı):** `docker compose --profile web up -d web` çalıştır, ardından `http://127.0.0.1:8788` adresini aç.

## 8. Silme (onay gerektirir)

Taşıma 3–7. adımlarla doğrulandıktan sonra silinebilecekler:

- `F:\DeepPanda-Proje\DeepPanda-AI-Next`: kurtarılmış 113 dosya. İçeriği bu projeye alındı; canlı konteynerler taşınana kadar buraya bağlı.
- `F:\DeepPanda-Proje\DeepPanda-AI`: boş `models` ve `AI-Runtimes` klasörleri.
- `F:\DeepPanda-Proje\_kurtarma-arsivi.zip`: kurtarma arşivi. İstenirse önce başka yere yedeklenebilir.

Kapsam dışı: `C:\Users\emre\Desktop\DeepPanda-Proje` bir junction değil. Yaklaşık 220 GB'lık ayrı ve gerçek bir klasör (LocalQwenAgent, GEMMA, Tools, yara ...). Bu çalışmada dokunulmadı; F:'ye taşınması ayrı bir iş ve onay gerektirir.

## 9. Sonraki yol haritası

1. Çoklu ajan (planlayıcı / kodlayıcı / test-inceleme / araştırmacı), izin sınırlarıyla. Başlangıç noktası `workflows.py` ve `analysis_workflow.py` (LangGraph).
2. Bulut sağlayıcı kapsamı (Gemini, Kimi, Claude, GPT ve ücretsiz API'ler). `cloud_providers` anahtar kaydı ve "başka yapay zekâya sor" hazır; sağlayıcı listesi son kontrolde gözden geçirilecek. Dış API'ye veri yalnızca açık seçimle gider.
3. Redis tabanlı iş kuyruğu (şu an SQLite).
4. Nihai projeyi D:'ye taşıma. Yalnızca onayla ve F:'de doğrulanmış yedekle yapılacak.
