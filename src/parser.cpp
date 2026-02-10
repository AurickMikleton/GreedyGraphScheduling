#include "parser.hpp"

const std::string students_path = "../data/students.ttl";
const std::string classes_path = "../data/classes.ttl";
const std::string rooms_path = "../data/rooms.ttl";

std::unique_ptr<Graph> Graph::parse_file(std::string filepath) {
    std::ifstream file(filepath);
    std::string line;

    if (!file.is_open()) std::cerr << "we cooked" << std::endl;

    while (getline(file, line)) {
        std::cout << line << "\n";
    }
    
    file.close();

    return std::make_unique<Graph>();
}

std::string Graph::read_all(const std::string& filepath) {}
void Graph::remove_comments_inplace(std::string& contents) {}

void Graph::tokenize(const std::string& contents) {}
bool Graph::peek(const std::string& token) const {}
std::string Graph::next() {}
void Graph::expect(const std::string& token) {}
void Graph::parse_prefixed() {}
std::string Graph::expand_term(const std::string& token) {}
std::string Graph::parse_object() {}
std::vector<Triple> Graph::parse_triples() {}

int main() {
    std::unique_ptr<Graph> students_graph = Graph::parse_file(students_path);
}
