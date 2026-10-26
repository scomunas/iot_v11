#!/bin/sh
set -e
cat <<EOF > /usr/share/nginx/html/config.js
window.IOT_CONFIG = {
  apiKey: "${API_KEY:-}"
};
EOF
