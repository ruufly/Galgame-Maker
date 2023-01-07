import tkinter
from tkinter import messagebox
import time
import random
from lib.PIL import Image, ImageTk
import lib.yaml as yaml

start = tkinter.Tk()
start.title("GalMaker")
start.overrideredirect(True)
start.geometry("800x350+%d+%d" % (start.winfo_screenwidth() // 2 - 400,start.winfo_screenheight() // 2 - 220))
start.wm_attributes("-transparentcolor", "#361599")

def get_yaml_data(yaml_file):
    file = open(yaml_file, 'r', encoding="utf-8")
    file_data = file.read()
    file.close()
    data = yaml.load(file_data,Loader=yaml.FullLoader)
    return data

try:
    languagesetup = get_yaml_data("lang\\languages.yaml")
    mainlang = get_yaml_data("lang\\" + languagesetup["languages"][languagesetup["enable"]]["file"])
    defaultlang = get_yaml_data("lang\\" + languagesetup["languages"][languagesetup["default"]]["file"])
except FileNotFoundError:
    messagebox.showerror("Galgame Maker","Cannot Load Languages!")
    exit()

def getlang(code):
    try:
        return mainlang[code]
    except KeyError:
        try:
            return defaultlang[code]
        except KeyError:
            messagebox.showerror("Galgame Maker",getlang("cannotstart") % (languagesetup["errorfield"] % code))
            exit()

files1 = ["data\\start1.dat","data\\start2.dat","data\\start3.dat","data\\logo.dat"]
files2 = ["data\\262626.dat","data\\newfile.dat","data\\patch.dat","data\\timefiles.dat",
          "fonts\\SourceHanSansSC.otf","fonts\\Ubuntu-R.ttf","nowfiletmp\\nowfiledata.dat",
          "lang\\languages.yaml","lang\\" + languagesetup["languages"][languagesetup["enable"]]["file"],"lang\\" + languagesetup["languages"][languagesetup["default"]]["file"]]


for i in files1:
    try:
        f = open(i,"r")
    except FileNotFoundError:
        messagebox.showerror("Galgame Maker",getlang("cannotstart") % i)
        exit()

start.iconbitmap("data\\logo.dat")

startphoto1 = ImageTk.PhotoImage(Image.open('data\\start1.dat'))
startphoto2 = ImageTk.PhotoImage(Image.open('data\\start2.dat'))
startphoto3 = ImageTk.PhotoImage(Image.open('data\\start3.dat'))

startlabel1 = tkinter.Label(start,image=startphoto1,width=800,height=350)
startlabel2 = tkinter.Label(start,image=startphoto2,width=800,height=350)
startlabel3 = tkinter.Label(start,image=startphoto3,width=800,height=350)
start.update()
startlabel1.place(x=-2,y=-2)
start.update()
time.sleep(random.uniform(1.5,2.5))

startlabel2.place(x=-2,y=-2)
start.update()
time.sleep(random.uniform(1.5,2.5))

startlabel3.place(x=-2,y=-2)
start.update()

for i in files2:
    try:
        f = open(i,"r")
    except FileNotFoundError:
        messagebox.showerror("Galgame Maker",getlang("cannotstart") % i)
        exit()

canvas = tkinter.Canvas(start, width=456, height=5, bg="#67A6E0")
canvas.place(x=291, y=242)
fill_line = canvas.create_rectangle(1.5, 1.5, 0, 23, width=0, fill="#DB9AE0")
x = 100
n = 465 / x
for i in range(x):
    n = n + 465 / x
    canvas.coords(fill_line, (0, 0, n, 60))
    start.update()
    time.sleep(random.uniform(0.01,0.05))
start.destroy()

import mainprogram
