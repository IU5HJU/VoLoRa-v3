// Prova del BOOST del firmware V3 sul PC: comando, potenza, ciclo di lavoro, avvisi (src/boost.h).
#include <cstdio>

#include "../src/boost.h"

using namespace v3::boost;
static int g_fails = 0, g_checks = 0;
#define CHECK(c, ...) do { g_checks++; if (!(c)) { g_fails++; std::printf("FALLITO: "); std::printf(__VA_ARGS__); std::printf("\n"); } } while (0)

int main() {
  // comando
  CHECK(parse("BOOST ON RISCHIO") == Cmd::On, "ON RISCHIO");
  CHECK(parse("  boost   on   rischio  ") == Cmd::On, "minuscole e spazi");
  CHECK(parse("BOOST ON") == Cmd::NeedsAck, "ON da solo non attiva");
  CHECK(parse("BOOST ON SI") == Cmd::NeedsAck, "ON con altra parola non attiva");
  CHECK(parse("BOOST ON RISCHIO ancora") == Cmd::NeedsAck && parse("BOOST ON RISCHIO a b c d") == Cmd::Invalid, "parole in piu': non attiva");
  CHECK(parse("BOOST OFF") == Cmd::Off && parse("boost off") == Cmd::Off, "OFF");
  CHECK(parse("BOOST STATUS") == Cmd::Status, "STATUS");
  CHECK(parse("BOOST OFF 1") == Cmd::Invalid && parse("BOOST") == Cmd::Invalid && parse("") == Cmd::Invalid && parse("POWER 20") == Cmd::Invalid, "comandi sbagliati");
  CHECK(parse("BOOSTER ON RISCHIO") == Cmd::Invalid, "un'altra parola");
  // spento all'avvio, potenza
  State a(false);
  CHECK(!a.on() && a.power() == 17, "spento all'avvio: +17 dBm");
  a.enable();
  CHECK(a.on() && a.power() == 20, "acceso: +20 dBm");
  a.disable();
  CHECK(!a.on() && a.power() == 17, "spento: di nuovo +17 dBm");
  CHECK(!a.txStarted(1000, 500000), "spento: nessun conteggio ne' avviso");
  CHECK(a.duty(1000) == 0.0f, "spento: ciclo zero");
  // SX1278: sopra l'1% su 100 s (1 s di trasmissione) si avvisa, al massimo ogni 5 s, e non si spegne
  State b(false);
  b.enable();
  uint32_t t = 10000;
  CHECK(!b.txStarted(t, 900000), "0,9%% non avvisa");
  t += 1000;
  CHECK(b.txStarted(t, 300000), "1,2%% avvisa (%.2f)", b.duty(t));
  t += 1000;
  CHECK(!b.txStarted(t, 300000), "entro 5 s non ripete");
  t += 5000;
  CHECK(b.txStarted(t, 300000), "dopo 5 s ripete");
  CHECK(b.on() && b.power() == 20, "il BOOST non si spegne da solo");
  // la finestra scorre: dopo 100 s senza trasmettere il ciclo torna a zero
  CHECK(b.duty(t + 101000) < 0.001f, "dopo 100 s il ciclo e' zero (%.3f)", b.duty(t + 101000));
  // ciclo con tempi lontani nel tempo: nessun conteggio doppio
  State c(false);
  c.enable();
  for (int i = 0; i < 100; i++) c.txStarted(1000u * i, 5000);        // 5 ms al secondo = 0,5%
  CHECK(c.duty(99000) > 0.45f && c.duty(99000) < 0.55f, "0,5%% su 100 s (%.3f)", c.duty(99000));
  CHECK(!c.txStarted(100000, 5000), "0,5%% non avvisa");
  // SX1262: +20 dBm e' sotto il suo massimo, nessun controllo del ciclo ma il ciclo si misura lo stesso
  State d(true);
  d.enable();
  CHECK(!d.txStarted(1000, 900000) && !d.txStarted(2000, 900000) && !d.txStarted(3000, 900000), "SX1262 non avvisa per il ciclo");
  CHECK(d.duty(3000) > 2.0f, "SX1262: il ciclo si misura (%.2f)", d.duty(3000));
  // riaccendere azzera il conteggio
  b.disable(); b.enable();
  CHECK(b.duty(t) == 0.0f, "enable azzera il ciclo");
  CHECK(std::strstr(kWarning, "RISCHIO") && std::strstr(kWarning, "1%") && std::strstr(kWarning, "VSWR"), "il testo dell'avviso dice rischio, 1%% e antenna");
  // IOF MODE: +22 dBm, solo SX1262, uno solo livello alla volta
  CHECK(parseIof("IOF ON RISCHIO") == Cmd::On && parseIof("iof on rischio") == Cmd::On && parseIof("IOF ON") == Cmd::NeedsAck, "IOF ON RISCHIO");
  CHECK(parseIof("IOF OFF") == Cmd::Off && parseIof("IOF STATUS") == Cmd::Status && parseIof("BOOST ON RISCHIO") == Cmd::Invalid && parse("IOF ON RISCHIO") == Cmd::Invalid, "IOF OFF/STATUS, parole non scambiate");
  State i78(false);
  CHECK(!i78.enableIof() && !i78.on() && i78.power() == 17, "SX1278: IOF MODE rifiutato, resta +17 dBm");
  State i62(true);
  CHECK(i62.level() == Level::Normal && i62.power() == 17, "SX1262 spento all'avvio");
  CHECK(i62.enableIof() && i62.iofOn() && i62.on() && !i62.boostOn() && i62.power() == 22, "SX1262: IOF MODE +22 dBm");
  i62.enable();
  CHECK(i62.boostOn() && !i62.iofOn() && i62.power() == 20, "BOOST dopo IOF: uno solo, +20 dBm");
  i62.enableIof(); i62.txStarted(1000, 500000);
  CHECK(i62.duty(1000) > 0.4f, "IOF MODE: il ciclo si misura");
  CHECK(!i62.txStarted(2000, 900000) && !i62.txStarted(3000, 900000), "IOF MODE: nessun avviso di ciclo (non e' il limite dell'SX1262)");
  i62.disable();
  CHECK(!i62.on() && i62.power() == 17, "disable torna a +17 dBm");
  CHECK(std::strstr(kIofWarning, "RISCHIO") && std::strstr(kIofWarning, "antenna") && std::strstr(kIofWarning, "22") && std::strstr(kIofWarning, "IZ5IOF Andrea"), "il testo dell'avviso IOF dice rischio, antenna, +22 e la dedica");
  // POWER: potenza normale ridotta (prove con attenuatori)
  int dbmv = 99;
  CHECK(parsePower("POWER", &dbmv) == PowerCmd::Show && parsePower("  power  ", &dbmv) == PowerCmd::Show, "POWER da solo mostra");
  CHECK(parsePower("POWER 5", &dbmv) == PowerCmd::Set && dbmv == 5, "POWER 5");
  CHECK(parsePower("power -3", &dbmv) == PowerCmd::Set && dbmv == -3, "POWER -3");
  CHECK(parsePower("POWER +10", &dbmv) == PowerCmd::Set && dbmv == 10, "POWER +10");
  CHECK(parsePower("POWER abc", &dbmv) == PowerCmd::Invalid && parsePower("POWER 5 dBm", &dbmv) == PowerCmd::Invalid && parsePower("POWER -", &dbmv) == PowerCmd::Invalid && parsePower("POWER 99999", &dbmv) == PowerCmd::Invalid, "numeri sbagliati");
  CHECK(parsePower("POWERS 5", &dbmv) == PowerCmd::NotPower && parsePower("CALL X", &dbmv) == PowerCmd::NotPower && parsePower("", &dbmv) == PowerCmd::NotPower, "altre righe");
  State pw78(false), pw62(true);
  CHECK(pw78.base() == 17 && pw78.power() == 17 && pw78.minDbm() == 2 && pw62.minDbm() == -9, "di partenza +17; minimi dei chip");
  CHECK(pw78.setBase(2) && pw78.power() == 2 && pw78.base() == 2, "SX1278: +2 dBm");
  CHECK(!pw78.setBase(1) && pw78.base() == 2, "SX1278: sotto +2 dBm rifiutato, niente cambia");
  CHECK(!pw78.setBase(18) && !pw78.setBase(20) && pw78.base() == 2, "oltre +17 dBm non si va con POWER (serve BOOST)");
  CHECK(pw62.setBase(-9) && pw62.power() == -9 && !pw62.setBase(-10), "SX1262: da -9 dBm");
  pw78.enable();
  CHECK(pw78.power() == 20 && pw78.base() == 2, "BOOST sopra la potenza ridotta: +20, la base resta");
  pw78.disable();
  CHECK(pw78.power() == 2, "spento il BOOST si torna alla potenza ridotta");
  pw62.enableIof();
  CHECK(pw62.power() == 22 && pw62.base() == -9, "IOF MODE: +22, la base resta");
  // giro della potenza del menu
  CHECK(nextBasePower(17, 2) == 10 && nextBasePower(10, 2) == 5 && nextBasePower(5, 2) == 2 && nextBasePower(2, 2) == 17, "giro SX1278: 17, 10, 5, 2, 17");
  CHECK(nextBasePower(2, -9) == -3 && nextBasePower(-3, -9) == -9 && nextBasePower(-9, -9) == 17, "giro SX1262: fino a -9");
  CHECK(nextBasePower(7, 2) == 10 || nextBasePower(7, 2) == 5, "un valore fuori giro rientra nel giro");
  std::printf("firmware/v3 BOOST: %d controlli, %d falliti\n", g_checks, g_fails);
  return g_fails ? 1 : 0;
}
