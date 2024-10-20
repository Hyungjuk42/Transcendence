#!/bin/sh

# Create the keystore
/usr/share/kibana/bin/kibana-keystore create
echo -e "${KIBANA_SYSTEM_PASSWORD}" | /usr/share/kibana/bin/kibana-keystore add elasticsearch.password
/usr/share/kibana/bin/kibana
# /usr/share/kibana/bin/kibana-kestore add elasticsearch.password