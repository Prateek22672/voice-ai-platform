#!/bin/sh
# Inject SIP trunk credentials from the environment (.env via docker-compose) into pjsip.conf.
# Keeps secrets out of git — the config in the repo only holds CHANGE_ME placeholders.
set -e
CONF=/etc/asterisk/pjsip.conf
# public IP for SDP: explicit PUBLIC_IP env wins; else auto-detect the default-route source IP
DETECTED_IP=$(ip route get 8.8.8.8 2>/dev/null | grep -oP 'src \K\S+' || true)
PUB="${PUBLIC_IP:-$DETECTED_IP}"
sed -i "s|CHANGE_ME_SIP_USER|${SIP_TRUNK_USER:-unset}|g" "$CONF"
sed -i "s|CHANGE_ME_SIP_PASS|${SIP_TRUNK_PASS:-unset}|g" "$CONF"
sed -i "s|CHANGE_ME_DID|${SIP_DID_NUMBER:-anonymous}|g" "$CONF"
sed -i "s|CHANGE_ME_PUBLIC_IP|${PUB:-127.0.0.1}|g" "$CONF"
echo "[entrypoint] pjsip.conf templated (user=${SIP_TRUNK_USER:-unset}, did=${SIP_DID_NUMBER:-anonymous}, public_ip=${PUB:-NONE})"
exec asterisk -f -vvv
