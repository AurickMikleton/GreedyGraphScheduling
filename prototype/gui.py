import time
import webbrowser
from tkinter import *

import main


def run_once():
    output.delete('1.0', END)
    output.insert(END, "running")
    root.update()

    start = time.time_ns()
    main.main()
    elapsed = (time.time_ns() - start) / 1_000_000_000

    output.delete('1.0', END)
    output.insert(END, f"code ran in {elapsed:.4f} seconds")


def run_hundred():
    output.delete('1.0', END)
    output.insert(END, "running")
    root.update()

    start = time.time_ns()
    for _ in range(100):
        main.main()
    elapsed = (time.time_ns() - start) / 1_000_000_000

    output.delete('1.0', END)
    output.insert(END, f"100 iterations ran in {elapsed:.4f} seconds\n")
    output.insert(END, f"\nAverage time: {elapsed / 100:.4f} seconds")


def open_repo(event):
    webbrowser.open_new_tab("https://github.com/AurickMikleton/GreedyGraphScheduling")


root = Tk()
root.title("Greedy Scheduling Algorithm")
root.geometry('350x300')

frame = Frame(root, padx=10, pady=10)
frame.place(relx=0.5, rely=0.5, anchor='center')

Label(
    frame,
    text="Greedy Scheduling Algorithm",
    bg="lightblue",
    font=("Comic Sans", 15, "bold"),
    fg="red",
    padx=10,
    pady=10,
    relief="raised",
    wraplength=250
).pack()

output = Text(frame, height=5, width=40)
output.pack(pady=5)
output.insert('1.0', "Waiting to run")

Button(frame, text="Run Scheduler", fg="red", command=run_once, cursor="hand2").pack(pady=2)
Button(frame, text="Run Scheduler 100 times", fg="red", command=run_hundred, cursor="hand2").pack(pady=2)

repo_link = Label(frame, text="Click here for the full project repo", bg="#3A7FF6", fg="white", cursor="hand2")
repo_link.pack(pady=5)
repo_link.bind('<Button-1>', open_repo)

root.mainloop()