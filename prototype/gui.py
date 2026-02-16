import os
import main
from tkinter import *
import time

# create root window
root = Tk()

T = Text(root, height=5, width=52)
T.pack()
T.insert('1.0', "Waiting to run", "center")

root.title("Greedy Scheduling Algorithm")
root.geometry('350x200')

lbl = Label(root, text="Greedy Scheduling Algorithm")
lbl.pack()

def clicked_once():
    T.delete('1.0', END)
    T.insert(END, "running")
    prev_time = time.time_ns()
    main.main()
    current_time = time.time_ns()
    time_optimum = (current_time - prev_time) / 1_000_000_000  # convert to seconds
    T.delete('1.0', END)
    T.insert(END, "code ran in " + str(time_optimum) + " seconds")

def clicked_one_hundred():
    T.delete('1.0', END)
    T.insert(END, "running")
    prev_time = time.time_ns()
    for i in range(100):
        main.main()
    current_time = time.time_ns()
    time_optimum = (current_time - prev_time) / 1_000_000_000  # convert to seconds
    T.delete('1.0', END)
    T.insert(END, "100 iterations ran in " + str(time_optimum) + " seconds\n")
    T.insert(END, "\nAverage time: " + str(time_optimum/100) + " seconds")


btn = Button(root, text="Run Scheduler", fg="red", command=clicked_once)
btn2 = Button(root, text="Run Scheduler 100 times", fg="red", command=clicked_one_hundred)


btn.pack()
btn2.pack()

root.mainloop()