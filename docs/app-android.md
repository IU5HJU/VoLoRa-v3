# App Android di VoLoRa V3 (Bluetooth LE)

**Stato (27/11/2026): scritta e compilata dalla CI; mai installata né provata su un telefono.** È uno studio.

## Perché
Chrome permette il Web Bluetooth solo da pagine https, e per le prove la pagina deve stare **dentro la scheda** ("Internet non è affidabile"). Il Wi-Fi della scheda risolve le prove di laboratorio (vedi [firmware-v3.md](firmware-v3.md)); per l'uso vero l'autore preferisce il **Bluetooth** (il telefono resta sulla rete mobile, consuma meno, accoppiamento con codice a 6 cifre). Quindi un'**app** che racchiude la stessa pagina.

## Com'è fatta
- **Guscio che racchiude la pagina** (decisione del 27/11/2026): un'app [Capacitor](https://capacitorjs.com) (WebView di Android) che carica `site/telefono.html` così com'è. La cartella è `app/`.
- Il WebView di Android **non ha** `navigator.bluetooth`: `app/src/ble-shim.js` lo fornisce alla pagina (solo la parte che la pagina usa: `requestDevice` con il filtro sul servizio, `gatt.connect`, caratteristiche, notifiche, scritture con e senza risposta, `gattserverdisconnected`) appoggiandosi al plugin `@capacitor-community/bluetooth-le`. La pagina non sa di essere in un'app. Alla connessione chiede subito l'accoppiamento (la caratteristica è cifrata), così la finestra del codice compare lì e non a metà di una scrittura.
- Lo schermo resta acceso durante un invio (plugin `keep-awake`): un collegamento che cade per 60 s fa fallire l'invio.
- Funziona con il firmware **`mobile_t3`** / **`mobile_tbeam1262`**: il Bluetooth è sempre acceso. **Chi ha l'iPhone non usa l'app**: accende il Wi-Fi della scheda (tasto BOOT 2 s) e usa la pagina dentro la scheda ([firmware-v3.md](firmware-v3.md)). Con il Wi-Fi acceso il Bluetooth è spento: per tornare all'app, di nuovo BOOT 2 s.
- La pagina nell'app non ha Internet da usare: la compressione dell'immagine, la posizione (GPS del telefono o locatore) e tutto il resto sono nella pagina e nel telefono.

## Compilazione
`app/` ha `package.json` (dipendenze fissate), `scripts/build-www.js` (prepara `www/` dalla pagina del sito e dallo strato, con esbuild) e `capacitor.config.json`. Il progetto Android **non è nel repository**: lo genera la CI a ogni compilazione (`npx cap add android`, versione dal `git describe`), poi `./gradlew assembleDebug`. Servono Node 22, Java 21 e l'SDK Android (sul runner c'è già).
L'APK esce come artefatto `volora3-apk` e, su `main`, viene pubblicato sul sito: `https://iu5hju.github.io/VoLoRa-v3/app/VoLoRa-V3.apk` (link nella pagina `firmware-v3.html`).

## Installazione sul telefono
L'APK è **di debug**, firmato con la chiave di prova di Android: non è sul Play Store e **Play Protect può avvisare**. Si scarica, si apre il file e si consente l'installazione da quella fonte. Al primo avvio: consentire Bluetooth e posizione. Una volta installata funziona senza Internet. Un APK firmato con una chiave propria (stabile fra le versioni, così gli aggiornamenti non chiedono di disinstallare) è da fare.

## Provato
- Sul PC (`tests/page/run_app_shim.js`, 13 controlli): la **pagina vera** con lo strato e un BleClient finto sopra la scheda finta: collegamento, accoppiamento, INFO, testo e file di 4 blocchi identici con CRC, schermo acceso durante l'invio, oggetto ricevuto dalla radio, ricollegamento dopo una caduta.
- **Non provato:** il plugin Bluetooth su un telefono vero, il selettore di Android, la finestra del codice, la dimensione dei pacchetti (MTU), i permessi, la durata del collegamento a schermo spento, l'installazione dell'APK.

## Difetto corretto (27/11/2026): la ricerca non trovava le schede
Prima prova sul telefono: l'app si installava ma la ricerca Bluetooth **non vedeva nessuna scheda**, mentre l'app Bluetooth del telefono le vedeva. Causa: la pagina inizializzava il plugin con `androidNeverForLocation: true` (non chiedere la posizione) ma il manifest non portava `neverForLocation` su `BLUETOOTH_SCAN`; su Android 12+ senza quel flag la ricerca non dà risultati se manca il permesso di posizione, che l'app non chiedeva. Ora `app/scripts/patch-android.py` mette il flag nel manifest e la CI controlla i permessi dell'APK (`aapt2 dump permissions`). La posizione resta dichiarata per il GPS del telefono. Il selettore ha testi in italiano. **Da riprovare sul telefono.**

## Esito delle prove sul telefono (27/11/2026)
Secondo l'autore, con la posizione attivata la ricerca trovava le schede; dopo la correzione dell'MTU (pacchetti secondo l'MTU negoziato, priorità alta) **"adesso funziona"** anche l'invio dell'immagine. Il dettaglio (Android, modello, immagine, tempi) non è registrato; la ricerca **senza** posizione attiva non è stata verificata.

## Limiti noti
- **Solo Android.** Su iPhone servirebbe l'ambiente Apple (account, Mac): per ora non c'è.
- Con lo schermo spento o l'app in secondo piano Android può sospendere il WebView e far cadere il collegamento: serve un servizio in primo piano (da fare).
- L'icona è quella predefinita di Capacitor.
