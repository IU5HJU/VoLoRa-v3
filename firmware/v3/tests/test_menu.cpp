#include <cstring>

#include "../src/menu.h"
#include "testing.h"

using namespace v3::menu;
using G = Gesture::Event;

static void fill(Menu& m) {
  Item it[4];
  std::strcpy(it[0].label, "Wi-Fi: accendi"); it[0].id = kIdWifi;
  std::strcpy(it[1].label, "Potenza: 17 dBm"); it[1].id = kIdPower;
  std::strcpy(it[2].label, "Info"); it[2].id = kIdInfo;
  std::strcpy(it[3].label, "Esci"); it[3].id = kIdExit;
  m.setItems(it, 4);
}

int main() {
  // antirimbalzo: un rimbalzo breve non e' una pressione
  Debounce d(30);
  CHECK(d.update(true, 0) == Debounce::Event::None);
  CHECK(d.update(false, 10) == Debounce::Event::None);
  CHECK(d.update(true, 20) == Debounce::Event::None);
  CHECK(d.update(true, 49) == Debounce::Event::None);
  CHECK(d.update(true, 60) == Debounce::Event::Pressed && d.pressed());
  CHECK(d.update(false, 100) == Debounce::Event::None && d.update(false, 131) == Debounce::Event::Released && !d.pressed());
  // gesti: breve, lungo (una volta, senza Short dopo)
  Gesture g(30, 2000);
  CHECK(g.update(true, 0) == G::None && g.update(true, 40) == G::None);
  CHECK(g.update(false, 300) == G::None && g.update(false, 340) == G::Short);
  CHECK(g.update(true, 1000) == G::None && g.update(true, 1040) == G::None && g.update(true, 2900) == G::None && g.update(true, 3050) == G::Long);
  CHECK(g.update(true, 3500) == G::None);                                  // una volta sola
  CHECK(g.update(false, 4000) == G::None && g.update(false, 4040) == G::None);   // il rilascio dopo un lungo non da' Short

  Menu m; Flow f(m);
  fill(m);
  // chiuso: i gesti brevi non fanno niente, il lungo chiede l'apertura (da A o da B) solo a scheda ferma
  CHECK(!f.wantsOpen(G::Short, G::None, true) && !f.wantsOpen(G::None, G::Short, true));
  CHECK(f.wantsOpen(G::Long, G::None, true) && f.wantsOpen(G::None, G::Long, true));
  CHECK(!f.wantsOpen(G::Long, G::None, false));
  CHECK(f.update(G::Short, G::None, true, 0).redraw == false);               // chiuso: update non fa niente
  CHECK(m.open(0) && m.isOpen() && m.selectedIndex() == 0);
  // A breve = avanti, con giro
  CHECK(f.update(G::Short, G::None, true, 100).redraw && m.selectedIndex() == 1);
  f.update(G::Short, G::None, true, 200); f.update(G::Short, G::None, true, 300);
  CHECK(m.selectedIndex() == 3);
  f.update(G::Short, G::None, true, 400);
  CHECK(m.selectedIndex() == 0);
  // B breve = conferma la voce
  f.update(G::Short, G::None, true, 500);
  Flow::Actions r = f.update(G::None, G::Short, true, 600);
  CHECK(r.outcome.kind == Menu::Outcome::Kind::Selected && r.outcome.id == kIdPower && !m.isOpen());
  // un solo tasto: A lungo apre, A breve avanti, A lungo conferma
  m.open(1000);
  f.update(G::Short, G::None, true, 1100); f.update(G::Short, G::None, true, 1150);
  r = f.update(G::Long, G::None, true, 1200);
  CHECK(r.outcome.kind == Menu::Outcome::Kind::Selected && r.outcome.id == kIdInfo && !m.isOpen());
  // "Esci" chiude senza voce scelta
  m.open(2000); f.update(G::Short, G::None, true, 2100); f.update(G::Short, G::None, true, 2200); f.update(G::Short, G::None, true, 2300);
  r = f.update(G::None, G::Short, true, 2400);
  CHECK(r.outcome.kind == Menu::Outcome::Kind::Closed && r.outcome.id == kIdExit && !m.isOpen());
  // B lungo esce senza scegliere
  m.open(3000); f.update(G::Short, G::None, true, 3100);
  r = f.update(G::None, G::Long, true, 3200);
  CHECK(r.outcome.kind == Menu::Outcome::Kind::None && !m.isOpen() && r.redraw);
  // 10 s senza tasti: si chiude da solo
  m.open(4000);
  CHECK(!f.update(G::None, G::None, true, 13999).redraw && m.isOpen());
  r = f.update(G::None, G::None, true, 14000);
  CHECK(r.redraw && !m.isOpen());
  // un tasto resetta il tempo
  m.open(20000); f.update(G::Short, G::None, true, 29000);
  CHECK(m.isOpen() && !f.update(G::None, G::None, true, 38999).redraw && m.isOpen());
  // arriva una ricezione (scheda non piu' a riposo): il menu si chiude
  r = f.update(G::None, G::None, false, 39000);
  CHECK(r.redraw && !m.isOpen());
  // voci non disponibili si saltano
  Item it[3];
  std::strcpy(it[0].label, "a"); it[0].id = kIdWifi;
  std::strcpy(it[1].label, "b"); it[1].id = kIdPower; it[1].enabled = false;
  std::strcpy(it[2].label, "c"); it[2].id = kIdInfo;
  m.setItems(it, 3);
  m.open(50000); m.next(50100);
  CHECK(m.selectedIndex() == 2);
  m.next(50200);
  CHECK(m.selectedIndex() == 0);
  // nessuna voce possibile: non si apre
  it[0].enabled = false; it[2].enabled = false; m.setItems(it, 3); m.cancel();
  CHECK(!m.open(60000) && !m.isOpen());
  // giro della potenza
  CHECK(nextPower(17, 2) == 10 && nextPower(10, 2) == 5 && nextPower(5, 2) == 2 && nextPower(2, 2) == 17);        // SX1278: minimo 2
  CHECK(nextPower(2, -9) == -3 && nextPower(-3, -9) == -9 && nextPower(-9, -9) == 17);                           // SX1262: fino a -9
  CHECK(nextPower(8, 2) == 17 || nextPower(8, 2) == 10);                                                            // un valore fuori giro riparte dall'inizio del giro
  TEST_MAIN_END();
}
