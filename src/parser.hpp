#include <memory>
#include <string>
#include <fstream>
#include <iostream>
// I do not believe this is an actuall graph datastructure
class Graph {
private:
public:
    static std::unique_ptr<Graph> parse(std::string filepath);
};
