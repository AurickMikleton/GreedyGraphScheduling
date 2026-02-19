CLANG = clang

CFLAGS = -g -Wall -Iinclude -std=c++17 -O3

TARGET = main.exe
SOURCE = *.cpp

all:
	$(CLANG) $(CFLAGS) $(SOURCE) -o $(TARGET)

clean:
	del *.o *.exe *.ilk *.pdb
