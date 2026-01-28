from rdflib import Graph, URIRef
from itertools import groupby
from operator import itemgetter
from datetime import datetime
from dataclasses import dataclass

from pathlib import Path
from typing import Dict, List, Tuple

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

def load_graph(path: Path) -> Graph:
    graph = Graph()
    graph.parse(str(path), format="turtle")
    return graph

def get_enrollment_counts(students: Graph) -> Dict[URIRef, int]:
    counts: Dict[URIRef, int] = {}
    for _, _, cls in g_students.triples((None, ENROLLED_IN, None)):
        if isinstance(cls, URIRef):
            counts[cls] = counts.get(cls, 0) + 1
    return counts

def main() -> None:
    students_path = data_directory + "students.ttl"
    classes_path = data_directory + "classes.ttl"
    rooms_path = data_directory + "rooms.ttl"

    students = load_graph(students_path)
    classes = load_graph(classes_path)
    rooms = load_graph(rooms_path)

    # Enrollment counts -> Dict[URIRef, int]
    enrollment_counts = get_enrollment_counts(students)
    # Rooms list -> List[Room]
    # Courses list -> List[Course]

    # Greedy algorithm
