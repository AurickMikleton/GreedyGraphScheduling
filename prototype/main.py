from rdflib import Graph, URIRef
from itertools import groupby
from operator import itemgetter
from datetime import datetime, timedelta
from dataclasses import dataclass

from pathlib import Path
from typing import Dict, List, Tuple

import json


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
class Student:
    uri: URIRef
    name: str
    classes: [str]
    #schedule: []


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
        min_cap = None
        for o in g_classes.objects(cls_uri, HAS_MIN_CAP):
            min_cap = int(o)

        courses.append(Course(uri=cls_uri, exam_minutes=minutes, enrollment=enrolled, min_room_capacity=min_cap))

    # Greedy order - longest exams first
    #change to students enrolled
    courses.sort(key=lambda c: c.exam_minutes, reverse=True)
    return courses

def schedule_greedy(courses: List[Course], rooms: List[Room]) -> List[dict]:
    out: List[dict] = []

    for course in courses:
        need = max(course.enrollment, course.min_room_capacity or 0)

        placed = False
        chosen_room: Room = None
        chosen_start: datetime = None
        chosen_end: datetime = None

        # Choose earliest placement across rooms
        best = None

        for ri, room in enumerate(rooms):
            if room.capacity < need:
                continue

            for block_i, (a, b) in enumerate(room.free):
                if (b - a).total_seconds() >= course.exam_minutes * 60:
                    start = a
                    end = a + timedelta(minutes=course.exam_minutes)
                    cand = (start, end, ri, block_i)
                    if best is None or cand[0] < best[0] or (cand[0] == best[0] and room.capacity < rooms[best[2]].capacity):
                        best = cand

        if best is not None:
            start, end, ri, block_i = best
            chosen_room = rooms[ri]
            chosen_start = start
            chosen_end = end

            # replace [a,b] with remainder after [start,end]
            a, b = chosen_room.free[block_i]
            chosen_room.free.pop(block_i)
            if end < b:
                chosen_room.free.insert(block_i, (end, b))
            placed = True

        # temporary json output (non compliant)
        out.append(
            { 
                "class": str(course.uri),
                "room": str(chosen_room.uri) if placed and chosen_room else None,
                "start": chosen_start.isoformat() if placed and chosen_start else None,
                "end": chosen_end.isoformat() if placed and chosen_end else None,
                "exam_minutes": course.exam_minutes,
                "enrollment": course.enrollment,
                "required_capacity": need,
            }
        )

    return out

def build_students_by_class(g_students: Graph) -> dict[str, list[str]]:
    students_by_class = {}
    for student, _, cls in g_students.triples((None, ENROLLED_IN, None)):
        students_by_class.setdefault(str(cls), []).append(str(student))
    return students_by_class

def schedule_students_by_class(g_students: Graph) -> dict[str, list[str]]:
    #
    for classes,students in g_students.items():
        #1 single course, list of students
        #2 map the student object to the list by name
        #3 grouping by the students
        #4 checking schedule conflicts (
        #5 reassigning
        

    return g_students


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

    # Greedy algorithm
    schedule = schedule_greedy(courses_list, rooms_list)
    # Add students to groups
    # TODO does not prevent students from having overlapping exams
    students_by_class = build_students_by_class(students)

    final_schedule = schedule_students_by_class(students_by_class)

    groups = {}
    counter = 1

    # Correct the json for automatic testing compliance
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


    scheduled = sum(1 for x in schedule if x["room"] is not None)
    unscheduled = len(schedule) - scheduled
    print(f"Wrote {out_path} | scheduled={scheduled} unscheduled={unscheduled}")

if __name__ == "__main__":
    main()
