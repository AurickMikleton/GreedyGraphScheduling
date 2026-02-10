from rdflib import Graph, URIRef
from datetime import datetime, timedelta
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Tuple

import json
import bisect
import time

data_directory = "../data/"

EX = "http://example.org/"
EXAM_DURATION = URIRef(EX + "examDuration")
HAS_MIN_CAP = URIRef(EX + "hasMinimumRoomCapacity")
ENROLLED_IN = URIRef(EX + "enrolledIn")

ROOM_CAPACITY = URIRef(EX + "roomCapacity")
HAS_AVAILABILITY = URIRef(EX + "hasAvailability")
AVAILABLE_FROM = URIRef(EX + "availableFrom")
AVAILABLE_UNTIL = URIRef(EX + "availableUntil")

@dataclass
class Room:
    uri: URIRef
    capacity: int
    free: List[Tuple[datetime, datetime]] # (start time, end time) pairs for availability

@dataclass
class Course:
    uri: URIRef
    exam_minutes: int
    enrollment: int
    min_room_capacity: int

def parse_iso_dt(value: str) -> datetime:
    return datetime.fromisoformat(value)

def load_graph(path: Path) -> Graph:
    graph = Graph()
    graph.parse(str(path), format="turtle")
    return graph

def intervals_overlap(a_start, a_end, b_start, b_end):
    return a_start < b_end and b_start < a_end

def can_place_for_students(student_intervals, students, start, end):

    #student_intervals: dict[student_iri] -> list[(start, end)]
    #current search time is in O(n) can be reduced to O(log n)
    #this is by implementing a bisection technique which cuts open the intervals
    #and asserts whether and exam can fit in the allotted time or not

    for stu in students:
        intervals = student_intervals.get(stu)
        if not intervals:
            continue

        i = bisect.bisect_right(intervals, (start, end))

        if i > 0:
            prev_start, prev_end = intervals[i - 1]
            if prev_end > start:
                return False
        if i < len(intervals):
            next_start, next_end = intervals[i]
            if end > next_start:
                return False

    return True

def commit_students(student_intervals, students, start, end):
    for stu in students:
        student_intervals.setdefault(stu, []).append((start, end))

def get_enrollment_counts(students: Graph) -> Dict[URIRef, int]:
    counts: Dict[URIRef, int] = {}
    for _, _, cls in students.triples((None, ENROLLED_IN, None)):
        if isinstance(cls, URIRef):
            counts[cls] = counts.get(cls, 0) + 1
    return counts

def get_rooms(rooms_graph: Graph) -> List[Room]:
    rooms: List[Room] = []

    for room_uri, _, cap_lit in rooms_graph.triples((None, ROOM_CAPACITY, None)):
        cap = int(cap_lit)

        slots = list(rooms_graph.objects(room_uri, HAS_AVAILABILITY))
        free: List[Tuple[datetime, datetime]] = []

        for slot in slots:
            for available_from in rooms_graph.objects(slot, AVAILABLE_FROM):
                for available_until in rooms_graph.objects(slot, AVAILABLE_UNTIL):
                    start_time = parse_iso_dt(str(available_from))
                    end_time = parse_iso_dt(str(available_until))
                    if end_time > start_time:
                        free.append((start_time, end_time))

        # Keep intervals sorted
        free.sort(key=lambda ab: (ab[0], ab[1]))

        if free:
            rooms.append(Room(uri=room_uri, capacity=cap, free=free))

    # sort rooms by capacity ascending to keep big rooms free if needed
    rooms.sort(key=lambda r: r.capacity)
    return rooms

def build_courses(g_classes: Graph, enrollment_counts: Dict[URIRef, int]) -> List[Course]:
    courses: List[Course] = []

    for cls_uri, _, dur_lit in g_classes.triples((None, EXAM_DURATION, None)):
        if not isinstance(cls_uri, URIRef):
            continue

        # examDuration stored as hours
        minutes = int(float(dur_lit) * 60)
        enrolled = enrollment_counts.get(cls_uri, 0)

        # per-class minimum room capacity constraint
        min_cap = 0
        for o in g_classes.objects(cls_uri, HAS_MIN_CAP):
            min_cap = int(o)

        courses.append(Course(uri=cls_uri, exam_minutes=minutes, enrollment=enrolled, min_room_capacity=min_cap))

    # Greedy order - longest exams first. LEGACY VERSION
    # courses.sort(key=lambda c: c.exam_minutes, reverse=True)
    # New version ensuring a full schedule
    courses.sort(key=lambda c: (max(c.enrollment, c.min_room_capacity or 0), c.enrollment, c.exam_minutes), reverse=True)

    return courses

def build_students_by_class(g_students: Graph) -> dict[str, list[str]]:
    students_by_class = {}
    for student, _, cls in g_students.triples((None, ENROLLED_IN, None)):
        students_by_class.setdefault(str(cls), []).append(str(student))
    return students_by_class

def schedule_greedy(courses: List[Course], rooms: List[Room], students_by_class: Dict[str, List[str]]):
    student_intervals: Dict[str, List[Tuple[datetime, datetime]]] = {}
    schedule = []
    prev_time = time.time_ns()
    for course in courses:
        cls_key = str(course.uri)
        mins = course.exam_minutes
        # required seats = max(enrollment, min_room_capacity)
        need = max(course.enrollment, course.min_room_capacity or 0)

        students = students_by_class.get(cls_key, [])

        best = None  # (start, end, room_index, block_index)

        for room_index, room in enumerate(rooms):
            if room.capacity < need:
                #break case if more students need room than available
                continue

            for block_index, (a, b) in enumerate(room.free):
                #goes through free rooms
                if (b - a).total_seconds() < mins * 60:
                    #checking a time condition
                    continue

                start = a
                end = a + timedelta(minutes=mins)

                if not can_place_for_students(student_intervals, students, start, end):
                    continue

                cand = (start, end, room_index, block_index)
                if best is None or cand[0] < best[0]: #what is the extra condition here
                    best = cand

        if best is None:
            schedule.append({
                "class": cls_key,
                "room": None,
                "start": None,
                "end": None
            })
            continue

        start, end, room_index, block_index = best
        room = rooms[room_index]

        # update room free blocks
        a, b = room.free[block_index]
        room.free.pop(block_index)
        if end < b:
            room.free.insert(block_index, (end, b))

        commit_students(student_intervals, students, start, end)

        schedule.append({
            "class": cls_key,
            "room": str(room.uri),
            "start": start.isoformat(),
            "end": end.isoformat()
        })
    current_time = time.time_ns()
    time_optimimum = current_time - prev_time
    print('total time for optimized scheduling', (time_optimimum/1000000000), 's')

    return schedule

def main() -> None:
    students_path = data_directory + "students.ttl"
    classes_path = data_directory + "classes.ttl"
    rooms_path = data_directory + "rooms.ttl"
    out_path = Path("exam_schedule.json")

    students = load_graph(students_path)
    classes = load_graph(classes_path)
    rooms = load_graph(rooms_path)

    # Enrollment counts -> Dict[URIRef, int]
    enrollment_counts = get_enrollment_counts(students)
    # Rooms list -> List[Room]
    rooms_list = get_rooms(rooms) 
    # Courses list -> List[Course]
    courses_list = build_courses(classes, enrollment_counts) 
    # Students by Class -> Dict[str, List[str]]
    students_by_class = build_students_by_class(students)

    # Greedy algorithm
    schedule = schedule_greedy(courses_list, rooms_list, students_by_class)

    groups = {}
    counter = 1

    for item in schedule:
        if item["room"] is None:
            continue

        group_id = f"group_{counter:04d}"
        counter += 1

        class_iri = item["class"]

        groups[group_id] = {
            "students": students_by_class.get(class_iri, []),
            "room": {
                "room_iri": item["room"],
                "start": item["start"],
                "end": item["end"]
            },
            "class_iri": class_iri
        }

    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(groups, f, indent=2)

    # Diagnoses test statements
    scheduled = sum(1 for x in schedule if x["room"] is not None)
    unscheduled = len(schedule) - scheduled
    print(f"Wrote {out_path} | scheduled={scheduled} unscheduled={unscheduled}")

if __name__ == "__main__":
    main()
