import sys
import random, pyperclip, json
from pdf2image import convert_from_path
import fitz
import io 
import numpy as np
import cv2 as cv
from tkinter import *
from PIL import Image, ImageTk

from classes import Session, Processor, Highlighter, Pencil, Text

tools = {
    'highlight': {
        "icon": "./icons/highlight.png",
        "class": Highlighter,
        "export_layer": "behind"
    },
    'pencil': {
        "icon": "./icons/pencil.png",
        "class": Pencil,
        "export_layer": "above"
    },
    'text': {
        "icon": "./icons/text.png",
        "class": Text,
        "export_layer": "above"
    },
    # 'eraser': {
    #     "icon": "./icons/eraser.png"
    # },
}

def log_data(data):
    if len(data) == 0: return 'no types present'

    types = {}

    for item in data:
        _type = item['type']
        if _type in list(types.keys()):
            types[_type] += 1
        else:
            types[_type] = 1

    message = list(map(lambda e: f'{e[1]} {e[0]} type{"s" if e[1] != 1 else ""}', types.items()))
    message[-1] = 'and ' + message[-1] if len(message) != 1 else message[-1]

    message = ', '.join(message)

    return message

# FIXME: Highlight rectangles can only be created from the top left
# FIXME: Exporting on last page removes pencil lines
# FIXME: Exported pencil lines connect start and end points

# TODO: Zoom out of large images to achieve an editable window size (*)
# TODO: Add save functionality (*)
# TODO: Retain history between pages (*)
# TODO: Add pencil tool (*)
# TODO: Organize pencil and highlight into tools (*)
# TODO: Add zoom in/out tool

# images = []
# for i in range(1, 13):
#     images.append(cv.imread(f'{i}.jpeg'))
# 

# pdf = input('PDF File: ')
# if not pdf.endswith('.pdf'): sys.exit()

pdf = 'file.pdf'

# images = convert_from_path(pdf)
images = convert_from_path(pdf)[0:2]
print(f'Got {len(images)} image(s)')

rects = []
session = None

processor = Processor(images)

root = Tk()
root.geometry('721x1020+1+1')
# root.geometry('0x0+0+0')
root.title("Highlighter")
canvas = Canvas(root)
canvas.pack()


data = [] # Data in current page
history = [[]] * len(images) # Data across all pages
current_tool = 'highlight'
active_class = None

active = False # Active in a current session
holding = False # If the highlight tool is held down
page = 0

image = None

print('Initialized')

def update_canvas():
    canvas.delete('all')

    for item in data:
        tools[item["type"]]["class"].render(canvas, item["info"])
        
    canvas.create_image(0,0, anchor=NW, image=image) # Page image

    session.change_data(page, data)

def initialize_tool(reference):
    global canvas
    return reference(canvas, update_canvas)

def on_tool_change(new_tool):
    global current_tool
    global active_class

    if new_tool == None:
        current_tool = None
        active_class = None
    else:
        print(f'Changed tool from {current_tool} to {new_tool}')
        current_tool = new_tool
        active_class = initialize_tool(tools[new_tool]["class"])

def log_history():
    for i in range(len(history)):
        print(f'Page {i + 1}: {log_data(history[i])}')


def get_tool_layers():
    print(list(tools.items()))

    for thing in list(tools.items()):
        print(thing[1])
    behind = list(map(lambda e: e[0], filter(lambda e: e[1]["export_layer"] == "behind", list(tools.items()))))
    above = list(map(lambda e: e[0], filter(lambda e: e[1]["export_layer"] == "above", list(tools.items()))))

    return [behind, above]

def export():
    doc = fitz.open()

    for i in range(len(images)):
        image = processor.get_image(i)

        (height, width, _) = image.shape

        page = doc.new_page(-1,
                            width = width,
                            height = height)
        

        behind_tools, above_tools = get_tool_layers()

        behind = list(filter(lambda e: e["type"] in behind_tools, history[i]))
        above = list(filter(lambda e: e["type"] in above_tools, history[i]))

        for cluster in behind:
            tools[cluster["type"]]["class"].export_render(fitz, page, image, cluster["info"])

        image_rect = fitz.Rect(0, 0, width, height)

        _, buffer = cv.imencode('.png', image)
        byte_array = np.array(buffer).tobytes()
        
        pixmap = fitz.Pixmap(byte_array)

        page.insert_image(image_rect, pixmap=pixmap) 

        for cluster in above:
            tools[cluster["type"]]["class"].export_render(fitz, page, image, cluster["info"])
            


    doc.save('exported.pdf')
    doc.close()

def update_all():
    global canvas
    global highlight
    global image

    canvas.delete('all')

    image = processor.get_image(page)

    print(f'Got first image')

    (height, width, _) = image.shape
    scale = min(721 / width, 1020 / height)

    height *= scale
    width *= scale

    root.title("Highlighter")
    root.configure(width=width, height=height)

    canvas.config(width=width, height=height)

    image = cv.cvtColor(image, cv.COLOR_BGRA2RGBA)
    image = cv.resize(image, (int(width), int(height)), interpolation=cv.INTER_AREA)
    print(f'Resized image')

    image = Image.fromarray(image)
    image = ImageTk.PhotoImage(image=image)

    canvas.create_image(0,0, anchor=NW, image=image)  

    print(f'Created image')


def motion(event):
    if not active: return
    if not holding: return

    global data

    active_class.on_move(event.x, event.y, data, right=(event.state == 1024))

def on_press(event):
    global holding
    if not active: return
    # if event.num == 3: return

    holding = True

    active_class.on_press(event.x, event.y, right=(event.num == 3))

def on_release(event):
    if not active: return
    global holding
    global data

    holding = False

    active_class.on_release(event.x, event.y, data=data, right=(event.state == 1024))

    update_canvas()

def on_key(event):
    if not active: return

    global history
    global rects 
    global holding
    global page
    global data

    if event.char not in ['f', 'd']: return


    num = 1 if event.char == 'f' else -1

    if page + num < 0: return

    history[page] = data.copy()

    print(f'Moving to {"next" if num > 0 else "previous"} page ({page} -> {page + num}), current page data:\n{log_data(data)}')

    pages = len(images)
    if page + num >= pages:
        print(f'Page "{page + num}" has reached the limit of "{pages}"')

        history[-1] = data
        data = []    

        export()
        return
    
    page += num
    
    
    holding = False

    data = history[page].copy()
    
    update_all()
    update_canvas()

root.bind("<Button>", on_press)
root.bind("<ButtonRelease>", on_release)
root.bind('<Motion>', motion)
root.bind('<Key>', on_key)

session_window = Toplevel(root)
session_window.configure(bg='#262626')
# 1080 / 2 - 200 / 2
session_window.geometry('1187x600+723+200')
# session_window.geometry('0x0+0+0')
session_window.title("Session Manager")
# session_canvas = Canvas(session_window)
# session_canvas.configure(bg='#262626')
# session_canvas.pack(fill="both", expand=True)

main_frame = Frame(session_window)
main_frame.configure(bg='#262626')
main_frame.pack(fill="both", expand=True)

session_canvas=Canvas(main_frame, bg='#262626')
session_canvas.pack(side=LEFT, fill="both", expand=True)

scroll=Scrollbar(main_frame,orient=VERTICAL, command=session_canvas.yview)
scroll.pack(side=RIGHT,fill=Y)

session_canvas.configure(yscrollcommand=scroll.set)
session_canvas.bind('<Configure>', lambda e: session_canvas.configure(scrollregion=session_canvas.bbox('all')))

second_frame = Frame(session_canvas)
second_frame.configure(bg="#262626")
# second_frame.pack(fill="both", expand=True)

# entry = Entry(session_canvas) 
# session_canvas.create_window((1030, 50), window=entry, anchor='nw')

session_canvas.create_window((0, 0), window=second_frame, anchor='nw')

def new_session():
    global active
    global active_class
    global session

    session_window.destroy()

    session = Session(pdf)

    # initialize_sessions()

    active = True
    active_class = initialize_tool(tools[current_tool]["class"])

    update_all()
    
def fill_frame():
    global enter_session
    global delete_session

    empty_frame = Frame(second_frame, bg="#262626", height=0, width=1187)
    empty_frame.grid(row=0, column=0)

    label = Label(second_frame, text="Session Manager", font=("Arial", 30), bg='#262626', fg='white')
    label.grid(row=1, column=0)

    button = Button(second_frame, text ="New session", width=45, font=("Arial", 25), command=new_session)
    button.grid(row=2, column=0)

    # sessions = get_sessions()
    sessions = Session.get()
    for i in range(len(sessions)):
        frame = Frame(second_frame, highlightbackground="white", highlightthickness=2, bg="#262626", width=1100, height=80)
        frame.grid(row=4 + i, column=0, pady=10)

        label = Label(frame, text=f'Session {sessions[i]["id"]} - {sessions[i]["file"]}', font=("Arial", 20), bg='#262626', fg='white')
        label.place(relx=0, rely=0.5, anchor='w', x=10)

        button = Button(frame, text="Enter session", command=lambda i=i: enter_session(i), font=("Arial", 15), width=13)
        button.place(relx=1, rely=0.5, anchor='e', x=-10)

        button = Button(frame, text="Delete session", command=lambda i=i: delete_session(i), font=("Arial", 15), width=13)
        button.place(relx=1, rely=0.5, anchor='e', x=-180)

def enter_session(number):
    global active
    global active_class
    global session
    global history
    global data

    session_window.destroy()

    sessions = Session.get()
    session = Session(_id=sessions[number]["id"])

    active = True
    active_class = initialize_tool(tools[current_tool]["class"])

    history = sessions[number]["data"]
    data = history[0]
    
    update_all()
    update_canvas()

def delete_session(index):
    Session.delete(index)

    for widget in second_frame.winfo_children():
        widget.destroy()
    second_frame.pack_forget()
    
    fill_frame()

fill_frame()



toolbar = Toplevel(root)
# toolbar.geometry(f'36x{len(list(tools.keys())) * 32 + 4}+0+0')
toolbar.geometry(f'200x200+0+0')
toolbar.title("Toolbar")

buttons = []


tool_images = []

for i in range(len(list(tools.keys()))):
    icon = list(tools.values())[i]["icon"]
    tool_images.append(PhotoImage(file=icon))

for i in range(len(list(tools.keys()))):
    icon = list(tools.values())[i]["icon"]
    white_icon = f'.{icon.split(".")[1]}-white.png'
    tool_images.append(PhotoImage(file=white_icon))

def button_click(button, index):
    global current_tool

    tool_name = list(tools.keys())[index]

    # Reset the color of all buttons
    for i in range(len(buttons)):
        # white_icon = tool_images[index + 4]
        icon = tool_images[i]
        buttons[i].config(bg="white", fg="black", image=icon)

    # Change the color of the clicked button
    if current_tool != tool_name:
        white_icon = tool_images[index + 4]
        button.config(bg="black", fg="white", image=white_icon)
        current_tool = tool_name
    else:
        current_tool = None
    
    on_tool_change(current_tool)



for i in range(len(tools.items())):
    icon = tool_images[i]

    image = Button(toolbar, image=icon, borderwidth=1, relief="solid")
    image.image = icon  # <== this is were we anchor the img object
    image.configure(image=icon, command=lambda btn=image, i=i: button_click(btn, i))
    image.place(anchor='nw', height=32, width=32, y=i*32)

    if current_tool == list(tools.keys())[i]:
        white_icon = tool_images[i + 4]
        image.config(bg="black", fg="white", image=white_icon)

    buttons.append(image)

root.mainloop()

