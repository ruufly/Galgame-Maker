import tkinter
import time
import random
import hashlib
import pickle
import uuid
import os, sys, zipfile
from tkinter import messagebox, filedialog, ttk
from PIL import Image, ImageTk
import pyglet
import windnd
import yaml
import shutil

# for i in ((lambda num: (print(i if i else '', end=' ' if i else '') for i in (lambda r: (print(i) for i in (lambda r, k: ([i for i in range(r, k)]))(1,r+1)))(num)))(10)): print(i if i else '', end=(lambda q: '\n' + str(ord(q)))('!') if i else (lambda q: q + str(ord(q)))(chr(ord('!'+i)) if i else '!'))

isopenafile = False
thisfilefilefile = []

pyglet.font.add_file("fonts\\SourceHanSansSC.otf")

def get_yaml_data(yaml_file):
    file = open(yaml_file, 'r', encoding="utf-8")
    file_data = file.read()
    file.close()
    data = yaml.load(file_data,Loader=yaml.FullLoader)
    return data

languagesetup = get_yaml_data("lang\\languages.yml")
settings = get_yaml_data("settings.yml")
mainlang = get_yaml_data("lang\\" + languagesetup["languages"][settings["language"]]["file"])
defaultlang = get_yaml_data("lang\\" + languagesetup["languages"][settings["default_language"]]["file"])
stylesetting = get_yaml_data("style\\styles.yml")
thethemeset = get_yaml_data("style\\" + stylesetting["styles"][settings["theme"]]["file"])
defthemeset = get_yaml_data("style\\" + stylesetting["styles"][settings["default_theme"]]["file"])


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

def make_ngal(galfile,galname):
    path = '.\\%s' % galname
    zipName = galfile
     
    f = zipfile.ZipFile(zipName, 'w', zipfile.ZIP_DEFLATED)
    os.chdir("nowfiletmp")
    for dirpath, dirnames, filenames in os.walk( path ):
        for filename in filenames:
            print(filename)
            f.write(os.path.join(dirpath,filename))
    f.close()
    os.chdir("..\\")
    shutil.rmtree("nowfiletmp\\%s" % galname)

def open_ngal(galfile):
    path = '.\\'
    f = zipfile.ZipFile(galfile, 'r')
    os.chdir("nowfiletmp")
    for file in f.namelist():
        f.extract(file, path)
    os.chdir("..\\")

# def firststart(code):
#     with open("data\\patch.dat","wb") as file:
#         pickle.dump({"MAC":hashlib.sha256(("%s ヾ(≧▽≦*)o" % (":".join([uuid.UUID(int = uuid.getnode()).hex[-12:][e:e+2] for e in range(0,11,2)]))).encode('utf-8')).hexdigest(),"CODE":hashlib.sha256(("%s []~(￣▽￣)~*" % (code)).encode('utf-8')).hexdigest()},file)


def getlang(code):
    try:
        return mainlang[code]
    except KeyError:
        try:
            return defaultlang[code]
        except KeyError:
            messagebox.showerror("Galgame Maker",getlang("cannotstart") % (languagesetup["errorfield"] % code))
            exit()


root = tkinter.Tk()
root.title("Galgame Maker")
root.iconbitmap("data\\logo.dat")
root.state("zoomed")
scx, scy = root.winfo_screenwidth(), root.winfo_screenheight()
wdx, wdy = root.winfo_width(), root.winfo_height()
# print(scx,scy,wdx,wdy)
root.minsize(wdx,wdy)

_262626 = ImageTk.PhotoImage(Image.open('data\\262626.dat'))


menu = tkinter.Menu(root)

filesubmenu = tkinter.Menu(menu, tearoff=0)
newfilesubmenu = tkinter.Menu(menu,tearoff=0)
newfilesubmenu.add_command(label=getlang("newfile_empty"),accelerator="Ctrl+N",command=lambda: newfilewindow(False))
newfilesubmenu.add_command(label=getlang("newfile_template"),accelerator="Ctrl+Shift+N",command=lambda: newfiletemwindow(False))
filesubmenu.add_cascade(label=getlang("newfile"),menu=newfilesubmenu)
filesubmenu.add_command(label=getlang("open"),accelerator="Ctrl+O",command=lambda: openfilewindow(False))
filesubmenu.add_command(label=getlang("save"),accelerator="Ctrl+S",state='disable')
filesubmenu.add_command(label=getlang("saveas"),accelerator="Ctrl+Shift+S",state='disable')
thisfilesubmenu = tkinter.Menu(menu,tearoff=0)

with open("data\\timefiles.dat","rb") as f:
    thisfilefilefile = pickle.load(f)[:10]

def deleteallfilenow(*args):
    global thisfilefilefile
    for i in thisfilefilefile:
        thisfilesubmenu.delete(i["position"])
    thisfilefilefile = []
    f = open("data\\timefiles.dat","wb")
    pickle.dump(thisfilefilefile,f)
    f.close()

for i in thisfilefilefile:
    thisfilesubmenu.add_command(label=i["position"])

thisfilesubmenu.add_separator()
thisfilesubmenu.add_command(label=getlang("deletelist"),command=deleteallfilenow)

# thisfilesubmenu.delete("清除文件列表")

filesubmenu.add_cascade(label=getlang("filelist"),menu=thisfilesubmenu)
filesubmenu.add_separator()
filesubmenu.add_command(label=getlang("quit"),accelerator="Ctrl+Q")
menu.add_cascade(label=getlang("file"),menu=filesubmenu)

editsubmenu = tkinter.Menu(menu, tearoff=0)
editsubmenu.add_command(label=getlang("undo"),accelerator="Ctrl+Z")
editsubmenu.add_command(label=getlang("redo"),accelerator="Ctrl+Shift+Z")
editsubmenu.add_command(label=getlang("copy"),accelerator="Ctrl+C")
editsubmenu.add_command(label=getlang("cut"),accelerator="Ctrl+X")
editsubmenu.add_command(label=getlang("paste"),accelerator="Ctrl+V")
editsubmenu.add_separator()
editsubmenu.add_command(label=getlang("file_setting"),state='disable')
editsubmenu.add_command(label=getlang("preferences"),accelerator="Ctrl+,")
menu.add_cascade(label=getlang("edit"),menu=editsubmenu)

worksubmenu = tkinter.Menu(menu, tearoff=0)
worksubmenu.add_command(label=getlang("material"))
worksubmenu.add_command(label=getlang("style"))
worksubmenu.add_command(label=getlang("logic"))
worksubmenu.add_command(label=getlang("compile"))
worksubmenu.add_separator()
worksubmenu.add_command(label=getlang("workspace_setting"),accelerator="Alt+Ctrl+,")
menu.add_cascade(label=getlang("window"),menu=worksubmenu)

plugsubmenu = tkinter.Menu(menu, tearoff=0)
plugsubmenus = tkinter.Menu(menu,tearoff=0)
plugsubmenus.add_command(label="Live2d")
plugsubmenus.add_command(label="Video")
plugsubmenus.add_command(label="Languages")
plugsubmenus.add_command(label="Plug-in")
plugsubmenus.add_separator()
plugsubmenu.add_cascade(label=getlang("plugin_open"), menu=plugsubmenus)
plugsubmenu.add_separator()
plugsubmenu.add_command(label=getlang("plugin_manage"),accelerator="Ctrl+Shift+,")
plugsubmenu.add_command(label=getlang("plugin_about"))
menu.add_cascade(label=getlang("plugin"),menu=plugsubmenu)

helpsubmenu = tkinter.Menu(menu, tearoff=0)
helpsubmenu.add_command(label=getlang("about_about"))
helpsubmenu.add_command(label=getlang("helpdoc"))
menu.add_cascade(label=getlang("help"),menu=helpsubmenu)

root.config(menu=menu)



menuframe = tkinter.Label(root,bg=themeset["main_window"]["bg_menu"],width=wdx,height=50,highlightbackground=themeset["main_window"]["highlightbackground"],highlightcolor=themeset["main_window"]["highlightcolor"],highlightthickness=1,image=_262626)


materialgoinlabel = tkinter.Label(menuframe,bg=themeset["main_window"]["bg_menu"],font=("Source Han Sans SC",12),text=getlang("material"),fg=themeset["main_window"]["n_select_fg"],cursor="hand2")
materialgoinlabel.place(x=wdx//2-100,y=8)
stylegoinlabel = tkinter.Label(menuframe,bg=themeset["main_window"]["bg_menu"],font=("Source Han Sans SC",12),text=getlang("style"),fg=themeset["main_window"]["n_select_fg"],cursor="hand2")
stylegoinlabel.place(x=wdx//2-50,y=8)
logicgoinlabel = tkinter.Label(menuframe,bg=themeset["main_window"]["bg_menu"],font=("Source Han Sans SC",12),text=getlang("logic"),fg=themeset["main_window"]["n_select_fg"],cursor="hand2")
logicgoinlabel.place(x=wdx//2,y=8)
compilegoinlabel = tkinter.Label(menuframe,bg=themeset["main_window"]["bg_menu"],font=("Source Han Sans SC",12),text=getlang("compile"),fg=themeset["main_window"]["n_select_fg"],cursor="hand2")
compilegoinlabel.place(x=wdx//2+50,y=8)

menuframe.place(x=0,y=0)

mainframe = tkinter.Frame(root,bg=themeset["main_window"]["bg_main"],width=wdx,height=wdy-20-70,highlightbackground=themeset["main_window"]["highlightbackground"],highlightcolor=themeset["main_window"]["highlightcolor"],highlightthickness=1)
mainframe.place(x=0,y=50)

downframe = tkinter.Frame(root,bg=themeset["main_window"]["bg_state"],width=wdx,height=20,highlightbackground=themeset["main_window"]["highlightbackground"],highlightcolor=themeset["main_window"]["highlightcolor"],highlightthickness=1)
downframe.place(x=0,y=wdy-20-20)

materialframe = tkinter.Frame(mainframe,bg=themeset["main_window"]["bg_main"],highlightbackground=themeset["main_window"]["highlightbackground"],highlightcolor=themeset["main_window"]["highlightcolor"],highlightthickness=1)
styleframe = tkinter.Frame(mainframe,bg=themeset["main_window"]["bg_main"],highlightbackground=themeset["main_window"]["highlightbackground"],highlightcolor=themeset["main_window"]["highlightcolor"],highlightthickness=1)
logicframe = tkinter.Frame(mainframe,bg=themeset["main_window"]["bg_main"],highlightbackground=themeset["main_window"]["highlightbackground"],highlightcolor=themeset["main_window"]["highlightcolor"],highlightthickness=1)
compileframe = tkinter.Frame(mainframe,bg=themeset["main_window"]["bg_main"],highlightbackground=themeset["main_window"]["highlightbackground"],highlightcolor=themeset["main_window"]["highlightcolor"],highlightthickness=1)

def gotomaterial():
    materialframe.place(x=0,y=0,relx=1,rely=1)
    styleframe.place_forget()
    logicframe.place_forget()
    compileframe.place_forget()
    materialgoinlabel.configure(fg=themeset["main_window"]["select_fg"])
    stylegoinlabel.configure(fg=themeset["main_window"]["n_select_fg"])
    logicgoinlabel.configure(fg=themeset["main_window"]["n_select_fg"])
    compilegoinlabel.configure(fg=themeset["main_window"]["n_select_fg"])

def gotostyle():
    styleframe.place(x=0,y=0,relx=1,rely=1)
    materialframe.place_forget()
    logicframe.place_forget()
    compileframe.place_forget()
    materialgoinlabel.configure(fg=themeset["main_window"]["n_select_fg"])
    stylegoinlabel.configure(fg=themeset["main_window"]["select_fg"])
    logicgoinlabel.configure(fg=themeset["main_window"]["n_select_fg"])
    compilegoinlabel.configure(fg=themeset["main_window"]["n_select_fg"])


def gotologic():
    logicframe.place(x=0,y=0,relx=1,rely=1)
    styleframe.place_forget()
    materialframe.place_forget()
    compileframe.place_forget()
    materialgoinlabel.configure(fg=themeset["main_window"]["n_select_fg"])
    stylegoinlabel.configure(fg=themeset["main_window"]["n_select_fg"])
    logicgoinlabel.configure(fg=themeset["main_window"]["select_fg"])
    compilegoinlabel.configure(fg=themeset["main_window"]["n_select_fg"])


def gotocompile():
    compileframe.place(x=0,y=0,relx=1,rely=1)
    styleframe.place_forget()
    logicframe.place_forget()
    materialframe.place_forget()
    materialgoinlabel.configure(fg=themeset["main_window"]["n_select_fg"])
    stylegoinlabel.configure(fg=themeset["main_window"]["n_select_fg"])
    logicgoinlabel.configure(fg=themeset["main_window"]["n_select_fg"])
    compilegoinlabel.configure(fg=themeset["main_window"]["select_fg"])


materialgoinlabel.bind("<Button-1>",lambda event: gotomaterial())
stylegoinlabel.bind("<Button-1>",lambda event: gotostyle())
logicgoinlabel.bind("<Button-1>",lambda event: gotologic())
compilegoinlabel.bind("<Button-1>",lambda event: gotocompile())


def openfile(filename):
    global isopenafile
    global data
    data = {}
    with open(filename,"rb") as f:
        try:
            data = pickle.load(f)
        except Exception:
            try:
                filestr = filestr = os.path.splitext(filename)[0].split("/")[-1].replace(os.path.split(filename)[1],"")
                open_ngal(filename)
                with open("nowfiletmp\\%s\\%s.ngalmain" % (filestr,filestr),"rb") as rf:
                    try:
                        data = pickle.load(rf)
                    except Exception:
                        messagebox.showerror("Galgame Maker",getlang("unrecognized_type"))
            except zipfile.BadZipFile:
                messagebox.showerror("Galgame Maker",getlang("unrecognized_type"))
    if data != {}:
        filesubmenu.entryconfig(getlang("save"),state='normal')
        filesubmenu.entryconfig(getlang("saveas"),state='normal')
        filesubmenu.entryconfig(getlang("file_setting"),state='normal')
        isopenafile = False
        print(data)


def newfilewindow(window):
    pass

def newfiletemwindow(window):
    pass

def openfilewindow(window):
    filepath = ''
    if window:
        window.withdraw()
    if not isopenafile:
        filepath = filedialog.askopenfilename(title=getlang("open_file"),filetypes=[("Galgame Project","*.ngal"),("Galgame Project Index File","*.ngalmain"),("Galgame Plug-in","*.ngpl"),("All files","*")])
    else:
        isclose = messagebox.askyesnocancel("Galgame Maker",getlang("saveornot"))
        if isclose == True:
            filesave()
            filepath = filedialog.askopenfilename(title=getlang("open_file"),filetypes=[("Galgame Project","*.ngal"),("Galgame Project Index File","*.ngalmain"),("Galgame Plug-in","*.ngpl"),("All files","*")])
        elif isclose == False:
            filepath = filedialog.askopenfilename(title=getlang("open_file"),filetypes=[("Galgame Project","*.ngal"),("Galgame Project Index File","*.ngalmain"),("Galgame Plug-in","*.ngpl"),("All files","*")])
        else:
            pass
    if filepath == '':
        if window:
            window.deiconify()
        return
    else:
        openfile(filepath)


# def dragged_files(files):
#     msg = '\n'.join((item.decode('gbk') for item in files))
#     showinfo('您拖放的文件',msg)
# windnd.hook_dropfiles(root,func=dragged_files)

# 161616
# 313131
# 1d1d1d
# ,cursor="hand2"

welcome = tkinter.Toplevel()
welcome.title(getlang("welcome"))
welcome.iconbitmap("data\\logo.dat")
welcome.geometry("800x600+%d+%d" % (scx//2-800//2,scy//2-600//2-80))
welcome.resizable(0,0)

welcomelabelphoto = ImageTk.PhotoImage(Image.open('data\\newfile.dat'))
welcomelabel = tkinter.Label(welcome,image=welcomelabelphoto)
welcomelabel.place(x=-2,y=-2)

welcomelabel1 = tkinter.Label(welcome,text=getlang("newfile_file"),font=("Source Han Sans SC",12),fg=themeset["welcome_window"]["text_fg"],bg="#262626")
welcomelabel1.place(x=60,y=190)

welcomelabel1 = tkinter.Label(welcome,text=getlang("filelist"),font=("Source Han Sans SC",12),fg=themeset["welcome_window"]["text_fg"],bg="#1f1f1f")
welcomelabel1.place(x=520,y=190)

newlabel1 = tkinter.Label(welcome,bg="#262626",image=_262626)
newlabel2 = tkinter.Label(welcome,bg="#262626",image=_262626)
newlabel3 = tkinter.Label(welcome,bg="#262626",image=_262626)

cess__ = {newlabel1:[getlang("newfile_empty")],
          newlabel2:[getlang("newfile_template")],
          newlabel3:[getlang("open_file")]}

def reinitc__(bg,code):
    newlabel11 = tkinter.Label(code,bg=bg,font=("Source Han Sans SC",10),text=cess__[code][0],fg=themeset["welcome_window"]["list_text_fg"])
    newlabel11.place(x=5,y=5)

newlabel1.place(x=184,y=259)
newlabel2.place(x=184,y=353)
newlabel3.place(x=184,y=447)

def newenter(code):
    code.configure(bg="#383838")
    reinitc__("#383838",code)

def newleave(code):
    code.configure(bg="#262626")
    reinitc__("#262626",code)

newlabel1.bind("<Enter>",lambda event: newenter(newlabel1))
newlabel1.bind("<Leave>",lambda event: newleave(newlabel1))
newlabel2.bind("<Enter>",lambda event: newenter(newlabel2))
newlabel2.bind("<Leave>",lambda event: newleave(newlabel2))
newlabel3.bind("<Enter>",lambda event: newenter(newlabel3))
newlabel3.bind("<Leave>",lambda event: newleave(newlabel3))

newlabel1.bind("<Button-1>",lambda event: newfilewindow(welcome))
newlabel2.bind("<Button-1>",lambda event: newfiletemwindow(welcome))
newlabel3.bind("<Button-1>",lambda event: openfilewindow(welcome))

reinitc__("#262626",newlabel1)
reinitc__("#262626",newlabel2)
reinitc__("#262626",newlabel3)

k = 0
for i in thisfilefilefile:
    qwertyuiop = (getlang("at") % (i["filename"],i["position"]))
    thisfilefilefilelabellabel = tkinter.Label(welcome,bg="#1f1f1f",font=("Source Han Sans SC",8),text=qwertyuiop if len(qwertyuiop) <= 50 else qwertyuiop[:47] + "...",fg=themeset["welcome_window"]["list_text_fg"],width=50,anchor="w",cursor="hand2")
    thisfilefilefilelabellabel.place(x=505,y=261+k*22)
    k += 1

# 505 261

welcome.update()

def filesave():
    pass

def exit_win(*args):
    if isopenafile:
        isclose = messagebox.askyesnocancel("Galgame Maker",getlang("saveornot"))
        if isclose == True:
            filesave()
            exit()
        elif isclose == False:
            exit()
        else:
            pass
    else:
        exit()

# filesubmenu.entryconfig("保存",state='normal')
root.protocol("WM_DELETE_WINDOW",exit_win)
#47 261
#184 261

# f = open("data\\timefiles.dat","wb")
# pickle.dump([{"filename":"test.ngal","position":"test.ngal","time":1672910958.9598482},{"filename":"nya.ngal","position":"nya.ngal","time":1672901958.9598482}],f)
# f.close()

# PROGRAM:
#
# for i in ((lambda num: (print(i if i else '', end=' ' if i else '') for i in (lambda r: (print(i) for i in (lambda r, k: ([i for i in range(r, k)]))(1,r+1)))(num)))(10)): print(i if i else '', end=(lambda q: '\n' + str(ord(q)))('!') if i else (lambda q: q + str(ord(q)))(chr(ord('!'+i)) if i else '!'))
#
# OUTPUT:
#
# 1
# !332
# !333
# !334
# !335
# !336
# !337
# !338
# !339
# !3310
# !33

gotomaterial()

root.mainloop()
