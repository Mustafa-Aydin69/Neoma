# Noema: SPSS MCP köprüsü (prototip)

Claude Desktop ile yerel IBM SPSS Statistics arasında köprü kurar.

```
Claude Desktop ──MCP──> noema_mcp/server.py  (modern Python 3.10+)
                              │  JSON dosyası
                              ▼
                        worker/spss_worker.py (SPSS'in kendi Python'u, 3.8)
                              │  spss.Submit + OMS (OXML)
                              ▼
                        SPSS motoru
```

İki Python kullanmamızın sebebi şu: MCP kütüphanesi 3.10 veya üstünü istiyor, SPSS 27'deki `spss` modülü ise yalnızca 3.8 ile çalışıyor.

## Araçlar
| Araç | Ne yapar |
|---|---|
| `check_spss` | SPSS motorunun açılıp açılmadığını test eder |
| `inspect_dataset(path)` | Değişkenleri, etiketleri, ölçüm düzeyini, değer etiketlerini ve eksik değer tanımlarını getirir |
| `run_descriptives(path, variables, statistics?)` | DESCRIPTIVES komutunu çalıştırır ve gerçek SPSS tablosunu ve syntax'ı döndürür |

Her çalıştırma `~/Noema/logs/runs.jsonl` dosyasına (istek ve sonuç), kullanılan syntax da `~/Noema/logs/syntax.sps` dosyasına eklenir. `.sps` dosyası doğrudan SPSS'te açılıp çalıştırılabilir.

## Bilinen sorun: Türkçe Windows bölge ayarı
Windows 11, bölge adını `Turkish_Türkiye.1254` olarak veriyor. SPSS 27 bu adı UTF-8 sanıp okuyor ve `ü` harfinde çöküyor. İşçi süreç `spss` modülünü yüklemeden önce bölge ayarını sabitliyor ve SPSS'in hatalı fonksiyonunu sarmalıyor. Bu yüzden kullanıcının Windows ayarına dokunması gerekmiyor.

## Kurulum (Windows)
1. `C:\noema` klasörüne bu dosyaları kopyalayın: `noema_mcp\`, `worker\`, `requirements.txt`.
2. python.org'dan **Python 3.12** kurun. Kurulumda "Add python.exe to PATH" kutusunu işaretleyin. SPSS'in kendi Python'unu kullanmayın.
3. Komut İstemi'nde:
   ```
   cd C:\noema
   py -3.12 -m venv .venv
   .venv\Scripts\pip install -r requirements.txt
   ```
4. Önce işçi süreci tek başına test edin:
   ```
   "C:\Program Files\IBM\SPSS\Statistics\27\Python3\python.exe" C:\noema\worker\spss_worker.py --test
   "C:\Program Files\IBM\SPSS\Statistics\27\Python3\python.exe" C:\noema\worker\spss_worker.py --test "C:\yol\ornek.sav"
   ```
   Her iki komut da `=== NOEMA ===` satırından sonra JSON çıktısı vermeli.
5. Claude Desktop'ta Settings > Developer > Edit Config ile `claude_desktop_config.json` dosyasını açın ve şunu ekleyin:
   ```json
   {
     "mcpServers": {
       "noema-spss": {
         "command": "C:\\noema\\.venv\\Scripts\\python.exe",
         "args": ["-m", "noema_mcp.server"],
         "cwd": "C:\\noema",
         "env": {
           "PYTHONPATH": "C:\\noema",
           "NOEMA_SPSS_PYTHON": "C:\\Program Files\\IBM\\SPSS\\Statistics\\27\\Python3\\python.exe"
         }
       }
     }
   }
   ```
6. Claude Desktop'u tamamen kapatıp yeniden açın. Görev çubuğundaki simgeden de çıkın. Sonra Claude'a şunu yazın: "check_spss aracını çalıştır."

## Ayarlar (ortam değişkenleri)
- `NOEMA_SPSS_PYTHON`: SPSS'in python.exe yolu. Verilmezse olağan kurulum klasörlerinde aranır.
- `NOEMA_LOG_DIR`: Kayıt klasörü. Varsayılan `~/Noema/logs`.
- `NOEMA_TIMEOUT`: Saniye cinsinden zaman aşımı. Varsayılan 300.

## Durum
- Sahte bir `spss` modülüyle uçtan uca test edildi: MCP istemcisi, sunucu, işçi süreç ve OXML ayrıştırma.
- Gerçek SPSS 27 üzerinde yalnızca bölge ayarı düzeltmesi doğrulandı. `inspect_dataset` çağrısının kullandığı `spss.Dataset` alanları (valueLabels, missingValues) henüz gerçek SPSS'te denenmedi.
- macOS'taki SPSS Python yolları tahmin; gerçek bir Mac kurulumunda doğrulanması gerekiyor.
