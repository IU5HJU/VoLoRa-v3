# Prove della logica del firmware di misura sul PC (serve solo g++ con C++17).
CXX ?= g++
test: build/test_core
	./build/test_core
build/test_core: tests/test_core.cpp src/misura_core.h
	mkdir -p build
	$(CXX) -std=c++17 -Wall -Wextra -O1 -o $@ tests/test_core.cpp
clean:
	rm -rf build
.PHONY: test clean
