#!/bin/sh

# Generate a self-signed certificate for the server
mkdir -p /etc/ssl/certs

generate_cert() {
  local service_name=$1
  local common_name=$2

  echo "[ req ]
default_bits = 2048
default_md = sha256
distinguished_name = req_distinguished_name
x509_extensions = v3_req

[ req_distinguished_name ]
C = KR
ST = GEYOUNG-GI-DO
L = SEOUL
O = 42SEOUL
OU = CARDET
CN = $common_name

[ v3_req ]
subjectAltName = @alt_names

[ alt_names ]
DNS.1 = $service_name
" > /tmp/openssl_$service_name.cnf

  openssl req -x509 -newkey rsa:2048 -nodes \
    -keyout /etc/ssl/certs/${service_name}-selfsigned.key \
    -out /etc/ssl/certs/${service_name}-selfsigned.crt \
    -subj "/C=KR/ST=GEYOUNG-GI-DO/L=SEOUL/O=42SEOUL/OU=CARDET/CN=$common_name" \
    -days 365 \
    -extensions v3_req \
    -config /tmp/openssl_$service_name.cnf

  echo "Certificate for $service_name generated successfully"
}

# Generate certificates for each service
generate_cert "prometheus" "prometheus"
generate_cert "node-exporter" "node-exporter"
generate_cert "alertmanager" "alertmanager"

echo "Certificates generated successfully"
