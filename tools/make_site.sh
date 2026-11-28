#!/usr/bin/env bash
# Assembla il sito statico (pagina di installazione del firmware di misura) in una cartella.
#   tools/make_site.sh <cartella-artefatti> <cartella-uscita> <versione> <commit>
# <cartella-artefatti> contiene firmware-t3/, firmware-tbeam1262/ e firmware-tbeam1278/ (come li scarica actions/download-artifact), ognuna con web_factory.bin.
# App Android (facoltativa): <cartella-artefatti>/volora3-apk/VoLoRa-V3.apk -> app/VoLoRa-V3.apk
# Firmware V3: <cartella-artefatti>/firmware-v3-<env>/ con bootloader.bin, partitions.bin, boot_app0.bin, firmware.bin (env: mobile_t3 mobile_tbeam1262 mobile_tbeam1278 mobile_heltec_v3 bench_t3 bench_tbeam1262 bench_tbeam1278 ble_sim_t3 ble_sim_tbeam1262).
# Struttura prodotta: index.html, firmware-v3.html, version.json, firmware/<scheda>/{web_factory.bin,manifest.json}, firmware-v3/<env>/{4 binari,manifest.json}
# Il firmware di misura non salva impostazioni, quindi si scrive l'immagine intera all'indirizzo 0 (un solo pezzo).
set -euo pipefail
in=${1:?cartella degli artefatti}
out=${2:?cartella di uscita}
version=${3:?versione}
commit=${4:?commit}
here=$(cd "$(dirname "$0")/.." && pwd)

rm -rf "$out"
mkdir -p "$out/firmware"
cp "$here/site/index.html" "$here/site/firmware-v3.html" "$here/site/nodo.html" "$here/site/telefono.html" "$here/site/modi.html" "$here/site/jpeg_prog.js" "$out/"
touch "$out/.nojekyll"

for pair in "t3:firmware-t3" "tbeam1262:firmware-tbeam1262" "tbeam1278:firmware-tbeam1278"; do
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

# firmware V3: quattro parti agli indirizzi di sempre (bootloader 0x1000, partizioni 0x8000, boot_app0 0xe000, programma 0x10000), cosi' le impostazioni in NVS (nominativo, accoppiamento) restano
for env in mobile_t3 mobile_tbeam1262 mobile_tbeam1278 mobile_heltec_v3 bench_t3 bench_tbeam1262 bench_tbeam1278 ble_sim_t3 ble_sim_tbeam1262; do
  art="firmware-v3-$env"
  family=ESP32; boot=4096; [ "$env" = mobile_heltec_v3 ] && { family=ESP32-S3; boot=0; }   # l'ESP32-S3 vuole il bootloader a 0x0
  for f in bootloader.bin partitions.bin boot_app0.bin firmware.bin; do
    test -f "$in/$art/$f" || { echo "manca $in/$art/$f" >&2; exit 1; }
  done
  mkdir -p "$out/firmware-v3/$env"
  cp "$in/$art/bootloader.bin" "$in/$art/partitions.bin" "$in/$art/boot_app0.bin" "$in/$art/firmware.bin" "$out/firmware-v3/$env/"
  cat > "$out/firmware-v3/$env/manifest.json" <<JSON
{
  "name": "VoLoRa V3 firmware V3 ($env)",
  "version": "$version",
  "new_install_prompt_erase": false,
  "builds": [
    { "chipFamily": "$family", "parts": [
      { "path": "bootloader.bin", "offset": $boot },
      { "path": "partitions.bin", "offset": 32768 },
      { "path": "boot_app0.bin", "offset": 57344 },
      { "path": "firmware.bin", "offset": 65536 }
    ] }
  ]
}
JSON
done

# App Android (APK debug firmato con la chiave di debug): si installa a mano; poi funziona senza Internet
if [ -f "$in/volora3-apk/VoLoRa-V3.apk" ]; then
  mkdir -p "$out/app"
  cp "$in/volora3-apk/VoLoRa-V3.apk" "$out/app/VoLoRa-V3.apk"
  echo "app Android inclusa: $(wc -c < "$out/app/VoLoRa-V3.apk") byte"
elif [ -n "${REQUIRE_APK:-}" ]; then
  echo "manca $in/volora3-apk/VoLoRa-V3.apk (REQUIRE_APK): il sito non va pubblicato senza l'app" >&2
  exit 1
fi

cat > "$out/version.json" <<JSON
{ "version": "$version", "commit": "$commit" }
JSON
echo "sito in $out (versione $version, commit $commit)"
