import json
import jsonschema
import os
import sys
from rdflib import Graph, Namespace, URIRef
from datetime import datetime

# ---------------------------------------------------------
# Typing
from typing import TypedDict


class RoomInfo(TypedDict):
    end: str
    room_iri: str
    start: str


class GroupInfo(TypedDict):
    students: list[str]
    room: RoomInfo
    class_iri: str


OutputType = dict[str, GroupInfo]


# ---------------------------------------------------------
# Constants
TTL_DIRECTORY = os.path.join(os.path.dirname(
    os.path.abspath(__file__)), "../data/")

# Namespaces
EX = Namespace("http://example.org/")
SCHEMA = Namespace("http://schema.org/")
RDF = Namespace("http://www.w3.org/1999/02/22-rdf-syntax-ns#")

# Import data
g = Graph()
for filename in os.listdir(TTL_DIRECTORY):
    if filename.endswith(".ttl"):
        file_path = os.path.join(TTL_DIRECTORY, filename)
        g.parse(file_path, format="ttl")
print("Successfully loaded data!\n")

# ---------------------------------------------------------
# Verification functions


def verify_room_capacity(output: OutputType, graph: Graph):
    """
    Check that no room has more students assigned than it can hold.

    Arguments:
        output (dict): The exam schedule.
        graph (rdflib.Graph): The RDF graph containing room capacities.
    Returns:
        bool: True if all groups fit in their rooms, False if any group exceeds the room capacity.
    """
    all_ok = True

    for group_id, group_info in output.items():
        room_iri = group_info["room"]["room_iri"]
        assigned_students = group_info["students"]

        # Get room capacity from RDF graph
        room_capacity = int(
            next(graph.objects(URIRef(room_iri), EX.roomCapacity)))

        if len(assigned_students) > room_capacity:
            print(f"ERROR: {group_id} has {len(assigned_students)} students "
                  f"but room capacity is {room_capacity} ({room_iri})")
            all_ok = False

    assert all_ok


def verify_student_exam_conflicts(output: OutputType):
    """
    Check that no student has two exams scheduled at the same time.

    Arguments:
        output (dict): The exam schedule.
    Returns:
        bool: True if no student has overlapping exams, False if any conflicts are found.
    """
    all_ok = True
    student_assignments = {}

    # Step 1: Collect all student assignments
    for group_id, group_info in output.items():
        start_dt, end_dt = parse_slot_time_slot(group_info["room"])
        class_iri = group_info["class_iri"]
        for student in group_info["students"]:
            student_assignments.setdefault(student, []).append({
                "class": class_iri,
                "start": start_dt,
                "end": end_dt,
                "group_id": group_id
            })

    # Step 2: Check each student's assignments for overlaps
    for student, assignments in student_assignments.items():
        # Sort by start time for easier checking
        assignments.sort(key=lambda x: x["start"])
        for i in range(len(assignments) - 1):
            current = assignments[i]
            next_ = assignments[i + 1]
            if current["end"] > next_["start"]:
                print(f"CONFLICT: {student} has overlapping exams "
                      f"{current['class']} (group {current['group_id']}) and "
                      f"{next_['class']} (group {next_['group_id']})")
                all_ok = False

    assert all_ok


def verify_all_students_have_all_finals(output: OutputType, graph: Graph):
    """
    Verify that every student is assigned to a final for each class
    they are enrolled in.

    Arguments:
        output (dict): Scheduler output.
        graph (rdflib.Graph): RDF graph with enrollment data.
    Returns:
        bool: True if all students are correctly scheduled, False otherwise
    """
    all_ok = True

    # Step 1: Build map of scheduled classes per student
    scheduled_classes: dict[str, set] = {}  # student -> set(classIRI)

    for group in output.values():
        class_iri = group["class_iri"]
        for student in group["students"]:
            scheduled_classes.setdefault(student, set()).add(class_iri)

    # Step 2: Compare with enrolled classes from RDF
    for student in scheduled_classes:
        enrolled_classes = {
            str(c) for c in graph.objects(URIRef(student), EX.enrolledIn)
        }

        assigned_classes = scheduled_classes.get(student, set())

        missing_classes = enrolled_classes - assigned_classes

        if len(missing_classes):
            print(f"ERROR: {student} missing finals for:")
            for cls in missing_classes:
                print(f"  - {cls}")
            all_ok = False

    assert all_ok


def verify_exam_room_fit(output: OutputType, graph: Graph):
    """
    Check that each scheduled exam fits within the available times of its assigned room.

    Arguments:
        output (dict): The exam schedule.
        graph (rdflib.Graph): RDF graph containing rooms and their available times
    Returns:
        bool: True if all exams are scheduled within room availability, False otherwise.
    """
    all_ok = True

    for group_id, group_info in output.items():
        room_iri = URIRef(group_info["room"]["room_iri"])

        start_str = group_info["room"]["start"]
        end_str = group_info["room"]["end"]
        exam_start = datetime.fromisoformat(start_str)
        exam_end = datetime.fromisoformat(end_str)

        # Convert to datetime pairs
        availability_windows = get_room_slots(graph, room_iri)

        # Check if exam fits in any availability window
        fits = False
        for avail_start, avail_end in availability_windows:
            if exam_start >= avail_start and exam_end <= avail_end:
                fits = True
                break

        if not fits:
            print(f"ERROR: Exam {group_info['class_iri']} in group {group_id} "
                  f"scheduled {exam_start} - {exam_end} does NOT fit in room {room_iri} availability")
            all_ok = False
        else:
            pass

    assert all_ok


def verify_no_room_overlaps(output: OutputType):
    """
    Verify that no room is assigned overlapping exams.

    Arguments:
        output (OutputType): Scheduler output.
    Returns:
        bool: True if no room overlaps are found, False otherwise
    """
    all_ok = True
    # Key is the room IRI and the value is the exam info (start, end, and ID of the exam)
    exam_assignments: dict[str, list[tuple[str, str, str]]] = {}

    # Step 1: Collect all exams per room
    for group_id, group_info in output.items():
        room_iri = group_info["room"]["room_iri"]
        start_dt, end_dt = parse_slot_time_slot(group_info["room"])

        exam_assignments.setdefault(room_iri, []).append(
            (start_dt, end_dt, group_id)
        )

    # Step 2: Check overlaps per room
    for room_iri, exams in exam_assignments.items():
        # Sort by start time
        exams.sort(key=lambda x: x[0])

        for i in range(len(exams) - 1):
            curr_start, curr_end, curr_group = exams[i]
            next_start, next_end, next_group = exams[i + 1]

            if curr_end > next_start:
                print(
                    f"ROOM CONFLICT: Room {room_iri} has overlapping exams "
                    f"{curr_group} ({curr_start} - {curr_end}) and "
                    f"{next_group} ({next_start} - {next_end})"
                )
                all_ok = False

    assert all_ok


def verify_no_duplicate_exam_assignments(output: OutputType):
    """
    Verify that no student is assigned to more than one group
    of the same exam (class).

    Arguments:
        output (OutputType): Scheduler output
    Returns:
        bool: True if no duplicate assignments are found, False otherwise
    """
    all_ok = True

    # {
    #   [student_iri]: { [class_iri]: list of group_ids[] }
    # }
    student_exam_map: dict[str, dict[str, list[str]]] = {}

    for group_id, group_info in output.items():
        class_iri = group_info["class_iri"]

        for student in group_info["students"]:
            student_exam_map.setdefault(student, {}).setdefault(
                class_iri, []).append(group_id)

    # Check for duplicates
    for student, classes in student_exam_map.items():
        seen = set()
        duplicates = set()

        for cls in classes:
            if cls in seen:
                duplicates.add(cls)
            else:
                seen.add(cls)
        if len(duplicates):
            print(
                f"DUPLICATE EXAM: {student} was assigned to the following class exams multiple times: {duplicates}")
        for class_iri, groups in classes.items():
            if len(groups) > 1:
                print(
                    f"DUPLICATE EXAM: {student} assigned to multiple groups for class {class_iri}: {groups}")
                all_ok = False

    assert all_ok


def verify_all_student_exams_are_accounted_for(output: OutputType, graph: Graph):
    """
    Check that every student is scheduled for all of their enrolled exams.

    Arguments:
        output (dict): The exam schedule.
        graph (rdflib.Graph): RDF graph containing students and their enrolled classes

    Returns:
        bool: True if every student appears in all of their classes' exams, False otherwise.
    """
    students_in_exams = 0
    expected_number_of_students_in_exams = 0
    for group_info in output.values():
        students_in_exams += len(group_info["students"])
    students = get_students(graph)
    for student in students:
        expected_number_of_students_in_exams += len(
            get_student_classes(graph, student))

    all_ok = students_in_exams == expected_number_of_students_in_exams

    assert all_ok


# ---------------------------------------------------------
# Helper Functions
def parse_time_slot(start_str: str, end_str: str):
    """Convert xsd:dateTime string to Python datetime tuple"""
    return datetime.fromisoformat(start_str), datetime.fromisoformat(end_str)


def parse_slot_time_slot(data: dict[str, str]):
    """
    Convert a time_slot into a tuple of (start_datetime, end_datetime)
    """
    start_str = data["start"]
    end_str = data["end"]
    start_dt = datetime.fromisoformat(start_str)
    end_dt = datetime.fromisoformat(end_str)
    return start_dt, end_dt


def get_students(graph: Graph):
    """Return a list of student URIs"""
    return list(graph.subjects(predicate=RDF.type, object=EX.Person))


def get_student_classes(graph: Graph, student_uri: URIRef):
    """Return a list of class URIs the student is enrolled in"""
    return list(graph.objects(student_uri, EX.enrolledIn))


def get_room_slots(graph: Graph, room_uri: URIRef):
    """
    Return all availability slots for a room as tuples:
    (start_datetime, end_datetime)
    """
    availability_slots = list(graph.objects(room_uri, EX.hasAvailability))

    starts = []
    ends = []

    for availability_node in availability_slots:
        # There aren't multiple from/to times on a time slot
        starts.append(
            next(graph.objects(availability_node, EX.availableFrom), None))
        ends.append(
            next(graph.objects(availability_node, EX.availableUntil), None))
    # Pair starts and ends by index
    return [parse_time_slot(str(s), str(e)) for s, e in zip(starts, ends)]


def get_rooms(graph: Graph):
    """Return a list of room URIs"""
    return list(graph.subjects(predicate=RDF.type, object=EX.Room))


def get_exam_duration_hours(graph: Graph, class_iri: str):
    """
    Return exam duration in hours as a float.
    Supports:
      - xsd:integer (e.g. 2)
    """
    duration_literal = next(graph.objects(URIRef(class_iri), EX.examDuration))

    # If duration is a plain number (int or float)
    try:
        return float(duration_literal)
    except ValueError:
        raise ValueError(
            f"Unsupported examDuration format: {duration_literal}")


# ---------------------------------------------------------
# Main
if "__main__" == __name__:
    # Check if a filename was provided
    if len(sys.argv) < 2:
        print(f"Usage: python {sys.argv[0]} <filename.json>")
        sys.exit(1)

    # Get the filename from command-line arguments
    filename = sys.argv[1]
    # Open the JSON file and load it into a Python dictionary
    with open(filename, "r") as f:
        schedule = json.load(f)

    schema = {
        "type": "object",
        "additionalProperties": {
            "type": "object",
            "properties": {
                "students": {
                    "type": "array",
                    "items": {"type": "string"},
                    "minItems": 1  # ensures the array is not empty
                },
                "room": {
                    "type": "object",
                    "properties": {
                        "room_iri": {"type": "string"},
                        "start": {"type": "string"},
                        "end": {"type": "string"}
                    },
                    "required": ["room_iri", "start", "end"]
                },
                "class_iri": {"type": "string"}
            },
            "required": ["students", "room", "class_iri"]
        }
    }

    # Validate the input is correctly structure JSON
    try:
        jsonschema.validate(instance=schedule, schema=schema)
        verify_room_capacity(schedule, g)
        verify_student_exam_conflicts(schedule)
        verify_all_students_have_all_finals(schedule, g)
        verify_exam_room_fit(schedule, g)
        verify_no_room_overlaps(schedule)
        verify_no_duplicate_exam_assignments(schedule)
        verify_all_student_exams_are_accounted_for(schedule, g)
        print("This is a valid schedule!")
    except jsonschema.ValidationError as e:
        print("Validation error:", e)
