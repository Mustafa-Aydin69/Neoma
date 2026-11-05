# Noema

**Claude ile yerel IBM SPSS Statistics arasında MCP köprüsü ve tez analiz rehberi**

![Sürüm](https://img.shields.io/badge/s%C3%BCr%C3%BCm-0.5.0-blue)
![SPSS](https://img.shields.io/badge/SPSS-27-052FAD)
![Platform](https://img.shields.io/badge/platform-Windows%20%7C%20macOS%20(deneysel)-lightgrey)
![Python](https://img.shields.io/badge/python-3.10%2B-3776AB)
![Durum](https://img.shields.io/badge/durum-prototip-orange)

Noema, yüksek lisans öğrencilerinin tez analizlerini kendi bilgisayarlarındaki IBM SPSS Statistics üzerinde yapmalarına **ve anlamalarına** yardım eder. Claude Desktop, analizi SPSS motorunda çalıştırır, gerçek SPSS çıktısını okur, sonucu sade Türkçeyle açıklar ve aynı işlemin SPSS'te nasıl yapılacağını (syntax ve menü yolu) gösterir.

> **Temel ilke:** İstatistikler yalnızca SPSS'ten gelir. Claude hiçbir testi kendisi hesaplamaz; SPSS'in vermediği bir değer türetilirse formülüyle birlikte gösterilir. `.sav` dosyası hiçbir zaman değiştirilmez veya kaydedilmez.

---

## İçindekiler

- [Özellikler](#özellikler)
- [Nasıl çalışır](#nasıl-çalışır)
- [Gereksinimler](#gereksinimler)
- [Kurulum](#kurulum)
  - [Seçenek A: Tek tıkla kurulum (.mcpb)](#seçenek-a-tek-tıkla-kurulum-mcpb)
  - [Seçenek B: Elle kurulum (geliştirici)](#seçenek-b-elle-kurulum-geliştirici)
  - [Rehber skill'i ekleme](#rehber-skilli-ekleme)
- [Kullanım](#kullanım)
- [Analiz araçları](#analiz-araçları)
- [Grafikler](#grafikler)
- [Kayıtlar ve tekrarlanabilirlik](#kayıtlar-ve-tekrarlanabilirlik)
- [Yapılandırma](#yapılandırma)
- [Sorun giderme](#sorun-giderme)
- [Geliştirme](#geliştirme)
- [Proje yapısı](#proje-yapısı)
- [Durum ve yol haritası](#durum-ve-yol-haritası)

---

## Özellikler

- **23 analiz aracı:** betimsel istatistik, normallik, t-testleri, tek/çok yönlü ANOVA, tekrarlı ölçümler ve karışık desen ANOVA, ANCOVA, MANOVA/MANCOVA, korelasyon, doğrusal ve lojistik regresyon, faktör analizi, güvenirlik (Cronbach alfa), ki-kare ve parametrik olmayan testler.
- **Gerçek SPSS çıktısı:** Analizler SPSS motorunda çalışır; tablolar OMS (XML) üzerinden okunur.
- **Öğretici çıktı:** Her sonuçla birlikte çalışan syntax ve İngilizce arayüzdeki menü yolu gelir; kullanıcı aynı analizi SPSS'te kendisi tekrarlayabilir.
- **Grafikler:** `charts=True` ile boxplot, Q-Q, artık, scree ve profil grafikleri resim olarak Claude'a aktarılır.
- **Rehber skill:** Araştırma desenini netleştiren, uygun testi gerekçelendiren ve sonuçları APA tarzında raporlamaya yardım eden Claude skill'i.
- **Hızlı ve güvenli motor:** SPSS motoru çağrılar arasında açık kalır (yalnızca `127.0.0.1`, token ile korunur), boşta kalınca ve Claude kapanınca kendini kapatır.
- **Türkçe Windows desteği:** SPSS 27'nin Türkçe bölge ayarında çökmesine yol açan hata otomatik olarak aşılır; Windows ayarlarına dokunmak gerekmez.
- **Tek tıkla kurulum:** `.mcpb` paketiyle Python veya git kurmadan yüklenebilir.

## Nasıl çalışır

```
Claude Desktop
     │  MCP (stdio)
     ▼
noema_mcp/server.py          Modern Python (3.10+), MCP sunucusu
     │  JSON · 127.0.0.1 + token
     ▼
worker/spss_worker.py        SPSS'in kendi Python'u (SPSS 27'de 3.8)
     │  spss.Submit + OMS (XML, İngilizce çıktı)
     ▼
IBM SPSS Statistics motoru
```

İki ayrı Python kullanılmasının nedeni: MCP kütüphanesi Python 3.10 veya üstünü gerektirir, SPSS 27 ile gelen `spss` modülü ise yalnızca SPSS'in kendi Python 3.8 kurulumunda çalışır. Sunucu, SPSS işlerini ayrı bir işçi sürece devreder ve sonuçları JSON olarak geri alır.

Analiz syntax'ı `worker/analyses.py` içinde araç parametrelerinden üretilir. Değişken adları doğrulanır; kullanıcıdan veya modelden gelen ham syntax çalıştırılmaz.

## Gereksinimler

| | |
|---|---|
| **İşletim sistemi** | Windows 10/11 (test edildi). macOS desteği deneysel, henüz doğrulanmadı. |
| **SPSS** | IBM SPSS Statistics, Python Essentials ile birlikte (SPSS 27 ile test edildi). İleri analizler için ilgili modüller (ör. Advanced Statistics, Exact Tests) lisanslı olmalı. |
| **Claude** | Claude Desktop (Microsoft Store ve standart sürüm). |
| **Python** | Yalnızca elle kurulumda: Python 3.10+ (3.13 ve 3.14 ile denendi). `.mcpb` kurulumunda gerekmez. |

## Kurulum

### Seçenek A: Tek tıkla kurulum (.mcpb)

Önerilen yol budur. Python ya da git gerekmez; Claude Desktop gerekli Python ortamını (`uv` ile) kendisi hazırlar.

1. `noema-spss-0.5.0.mcpb` dosyasını edinin (ya da [kendiniz paketleyin](#mcpb-paketini-üretme)).
2. Claude Desktop'ta **Settings › Extensions** sayfasına dosyayı sürükleyip bırakın veya dosyaya çift tıklayın, ardından **Install**'a basın.
3. SPSS olağan kurulum klasörlerinde otomatik bulunur. Bulunamazsa eklentinin **Configure** ekranında SPSS klasöründeki `Python3\python.exe` dosyasını seçin
   (ör. `C:\Program Files\IBM\SPSS\Statistics\27\Python3\python.exe`).
4. Yeni bir sohbet açıp **"check_spss çalıştır"** yazın. SPSS sürümü ve bağlantı bilgisi gelmelidir.

> Daha önce elle kurulum yaptıysanız `claude_desktop_config.json` içindeki `noema-spss` girdisini silin; aksi halde araçlar iki kez görünür.

### Seçenek B: Elle kurulum (geliştirici)

1. Repoyu klonlayın:
   ```bat
   git clone https://github.com/Mustafa-Aydin69/Neoma.git C:\noema
   ```
2. Sanal ortamı kurun (SPSS'in kendi Python'unu **kullanmayın**):
   ```bat
   cd C:\noema
   py -3.14 -m venv .venv
   .venv\Scripts\pip install -r requirements.txt
   ```
3. İşçi süreci tek başına test edin (PowerShell'de satırın başına `& ` ekleyin):
   ```bat
   "C:\Program Files\IBM\SPSS\Statistics\27\Python3\python.exe" C:\noema\worker\spss_worker.py --test
   "C:\Program Files\IBM\SPSS\Statistics\27\Python3\python.exe" C:\noema\worker\spss_worker.py --test "C:\Program Files\IBM\SPSS\Statistics\27\Samples\English\Employee data.sav"
   ```
   İki komut da `=== NOEMA ===` satırından sonra JSON çıktısı vermelidir.
4. Claude Desktop'u tamamen kapatın (sistem tepsisinden **Quit**) ve sunucuyu ayarlara ekleyin:
   ```bat
   .venv\Scripts\python.exe tools\add_to_claude_config.py
   ```
   Betik mevcut ayarlara dokunmadan yalnızca `mcpServers.noema-spss` girdisini ekler ve bir `.yedek` kopyası alır. Ayar dosyası bulunamazsa gerçek yolu **Settings › Desktop app › Extensions › Local MCP servers › Edit config** ekranından bulup betiğe argüman olarak verin.
5. Claude Desktop'u açın; aynı ekranda `noema-spss` **Running** görünmelidir.
6. **Chat** sekmesinde yeni bir sohbette **"check_spss çalıştır"** yazın.

**Güncelleme:** `git pull`, ardından Claude Desktop'u tamamen kapatıp yeniden açın.

### Rehber skill'i ekleme

`skill/noema-spss-rehber/` klasörü, Claude'a tez danışmanı gibi davranmayı öğreten skill'i içerir: önce araştırma sorusunu ve deseni netleştirir, testi gerekçelendirir, varsayımları kontrol eder, sonra analizi çalıştırıp raporlamaya yardım eder.

1. `skill/noema-spss-rehber` klasörünü zip olarak sıkıştırın (zip'in içinde `noema-spss-rehber/SKILL.md` bulunmalı).
2. Claude'da **Settings › Capabilities › Skills** bölümünden zip dosyasını yükleyin.

Başvuru dosyaları: [`test-secimi.md`](skill/noema-spss-rehber/references/test-secimi.md) (desene göre test seçimi) ve [`raporlama.md`](skill/noema-spss-rehber/references/raporlama.md) (APA tarzı raporlama).

## Kullanım

Örnek bir konuşma akışı:

1. **Veriyi tanıma:** *"C:\Users\Ad\Desktop\tez.sav dosyasındaki değişkenlere bak."* → `inspect_dataset` değişkenleri, etiketleri, ölçüm düzeylerini ve eksik değer tanımlarını listeler.
2. **Deseni netleştirme:** Skill; grup yapısını (ör. deney/kontrol), ölçüm zamanlarını (ön test, son test, izleme) ve hipotezleri sorar.
3. **Plan:** Uygulanacak testler, varsayımlar ve gerekçe analizden önce açıklanır.
4. **Analiz:** Araçlar SPSS'te çalışır; sonuçla birlikte syntax ve menü yolu gelir.
5. **Yorum ve raporlama:** Sonuçlar sade dille açıklanır, etki büyüklükleri ve raporlama önerileri verilir.

> `path` her zaman `.sav` dosyasının **tam yoludur**. Türkçe karakterli yollar olduğu gibi kullanılabilir.

## Analiz araçları

| Araç | SPSS komutu | Ne için |
|---|---|---|
| `check_spss` | SHOW N | Bağlantı ve sürüm testi |
| `inspect_dataset` | Dataset API | Değişkenler, etiketler, ölçüm düzeyi, eksik değer tanımları |
| `run_descriptives` | DESCRIPTIVES | Sürekli değişkenlerin özeti |
| `run_frequencies` | FREQUENCIES | Kategorik ve demografik değişkenler |
| `run_normality` | EXAMINE | Kolmogorov-Smirnov ve Shapiro-Wilk (gruplara göre de) |
| `run_ttest_independent` | T-TEST GROUPS | İki bağımsız grup; Levene ve Cohen's d |
| `run_ttest_paired` | T-TEST PAIRS | Ön test / son test karşılaştırması |
| `run_anova_oneway` | ONEWAY | 3+ grup; Levene, Welch, eta kare, Tukey / Games-Howell |
| `run_anova_factorial` | UNIANOVA | İki/üç yönlü ANOVA, etkileşim, basit etkiler, post hoc |
| `run_rm_anova` | GLM /WSFACTOR | Tekrarlı ölçümler ANOVA; `group` ile karışık desen (zaman × grup) |
| `run_ancova` | UNIANOVA … WITH | Kovaryat kontrolüyle grup farkı; eğim homojenliği, düzeltilmiş ortalamalar |
| `run_manova` | GLM (çok bağımlı) | MANOVA/MANCOVA; Box's M, Pillai/Wilks, tek değişkenli izleme testleri |
| `run_correlation` | CORRELATIONS / NONPAR CORR | Pearson veya Spearman |
| `run_regression` | REGRESSION | Çoklu/hiyerarşik regresyon; R², ΔR², β, VIF, Durbin-Watson |
| `run_logistic` | LOGISTIC REGRESSION | İkili lojistik regresyon; Nagelkerke R², Hosmer-Lemeshow, odds oranları |
| `run_factor` | FACTOR | Açıklayıcı faktör analizi; KMO, Bartlett, döndürülmüş yükler |
| `run_reliability` | RELIABILITY | Cronbach alfa, madde-toplam korelasyonları, ters maddeler |
| `run_scale_score` | COMPUTE + DESCRIPTIVES | Maddelerden toplam/ortalama puan (ters maddeler dahil, dosyaya kaydedilmez) |
| `run_crosstabs` | CROSSTABS | Ki-kare, Phi / Cramér's V, beklenen frekanslar |
| `run_mann_whitney` | NPAR TESTS /M-W | Bağımsız t-testinin parametrik olmayan karşılığı |
| `run_wilcoxon` | NPAR TESTS /WILCOXON | Bağımlı t-testinin parametrik olmayan karşılığı |
| `run_kruskal_wallis` | NPAR TESTS /K-W | Tek yönlü ANOVA'nın parametrik olmayan karşılığı |
| `run_friedman` | NPAR TESTS /FRIEDMAN + /KENDALL | Aynı kişilerde 3+ ölçüm |

**Ortak seçenekler**

- `filter_variable` / `filter_value`: Analizi bir alt gruba sınırlar (ör. yalnızca deney grubu: `grup` = `1`).
- `exact=True`: Parametrik olmayan testlerde kesin p değeri verir; küçük örneklemlerde önerilir (Exact Tests modülü gerekir).
- `reverse_items` + `scale_min` / `scale_max`: Güvenirlik ve ölçek puanında ters maddeleri çevirir.

**Her analiz aracının döndürdüğü alanlar**

| Alan | İçerik |
|---|---|
| `syntax` | SPSS'te çalıştırılan syntax |
| `spss_menu` | Aynı işlemin SPSS menüsündeki yolu (İngilizce arayüz) |
| `tables` | Tüm çıktı tabloları |
| `engine`, `elapsed_seconds` | Motor durumu ("sicak" / "yeni baslatildi") ve süre |

## Grafikler

`run_normality`, `run_regression`, `run_factor`, `run_rm_anova`, `run_anova_factorial`, `run_ancova` ve `run_manova` araçlarına `charts=True` verildiğinde SPSS'in ürettiği grafikler (boxplot, Q-Q, artık, scree, profil, gruplara göre saçılım) resim olarak Claude'a gönderilir. Çağrı başına en fazla 16 grafik aktarılır; grafikler log dosyalarına yazılmaz.

## Kayıtlar ve tekrarlanabilirlik

Her çalıştırma `~/Noema/logs/` altında kayıt altına alınır:

| Dosya | İçerik |
|---|---|
| `runs.jsonl` | Her isteğin ve sonucun tam kaydı |
| `syntax.sps` | Çalıştırılan tüm syntax; doğrudan SPSS'te açılıp yeniden çalıştırılabilir |
| `worker.log` | İşçi sürecin konsol çıktısı (sorun giderme için) |

Bu sayede tezdeki her sonucun hangi komutla üretildiği belgelenmiş olur.

## Yapılandırma

Elle kurulumda ortam değişkenleriyle, `.mcpb` kurulumunda eklentinin **Configure** ekranından ayarlanır.

| Değişken | Varsayılan | Açıklama |
|---|---|---|
| `NOEMA_SPSS_PYTHON` | otomatik | SPSS'in `python.exe` yolu |
| `NOEMA_LOG_DIR` | `~/Noema/logs` | Kayıt klasörü |
| `NOEMA_TIMEOUT` | `300` | Tek analiz için zaman aşımı (sn) |
| `NOEMA_PERSISTENT` | `1` | `1`: SPSS motoru çağrılar arasında açık kalır. `0`: her çağrıda yeniden başlar |
| `NOEMA_IDLE_MINUTES` | `30` | Motor bu süre kullanılmazsa kapanır; sonraki çağrıda yeniden açılır |
| `NOEMA_START_TIMEOUT` | `180` | Motorun açılması için beklenecek süre (sn) |

### Sıcak motor

İlk araç çağrısında `spss_worker.py --serve` başlar, SPSS motorunu açar ve yalnızca `127.0.0.1` üzerinde rastgele bir portu dinler. Her istek, sunucunun ürettiği rastgele bir token taşır. Claude kapanınca bağlantı kopar ve işçi de kendini kapatır; arkada SPSS süreci kalmaz. İşçi çökerse sonraki çağrıda bir kez otomatik olarak yeniden başlatılır.

## Sorun giderme

<details>
<summary><b>Türkçe Windows'ta SPSS çöküyor (UnicodeDecodeError)</b></summary>

Windows 11 bölge adını `Turkish_Türkiye.1254` olarak bildirir. SPSS 27 bu adı UTF-8 sanarak okur ve `ü` harfinde çöker. Noema, `spss` modülünü yüklemeden önce bölge ayarını uyumlu bir değere sabitler ve SPSS'in hatalı fonksiyonunu sarmalar. Kullanıcının bir şey yapmasına gerek yoktur.
</details>

<details>
<summary><b>Microsoft Store sürümünde ayar dosyası bulunamıyor</b></summary>

Store sürümünde `claude_desktop_config.json` dosyası `%APPDATA%\Claude` içinde değil, `%LOCALAPPDATA%\Claude-Data\claude_<id>\` içindedir. Ayarlarda "Developer" bölümü yoktur; dosyaya **Settings › Desktop app › Extensions › Local MCP servers › Edit config** ile ulaşılır.
</details>

<details>
<summary><b>Araçlar Code sekmesinde görünmüyor</b></summary>

`claude_desktop_config.json` dosyasını **Chat** sekmesi okur. **Code** sekmesi MCP sunucularını proje klasöründeki `.mcp.json` dosyasından alır.
</details>

<details>
<summary><b>Yeni bir araç görünmüyor</b></summary>

`git pull` yapın (ya da yeni `.mcpb` paketini kurun) ve Claude Desktop'u sistem tepsisinden **Quit** ile tamamen kapatıp yeniden açın.
</details>

<details>
<summary><b>Analiz 60 saniyede zaman aşımına uğruyor</b></summary>

İşçi süreç MCP'nin stdin kanalını devralırsa SPSS takılır. Sunucu bu yüzden işçiyi `stdin=DEVNULL` ile başlatır. Sorun sürerse `~/Noema/logs/worker.log` dosyasına bakın.
</details>

## Geliştirme

### İşçiyi tek başına test etme

```bat
"<SPSS Python>" worker\spss_worker.py --test               :: bağlantı testi
"<SPSS Python>" worker\spss_worker.py --test "veri.sav"    :: veri seti inceleme
```

### .mcpb paketini üretme

Repo kökünde:

```bash
npx @anthropic-ai/mcpb pack . dist/noema-spss.mcpb
```

`.mcpbignore`; skill, araç betikleri ve veri dosyalarını (`.sav`, `.spv`) paketin dışında bırakır. Paket `uv` sunucu tipini kullanır; bağımlılıklar `pyproject.toml` dosyasından kurulur.

### Yeni analiz eklerken

1. Syntax üreticisini `worker/analyses.py` içine ekleyin (değişken adlarını doğrulayın, `spss_menu` yolunu tanımlayın).
2. Aracı `noema_mcp/server.py` içinde `@mcp.tool()` ile tanımlayın.
3. Önce sahte `spss` modülüyle, ardından gerçek SPSS'te bilinen bir veri setiyle (ör. `Employee data.sav`) doğrulayın.
4. Skill'deki test seçimi ve raporlama rehberini güncelleyin.

## Proje yapısı

```
Neoma/
├── noema_mcp/
│   └── server.py              MCP sunucusu: araç tanımları, işçi yönetimi, loglama
├── worker/
│   ├── spss_worker.py         SPSS'in Python'unda çalışan işçi (OMS, locale düzeltmesi, sıcak motor)
│   └── analyses.py            Analiz başına syntax üreticileri ve menü yolları
├── skill/
│   └── noema-spss-rehber/     Claude rehber skill'i (SKILL.md + references/)
├── tools/
│   └── add_to_claude_config.py  Elle kurulum için Claude Desktop ayar betiği
├── manifest.json              .mcpb paket tanımı
├── pyproject.toml             Paket bağımlılıkları (mcp>=1.2,<2)
└── requirements.txt           Elle kurulum bağımlılıkları
```

## Durum ve yol haritası

**Sürüm 0.5.0 · prototip**

Doğrulananlar (Windows 11, Türkçe bölge ayarı, SPSS 27.0.1):

- [x] Claude Desktop Chat üzerinden uçtan uca çalışma, sıcak motor
- [x] `inspect_dataset`, betimsel istatistikler
- [x] Karışık desen ANOVA (`run_rm_anova`); sonuçlar SPSS arayüzünde elde edilen çıktılarla birebir eşleşti
- [x] Güvenirlik (ters maddeler dahil) ve ölçek puanı
- [x] ANCOVA ve MANOVA
- [x] Grafiklerin resim olarak aktarılması (`charts=True`)
- [x] Türkçe bölge ayarı düzeltmesi
- [x] Rehber skill

Sırada:

- [ ] Kalan araçların gerçek SPSS'te doğrulanması (tek yönlü ANOVA, Kruskal-Wallis, korelasyon, ki-kare vb.; bunlar şimdilik sahte `spss` modülüyle test edildi)
- [ ] `.mcpb` paketinin farklı bilgisayarlarda denenmesi
- [ ] macOS desteği (SPSS Python yolları şimdilik tahmine dayalı)
- [ ] Diğer SPSS sürümleriyle uyumluluk testi

---

*IBM ve SPSS, International Business Machines Corporation'ın ticari markalarıdır. Noema bağımsız bir projedir; IBM ile bağlantılı değildir. Noema bir SPSS lisansı içermez, kullanıcının kendi lisanslı kurulumuyla çalışır.*
