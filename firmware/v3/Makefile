# Prove del nucleo del firmware V3 sul PC (serve solo g++ con C++17). I vettori vengono dal riferimento Python (tools/gen_vettori_firmware.py).
CXX ?= g++
test: build/test_conformance build/test_frames build/test_limits build/test_protocol build/test_medium build/test_live build/test_boost build/test_freq build/test_display build/test_position build/test_nmea build/test_geo build/test_testlog build/test_menu
	./build/test_conformance tests/vettori
	./build/test_frames tests/vettori
	./build/test_limits tests/vettori
	python3 ../../tools/gen_tracce_protocollo.py build/tracce > /dev/null
	./build/test_protocol build/tracce
	python3 ../../tools/gen_riferimento_medio.py build/riferimento_medio.txt > /dev/null
	./build/test_medium build/riferimento_medio.txt
	./build/test_live
	./build/test_boost
	./build/test_freq
	./build/test_display
	./build/test_position
	./build/test_nmea
	./build/test_geo
	./build/test_testlog
	./build/test_menu
	$(MAKE) -s oled-real
	python3 tools/embed_site.py --check ../../site build/web_assets.h
build/test_medium: tests/test_medium.cpp tests/sim_world.h src/medium.h src/img_proto.h src/frames.h src/limits.h src/estimate.h
	mkdir -p build
	$(CXX) -std=c++17 -Wall -Wextra -O1 -g -fsanitize=address,undefined -o $@ tests/test_medium.cpp
build/test_live: tests/test_live.cpp tests/sim_world.h src/live_bridge.h src/ble_bridge.h src/medium.h src/img_proto.h src/frames.h src/limits.h src/estimate.h
	mkdir -p build
	$(CXX) -std=c++17 -Wall -Wextra -O1 -g -fsanitize=address,undefined -o $@ tests/test_live.cpp
build/test_boost: tests/test_boost.cpp src/boost.h
	mkdir -p build
	$(CXX) -std=c++17 -Wall -Wextra -O1 -g -fsanitize=address,undefined -o $@ tests/test_boost.cpp
build/test_freq: tests/test_freq.cpp tests/sim_world.h src/freq.h src/limits.h src/medium.h src/img_proto.h src/frames.h src/estimate.h
	mkdir -p build
	$(CXX) -std=c++17 -Wall -Wextra -O1 -g -fsanitize=address,undefined -o $@ tests/test_freq.cpp
build/test_display: tests/test_display.cpp src/display_model.h src/battery_info.h
	mkdir -p build
	$(CXX) -std=c++17 -Wall -Wextra -O1 -g -fsanitize=address,undefined -o $@ tests/test_display.cpp
build/test_position: tests/test_position.cpp src/position.h tests/testing.h
	mkdir -p build
	$(CXX) -std=c++17 -Wall -Wextra -O1 -g -fsanitize=address,undefined -I tests -o $@ tests/test_position.cpp
build/test_nmea: tests/test_nmea.cpp src/nmea.h src/position.h tests/testing.h
	mkdir -p build
	$(CXX) -std=c++17 -Wall -Wextra -O1 -g -fsanitize=address,undefined -I tests -o $@ tests/test_nmea.cpp
build/test_geo: tests/test_geo.cpp src/position.h tests/testing.h
	mkdir -p build
	$(CXX) -std=c++17 -Wall -Wextra -O1 -g -fsanitize=address,undefined -I tests -o $@ tests/test_geo.cpp
build/test_testlog: tests/test_testlog.cpp src/testlog.h tests/testing.h
	mkdir -p build
	$(CXX) -std=c++17 -Wall -Wextra -O1 -g -fsanitize=address,undefined -I tests -o $@ tests/test_testlog.cpp
build/test_menu: tests/test_menu.cpp src/menu.h tests/testing.h
	mkdir -p build
	$(CXX) -std=c++17 -Wall -Wextra -O1 -g -fsanitize=address,undefined -I tests -o $@ tests/test_menu.cpp
build/test_protocol: tests/test_protocol.cpp src/img_proto.h src/frames.h src/limits.h src/estimate.h
	mkdir -p build
	$(CXX) -std=c++17 -Wall -Wextra -O1 -g -fsanitize=address,undefined -o $@ tests/test_protocol.cpp
build/test_limits: tests/test_limits.cpp src/limits.h src/estimate.h
	mkdir -p build
	$(CXX) -std=c++17 -Wall -Wextra -O1 -g -fsanitize=address,undefined -o $@ tests/test_limits.cpp
build/test_frames: tests/test_frames.cpp src/frames.h
	mkdir -p build
	$(CXX) -std=c++17 -Wall -Wextra -O1 -g -fsanitize=address,undefined -o $@ tests/test_frames.cpp
build/test_conformance: tests/test_conformance.cpp src/ble_bridge.h src/estimate.h
	mkdir -p build
	$(CXX) -std=c++17 -Wall -Wextra -O1 -g -fsanitize=address,undefined -o $@ tests/test_conformance.cpp
clean:
	rm -rf build
.PHONY: test clean

# Il disegno dell'OLED contro la libreria VERA Adafruit_GFX 2.0.0 (la stessa di platformio.ini), scaricata da GitHub (serve la rete). Senza rete la prova si salta e lo dice.
GFX_VERSION = 2.0.0
build/gfx/src/Adafruit_GFX.cpp:
	mkdir -p build
	-git clone -q --depth 1 --branch $(GFX_VERSION) https://github.com/adafruit/Adafruit-GFX-Library build/gfx
build/gfx.o: build/gfx/src/Adafruit_GFX.cpp
	$(CXX) -std=c++17 -w -O1 -DARDUINO=100 -Itests/arduino_stub -Ibuild/gfx/src -c -o $@ build/gfx/src/Adafruit_GFX.cpp
build/test_oled_real: tests/test_oled_real.cpp src/display_draw.h src/display_model.h build/gfx.o tests/testing.h
	$(CXX) -std=c++17 -Wall -Wextra -O1 -g -fsanitize=address,undefined -DARDUINO=100 -Itests/arduino_stub -Ibuild/gfx/src -I tests -o $@ tests/test_oled_real.cpp build/gfx.o
oled-real:
	-$(MAKE) -s build/gfx/src/Adafruit_GFX.cpp
	@if [ -f build/gfx/src/Adafruit_GFX.cpp ]; then $(MAKE) -s build/test_oled_real && ./build/test_oled_real; else echo "test_oled_real SALTATA: libreria Adafruit_GFX $(GFX_VERSION) non scaricabile (serve la rete)"; fi
.PHONY: oled-real
