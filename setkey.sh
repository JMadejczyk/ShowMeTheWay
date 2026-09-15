#!/bin/sh
# Sets GEMINI_API_KEY in .env.local without touching any other line.
# Key is read silently: never echoed, never in shell history.
cd "$(dirname "$0")" || exit 1
[ -f .env.local ] || printf 'GEMINI_API_KEY=\n' > .env.local

printf 'Gemini API key (input hidden): '
stty -echo 2>/dev/null; IFS= read -r K; stty echo 2>/dev/null; printf '\n'

[ -n "$K" ] || { echo "empty, nothing changed"; exit 1; }

TMP=$(mktemp)
if grep -q '^GEMINI_API_KEY=' .env.local; then
  awk -v k="$K" '/^GEMINI_API_KEY=/{print "GEMINI_API_KEY=" k; next} {print}' .env.local > "$TMP"
else
  { cat .env.local; printf 'GEMINI_API_KEY=%s\n' "$K"; } > "$TMP"
fi
mv "$TMP" .env.local
chmod 600 .env.local
unset K

echo "written (length hidden). reloading server config…"
curl -s localhost:8000/api/health | python3 -m json.tool
