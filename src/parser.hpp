#include <memory>
#include <fstream>
#include <iostream>

#include <string>
#include <unordered_map>
#include <vector>

struct Triple {
    std::string subject;
    std::string predicate;
    std::string object;
};

// I do not believe this is an actuall graph datastructure
class Graph {
private:
    std::vector<std::string> m_tokens;
    size_t m_class_index = 0;
private:
    // 32% that these function stubs will be right
    static std::string read_all(const std::string& filepath);
    static void remove_comments_inplace(std::string& contents);

    void tokenize(const std::string& contents);
    bool peek(const std::string& token) const;
    std::string next();
    void expect(const std::string& token);
    void parse_prefixes();
    std::string expand_term(const std::string& token);
    std::string parse_object();
    std::vector<Triple> parse_triples();
public:
    std::vector<Triple> parse_file(const std::string& filepath);
    std::unordered_map<std::string, std::string> m_prefixes;
};
