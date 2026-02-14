#include "parser.hpp"

const std::string students_path = "../data/students.ttl";
const std::string classes_path = "../data/classes.ttl";
const std::string rooms_path = "../data/rooms.ttl";

std::string Graph::read_all(const std::string& filepath) {
    std::ifstream in(filepath, std::ios::binary);
    if (!in) throw std::runtime_error("Failed to open: " + filepath);
    std::string s((std::istreambuf_iterator<char>(in)), std::istreambuf_iterator<char>());
    return s;
}


void Graph::remove_comments_inplace(std::string& contents) {
    std::string out;
    out.reserve(contents.size());

    bool in_string = false;
    bool in_iri = false;

    for (size_t index = 0; index < contents.size(); ++index) {
        char c = contents[index];

        // Track entering/leaving IRI blocks
        if (!in_string) {
            if (c == '<') in_iri = true;
            else if (c == '>') in_iri = false;
        }

        // Track entering/leaving string literals
        if (!in_iri && c == '"' && (index == 0 || contents[index - 1] != '\\')) {
            in_string = !in_string;
            out.push_back(c);
            continue;
        }

        // Only treat # as comment when not inside string or iri
        if (!in_string && !in_iri && c == '#') {
            while (index < contents.size() && contents[index] != '\n') index++;
            if (index < contents.size()) out.push_back('\n');
            continue;
        }

        out.push_back(c);
    }

    contents.swap(out);
}


void Graph::tokenize(const std::string& contents) {
    m_tokens.clear();
    m_class_index = 0;

    size_t i = 0;
    auto skip_white_space = [&]() {
        while (i < contents.size() && std::isspace((unsigned char) contents[i])) i++;
    };

    while (true) {
        skip_white_space();
        if (i >= contents.size()) break;

        char c = contents[i];

        // punctuation
        if (c == '.' || c == ';' || c == ',' ) {
            m_tokens.emplace_back(1, c);
            i++;
            continue;
        }

        // IRI <...>
        if (c == '<') {
            size_t start = i++;
            while (i < contents.size() && contents[i] != '>') i++;
            if (i >= contents.size()) throw std::runtime_error("Unterminated <...> IRI");
            i++;
            m_tokens.push_back(contents.substr(start, i - start)); // includes angle brackets
            continue;
        }

        // string literal "..."
        if (c == '"') {
            size_t start = i++;
            while (i < contents.size()) {
                if (contents[i] == '"' && contents[i - 1] != '\\') { i++; break; }
                i++;
            }
            if (i > contents.size()) throw std::runtime_error("Unterminated string literal");
            m_tokens.push_back(contents.substr(start, i - start)); // includes quotes
            continue;
        }

        // typed literal marker ^^
        if (c == '^' && i + 1 < contents.size() && contents[i + 1] == '^') {
            m_tokens.push_back("^^");
            i += 2;
            continue;
        }

        // normal token: read until whitespace or punctuation
        size_t start = i;
        while (i < contents.size() && !std::isspace((unsigned char)contents[i])) {
            char d = contents[i];
            if (d == '.' || d == ';' || d == ',' || d == '<' || d == '"' ) break;
            if (d == '^' && i + 1 < contents.size() && contents[i + 1] == '^') break;
            i++;
        }
        m_tokens.push_back(contents.substr(start, i - start));
    }
}

bool Graph::peek(const std::string& token) const {
    return m_class_index < m_tokens.size() && m_tokens[m_class_index] == token;
}

std::string Graph::next() {
    if (m_class_index >= m_tokens.size()) throw std::runtime_error("Unexpected EOF");
    return m_tokens[m_class_index++];
}

void Graph::expect(const std::string& token) {
    std::string got = next();
    if (got != token) throw std::runtime_error("Expected '" + token + "', got '" + got + "'");
}

void Graph::parse_prefixes() {
    while (m_class_index < m_tokens.size() && m_tokens[m_class_index] == "@prefix") {
        next(); // @prefix
        std::string prefix = next(); // ex:
        std::string iri = next(); // <http://example.org/>
        expect(".");

        if (prefix.size() < 2 || prefix.back() != ':')
            throw std::runtime_error("Bad prefix token: " + prefix);
        if (iri.size() < 2 || iri.front() != '<' || iri.back() != '>')
            throw std::runtime_error("Bad prefix IRI: " + iri);

        prefix.pop_back(); // remove ':'
        m_prefixes[prefix] = iri.substr(1, iri.size() - 2); // strip angle brackets
    }
}

std::string Graph::expand_term(const std::string& token) {
    // a -> rdf:type
    if (token == "a") return "http://www.w3.org/1999/02/22-rdf-syntax-ns#type";
    // <http://...>
    if (token.size() >= 2 && token.front() == '<' && token.back() == '>')
        return token.substr(1, token.size() - 2);
    // "literal"
    if (token.size() >= 2 && token.front() == '"' && token.back() == '"')
        return token;

    // prefixed name ex:Thing
    auto colon = token.find(':');
    if (colon != std::string::npos && colon > 0) {
        std::string prefix = token.substr(0, colon);
        std::string local = token.substr(colon + 1);
        auto it = m_prefixes.find(prefix);
        if (it != m_prefixes.end()) {
            return it->second + local;
        }
    }

    return token;
}

std::string Graph::parse_object() {
    std::string obj = next();

    // Handle typed literal i.e. datetime
    if (peek("^^")) {
        next();
        std::string dtype = next();
        std::string dtype_expanded = expand_term(dtype);
        return expand_term(obj) + "^^" + dtype_expanded;
    }

    return expand_term(obj);
}

std::vector<Triple> Graph::parse_triples() {
    std::vector<Triple> out;

    while (m_class_index < m_tokens.size()) {
        std::string subject = expand_term(next());

        bool done_subject = false;
        while (!done_subject) {
            std::string predicate = expand_term(next());

            bool done_predicate = false;
            while (!done_predicate) {
                std::string object = parse_object();
                out.push_back({subject, predicate, object});

                // After an object expect ',', ';', or '.'
                std::string sep = next();

                if (sep == ",") {
                    // same subject, same predicate, another object
                    continue;
                }

                if (sep == ";") {
                    // same subject, new predicate
                    done_predicate = true;
                    if (peek(".")) {
                        next(); // consume '.'
                        done_subject = true;
                    }
                    break;
                }

                if (sep == ".") {
                    // end of subject
                    done_predicate = true;
                    done_subject = true;
                    break;
                }

                throw std::runtime_error("Expected one of ',', ';', '.' after object, got '" + sep + "'");
            }
        }
    }

    return out;
}

std::vector<Triple> Graph::parse_file(const std::string& filepath) {
    std::string text = Graph::read_all(filepath);
    Graph::remove_comments_inplace(text);

    this->Graph::tokenize(text);
    this->Graph::parse_prefixes();
    return this->Graph::parse_triples();
}

//int main() {
//    Graph students_graph;
//    std::vector<Triple> triples = students_graph.parse_file(students_path);
//
//    int enrolled = 0;
//    for (auto& t : triples) {
//        if (t.predicate.find("enrolledIn") != std::string::npos) enrolled++;
//    }
//    std::cout << "enrolledIn triples: " << enrolled << "\n";
//
//    std::cout << "Triples: " << triples.size() << "\n";
//    for (size_t i = 0; i < std::min<size_t>(triples.size(), 10); ++i) {
//        std::cout << triples[i].subject << "\n  "
//            << triples[i].predicate << "\n  "
//            << triples[i].object << "\n\n";
//    }
//}
//
//
