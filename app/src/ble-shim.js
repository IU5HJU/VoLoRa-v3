// Web Bluetooth per la pagina del telefono dentro l'app Android.
// Il WebView di Android non ha navigator.bluetooth: questo strato offre alla pagina (site/telefono.html, che non cambia) la parte di Web Bluetooth che usa,
// appoggiandosi al plugin @capacitor-community/bluetooth-le (BleClient). Nessuna dipendenza: si prova con un BleClient finto (tests/page/run_app_shim.js).
// STUDIO: mai eseguito su un telefono.
(function (root) {
  'use strict';
  function toView(v) {                                    // la pagina scrive Uint8Array, il plugin vuole DataView
    if (v instanceof DataView) return v;
    const u = v instanceof Uint8Array ? v : new Uint8Array(v.buffer ? v.buffer : v);
    return new DataView(u.buffer, u.byteOffset, u.byteLength);
  }

  function installShim(BleClient, win) {
    win = win || root;
    let initialized = false;
    const init = async () => {
      if (initialized) return;
      await BleClient.initialize({ androidNeverForLocation: true });
      initialized = true;
    };

    function makeChar(deviceId, service, uuid) {
      const ch = { uuid, properties: {}, _l: [], _on: false };
      ch.addEventListener = (type, f) => { if (type === 'characteristicvaluechanged') ch._l.push(f); };
      ch.startNotifications = async () => {
        if (!ch._on) {
          ch._on = true;
          await BleClient.startNotifications(deviceId, service, uuid, value => { for (const f of ch._l) f({ target: { value } }); });
        }
        return ch;
      };
      ch.writeValue = async v => { await BleClient.write(deviceId, service, uuid, toView(v)); };
      ch.writeValueWithoutResponse = async v => { await BleClient.writeWithoutResponse(deviceId, service, uuid, toView(v)); };
      return ch;
    }

    function makeDevice(d) {
      const listeners = [];
      const dev = { id: d.deviceId, name: d.name || 'VoLoRa-V3', gatt: { connected: false } };
      dev.gatt.device = dev;
      dev.addEventListener = (type, f) => { if (type === 'gattserverdisconnected') listeners.push(f); };
      const server = { device: dev, connected: false };
      server.getPrimaryService = async service => ({ getCharacteristic: async uuid => makeChar(d.deviceId, service, uuid) });
      dev.gatt.connect = async () => {
        await BleClient.connect(d.deviceId, () => {       // la scheda e' sparita o ha chiuso
          dev.gatt.connected = false; server.connected = false;
          for (const f of listeners) f({ target: dev });
        });
        // la caratteristica e' cifrata (codice a 6 cifre): si chiede l'accoppiamento subito, cosi' la finestra di Android compare qui e non a meta' di una scrittura
        try { if (BleClient.isBonded && BleClient.createBond && !(await BleClient.isBonded(d.deviceId))) await BleClient.createBond(d.deviceId); } catch (e) { /* si prova lo stesso */ }
        dev.gatt.connected = true; server.connected = true;
        return Object.assign(server, { getPrimaryService: server.getPrimaryService });
      };
      dev.gatt.disconnect = () => { dev.gatt.connected = false; server.connected = false; BleClient.disconnect(d.deviceId).catch(() => {}); };
      return dev;
    }

    const bluetooth = {
      getAvailability: async () => { try { await init(); return true; } catch (e) { return false; } },
      requestDevice: async opts => {
        await init();
        const services = [];
        for (const f of (opts && opts.filters) || []) for (const s of f.services || []) services.push(s);
        const d = await BleClient.requestDevice({ services });          // il selettore di Android: elenca solo le schede VoLoRa-V3
        return makeDevice(d);
      }
    };
    Object.defineProperty(win.navigator, 'bluetooth', { value: bluetooth, configurable: true });
    return bluetooth;
  }

  root.VolShim = { installShim };
})(typeof window !== 'undefined' ? window : globalThis);
