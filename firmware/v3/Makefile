# Prove del nucleo del firmware V3 sul PC (serve solo g++ con C++17). I vettori vengono dal riferimento Python (tools/gen_vettori_firmware.py).
CXX ?= g++
test: build/test_conformance
	./build/test_conformance tests/vettori
build/test_conformance: tests/test_conformance.cpp src/ble_bridge.h src/estimate.h
	mkdir -p build
	$(CXX) -std=c++17 -Wall -Wextra -O1 -g -fsanitize=address,undefined -o $@ tests/test_conformance.cpp
clean:
	rm -rf build
.PHONY: test clean
