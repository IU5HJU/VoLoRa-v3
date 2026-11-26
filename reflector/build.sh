#!/usr/bin/env bash
# Costruisce il reflector V3 (e prova le sue regole) applicando reflector/v3.patch ai file della v2 del submodule, in una cartella di compilazione: il submodule non si tocca.
#   reflector/build.sh <cartella-di-compilazione> [cartella-della-v2]
# Produce <cartella>/build/vlreflector (il reflector V3, stesse opzioni del v2) e <cartella>/build/test_reflector_v3 (prove in C++, con ASan e UBSan).
# Se la v2 cambia i file toccati dalla patch, `patch` fallisce: e' voluto (la CI lo segnala).
set -euo pipefail
here=$(cd "$(dirname "$0")" && pwd)
out=${1:?cartella di compilazione}
v2=${2:-$here/../third_party/VoLoRa-v2}
test -f "$v2/lib/voicecore/node_link.cpp" || { echo "manca il submodule della v2 in $v2" >&2; exit 1; }
rm -rf "$out"
mkdir -p "$out/lib" "$out/tools" "$out/tests" "$out/build"
cp -r "$v2/lib/voicecore" "$out/lib/"
cp "$v2"/tools/vlreflector.cpp "$v2"/tools/vlreflector_page.h "$v2"/tools/vlreflector_public.h "$out/tools/"
cp "$v2"/tests/testing.h "$v2"/tests/test_reflector_core.cpp "$v2"/tests/test_node_link.cpp "$out/tests/"
patch -p1 -d "$out" < "$here/v3.patch" > /dev/null
cd "$out"
# soli 8 file della v2 (provato: nessuna dipendenza dalla parte audio e radio)
L=lib/voicecore
SRC="$L/admin_auth.cpp $L/http_mini.cpp $L/packet.cpp $L/position.cpp $L/reflector_config.cpp $L/reflector_core.cpp $L/node_link.cpp $L/sha256.cpp"
g++ -std=c++17 -Wall -Wextra -O1 -I"$L" -o build/vlreflector tools/vlreflector.cpp $SRC
g++ -std=c++17 -Wall -Wextra -O1 -g -fsanitize=address,undefined -I"$L" -Itests -o build/test_reflector_v3 "$here/tests/test_reflector_v3.cpp" $SRC
# le prove della v2 sui moduli con la patch: il comportamento v2 non deve cambiare
for t in test_reflector_core test_node_link; do
  g++ -std=c++17 -Wall -Wextra -O1 -g -fsanitize=address,undefined -I"$L" -Itests -o build/$t tests/$t.cpp $SRC
done
echo "costruito: $out/build/vlreflector e $out/build/test_reflector_v3"
