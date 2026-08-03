# Release ingest token

`scripts/new_release.py` GUI'ye paylaşılan bir token'la bağlanır. Token repoda durmaz.

## Üretme

    python3 -c "import secrets; print(secrets.token_urlsafe(32))"

## Yerel

Değeri `.env` dosyasına yaz (`.gitignore` kapsamında):

    RELEASE_INGEST_TOKEN=<üretilen değer>

## Production

    kubectl create secret generic release-ingest-secret \
      --from-literal=RELEASE_INGEST_TOKEN='<üretilen değer>'

`k8s/frontend/deployment.yaml` bu secret'ı `optional: true` ile bağlar. Secret yoksa
pod yine başlar; `/internal/platform/releases*` yolları 503 döner ve panel değişmez.

## Döndürme

Secret'ı güncelle, frontend deployment'ını yeniden başlat, sonra release'i açan
makinedeki değeri değiştir. İki taraf uyuşmazsa endpoint 403 döner.
