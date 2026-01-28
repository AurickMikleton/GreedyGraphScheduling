from rdflib import Graph

data_directory = "../data/"

students = Graph()
classes = Graph()
rooms = Graph()

students.parse(data_directory + "students.ttl", format="turtle")
classes.parse(data_directory + "classes.ttl", format="turtle")
rooms.parse(data_directory + "rooms.ttl", format="turtle")

#students.print()
#classes.print()
#rooms.print()

for s, p, o in students:
    print(s)
    print(p)
    print(o)
    print()
