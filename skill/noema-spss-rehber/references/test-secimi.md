# Test seçimi

| Soru | Bağımlı değişken | Desen | Parametrik (varsayımlar sağlanırsa) | Parametrik olmayan |
|---|---|---|---|---|
| İki grup farklı mı? | Sürekli | Bağımsız 2 grup | `run_ttest_independent` | `run_mann_whitney` |
| Üç ve üzeri grup farklı mı? | Sürekli | Bağımsız k grup | `run_anova_oneway` (+ post hoc) | `run_kruskal_wallis` |
| İki etken birlikte (ve etkileşimi)? | Sürekli | Bağımsız gruplar, 2–3 faktör | `run_anova_factorial` | — |
| Ön test ve son test farklı mı? | Sürekli | Aynı kişiler, 2 ölçüm | `run_ttest_paired` | `run_wilcoxon` |
| Aynı kişilerde 3+ ölçüm farklı mı? | Sürekli/sıralı | Aynı kişiler, k ölçüm | `run_rm_anova` (gruplu desende `group` ile zaman × grup) | `run_friedman` + Bonferroni'li `run_wilcoxon` |
| Ölçek güvenilir mi? | Maddeler | — | `run_reliability` (Cronbach alfa; ters maddeler `reverse_items`) | — |
| Ölçek puanı nasıl? | Maddeler | — | `run_scale_score` (toplam/ortalama + betimsel) | — |
| İki değişken ilişkili mi? | İki sürekli değişken | — | `run_correlation` (pearson) | `run_correlation` (spearman) |
| Değişkenler bir sonucu ne kadar yordar? | Sürekli | — | `run_regression` (enter; hiyerarşik bloklar) | — |
| İki kategorili bir sonucu ne yordar? | İki kategorili | — | `run_logistic` | — |
| Ölçek kaç boyutlu? | Maddeler | — | `run_factor` (AFA) | — |
| İki kategorik değişken ilişkili mi? | Kategorik | — | `run_crosstabs` (ki-kare) | — |
| Örneklem nasıl? | Her tür | — | `run_frequencies`, `run_descriptives` | — |

## Notlar
- **Likert:** Tek bir Likert maddesi sıralı veridir. Parametrik olmayan test veya
  frekans uygundur. Maddelerin toplam/ortalama puanı ise genelde sürekli kabul edilir.
- **Küçük gruplar:** Grup başına n < 30 ve normallik şüpheliyse parametrik olmayan teste yönel.
- **ANOVA post hoc:** Varyanslar homojense Tukey, değilse Games-Howell (GH).
- **Çoklu karşılaştırma:** Aynı veride çok sayıda test yapılıyorsa I. tip hata
  riskinden söz et.
