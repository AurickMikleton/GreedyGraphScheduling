from rdflib import Graph, URIRef
from itertools import groupby
from operator import itemgetter

data_directory = "../data/"

EX = "http://example.org/"
EXAM_DURATION = URIRef(EX + "examDuration")
HAS_MIN_CAP = URIRef(EX + "hasMinimumRoomCapacity")
ENROLLED_IN = URIRef(EX + "enrolledIn")

ROOM_CAPACITY = URIRef(EX + "roomCapacity")
HAS_AVAILABILITY = URIRef(EX + "hasAvailability")
AVAILABLE_FROM = URIRef(EX + "availableFrom")
AVAILABLE_UNTIL = URIRef(EX + "availableUntil")

def load_graph(path: Path) -> Graph:
    graph = Graph()
    graph.parse(str(path), format="turtle")
    return graph

def main():
    students_path = data_directory + "students.ttl"
    classes_path = data_directory + "classes.ttl"
    rooms_path = data_directory + "rooms.ttl"

    students = load_graph(students_path)
    classes = load_graph(classes_path)
    rooms = load_graph(rooms_path)

    # Enrollment counts -> Dict[URIRef, int]
    # Rooms list
    # Courses list

    # Greedy algorithm
