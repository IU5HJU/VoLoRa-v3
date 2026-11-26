#!/usr/bin/env bash
# Assembla il sito statico (pagina di installazione del firmware di misura) in una cartella.
#   tools/make_site.sh <cartella-artefatti> <cartella-uscita> <versione> <commit>
# <cartella-artefatti> contiene firmware-t3/ e firmware-tbeam1262/ (come li scarica actions/download-artifact), ognuna con web_factory.bin.
# Struttura prodotta: index.html, version.json, firmware/<scheda>/{web_factory.bin,manifest.json}
# Il firmware di misura non salva impostazioni, quindi si scrive l'immagine intera all'indirizzo 0 (un solo pezzo).
set -euo pipefail
in=${1:?cartella degli artefatti}
out=${2:?cartella di uscita}
version=${3:?versione}
commit=${4:?commit}
here=$(cd "$(dirname "$0")/.." && pwd)

rm -rf "$out"
mkdir -p "$out/firmware"
cp "$here/site/index.html" "$here/site/nodo.html" "$out/"
touch "$out/.nojekyll"

for pair in "t3:firmware-t3" "tbeam1262:firmware-tbeam1262"; do
  board=${pair%%:*}
  art=${pair#*:}
  test -f "$in/$art/web_factory.bin" || { echo "manca $in/$art/web_factory.bin" >&2; exit 1; }
  mkdir -p "$out/firmware/$board"
  cp "$in/$art/web_factory.bin" "$out/firmware/$board/web_factory.bin"
  cat > "$out/firmware/$board/manifest.json" <<JSON
{
  "name": "VoLoRa V3 misura ($board)",
  "version": "$version",
  "new_install_prompt_erase": false,
  "builds": [
    { "chipFamily": "ESP32", "parts": [ { "path": "web_factory.bin", "offset": 0 } ] }
  ]
}
JSON
done

cat > "$out/version.json" <<JSON
{ "version": "$version", "commit": "$commit" }
JSON
echo "sito in $out (versione $version, commit $commit)"
