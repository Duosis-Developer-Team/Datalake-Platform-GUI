🌐 Datalake-Platform-GUI (Microservices)
Bu proje, mevcut monolitik veri gölü platformunun ölçeklenebilirlik, sürdürülebilirlik ve yüksek performans hedefleri doğrultusunda mikroservis mimarisine dönüştürülmüş halidir. Platform; VMware, Nutanix, IBM ve Loki gibi çeşitli veri kaynaklarından gelen metrikleri asenkron olarak toplar ve Plotly Dash tabanlı modern bir arayüz ile sunar.

## 🏗️ Mimari Genel Bakış
Proje, birbirleriyle Docker network üzerinden haberleşen bağımsız servislerden oluşmaktadır:
GUI Service (Port 8050): Plotly Dash ve Dash Mantine Components (DMC) kullanılarak geliştirilmiş frontend katmanıdır.
Query Service (Port 8002): İş mantığını (Business Logic) yürüten, veri kaynaklarına (VMware, Nutanix, vb.) özel sorguları yöneten ve caching mekanizmasını barındıran asenkron FastAPI servisidir.
DB Service (Port 8001): Veritabanı erişim katmanıdır (DAL). Grafana-backed veritabanlarına güvenli erişim sağlar ve ham veriyi Pydantic modellerine dönüştürerek sunar.

## 🛠️ Teknoloji Stack
Frontend: Plotly Dash, Dash Mantine Components (v0.14+).
Backend: Python 3.11+, FastAPI (Asynchronous).
Veri Yönetimi: PostgreSQL, SQLAlchemy (ORM), Redis (Caching).
Altyapı: Docker, Docker Compose.
Geliştirme Ortamı: Cursor IDE, Claude Code (Senior Agent).

## 🚦 Hızlı Başlangıç (Setup)
Projeyi yerel ortamda çalıştırmak için:
Gereksinimler: Docker Desktop'ın kurulu ve çalışır durumda olduğundan emin olun.
Ortam Değişkenleri: .env dosyasındaki veritabanı ve API bilgilerini güncelleyin.
Çalıştırma: Terminalden aşağıdaki komutu verin:
Bash
docker-compose up --build
Erişim: Tarayıcınızdan http://localhost:8050 adresine gidin.

## 📜 Geliştirme Standartları
Bu projede çalışan tüm geliştiriciler (AI ve İnsan) docs/skills.md dosyasındaki "Workflow Orchestration" kurallarına uymak zorundadır. Temel prensiplerimiz:
Plan Mode: Her büyük değişiklikten önce bir plan sunulmalıdır.
Legacy Integrity: docs/legacy/ klasöründeki eski kodların mantığı korunarak modernize edilmelidir.
Elegance: Kod yazımında "Staff Level" mühendislik standartları esastır.

## 📅 Yol Haritası (Roadmap)
Güncel iş listesi ve aşamalar için docs/todolist.md dosyasını takip edin.