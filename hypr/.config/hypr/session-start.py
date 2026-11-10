#!/usr/bin/env python3
"""Idempotent restoration of this PC's original session startup."""
import os, pathlib, subprocess, json, time, fcntl
h=pathlib.Path.home();ipc=['python3',str(h/'.config/hypr/compositor-ipc.py')];state=h/'.local/state/hyprland-recovery';state.mkdir(parents=True,exist_ok=True)
lock=open(state/'session-start.lock','w')
try: fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
except BlockingIOError: raise SystemExit(0)
log=open(state/'session-start.log','a',buffering=1)
def run(args):
 r=subprocess.run(args,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True);log.write(str(args)+'\n'+r.stdout+'\n');return r
subprocess.run(['dbus-update-activation-environment','--systemd','WAYLAND_DISPLAY','XDG_CURRENT_DESKTOP','HYPRLAND_INSTANCE_SIGNATURE','GDK_WAYLAND_DISABLE'])
subprocess.run(['systemctl','--user','import-environment','WAYLAND_DISPLAY','XDG_CURRENT_DESKTOP','HYPRLAND_INSTANCE_SIGNATURE','GDK_WAYLAND_DISABLE'])
run(['systemctl','--user','start','hyprland-session.target','hyprsunset-controller.service','media-autopause.service'])
run(['python3',str(h/'.config/hypr/notification-start.py')])
def spawn(cmd):
 log.write('Starting '+cmd+'\n');subprocess.Popen(cmd,shell=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,start_new_session=True)
def alive(name):return subprocess.run(['pgrep','-u',str(os.getuid()),'-x',name],stdout=subprocess.DEVNULL).returncode==0
for process,cmd in [('playerctld','playerctld daemon'),('awww-daemon','awww-daemon'),('waybar','waybar'),('hypridle','hypridle')]:
 if not alive(process):spawn(cmd)
procs=subprocess.check_output(['ps','-u',str(os.getuid()),'-o','args='],text=True)
if 'wl-paste --type text --watch cliphist store' not in procs:spawn('wl-paste --type text --watch cliphist store')
if 'wl-paste --type image --watch cliphist store' not in procs:spawn('wl-paste --type image --watch cliphist store')
# Restore exactly the last wallpaper; do not advance the wallpaper cycle or recolour.
p=h/'.last_wallpaper'
try: wall=p.read_text().strip() if p.exists() else json.loads((h/'.cache/wal/colors.json').read_text())['wallpaper']
except (OSError, ValueError, KeyError): wall=''
if wall and pathlib.Path(wall).is_file():
 for _ in range(30):
  r=subprocess.run(['awww','query'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
  if r.returncode==0:break
  time.sleep(.2)
 run(['awww','img',wall,'--transition-type','none'])
run(['xrdb','-merge',str(h/'.Xresources')])
run(['gsettings','set','org.gnome.desktop.interface','color-scheme','prefer-dark'])
clients=json.loads(subprocess.check_output(['hyprctl','clients','-j'],text=True))
classes={w['class'].lower() for w in clients}
for cls,cmd in [('discord','discord'),('org.telegram.desktop','Telegram'),('zen','zen-browser'),('obsidian','obsidian'),('yandexmusic','yandexmusic')]:
 if cls not in classes and not (cls=='yandexmusic' and 'yandex-music' in classes) and not (cls=='obsidian' and any('obsidian' in c for c in classes)):
  if cls=='org.telegram.desktop':run(ipc+['exec','--workspace','1 silent','Telegram'])
  elif cls=='obsidian':run(ipc+['exec','--workspace','7 silent','obsidian'])
  else:spawn(cmd)
if not any('openweb.nexuszone.org' in w.get('class','') or 'openweb.nexuszone.org' in w.get('initialTitle','') or 'openweb.nexuszone.org' in w.get('title','') for w in clients):
 run(ipc+['exec','--workspace','6 silent','/usr/bin/chromium --new-window --app=https://openweb.nexuszone.org'])
