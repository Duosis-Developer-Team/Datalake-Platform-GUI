# Release ingest token

`scripts/new_release.py` GUI'ye paylaşılan bir token'la bağlanır. Token repoda durmaz.

## Gerekli mi?

Hayır — panel ve "Yeniden üret" düğmesi bu token'ı kullanmaz, o iş pod'un içinde
sunucu tarafında koşar. Token yalnızca release'i **dışarıdan** açan script'ler için
gerekli. Secret tanımlı değilse `/internal/platform/releases*` yolları 503 döner ve
panelde hiçbir şey değişmez.

## Üretme

    python3 -c "import secrets; print(secrets.token_urlsafe(32))"

## Yerel

Değeri **`.env.local`** dosyasına yaz:

    RELEASE_INGEST_TOKEN=<üretilen değer>

`.env`'e YAZMA. `.gitignore`'da adı geçse de bu repoda `.env` git tarafından takip
ediliyor (gitignore yalnızca henüz takip edilmeyen dosyaları korur), yani oraya
yazılan secret commit'lenir. Yeni bir dosyaya secret yazmadan önce
`git ls-files --error-unmatch <dosya>` ile takip durumuna bak; `git check-ignore`
takipli dosyalarda yanıltıcı sonuç verir.

`docker compose` `.env.local`'ı kendiliğinden okumaz; `app` servisi için değeri
shell'e `export` etmen gerekir.

## Production

    kubectl create secret generic release-ingest-secret \
      --from-literal=RELEASE_INGEST_TOKEN='<üretilen değer>'

`k8s/frontend/deployment.yaml` bu secret'ı `optional: true` ile bağlar. Secret yoksa
pod yine başlar; `/internal/platform/releases*` yolları 503 döner ve panel değişmez.

## Döndürme

Secret'ı güncelle, frontend deployment'ını yeniden başlat, sonra release'i açan
makinedeki değeri değiştir. İki taraf uyuşmazsa endpoint 403 döner.
