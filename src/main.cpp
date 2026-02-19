#include <algorithm>
#include <chrono>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <sstream>
#include <stdexcept>
#include <string>
// remove when converted
//#include <unordered_map>
#include <tsl/hopscotch_map.h>
#include <utility>
#include <vector>
#include <future>

#include "parser.hpp"

static const std::string EX = "http://example.org/";
static const std::string RDF_TYPE = "http://www.w3.org/1999/02/22-rdf-syntax-ns#type";

static const std::string EXAM_DURATION     = EX + "examDuration";
static const std::string HAS_MIN_CAP       = EX + "hasMinimumRoomCapacity";
static const std::string ENROLLED_IN       = EX + "enrolledIn";

static const std::string ROOM_CAPACITY     = EX + "roomCapacity";
static const std::string HAS_AVAILABILITY  = EX + "hasAvailability";
static const std::string AVAILABLE_FROM    = EX + "availableFrom";
static const std::string AVAILABLE_UNTIL   = EX + "availableUntil";

#ifdef _WIN32
    #include <time.h>
    static std::time_t timegm_portable(std::tm* tm) { return _mkgmtime(tm); }
#else
    static std::time_t timegm_portable(std::tm* tm) { return timegm(tm); }
#endif

static int64_t parse_iso_to_epoch_seconds(const std::string& iso) {
    std::string s = iso;

    // Strip datatype suffix
    auto pos_dtype = s.find("^^");
    if (pos_dtype != std::string::npos) s = s.substr(0, pos_dtype);

    // Strip quotes
    if (s.size() >= 2 && s.front() == '"' && s.back() == '"') {
        s = s.substr(1, s.size() - 2);
    }

    // Basic ISO: YYYY-MM-DDTHH:MM:SS
    if (s.size() < 19) {
        throw std::runtime_error("Bad ISO datetime: " + iso);
    }

    std::tm tm{};
    tm.tm_year = std::stoi(s.substr(0, 4)) - 1900;
    tm.tm_mon  = std::stoi(s.substr(5, 2)) - 1;
    tm.tm_mday = std::stoi(s.substr(8, 2));
    tm.tm_hour = std::stoi(s.substr(11, 2));
    tm.tm_min  = std::stoi(s.substr(14, 2));
    tm.tm_sec  = std::stoi(s.substr(17, 2));
    tm.tm_isdst = 0;

    std::time_t t = timegm_portable(&tm);
    return static_cast<int64_t>(t);
}

static std::string epoch_seconds_to_iso(int64_t t) {
    std::time_t tt = static_cast<std::time_t>(t);
    std::tm gm{};
#ifdef _WIN32
    gmtime_s(&gm, &tt);
#else
    gmtime_r(&tt, &gm);
#endif
    std::ostringstream os;
    os << std::put_time(&gm, "%Y-%m-%dT%H:%M:%S");
    return os.str();
}

static double parse_numeric_literal(const std::string& raw) {
    std::string s = raw;

    // Remove datatype suffix "^^"
    auto pos = s.find("^^");
    if (pos != std::string::npos) {
        s = s.substr(0, pos);
    }

    // Remove quotes if present
    if (s.size() >= 2 && s.front() == '"' && s.back() == '"') {
        s = s.substr(1, s.size() - 2);
    }

    // Trim whitespace, probably redundant
    while (!s.empty() && std::isspace((unsigned char)s.front())) s.erase(s.begin());
    while (!s.empty() && std::isspace((unsigned char)s.back())) s.pop_back();

    return std::stod(s);
}


struct Room {
    std::string uri;
    int capacity = 0;
    // available intervals: [start,end) epoch seconds, sorted by start
    std::vector<std::pair<int64_t,int64_t>> free;
};

struct Course {
    std::string uri;
    int exam_minutes = 0;
    int enrollment = 0;
    int min_room_capacity = 0;
};

static std::vector<Room>
get_rooms(const std::vector<Triple>& room_triples) {
    // First: map room -> capacity
    tsl::hopscotch_map<std::string, int> cap;
    for (const auto& t : room_triples) {
        if (t.predicate == ROOM_CAPACITY) {
            cap[t.subject] = std::stoi(t.object);
        }
    }

    // Second: map room -> slot nodes
    tsl::hopscotch_map<std::string, std::vector<std::string>> room_slots;
    for (const auto& t : room_triples) {
        if (t.predicate == HAS_AVAILABILITY) {
            room_slots[t.subject].push_back(t.object);
        }
    }

    // Third: slot -> from/until
    tsl::hopscotch_map<std::string, std::string> slot_from;
    tsl::hopscotch_map<std::string, std::string> slot_until;

    for (const auto& t : room_triples) {
        if (t.predicate == AVAILABLE_FROM)  slot_from[t.subject]  = t.object;
        if (t.predicate == AVAILABLE_UNTIL) slot_until[t.subject] = t.object;
    }

    // Build rooms
    std::vector<Room> rooms;
    rooms.reserve(cap.size());

    for (const auto& [room_uri, room_cap] : cap) {
        auto it_slots = room_slots.find(room_uri);
        if (it_slots == room_slots.end()) continue;

        Room r;
        r.uri = room_uri;
        r.capacity = room_cap;

        for (const auto& slot : it_slots->second) {
            auto it_f = slot_from.find(slot);
            auto it_u = slot_until.find(slot);
            if (it_f == slot_from.end() || it_u == slot_until.end()) continue;

            int64_t a = parse_iso_to_epoch_seconds(it_f->second);
            int64_t b = parse_iso_to_epoch_seconds(it_u->second);
            if (b > a) r.free.push_back({a,b});
        }

        std::sort(r.free.begin(), r.free.end(),
                  [](auto& x, auto& y){ return x.first < y.first || (x.first == y.first && x.second < y.second); });

        if (!r.free.empty()) rooms.push_back(std::move(r));
    }

    // Sort rooms by capacity ascending
    std::sort(rooms.begin(), rooms.end(),
              [](const Room& a, const Room& b){ return a.capacity < b.capacity; });

    return rooms;
}

static std::vector<Course>
build_courses(const std::vector<Triple>& class_triples,
              const tsl::hopscotch_map<std::string,int>& enrollment_counts) {
    // class -> durationHours, class -> minCap
    tsl::hopscotch_map<std::string, double> dur_hours;
    tsl::hopscotch_map<std::string, int> min_cap;

    for (const auto& t : class_triples) {
        if (t.predicate == EXAM_DURATION) {
            dur_hours[t.subject] = parse_numeric_literal(t.object);
        } else if (t.predicate == HAS_MIN_CAP) {
            min_cap[t.subject] = static_cast<int>(parse_numeric_literal(t.object));
        }
    }

    std::vector<Course> courses;
    courses.reserve(dur_hours.size());

    for (const auto& [cls_uri, hours] : dur_hours) {
        Course c;
        c.uri = cls_uri;
        c.exam_minutes = static_cast<int>(hours * 60.0);
        auto it_en = enrollment_counts.find(cls_uri);
        c.enrollment = (it_en == enrollment_counts.end()) ? 0 : it_en->second;
        auto it_mc = min_cap.find(cls_uri);
        c.min_room_capacity = (it_mc == min_cap.end()) ? 0 : it_mc->second;
        courses.push_back(std::move(c));
    }

    // Sort based on the "new version"
    std::sort(courses.begin(), courses.end(), [](const Course& a, const Course& b){
        int need_a = std::max(a.enrollment, a.min_room_capacity);
        int need_b = std::max(b.enrollment, b.min_room_capacity);
        if (need_a != need_b) return need_a > need_b;
        if (a.enrollment != b.enrollment) return a.enrollment > b.enrollment;
        return a.exam_minutes > b.exam_minutes;
    });

    return courses;
}

static bool can_place_for_students(
    const tsl::hopscotch_map<std::string, std::vector<std::pair<int64_t,int64_t>>>& student_intervals,
    const std::vector<std::string>& students,
    int64_t start, int64_t end
) {
    for (const auto& stu : students) {
        auto it = student_intervals.find(stu);
        if (it == student_intervals.end()) continue;
        const auto& intervals = it->second;
        if (intervals.empty()) continue;

        // Python - i = bisect_right(intervals, (start,end))
        auto pos = std::upper_bound(intervals.begin(), intervals.end(), std::make_pair(start,end));

        if (pos != intervals.begin()) {
            auto [ps, pe] = *(pos - 1);
            if (pe > start) return false;
        }
        if (pos != intervals.end()) {
            auto [ns, ne] = *pos;
            if (end > ns) return false;
        }
    }
    return true;
}

static void commit_students(
    tsl::hopscotch_map<std::string, std::vector<std::pair<int64_t,int64_t>>>& student_intervals,
    const std::vector<std::string>& students,
    int64_t start, int64_t end
) {
    for (const auto& stu : students) {
        auto& vec = student_intervals[stu];
        auto pos = std::upper_bound(vec.begin(), vec.end(), std::make_pair(start,end));
        vec.insert(pos, {start,end}); // keeps sorted
    }
}

struct StundentDerived {
    tsl::hopscotch_map<std::string,int> enrollment_counts;
    tsl::hopscotch_map<std::string,std::vector<std::string>> students_by_class; 
};

static StundentDerived build_student_derivations(const std::vector<Triple>& student_triples) {
    StundentDerived out;

    for (const auto& triple : student_triples) {
        if(triple.predicate == ENROLLED_IN) {
            out.enrollment_counts[triple.object] += 1;
            out.students_by_class[triple.object].push_back(triple.subject);
        }
    }

    return out;
}

struct ScheduledItem {
    std::string class_iri;
    std::string room_iri;
    int64_t start = 0;
    int64_t end = 0;
};

static std::vector<ScheduledItem>
schedule_greedy(const std::vector<Course>& courses,
                std::vector<Room>& rooms, // mutated (free blocks shrink)
                const tsl::hopscotch_map<std::string, std::vector<std::string>>& students_by_class) {

    tsl::hopscotch_map<std::string, std::vector<std::pair<int64_t,int64_t>>> student_intervals;
    std::vector<ScheduledItem> schedule;
    schedule.reserve(courses.size());
    auto t0 = std::chrono::high_resolution_clock::now(); 

    for (const auto& course : courses) {
        const std::string& cls = course.uri;
        int mins = course.exam_minutes;
        int need = std::max(course.enrollment, course.min_room_capacity);

        auto it_students = students_by_class.find(cls);
        const std::vector<std::string> empty_students;
        const auto& students = (it_students == students_by_class.end()) ? empty_students : it_students->second;

        // best = earliest start among all feasible candidates
        bool found = false;
        int best_room = -1;
        int best_block = -1;
        int64_t best_start = 0;
        int64_t best_end = 0;

        for (int ri = 0; ri < (int)rooms.size(); ++ri) {
            Room& room = rooms[ri];
            if (room.capacity < need) continue;

            for (int bi = 0; bi < (int)room.free.size(); ++bi) {
                auto [a,b] = room.free[bi];
                int64_t dur = (int64_t)mins * 60;
                if (b - a < dur) continue;

                int64_t start = a;
                int64_t end = a + dur;

                if (!can_place_for_students(student_intervals, students, start, end)) continue;

                if (!found || start < best_start) {
                    found = true;
                    best_room = ri;
                    best_block = bi;
                    best_start = start;
                    best_end = end;
                }
            }
        }

        if (!found) {
            schedule.push_back({cls, "", 0, 0});
            continue;
        }

        // Commit room usage (shrink free block)
        Room& room = rooms[best_room];
        auto [a,b] = room.free[best_block];
        room.free.erase(room.free.begin() + best_block);
        if (best_end < b) {
            room.free.insert(room.free.begin() + best_block, {best_end, b});
        }

        // Commit student usage
        commit_students(student_intervals, students, best_start, best_end);

        schedule.push_back({cls, room.uri, best_start, best_end});
    }

    auto t1 = std::chrono::high_resolution_clock::now();
    std::chrono::duration<double> dt = t1 - t0;
    std::cout << "total time for scheduling " << dt.count() << " s\n";

    return schedule;
}

static std::string json_escape(const std::string& s) {
    std::string out;
    out.reserve(s.size()+8);
    for (char c : s) {
        switch (c) {
            case '\\': out += "\\\\"; break;
            case '"':  out += "\\\""; break;
            case '\n': out += "\\n"; break;
            case '\r': out += "\\r"; break;
            case '\t': out += "\\t"; break;
            default:
                if ((unsigned char)c < 0x20) {
                    // control char -> \u00XX
                    std::ostringstream os;
                    os << "\\u" << std::hex << std::uppercase << std::setw(4) << std::setfill('0') << (int)(unsigned char)c;
                    out += os.str();
                } else out += c;
        }
    }
    return out;
}

static void write_schedule_json(
    const std::string& out_path,
    const std::vector<ScheduledItem>& schedule,
    const tsl::hopscotch_map<std::string, std::vector<std::string>>& students_by_class
) {
    std::ofstream out(out_path);
    if (!out) throw std::runtime_error("Failed to write: " + out_path);

    out << "{\n";
    int counter = 1;
    bool first_group = true;

    for (const auto& item : schedule) {
        if (item.room_iri.empty()) continue;

        if (!first_group) out << ",\n";
        first_group = false;

        std::ostringstream gid;
        gid << "group_" << std::setw(4) << std::setfill('0') << counter++;
        std::string group_id = gid.str();

        out << "  \"" << group_id << "\": {\n";

        // students array
        out << "    \"students\": [";
        auto it = students_by_class.find(item.class_iri);
        if (it != students_by_class.end()) {
            const auto& studs = it->second;
            for (size_t i = 0; i < studs.size(); ++i) {
                if (i) out << ", ";
                out << "\"" << json_escape(studs[i]) << "\"";
            }
        }
        out << "],\n";

        // room object
        out << "    \"room\": {\n";
        out << "      \"room_iri\": \"" << json_escape(item.room_iri) << "\",\n";
        out << "      \"start\": \"" << json_escape(epoch_seconds_to_iso(item.start)) << "\",\n";
        out << "      \"end\": \"" << json_escape(epoch_seconds_to_iso(item.end)) << "\"\n";
        out << "    },\n";

        // class iri
        out << "    \"class_iri\": \"" << json_escape(item.class_iri) << "\"\n";

        out << "  }";
    }

    out << "\n}\n";
}

int main() {
    try {
        const std::string data_directory = "../data/";
        const std::string students_path = data_directory + "students.ttl";
        const std::string classes_path  = data_directory + "classes.ttl";
        const std::string rooms_path    = data_directory + "rooms.ttl";
        const std::string out_path      = "exam_schedule.json";

        // Multithreaded file parsing, small performance increase
        Graph g1, g2, g3;

        auto fut_students = std::async(std::launch::async, [&] {
            StundentDerived out;
            auto student_triples = g1.parse_file(students_path);
            return build_student_derivations(student_triples);

        });
        auto fut_classes = std::async(std::launch::async, [&] {
            return g2.parse_file(classes_path);
        });
        auto fut_rooms = std::async(std::launch::async, [&] {
            auto rooms_triples =  g3.parse_file(rooms_path);
            return get_rooms(rooms_triples);
        });

        // .get() will rethrow any exception that happened in the thread
        auto student_derived = fut_students.get();
        auto classes_triples  = fut_classes.get();

        auto rooms = fut_rooms.get(); 

        //auto enrollment_counts = get_enrollment_counts(students_triples);
        //auto students_by_class = build_students_by_class(students_triples);

        auto courses = build_courses(classes_triples, student_derived.enrollment_counts);

        auto schedule = schedule_greedy(courses, rooms, student_derived.students_by_class);

        // JSON output
        write_schedule_json(out_path, schedule, student_derived.students_by_class);

    }
    catch (const std::exception& e) {
        std::cerr << "ERROR: " << e.what() << "\n";
        return 1;
    }
    return 0;
}

