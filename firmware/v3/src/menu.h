// Menu a bordo della scheda mobile V3, con i due tasti della v2 (third_party/VoLoRa-v2/lib/voicecore/menu.h, button_gesture.h, ptt_button.h): porta header-only, provata sul PC (tests/test_menu.cpp).
//   tasto A = il "PTT" della v2 (T3: GPIO0 BOOT; T-Beam: GPIO38 e GPIO0)      tasto B = il "volume" della v2 (GPIO15, esterno e facoltativo)
// Come nella v2: B lungo (2 s) a scheda ferma apre il menu; nel menu A breve = voce successiva, B breve = conferma, B lungo = esce, 10 s senza toccare niente = esce.
// In piu' per chi ha UN SOLO tasto (T3 senza il tasto esterno): A lungo apre il menu e, nel menu, A lungo conferma. Nel V3 non c'e' il PTT: fuori dal menu i tasti non fanno altro.
// STUDIO: mai provato su una scheda.
#pragma once
#include <cstddef>
#include <cstdint>
#include <cstring>

namespace v3 {
namespace menu {

constexpr uint32_t kTimeoutMs = 10000;
constexpr size_t kMaxItems = 8;
constexpr size_t kLabelLen = 24;

// ---- antirimbalzo e gesti (v2: PttButton e ButtonGesture) ----
class Debounce {
 public:
  enum class Event { None, Pressed, Released };
  explicit Debounce(uint32_t debounceMs = 30) : debounceMs_(debounceMs) {}
  Event update(bool rawPressed, uint32_t nowMs) {
    if (rawPressed != lastRaw_) { lastRaw_ = rawPressed; changedAt_ = nowMs; }
    if (lastRaw_ != stable_ && nowMs - changedAt_ >= debounceMs_) { stable_ = lastRaw_; return stable_ ? Event::Pressed : Event::Released; }
    return Event::None;
  }
  bool pressed() const { return stable_; }
 private:
  uint32_t debounceMs_;
  bool lastRaw_ = false, stable_ = false;
  uint32_t changedAt_ = 0;
};

// Short: rilasciato prima di longMs. Long: ancora premuto da longMs (una volta sola, mentre e' premuto: il rilascio dopo non da' Short).
class Gesture {
 public:
  enum class Event { None, Short, Long };
  explicit Gesture(uint32_t debounceMs = 30, uint32_t longMs = 2000) : button_(debounceMs), longMs_(longMs) {}
  Event update(bool rawPressed, uint32_t nowMs) {
    switch (button_.update(rawPressed, nowMs)) {
      case Debounce::Event::Pressed: pressedAtMs_ = nowMs; longFired_ = false; return Event::None;
      case Debounce::Event::Released: return longFired_ ? Event::None : Event::Short;
      case Debounce::Event::None: break;
    }
    if (button_.pressed() && !longFired_ && static_cast<int32_t>(nowMs - pressedAtMs_) >= static_cast<int32_t>(longMs_)) { longFired_ = true; return Event::Long; }
    return Event::None;
  }
  bool down() const { return button_.pressed(); }
 private:
  Debounce button_;
  uint32_t longMs_, pressedAtMs_ = 0;
  bool longFired_ = false;
};

// ---- le voci ----
// Identificatori (non sono profili: il V3 non ne ha)
constexpr uint8_t kIdWifi = 1, kIdPower = 2, kIdGps = 3, kIdInfo = 4, kIdExit = 5;

struct Item {
  char label[kLabelLen] = "";     // testo sul display (21 caratteri al massimo a testo piccolo)
  uint8_t id = 0;
  bool enabled = true;
};

enum class Beep { None, Open, Next, Confirm, Cancel };    // suggerimenti per una scheda con cicalino (il V3 mobile non ce l'ha)

class Menu {
 public:
  struct Outcome { enum class Kind { None, Selected, Closed } kind = Kind::None; uint8_t id = 0; };

  bool isOpen() const { return open_; }
  size_t count() const { return count_; }
  const Item& item(size_t i) const { return items_[i]; }
  size_t selectedIndex() const { return selected_; }
  // Imposta le voci (da rifare a ogni apertura: le etichette dicono lo stato, per esempio "Wi-Fi: accendi")
  void setItems(const Item* items, size_t n) { count_ = n > kMaxItems ? kMaxItems : n; for (size_t i = 0; i < count_; i++) items_[i] = items[i]; }
  // Apre con la prima voce scelta possibile. false se non ce ne sono.
  bool open(uint32_t nowMs) {
    size_t first = count_;
    for (size_t i = 0; i < count_; i++) if (items_[i].enabled) { first = i; break; }
    if (first == count_) return false;
    open_ = true; selected_ = first; lastActivityMs_ = nowMs;
    return true;
  }
  void next(uint32_t nowMs) {
    if (!open_) return;
    lastActivityMs_ = nowMs;
    for (size_t step = 1; step <= count_; step++) { const size_t i = (selected_ + step) % count_; if (items_[i].enabled) { selected_ = i; return; } }
  }
  // Conferma: la voce scelta e chiude il menu.
  Outcome confirm() {
    Outcome o;
    if (!open_) return o;
    open_ = false;
    o.kind = items_[selected_].id == kIdExit ? Outcome::Kind::Closed : Outcome::Kind::Selected;
    o.id = items_[selected_].id;
    return o;
  }
  void cancel() { open_ = false; }
  bool tick(uint32_t nowMs) { if (open_ && static_cast<int32_t>(nowMs - lastActivityMs_) >= static_cast<int32_t>(kTimeoutMs)) { open_ = false; return true; } return false; }

 private:
  Item items_[kMaxItems];
  size_t count_ = 0, selected_ = 0;
  bool open_ = false;
  uint32_t lastActivityMs_ = 0;
};

// Instrada i gesti dei due tasti.
class Flow {
 public:
  struct Actions { bool redraw = false; Beep beep = Beep::None; Menu::Outcome outcome; bool opened = false; };
  explicit Flow(Menu& m) : menu_(m) {}
  // a, b: gesti dei tasti; nodeIdle: la scheda e' a riposo (niente invio ne' ricezione in corso). Con il menu chiuso `opened` dice che e' appena stato aperto: il chiamante deve
  // riempire le voci PRIMA (setItems) leggendo lo stato: per questo l'apertura e' chiesta con wantsOpen() e fatta con open().
  bool wantsOpen(Gesture::Event a, Gesture::Event b, bool nodeIdle) const { return !menu_.isOpen() && nodeIdle && (a == Gesture::Event::Long || b == Gesture::Event::Long); }
  Actions update(Gesture::Event a, Gesture::Event b, bool nodeIdle, uint32_t nowMs) {
    Actions r;
    if (!menu_.isOpen()) return r;
    if (!nodeIdle) { menu_.cancel(); r.redraw = true; r.beep = Beep::Cancel; return r; }          // e' arrivata una ricezione o parte un invio: il menu si chiude
    if (menu_.tick(nowMs)) { r.redraw = true; r.beep = Beep::Cancel; return r; }
    if (b == Gesture::Event::Short || a == Gesture::Event::Long) { r.outcome = menu_.confirm(); r.redraw = true; r.beep = Beep::Confirm; }
    else if (b == Gesture::Event::Long) { menu_.cancel(); r.redraw = true; r.beep = Beep::Cancel; }
    else if (a == Gesture::Event::Short) { menu_.next(nowMs); r.redraw = true; r.beep = Beep::Next; }
    return r;
  }
 private:
  Menu& menu_;
};

// Potenza successiva nel giro del menu "Potenza": 17 -> 10 -> 5 -> minimo del chip -> 17
inline int nextPower(int current, int minDbm) {
  static const int steps[] = {17, 10, 5, 2, -3, -9};
  size_t i = 0;
  while (i < sizeof(steps) / sizeof(steps[0]) && steps[i] != current) i++;
  for (size_t j = (i < sizeof(steps) / sizeof(steps[0]) ? i + 1 : 0); j < sizeof(steps) / sizeof(steps[0]); j++) if (steps[j] >= minDbm) return steps[j];
  return 17;
}

}  // namespace menu
}  // namespace v3
