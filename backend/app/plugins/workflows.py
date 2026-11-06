from __future__ import annotations

from typing import Any, ClassVar

from app.plugins.contracts import PluginManifest


class WorkflowNotFoundError(ValueError):
    pass


class WorkflowsPlugin:
    manifest = PluginManifest(
        plugin_id="workflows",
        display_name="Engineering Workflows",
        description="Planlama, hata ayıklama, review ve audit için yerel çalışma modları.",
        actions=("catalog", "get"),
    )

    workflows: ClassVar[dict[str, dict[str, str]]] = {
        "standard": {
            "name": "Standart",
            "description": "Kanıta dayalı, güvenli ve dengeli çalışma.",
            "instructions": (
                "Önce isteği ve kapsamı anla. Belirsizlik sonucu etkiliyorsa soru sor. "
                "Dosya değiştirme veya araç kullanımı için ayrı açık onay gereklidir. "
                "Sonuçları test veya başka gözlenebilir kanıtla doğrula; belirsizliği açıkla."
            ),
        },
        "plan": {
            "name": "Planla",
            "description": "Kapsam ve doğrulama ölçütleri belli, küçük adımlı plan.",
            "instructions": (
                "Uygulamadan önce hedefi, kapsamı, kısıtları ve kabul ölçütlerini özetle. "
                "Adımları küçük, sıralı ve doğrulanabilir tut; bilinmeyen varsayımları belirt. "
                "Kullanıcı onayı gelmeden dosya değiştirme, paket kurma veya komut çalıştırma."
            ),
        },
        "debug": {
            "name": "Hata ayıkla",
            "description": "Önce tekrar üretim, sonra kök neden ve hedefli doğrulama.",
            "instructions": (
                "Önce gözlenen hata ve tekrar üretim koşulunu belirle. "
                "İlgili en yakın kodu ve testi incele, tek bir yanlışlanabilir hipotez kur. "
                "Kök nedeni düzelt, aynı koşulda testi çalıştır; test çalışmadıysa geçtiğini söyleme."
            ),
        },
        "review": {
            "name": "Kod inceleme",
            "description": "Önce bulgular: hata, gerileme, güvenlik ve eksik test.",
            "instructions": (
                "İncelemeyi değişen kod ve doğrudan çağrı zinciriyle sınırla. "
                "Bulguları önem sırasıyla, dosya/konum ve tetikleme koşuluyla bildir. "
                "Önemsiz stil notlarını bulgu gibi sunma; sorun yoksa bunu ve kalan riski açıkla."
            ),
        },
        "audit": {
            "name": "Salt okunur audit",
            "description": "Değişiklik yapmadan hata, risk ve kapsam raporu.",
            "instructions": (
                "Salt okunur inceleme yap. Kapsamı ve tarama sınırlarını başta belirt. "
                "Kod, yapılandırma ve test kanıtını ayır; hiçbir dosyayı değiştirme veya komut çalıştırma. "
                "Bulgu yoksa tarama kapsamı ve atlanan alanları da raporla."
            ),
        },
        "minimal": {
            "name": "En küçük çözüm",
            "description": "Önce mevcut araç ve kodu kullan; gereksiz soyutlamadan kaçın.",
            "instructions": (
                "Önce mevcut kodu, standart kütüphaneyi ve zaten kurulu bağımlılıkları değerlendir. "
                "Gereksinimi karşılayan en küçük değişikliği seç; yeni bağımlılık veya katman eklemeden önce gerekçesini açıkla. "
                "Güvenlik, doğruluk, hata yönetimi ve test kapsamını küçültme."
            ),
        },
    }

    async def invoke(self, action: str, payload: dict[str, Any]) -> dict[str, Any]:
        if action == "catalog":
            return {
                "workflows": [
                    {"id": workflow_id, "name": workflow["name"], "description": workflow["description"]}
                    for workflow_id, workflow in self.workflows.items()
                ]
            }
        if action == "get":
            workflow_id = payload.get("mode", "standard")
            if not isinstance(workflow_id, str) or workflow_id not in self.workflows:
                raise WorkflowNotFoundError("Unknown workflow mode.")
            return {"mode": workflow_id, **self.workflows[workflow_id]}
        raise ValueError(f"Unsupported workflow action: {action}")