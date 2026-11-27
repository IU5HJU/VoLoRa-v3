// Menu a bordo e gesti dei due tasti: PORTA FEDELE della v2 (third_party/VoLoRa-v2/lib/voicecore/menu.h, menu.cpp, button_gesture.h, ptt_button.h), header-only.
// La logica e' quella della v2, senza aggiunte:
//   volume, pressione lunga (~2 s), a scheda ferma  ->  apre il menu
//   nel menu:  PTT, pressione breve    voce successiva (le voci non disponibili si saltano)
//              volume, pressione breve conferma
//              volume, pressione lunga esce senza cambiare
//              10 s senza toccare niente: esce senza cambiare
//   fuori dal menu:  il PTT trasmette (nel V3 non c'e' ancora); volume, pressione breve, alza il volume (idem)
// Le voci sono QUELLE DELLA v2 (stesse etichette e stessi identificatori). Quali siano disponibili nel V3 lo decide il chiamante (MenuItem::enabled), e quello che e' specifico del V3 si decide con l'autore.
// I test sono quelli della v2 (tests/test_menu.cpp, copia). STUDIO: mai provato su una scheda.
#pragma once
#include <cstddef>
#include <cstdint>

namespace v3 {
namespace menu {

// ---- ptt_button.h ----
class PttButton {
 public:
  enum class Event { None, Pressed, Released };
  explicit PttButton(uint32_t debounceMs = 30) : debounceMs_(debounceMs) {}
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

// ---- button_gesture.h ----
class ButtonGesture {
 public:
  enum class Event { None, Short, Long };
  explicit ButtonGesture(uint32_t debounceMs = 30, uint32_t longMs = 2000) : button_(debounceMs), longMs_(longMs) {}
  Event update(bool rawPressed, uint32_t nowMs) {
    switch (button_.update(rawPressed, nowMs)) {
      case PttButton::Event::Pressed: pressedAtMs_ = nowMs; longFired_ = false; return Event::None;
      case PttButton::Event::Released: return longFired_ ? Event::None : Event::Short;
      case PttButton::Event::None: break;
    }
    if (button_.pressed() && !longFired_ && static_cast<int32_t>(nowMs - pressedAtMs_) >= static_cast<int32_t>(longMs_)) { longFired_ = true; return Event::Long; }
    return Event::None;
  }
  bool down() const { return button_.pressed(); }
 private:
  PttButton button_;
  uint32_t longMs_;
  uint32_t pressedAtMs_ = 0;
  bool longFired_ = false;
};

// ---- menu.h ----
constexpr uint32_t kMenuTimeoutMs = 10000;
constexpr uint8_t kMenuWifiId = 100;         // voce "Wi-Fi"
constexpr uint8_t kMenuTextId = 101;         // voce "Invia testo"
constexpr uint8_t kMenuMeshId = 102;         // voce "MeshCom"
constexpr uint8_t kMenuSysopId = 103;        // voce "Comandi Sysop" (modo Sysop)
constexpr uint8_t kMenuMeshListenId = 104;   // voce "MeshCom ascolto"
// Voci SPECIFICHE DEL V3 (decise con l'autore il 27/11/2026): non esistono nella v2
constexpr uint8_t kMenuPowerId = 110;        // "Potenza": cambia la potenza normale (17, 10, 5, 2... dBm)
constexpr uint8_t kMenuInfoId = 111;         // "Informazioni": versione, nomi di rete, password
constexpr uint8_t kMenuGpsId = 112;          // "GPS": acceso o spento (solo T-Beam)

struct MenuItem {
  const char* label;  // testo sul display
  uint8_t id;         // identificatore del profilo (profile.h della v2: Range 0, Messaggio 1, Standard 2, Diretta 3) o delle altre voci
  bool enabled;       // false: si vede ma non si puo' scegliere
};

// Le voci del menu della v2, nello stesso ordine (senza il modo Sysop)
inline const MenuItem* defaultMenuItems(size_t& count) {
  static const MenuItem kItems[] = {
      {"Modo Standard", 2, true},
      {"Modo Range", 0, true},
      {"Modo Messaggio", 1, true},
      {"Modo Diretta", 3, true},
      {"Invia testo", kMenuTextId, true},
      {"MeshCom", kMenuMeshId, true},
      {"MeshCom ascolto", kMenuMeshListenId, true},
      {"Wi-Fi", kMenuWifiId, true},
  };
  count = sizeof(kItems) / sizeof(kItems[0]);
  return kItems;
}

enum class MenuBeep { None, Open, Next, Confirm, Cancel };

class Menu {
 public:
  struct Outcome {
    enum class Kind { None, Selected, Closed } kind = Kind::None;
    uint8_t id = 0;
  };
  Menu(const MenuItem* items, size_t count) : items_(items), count_(count) {}
  bool isOpen() const { return open_; }
  size_t count() const { return count_; }
  const MenuItem& item(size_t i) const { return items_[i]; }
  size_t selectedIndex() const { return selected_; }

  bool open(uint8_t currentId, uint32_t nowMs) {
    size_t first = count_, cur = count_;
    for (size_t i = 0; i < count_; i++) {
      if (!items_[i].enabled) continue;
      if (first == count_) first = i;
      if (items_[i].id == currentId) cur = i;
    }
    if (first == count_) return false;  // nessuna voce scegliibile
    open_ = true;
    current_ = currentId;
    selected_ = cur != count_ ? cur : first;
    lastActivityMs_ = nowMs;
    return true;
  }
  void next(uint32_t nowMs) {
    if (!open_) return;
    lastActivityMs_ = nowMs;
    for (size_t step = 1; step <= count_; step++) {
      const size_t i = (selected_ + step) % count_;
      if (items_[i].enabled) { selected_ = i; return; }
    }
  }
  Outcome confirm(uint32_t nowMs) {
    Outcome o;
    if (!open_) return o;
    (void)nowMs;
    open_ = false;
    const MenuItem& it = items_[selected_];
    o.kind = it.id != current_ ? Outcome::Kind::Selected : Outcome::Kind::Closed;
    o.id = it.id;
    return o;
  }
  void cancel() { open_ = false; }
  bool tick(uint32_t nowMs) {
    if (open_ && static_cast<int32_t>(nowMs - lastActivityMs_) >= static_cast<int32_t>(kMenuTimeoutMs)) { open_ = false; return true; }
    return false;
  }

 private:
  const MenuItem* items_;
  size_t count_;
  bool open_ = false;
  size_t selected_ = 0;
  uint8_t current_ = 0;
  uint32_t lastActivityMs_ = 0;
};

class MenuFlow {
 public:
  struct Actions {
    bool pttToNode = false;
    bool volumeUp = false;
    bool redraw = false;
    MenuBeep beep = MenuBeep::None;
    Menu::Outcome outcome;
  };
  explicit MenuFlow(Menu& menu) : menu_(menu) {}
  Actions update(PttButton::Event ptt, ButtonGesture::Event vol, bool nodeIdle, uint8_t currentId, uint32_t nowMs) {
    Actions a;
    if (menu_.isOpen()) {
      if (!nodeIdle) {
        menu_.cancel(); a.redraw = true; a.beep = MenuBeep::Cancel;
      } else if (menu_.tick(nowMs)) {
        a.redraw = true; a.beep = MenuBeep::Cancel;
      }
    }
    if (menu_.isOpen()) {
      if (ptt == PttButton::Event::Pressed) {
        menu_.next(nowMs); pttSwallowed_ = true; a.redraw = true; a.beep = MenuBeep::Next;
      } else if (ptt == PttButton::Event::Released && pttSwallowed_) {
        pttSwallowed_ = false;
      }
      if (vol == ButtonGesture::Event::Short) {
        a.outcome = menu_.confirm(nowMs); a.redraw = true; a.beep = MenuBeep::Confirm;
      } else if (vol == ButtonGesture::Event::Long) {
        menu_.cancel(); a.redraw = true; a.beep = MenuBeep::Cancel;
      }
      return a;
    }
    if (ptt == PttButton::Event::Released && pttSwallowed_) {
      pttSwallowed_ = false;
    } else if (ptt != PttButton::Event::None) {
      a.pttToNode = true;
    }
    if (vol == ButtonGesture::Event::Short) {
      a.volumeUp = true;
    } else if (vol == ButtonGesture::Event::Long && nodeIdle && menu_.open(currentId, nowMs)) {
      a.redraw = true; a.beep = MenuBeep::Open;
    }
    return a;
  }
 private:
  Menu& menu_;
  bool pttSwallowed_ = false;
};

}  // namespace menu
}  // namespace v3
