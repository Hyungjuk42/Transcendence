#!/bin/sh

if [[ -f /usr/share/elasticsearch/ca.zip ]]; then
	cp -r ca /usr/share/elasticsearch/certs
	cp -r elasticsearch /usr/share/elasticsearch/certs
	if [[ -n "$ELASTIC_PASSWORD" ]]; then
		(echo "$ELASTIC_PASSWORD") | elasticsearch-keystore add bootstrap.password
	runuser --login elasticsearch --command elasticsearch
	fi
else
	# chroot --userspec=1000
	# elasticsearch > /dev/null &
	# sleep 6
	elasticsearch-keystore create
	elasticsearch-certutil ca --pem --pass "" --out ca.zip
	unzip ca.zip
	cat ca/ca.crt ca/ca.key > ca/ca.pem
	elasticsearch-certutil cert --name elasticsearch --dns elasticsearch --dns localhost --dns kibana --ca-cert ca/ca.crt --ca-key ca/ca.key --out elasticsearch.zip --pem
	unzip elasticsearch.zip
	cp ca/ca.crt /usr/share/elasticsearch/config/
	cp ca/ca.pem /usr/share/elasticsearch/config/
	cp elasticsearch/elasticsearch.crt /usr/share/elasticsearch/config/
	cp elasticsearch/elasticsearch.key /usr/share/elasticsearch/config/
	cp /usr/share/elasticsearch/elasticsearch.yml /usr/share/elasticsearch/config/
fi
