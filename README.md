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
1. Repoyu klonlayın: `git clone https://github.com/Mustafa-Aydin69/Neoma.git C:\noema`
2. **Python 3.10 veya üstü** gerekiyor (3.13 ve 3.14 ile denendi). SPSS'in kendi Python'u bu iş için kullanılmamalı.
3. Komut İstemi'nde:
   ```
   cd C:\noema
   py -3.14 -m venv .venv
   .venv\Scripts\pip install -r requirements.txt
   ```
4. Önce işçi süreci tek başına test edin (PowerShell'de satırın başına `& ` ekleyin):
   ```
   "C:\Program Files\IBM\SPSS\Statistics\27\Python3\python.exe" C:\noema\worker\spss_worker.py --test
   "C:\Program Files\IBM\SPSS\Statistics\27\Python3\python.exe" C:\noema\worker\spss_worker.py --test "C:\Program Files\IBM\SPSS\Statistics\27\Samples\English\Employee data.sav"
   ```
   Her iki komut da `=== NOEMA ===` satırından sonra JSON çıktısı vermeli.
5. Claude Desktop'u tamamen kapatın (sistem tepsisinden Quit), sonra sunucuyu ayara ekleyin:
   ```
   .venv\Scripts\python.exe tools\add_to_claude_config.py
   ```
   Betik, mevcut ayarlara dokunmadan yalnızca `mcpServers.noema-spss` ekler ve `.yedek` dosyası alır. Config bulunamazsa Claude Desktop'ta **Settings > Desktop app > Extensions > Local MCP servers > Edit config** ile gerçek yolu bulup betiğe argüman olarak verin.
6. Claude Desktop'u açın. Aynı ekranda noema-spss **Running** görünmeli.
7. **Chat** sekmesinde yeni bir sohbet açıp şunu yazın: "check_spss aracını çalıştır."

### Bilinen tuzaklar
- **Microsoft Store sürümü:** Config `%APPDATA%\Claude` içinde değil, `%LOCALAPPDATA%\Claude-Data\claude_<id>\` içindedir. Ayarlar ekranında "Developer" bölümü yoktur, yeri yukarıda yazıyor.
- **Chat ve Code sekmeleri:** `claude_desktop_config.json` dosyasını Chat sekmesi okur. Code sekmesi MCP sunucularını proje klasöründeki `.mcp.json` dosyasından alır.
- **60 sn zaman aşımı:** İşçi sürece MCP'nin stdin kanalı devredilirse SPSS takılır. Sunucu bu yüzden `stdin=DEVNULL` kullanıyor.

## Ayarlar (ortam değişkenleri)
- `NOEMA_SPSS_PYTHON`: SPSS'in python.exe yolu. Verilmezse olağan kurulum klasörlerinde aranır.
- `NOEMA_LOG_DIR`: Kayıt klasörü. Varsayılan `~/Noema/logs`.
- `NOEMA_TIMEOUT`: Saniye cinsinden zaman aşımı. Varsayılan 300.

## Durum (2026-11-04)
- SPSS 27 / Windows 11 (Türkçe bölge ayarı) üzerinde uçtan uca doğrulandı: Claude Desktop Chat, `check_spss`, `inspect_dataset` ve `run_descriptives` çalışıyor, gerçek SPSS tablosu geliyor.
- macOS'taki SPSS Python yolları tahmin; gerçek bir Mac kurulumunda doğrulanması gerekiyor.
- Sırada: rehber skill; frekans, normallik, t-testi, ANOVA ve korelasyon araçları; `.mcpb` paketi.
