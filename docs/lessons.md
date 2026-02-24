🎓 Lessons Learned & Pattern Prevention
Bu dosya, Datalake-GUI projesinin geliştirilmesi sırasında karşılaşılan teknik zorlukları, mimari hataları ve kullanıcı düzeltmelerini kayıt altına almak için kullanılır.

Senior Developer (Claude) için Kural: Herhangi bir hata veya kullanıcı uyarısından sonra bu dosyayı güncellemeden görevi "tamamlandı" olarak işaretleme.

## 📝 Pattern Tracking Table
Tarih	Hata/Sorun	Kök Neden	Çözüm/Yeni Kural
2026-02-23	Örnek: Port Çakışması	İki servis aynı portu denedi	architecture.md'deki port tablosuna sadık kalınacak 

## 🛠️ Öğrenilen Dersler (Kategorik)
### 1. Mimari ve Mikroservis Yönetimi
Servis İletişimi: Servisler arası asenkron yapıda Timeout hatalarını önlemek için merkezi bir retry mekanizması shared/utils altında planlanmalıdır.

Port Disiplini: architecture.md dosyasında tanımlanan port haritası dışına çıkılmamalıdır.

### 2. Kodlama ve Refactoring (Legacy -> Modern)
Tip Güvenliği: Pydantic modelleri (shared/schemas) tanımlanmadan servisler arası veri transferi yapılmamalıdır.

Legacy Logic: Eski koddaki SQL sorguları taşınırken, performans artışı için asyncpg veya benzeri asenkron sürücüler tercih edilmelidir.

### 3. Docker ve Altyapı
Build Süresi: .dockerignore dosyasının eksikliği imaj boyutlarını artırabilir. Gereksiz dosyalar (venv, pycache) her zaman hariç tutulmalıdır.

Volume Kalıcılığı: Veritabanı veya log verilerinin Docker konteyneri silindiğinde kaybolmaması için named volumes kullanımı zorunludur.

## 🚦 Nasıl Güncellenir?
Bir hata ile karşılaşıldığında şu adımları izle:
Sorunun kök nedenini (Root Cause) analiz et.
Çözümü uygula.
Çözümün kalıcı olması için bir "yazılım kuralı" türet ve bu tabloya ekle.
skills.md dosyasında bu hatayı engelleyecek bir madde eksikse orayı da güncelle.