# Uygulamayı Kapatma ve Yeniden Başlatma

## Sorun: Ctrl+C ile durdurdum ama arayüz hâlâ açılıyor

### Kök neden (derinlemesine analiz)

Uygulama `app.run(debug=True, port=8050)` ile çalışıyordu. **Flask/Dash, `debug=True` iken varsayılan olarak Werkzeug "reloader" kullanır:**

1. **İki süreç oluşur:**
   - **Ana (parent) süreç:** Dosya değişikliklerini izler, kodu yeniden yüklemek için child'ı yeniden başlatır.
   - **Child süreç:** Asıl web sunucusu; **8050 portunu bu süreç dinler**.

2. **Ctrl+C ne yapar?**
   - Sinyal çoğunlukla sadece **terminalde gördüğünüz ana sürece** gider.
   - Ana süreç ölür, terminal "KeyboardInterrupt" veya benzeri gösterir.
   - **Child süreç bazen ölmez** ve port 8050’de dinlemeye devam eder.
   - Sonuç: Siz uygulamayı kapattığınızı sanırsınız, ama tarayıcıdan arayüze erişmeye devam edersiniz.

3. **Neden böyle?**
   - Windows’ta sinyal yönetimi ve process tree davranışı; reloader’ın child’ı ayrı bir process olarak başlatması.
   - Bazen birden fazla kez Ctrl+C child’ı da öldürür, ama bu her zaman garantili değildir.

### Yapılan düzeltmeler

1. **`app.py`**
   - `app.run(debug=True, port=8050, use_reloader=False)` yapıldı.
   - Artık **tek süreç** çalışıyor; Ctrl+C bu tek süreci sonlandırır ve port 8050 serbest kalır.

2. **Yine de port takılı kalırsa**
   - `scripts\stop_app.ps1` ile 8050’i dinleyen süreç zorla kapatılır:
     ```powershell
     .\scripts\stop_app.ps1
     ```
   - Veya elle:
     ```powershell
     netstat -ano | findstr :8050
     # LISTENING satırındaki son sayı PID
     taskkill /F /PID <PID>
     ```

## Nasıl kapatıp yeniden başlatabilirim?

1. **Normal kapatma:** Çalıştırdığınız terminalde **Ctrl+C** (artık tek süreç olduğu için genelde yeterli).
2. **Yeniden başlatma:** Aynı terminalde:
   ```powershell
   python app.py
   ```
3. **Arayüz hâlâ açılıyorsa:** Önce `.\scripts\stop_app.ps1` çalıştırın, sonra `python app.py` ile tekrar başlatın.

## Özet

| Durum | Çözüm |
|--------|--------|
| Ctrl+C ile kapattım, arayüz hâlâ açılıyor | `use_reloader=False` sayesinde artık tek süreç; Ctrl+C yeterli olmalı. Eski oturumda kaldıysanız `scripts\stop_app.ps1` kullanın. |
| Port 8050 hâlâ meşgul | `.\scripts\stop_app.ps1` veya `taskkill /F /PID <PID>` |
| Temiz yeniden başlatma | `.\scripts\stop_app.ps1` → `python app.py` |
