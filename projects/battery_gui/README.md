# DeepPanda Pil Paneli

Bu uygulama Windows güç durumunu izler. Ayar değiştirmez.

## Çalıştırma

```bash
python app.py
```

Kod yerel model tarafından oluşturulmuştur.

## Doğrulama ve model kaynakları

Uygulama kaynaklarını yerel `qwen3.6:latest` yazdı. Kod asistanı kaynak
kodunu elle düzeltmedi; yerel modellere test çıktısını iletti ve işlemleri onayladı.

Son kalan bilinmeyen yüzde hatası için Qwen3.6 ve Qwen2.5 Coder 7B
birbirlerinin raporunu görmeden teşhis üretti. Gerçek `ChatAgent` akışı
başarısız testi çalıştırdı, Qwen3.6 yalnız `battery.py` dosyasını güncelledi
ve aynı dokuz test geçti. Ardından iki ayrı test çalıştırması daha 9/9 geçti.
Test dosyasının SHA-256'sı değişmedi:
`1188939263228b37d1bc27399dd577f51bd5df166b31fcaf0a6c11773132fd65`.

Kök dizinden test:

```powershell
.\.venv\Scripts\python.exe -B -m unittest discover -s .\projects\battery_gui -p "test_*.py" -v
```

Bağımsız kontrolde bilinmeyen yüzde için sekiz giriş birleşimi, native okuma
hatası ve gerçek grafik pencerede yenileme/bilinmeyen değer/hata gösterimi
doğrulandı. Bu testler güç ayarını değiştirmez.

İkinci modelin düzeltme sonrası raporu çelişkiliydi; gerçek testlerle
desteklenmediği için uygulanmadı. Model görüşü test kanıtının yerine geçmez.
Bu kontrollü, aşamalı yerel çoklu model denemesidir; her sohbet turunda otomatik
ikinci model seçimi veya bütün pil/donanım durumları için doğruluk garantisi değildir.
İşlem kimlikleri ve ayrıntılı sonuçlar kökteki
[ana planda](../../MASTER_PLAN.md) kayıtlıdır.