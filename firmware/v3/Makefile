# Prove del nucleo del firmware V3 sul PC (serve solo g++ con C++17). I vettori vengono dal riferimento Python (tools/gen_vettori_firmware.py).
CXX ?= g++
test: build/test_conformance build/test_frames build/test_limits build/test_protocol build/test_medium
	./build/test_conformance tests/vettori
	./build/test_frames tests/vettori
	./build/test_limits tests/vettori
	python3 ../../tools/gen_tracce_protocollo.py build/tracce > /dev/null
	./build/test_protocol build/tracce
	python3 ../../tools/gen_riferimento_medio.py build/riferimento_medio.txt > /dev/null
	./build/test_medium build/riferimento_medio.txt
build/test_medium: tests/test_medium.cpp src/medium.h src/img_proto.h src/frames.h src/limits.h src/estimate.h
	mkdir -p build
	$(CXX) -std=c++17 -Wall -Wextra -O1 -g -fsanitize=address,undefined -o $@ tests/test_medium.cpp
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
