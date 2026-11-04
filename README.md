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
| Araç | SPSS komutu | Ne zaman |
|---|---|---|
| `check_spss` | SHOW N | Bağlantı testi |
| `inspect_dataset` | (Dataset API) | Değişkenler, etiketler, ölçüm düzeyi, eksik değer tanımları |
| `run_descriptives` | DESCRIPTIVES | Sürekli değişkenlerin özeti |
| `run_frequencies` | FREQUENCIES | Kategorik/demografik değişkenler |
| `run_normality` | EXAMINE | Kolmogorov-Smirnov ve Shapiro-Wilk, gruplara göre de yapılabilir |
| `run_ttest_independent` | T-TEST GROUPS | İki bağımsız grup (Levene ve Cohen's d dahil) |
| `run_ttest_paired` | T-TEST PAIRS | Ön test/son test |
| `run_anova_oneway` | ONEWAY | 3+ grup: Levene, Welch, eta-kare, Tukey/Games-Howell |
| `run_correlation` | CORRELATIONS / NONPAR CORR | Pearson veya Spearman |
| `run_crosstabs` | CROSSTABS | Ki-kare, Phi/Cramer's V, beklenen frekanslar |
| `run_mann_whitney` | NPAR TESTS /M-W | Bağımsız t-testinin parametrik olmayan karşılığı |
| `run_kruskal_wallis` | NPAR TESTS /K-W | ANOVA'nın parametrik olmayan karşılığı |
| `run_wilcoxon` | NPAR TESTS /WILCOXON | Bağımlı t-testinin parametrik olmayan karşılığı |

Her analiz aracı şunları döndürür: çalışan SPSS syntax'ı (`syntax`), aynı işlemin SPSS menüsündeki yolu (`spss_menu`, İngilizce arayüz) ve tüm çıktı tabloları (`tables`). Syntax builder'ları `worker/analyses.py` içinde. Değişken adları doğrulanıyor, kullanıcıdan gelen ham syntax çalıştırılmıyor.

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
- `NOEMA_TIMEOUT`: Tek analiz için saniye cinsinden zaman aşımı. Varsayılan 300.
- `NOEMA_PERSISTENT`: `1` (varsayılan) SPSS motorunu çağrılar arasında açık tutar. `0` her çağrıda SPSS'i yeniden başlatır (eski davranış).
- `NOEMA_IDLE_MINUTES`: Motor bu kadar dakika boyunca kullanılmazsa kapanır, sonraki çağrıda yeniden açılır. Varsayılan 30.
- `NOEMA_START_TIMEOUT`: Motorun açılması için beklenecek süre (sn). Varsayılan 180.

### Sıcak motor nasıl çalışıyor
İlk araç çağrısında `spss_worker.py --serve` başlar, SPSS motorunu açar ve yalnızca `127.0.0.1` üzerinde rastgele bir portu dinler. Her istek, sunucunun ürettiği rastgele bir token taşır. Sunucu kapanınca (Claude kapatılınca) bağlantı kopar ve işçi de kendini kapatır, arkada SPSS süreci kalmaz. İşçi çökerse sonraki çağrıda bir kez otomatik yeniden başlatılır. Her yanıtta `engine` ("sicak" / "yeni baslatildi") ve `elapsed_seconds` alanları bulunur. İşçinin konsol çıktısı `~/Noema/logs/worker.log` dosyasına yazılır.

## Durum (2026-11-04)
- SPSS 27 / Windows 11 (Türkçe bölge ayarı) üzerinde uçtan uca doğrulandı: Claude Desktop Chat, `check_spss`, `inspect_dataset` ve `run_descriptives` çalışıyor, gerçek SPSS tablosu geliyor.
- macOS'taki SPSS Python yolları tahmin; gerçek bir Mac kurulumunda doğrulanması gerekiyor.
- Analiz araçları (frekans ... Wilcoxon) sahte `spss` modülüyle test edildi, gerçek SPSS'te henüz denenmedi.
- Sıcak motor (kalıcı işçi) sahte SPSS ile test edildi: yeniden kullanım, çökme sonrası yeniden başlatma, boşta kapanma ve sunucu öldürülünce işçinin kapanması.
- Rehber skill: `skill/noema-spss-rehber/`.
- Sırada: `.mcpb` paketi, Cronbach alfa ve ölçek puanı hesaplama araçları.
