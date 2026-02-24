🏗️ Datalake-GUI Mimari Detayları
Bu döküman, mikroservislerin birbirleriyle olan etkileşimini, ağ yapılandırmasını ve veri akış diyagramlarını tanımlar.

## 1. Servis Haberleşme Matrisi
Servis İsmi	Kapı    (Port)	    Görevi	                    Bağımlılıkları
GUI-Service	        8050	    Dash Frontend & UI	        query-service
Query-Service	    8002	    Business Logic & Caching	db-service, Redis
DB-Service	        8001	    Database Access (DAL)	    PostgreSQL / InfluxDB

## 2. Veri Akış Yönü (Data Flow)
Talep: Kullanıcı GUI üzerinden bir grafik yenilediğinde, gui-service bir HTTP isteği (REST) oluşturur.
Sorgu: query-service isteği alır. Önce Redis cache'e bakar.
Cache Hit: Veri varsa anında döner.
Cache Miss: Veri yoksa db-service'e sorgu atar.
Erişim: db-service veritabanından ham veriyi çeker, Pydantic modelleriyle valide eder ve JSON olarak geri gönderir.
Sunum: query-service veriyi işler (aggregate eder) ve GUI'ye iletir; GUI ise Plotly ile görselleştirir.

## 3. Ağ Yapılandırması (Networking)
Tüm servisler Docker üzerinde datalake_network adında bir bridge network üzerinden haberleşecektir. 
Servisler birbirlerine localhost yerine servis isimleriyle (örn: http://db-service:8001) erişeceklerdir.
Dış dünyaya sadece gui-service (Port 8050) açık olacaktır.

## 4. Güvenlik ve Kimlik Doğrulama
Servisler arası iletişimde .env dosyasındaki INTERNAL_API_KEY kontrolü yapılacaktır.
Veritabanı şifreleri asla kod içinde tutulmayacak, Docker Secrets veya .env üzerinden enjekte edilecektir.