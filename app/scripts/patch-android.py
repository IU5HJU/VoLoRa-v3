# Ritocca il progetto Android generato da `npx cap add android` (la CI lo rigenera a ogni compilazione):
#  - BLUETOOTH_SCAN con neverForLocation: la pagina inizializza il plugin con androidNeverForLocation=true, cioe' NON chiede il permesso di posizione per cercare le schede.
#    Se il manifest non porta il flag, Android 12+ non restituisce nessun risultato della ricerca senza il permesso di posizione (era il difetto della prima versione: "non rileva niente").
#    La posizione resta dichiarata (senza maxSdk) perche' serve al GPS del telefono della pagina.
#   python3 scripts/patch-android.py android/app/src/main/AndroidManifest.xml
import re
import sys

path = sys.argv[1]
xml = open(path, encoding="utf-8").read()
if "usesPermissionFlags" in xml:
    print("manifest gia' ritoccato")
    sys.exit(0)
if "xmlns:tools" not in xml:
    xml = xml.replace("<manifest xmlns:android=\"http://schemas.android.com/apk/res/android\"", "<manifest xmlns:android=\"http://schemas.android.com/apk/res/android\"\n    xmlns:tools=\"http://schemas.android.com/tools\"", 1)
add = """
    <!-- Bluetooth LE: cercare le schede senza chiedere la posizione (vedi scripts/patch-android.py) -->
    <uses-permission android:name="android.permission.BLUETOOTH_SCAN" android:usesPermissionFlags="neverForLocation" tools:targetApi="s" tools:node="replace" />
    <uses-permission android:name="android.permission.BLUETOOTH_CONNECT" tools:targetApi="s" />
    <!-- posizione per il GPS del telefono (pulsante nella pagina) -->
    <uses-permission android:name="android.permission.ACCESS_FINE_LOCATION" />
    <uses-permission android:name="android.permission.ACCESS_COARSE_LOCATION" />
"""
xml, n = re.subn(r"(</manifest>)", add + r"\1", xml, count=1)
assert n == 1, "manifest senza </manifest>"
open(path, "w", encoding="utf-8").write(xml)
print("manifest ritoccato: BLUETOOTH_SCAN neverForLocation")
