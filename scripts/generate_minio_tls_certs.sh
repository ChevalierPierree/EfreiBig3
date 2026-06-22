#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CERT_DIR="${ROOT_DIR}/security/minio/certs"
CERT_DAYS="${CERT_DAYS:-365}"
CERT_CN="${CERT_CN:-localhost}"

if ! command -v openssl >/dev/null 2>&1; then
  echo "ERREUR: openssl est requis pour générer les certificats TLS." >&2
  exit 1
fi

mkdir -p "${CERT_DIR}"
umask 077

OPENSSL_CFG="$(mktemp)"
cat > "${OPENSSL_CFG}" <<EOF
[req]
default_bits = 4096
distinguished_name = req_distinguished_name
req_extensions = req_ext
x509_extensions = req_ext
prompt = no

[req_distinguished_name]
CN = ${CERT_CN}

[req_ext]
subjectAltName = @alt_names
extendedKeyUsage = serverAuth

[alt_names]
DNS.1 = localhost
DNS.2 = minio
IP.1 = 127.0.0.1
EOF

openssl req \
  -x509 \
  -nodes \
  -newkey rsa:4096 \
  -keyout "${CERT_DIR}/private.key" \
  -out "${CERT_DIR}/public.crt" \
  -days "${CERT_DAYS}" \
  -config "${OPENSSL_CFG}"

rm -f "${OPENSSL_CFG}"

echo "Certificats TLS générés:"
echo " - ${CERT_DIR}/public.crt"
echo " - ${CERT_DIR}/private.key"
echo
echo "Pour activer TLS MinIO dans docker-compose:"
echo " - export MINIO_SCHEME=https"
echo " - export MINIO_TLS_INSECURE=true   # si certificat auto-signé"
