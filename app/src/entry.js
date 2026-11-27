// Punto d'ingresso dell'app: collega il plugin Bluetooth LE alla pagina (ble-shim.js) e il plugin dello schermo acceso.
import { BleClient } from '@capacitor-community/bluetooth-le';
import { KeepAwake } from '@capacitor-community/keep-awake';
import './ble-shim.js';

window.VolShim.installShim(BleClient, window);
// durante un invio lungo lo schermo non si spegne (un collegamento che cade per 60 s fa fallire l'invio)
window.__keepAwake = async on => { try { if (on) await KeepAwake.keepAwake(); else await KeepAwake.allowSleep(); } catch (e) { /* il plugin puo' rifiutare */ } };
