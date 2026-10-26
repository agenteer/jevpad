#!/bin/sh
# Network baseline: 20 unauthenticated requests per host; prints median connect, TLS and first-byte times (s).
label="$1"
for host in https://ai-gateway.vercel.sh/v1/models https://api.openai.com/v1/models https://ai-gateway.vercel.sh/v1/decisions; do
  for i in $(seq 1 20); do curl --connect-timeout 10 --max-time 30 -s -o /dev/null -w '%{time_connect} %{time_appconnect} %{time_starttransfer}\n' "$host"; done |
  sort -k3 -n | awk -v h="$host" -v l="$label" '{c[NR]=$1; t[NR]=$2; f[NR]=$3} END {m=int((NR+1)/2); printf "%s %s median connect=%.3f tls=%.3f first_byte=%.3f n=%d\n", l, h, c[m], t[m], f[m], NR}'
done
