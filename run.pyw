# import mainprogram
import tkinter
from tkinter import messagebox
import time
import random
from PIL import Image, ImageTk
import yaml as yaml

start = tkinter.Tk()
start.title("GalMaker")
start.overrideredirect(True)
start.geometry("800x350+%d+%d" % (start.winfo_screenwidth() //
               2 - 400, start.winfo_screenheight() // 2 - 220))
start.wm_attributes("-transparentcolor", "#361599")

start.attributes('-alpha', 0)
# start.attributes("-topmost",1)


def get_yaml_data(yaml_file):
    file = open(yaml_file, 'r', encoding="utf-8")
    file_data = file.read()
    file.close()
    data = yaml.load(file_data, Loader=yaml.FullLoader)
    return data


try:
    settings = get_yaml_data("settings.yml")
    stylesetting = get_yaml_data("style\\styles.yml")
    languagesetup = get_yaml_data("lang\\languages.yml")
    mainlang = get_yaml_data(
        "lang\\" + languagesetup["languages"][settings["language"]]["file"])
    defaultlang = get_yaml_data(
        "lang\\" + languagesetup["languages"][settings["default_language"]]["file"])
except FileNotFoundError:
    messagebox.showerror("Galgame Maker", "Cannot Load Languages!")
    exit()


def getlang(code):
    try:
        return mainlang[code]
    except KeyError:
        try:
            return defaultlang[code]
        except KeyError:
            messagebox.showerror("Galgame Maker", getlang(
                "cannotstart") % (languagesetup["errorfield"] % code))
            exit()


files1 = ["data\\start1.dat", "data\\start2.dat",
          "data\\start3.dat", "data\\logo.dat"]
files2 = ["data\\262626.dat", "data\\newfile.dat", "data\\patch.dat", "data\\timefiles.dat",
          "fonts\\SourceHanSansSC.otf", "fonts\\Ubuntu-R.ttf", "nowfiletmp\\nowfiledata.dat",
          "lang\\languages.yml", "lang\\" + languagesetup["languages"][settings["language"]]["file"], "lang\\" + languagesetup["languages"][settings["default_language"]]["file"],
          "settings.yml", "style\\styles.yml", "style\\" + stylesetting["styles"][settings["theme"]]["file"]]


for i in files1:
    try:
        f = open(i, "r")
    except FileNotFoundError:
        messagebox.showerror("Galgame Maker", getlang("cannotstart") % i)
        exit()

start.iconbitmap("data\\logo.dat")

startphoto1 = ImageTk.PhotoImage(Image.open('data\\start1.dat'))
startphoto2 = ImageTk.PhotoImage(Image.open('data\\start2.dat'))
startphoto3 = ImageTk.PhotoImage(Image.open('data\\start3.dat'))

startlabel1 = tkinter.Label(start, image=startphoto1, width=800, height=350)
startlabel2 = tkinter.Label(start, image=startphoto2, width=800, height=350)
startlabel3 = tkinter.Label(start, image=startphoto3, width=800, height=350)
start.update()
startlabel1.place(x=-2, y=-2)
start.update()
nowalpha = 0
while nowalpha <= 1:
    start.attributes('-alpha', nowalpha)
    nowalpha += 0.04
    time.sleep(0.01)
    start.update()
start.attributes('-alpha', 1)
start.update()
start.after(random.randint(1500, 2500))

startlabel2.place(x=-2, y=-2)
start.update()
start.after(random.randint(1500, 2500))

startlabel3.place(x=-2, y=-2)
start.update()

for i in files2:
    try:
        f = open(i, "r")
    except FileNotFoundError:
        messagebox.showerror("Galgame Maker", getlang("cannotstart") % i)
        exit()

thethemeset = get_yaml_data("style\\" + stylesetting["styles"][settings["theme"]]["file"])
defthemeset = get_yaml_data("style\\" + stylesetting["styles"][settings["default_theme"]]["file"])

# thethemeset["run_loading"] = {'bar_1': 'DB9AE0'}

themeset = {}

def rep(rdic, indic, sdic):
    for i in rdic:
        if type(rdic[i]) == dict:
            indic[i] = {}
            rep(rdic[i],indic[i],sdic[i] if i in sdic else {})
        else:
            if i in sdic:
                indic[i] = sdic[i]
            else:
                indic[i] = rdic[i]

rep(defthemeset,themeset,thethemeset)
# print(themeset)

canvas = tkinter.Canvas(start, width=456, height=5, bg=themeset["run_loading"]["bar_0"])
canvas.place(x=291, y=242)
fill_line = canvas.create_rectangle(1.5, 1.5, 0, 23, width=0, fill=themeset["run_loading"]["bar_1"])
x = 100
n = 465 / x
for i in range(x):
    n = n + 465 / x
    canvas.coords(fill_line, (0, 0, n, 60))
    start.update()
    time.sleep(random.uniform(0.01, 0.02))
start.destroy()

import mainprogram