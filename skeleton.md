# Project Skeleton: Datalake-GUI (Microservices Migration)

Bu dosya projenin fiziksel yapısını ve temel yapılandırma kurallarını tanımlar. Gemini, bu yapıyı fiziksel olarak oluşturmakla yükümlüdür.

## 1. Directory Hierarchy (Plaintext)

Datalake-GUI/
├── .env                        # Çevre değişkenleri
├── .gitignore                  # Python, OS ve IDE dosyaları
├── .dockerignore               # Docker build optimizasyonu
├── README.md                   # Proje genel dökümantasyonu
├── docker-compose.yml          # Servis orkestrasyonu (Base setup)
├── docs/                       # Proje Yönetim ve Bilgi Merkezi
│   ├── architecture.md         # Servis haberleşme şeması
│   ├── lessons.md              # Hatalardan çıkarılan dersler
│   ├── skills.md               # Senior Dev (Claude) çalışma kuralları
│   ├── todolist.md             # İş takip listesi
│   └── legacy/                 # Eski kod referansları (.md)
│       ├── db_logic.md
│       ├── query_logic.md
│       └── ui_components.md
├── scripts/                    # Setup ve otomasyon scriptleri
├── services/                   # Mikroservisler
│   ├── db-service/             # Veri Erişim Katmanı (FastAPI)
│   │   ├── Dockerfile (python:3.11-slim tabanlı)
│   │   ├── requirements.txt
│   │   ├── src/
│   │   └── tests/
│   ├── query-service/          # Veri Sorgu Katmanı (FastAPI)
│   │   ├── Dockerfile
│   │   ├── requirements.txt
│   │   └── src/
│   └── gui-service/            # Kullanıcı Arayüzü (Dash + DMC)
│       ├── app.py
│       ├── Dockerfile
│       ├── requirements.txt
│       ├── assets/
│       ├── components/
│       └── pages/
├── shared/                     # Ortak Kaynaklar
│   ├── schemas/                # Pydantic Veri Modelleri
│   └── utils/                  # Ortak logging ve helper fonksiyonları
└── .venv/                      # Root Python Virtual Environment

## 2. Technical Requirements

- **Base Requirements:**
    - db-service: fastapi, uvicorn, sqlalchemy, psycopg2-binary, python-dotenv
    - gui-service: dash, dash-mantine-components, pandas, requests, gunicorn
- **Dockerfile Standards:** Tüm servisler `python:3.11-slim` imajını kullanmalı ve `requirements.txt` üzerinden kurulmalıdır.
- **Documentation:** `docs/skills.md` içeriği CEO'nun paylaştığı "Workflow Orchestration" kurallarıyla başlatılmalıdır.