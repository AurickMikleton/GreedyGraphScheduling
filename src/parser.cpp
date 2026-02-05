#include "parser.hpp"

const std::string students_path = "../data/students.ttl";
const std::string classes_path = "../data/classes.ttl";
const std::string rooms_path = "../data/rooms.ttl";

std::unique_ptr<Graph> Graph::parse(std::string filepath) {
    std::ifstream file(filepath);
    std::string line;

    if (!file.is_open()) std::cerr << "we cooked" << std::endl;

    while (getline(file, line)) {
        std::cout << line << "\n";
    }
    
    file.close();

    return std::make_unique<Graph>();
}

int main() {
    std::unique_ptr<Graph> students_graph = Graph::parse(students_path);
}
