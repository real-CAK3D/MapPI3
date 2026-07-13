#!/usr/bin/env python3
import base64, fcntl, hashlib, http.server, io, json, math, os, pathlib, random, shutil, socket, sqlite3, struct, subprocess, threading, time, urllib.parse, urllib.request, uuid
APP_DIR = pathlib.Path('/opt/mappi3/app')
STATE = pathlib.Path('/var/lib/mappi3/state.json')
PORT = int(os.environ.get('MAPPI3_PORT','5050'))
SENSE_MODES = ['compass','liquid','weather','fire','flashlight','sos','message','boot','sun','gps','clock','progress','beacon','stars','temp','humidity','pressure','custom','border','magic8','water','snake']
ALLOWED = {'status','restart-web','reboot','shutdown','update-app','gps-sample','toggle-hotspot','connect-home-wifi','sense-mode','calibrate','harden-hotspot','plugin-update','vnc-setup','vnc-disable','weather-refresh','noaa-refresh','online-maintenance','gps-diagnose','field-ai-verify','captive-setup','captive-disable','captive-status','gps-pps-setup','plugin-status','plugin-install','plugin-install-all','plugin-uninstall'}
SENSE_CACHE = {'ok': False, 'mode': 'compass', 'message': 'Sense HAT display loop starting', 'updated': 0, 'joystick': {'seq': 0, 'direction': '', 'pressed': False, 'updated': 0}}
SENSE_LOCK = threading.Lock()
KEY_NAMES = {103:'up',108:'down',105:'left',106:'right',28:'press'}
COMPASS_PATTERNS = {
    'N': [(3,0),(4,0),(3,1),(4,1),(2,2),(5,2),(3,2),(4,2),(3,3),(4,3),(3,4),(4,4),(3,5),(4,5),(3,6),(4,6),(3,7),(4,7)],
    'NE': [(6,0),(7,0),(7,1),(6,1),(5,2),(6,2),(4,3),(5,3),(3,4),(4,4),(2,5),(3,5),(1,6),(2,6),(0,7),(1,7)],
    'E': [(7,3),(7,4),(6,2),(6,5),(5,3),(5,4),(4,3),(4,4),(3,3),(3,4),(2,3),(2,4),(1,3),(1,4),(0,3),(0,4)],
    'SE': [(6,7),(7,7),(7,6),(6,6),(5,5),(6,5),(4,4),(5,4),(3,3),(4,3),(2,2),(3,2),(1,1),(2,1),(0,0),(1,0)],
    'S': [(3,7),(4,7),(3,6),(4,6),(2,5),(5,5),(3,5),(4,5),(3,4),(4,4),(3,3),(4,3),(3,2),(4,2),(3,1),(4,1),(3,0),(4,0)],
    'SW': [(0,7),(1,7),(0,6),(1,6),(2,5),(1,5),(3,4),(2,4),(4,3),(3,3),(5,2),(4,2),(6,1),(5,1),(7,0),(6,0)],
    'W': [(0,3),(0,4),(1,2),(1,5),(2,3),(2,4),(3,3),(3,4),(4,3),(4,4),(5,3),(5,4),(6,3),(6,4),(7,3),(7,4)],
    'NW': [(0,0),(1,0),(0,1),(1,1),(2,2),(1,2),(3,3),(2,3),(4,4),(3,4),(5,5),(4,5),(6,6),(5,6),(7,7),(6,7)],
}
SOS_FRAMES = ['...','---','...','HELP','LOST','GPS','SOS']

def sh(cmd, timeout=20):
    try:
        p=subprocess.run(cmd, shell=True, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=timeout)
        return {'ok': p.returncode == 0, 'code': p.returncode, 'output': p.stdout[-4000:]}
    except Exception as e:
        return {'ok': False, 'code': -1, 'output': str(e)}

def read_state():
    try: return json.loads(STATE.read_text())
    except Exception: return {}

def write_state(data):
    STATE.parent.mkdir(parents=True, exist_ok=True)
    STATE.write_text(json.dumps(data, indent=2))

def normalize_mode(mode):
    raw = str(mode or 'compass').strip().lower().replace(' ', '-').replace('_','-')
    aliases = {'custom-message':'message','scroll-message':'message','sunrise':'sun','sunset':'sun','sunrise-sunset':'sun','gps-fix':'gps','weather-now':'weather','flash-light':'flashlight'}
    raw = aliases.get(raw, raw)
    return raw if raw in SENSE_MODES else ('liquid' if raw.startswith('liq') else 'compass')

def gps_device():
    for dev in ('/dev/serial0','/dev/ttyACM0','/dev/ttyUSB0'):
        if pathlib.Path(dev).exists(): return dev
    return None

def gps_json_sample():
    out = sh('timeout 7 gpspipe -w -n 10 2>&1', timeout=10)['output']
    parsed=[]
    for line in out.splitlines():
        try: parsed.append(json.loads(line))
        except Exception: pass
    tpv = next((x for x in parsed if x.get('class') == 'TPV'), {})
    sky = next((x for x in parsed if x.get('class') == 'SKY'), {})
    dev = next((x for x in parsed if x.get('class') == 'DEVICE'), {})
    return {'raw': out[-2000:], 'tpv': tpv, 'sky': sky, 'device': dev}

def gps_sample():
    dev=gps_device()
    if not dev: return {'ok': False, 'device': None, 'output': 'No GPS serial device present at /dev/serial0, /dev/ttyACM0, or /dev/ttyUSB0'}
    sample = gps_json_sample()
    if sample['raw'].strip(): return {'ok': True, **sample, 'device': dev, 'gpsd_device': sample.get('device')}
    raw = sh(f"timeout 5 bash -lc 'stty -F {dev} 9600 -echo -icrnl; cat {dev}'", timeout=8)
    raw['device'] = dev
    return raw

def gps_status():
    dev = gps_device()
    if not dev: return {'ok': False, 'device': None, 'mode': 0, 'message': 'GPS serial device missing'}
    sample = gps_json_sample(); tpv = sample.get('tpv') or {}; sky = sample.get('sky') or {}; device = sample.get('device') or {}
    mode = int(tpv.get('mode') or 0)
    return {'ok': bool(dev), 'device': dev, 'mode': mode, 'fix': mode >= 2, 'lat': tpv.get('lat'), 'lon': tpv.get('lon'), 'alt': tpv.get('altHAE') or tpv.get('altMSL'), 'speed': tpv.get('speed'), 'track': tpv.get('track'), 'satellites': sky.get('uSat') or sky.get('nSat'), 'driver': device.get('driver'), 'bps': device.get('bps'), 'raw': sample.get('raw','')[-600:]}

def wifi_info():
    active = sh("nmcli -t -f NAME,TYPE,DEVICE connection show --active 2>/dev/null || true", timeout=5)['output']
    dev = sh("nmcli -t -f DEVICE,TYPE,STATE device 2>/dev/null || true", timeout=5)['output']
    hotspot_active = 'MapPI3-hotspot' in active
    ssid = ''
    for line in active.splitlines():
        parts=line.split(':')
        if len(parts) >= 3 and parts[1] == 'wifi' and parts[0] != 'MapPI3-hotspot': ssid = parts[0]
    return {'active_connections': active, 'devices': dev, 'hotspot_active': hotspot_active, 'home_wifi_ssid': ssid}

def _cpu_sample():
    try:
        vals=[int(x) for x in pathlib.Path('/proc/stat').read_text().splitlines()[0].split()[1:]]
        idle=vals[3]+(vals[4] if len(vals)>4 else 0); total=sum(vals)
        return idle,total
    except Exception: return 0,0

def system_stats():
    try:
        idle1,total1=_cpu_sample(); time.sleep(0.08); idle2,total2=_cpu_sample()
        dt=max(1,total2-total1); cpu=max(0,min(100, round((1-((idle2-idle1)/dt))*100,1)))
        mem={}
        for line in pathlib.Path('/proc/meminfo').read_text().splitlines():
            k,v=line.split(':',1); mem[k]=int(v.strip().split()[0])
        total=mem.get('MemTotal',1); avail=mem.get('MemAvailable',0); used=total-avail
        disk=shutil.disk_usage('/')
        net={}
        for line in pathlib.Path('/proc/net/dev').read_text().splitlines()[2:]:
            if ':' not in line: continue
            name,rest=line.split(':',1); vals=rest.split(); net[name.strip()]={'rx_bytes':int(vals[0]),'tx_bytes':int(vals[8])}
        load=os.getloadavg() if hasattr(os,'getloadavg') else (0,0,0)
        uptime=float(pathlib.Path('/proc/uptime').read_text().split()[0])
        throttled=sh('vcgencmd get_throttled 2>/dev/null || true', timeout=3)['output'].strip()
        temp_raw=sh("cat /sys/class/thermal/thermal_zone0/temp 2>/dev/null || echo 0", timeout=3)['output'].strip().splitlines()[-1]
        temp_c=round(int(temp_raw)/1000,1) if temp_raw.isdigit() else None
        return {'cpu_percent':cpu,'load1':round(load[0],2),'load5':round(load[1],2),'load15':round(load[2],2),'memory':{'total_mb':round(total/1024),'used_mb':round(used/1024),'available_mb':round(avail/1024),'percent':round((used/total)*100,1)},'disk':{'total_gb':round(disk.total/1e9,1),'used_gb':round(disk.used/1e9,1),'free_gb':round(disk.free/1e9,1),'percent':round((disk.used/disk.total)*100,1)},'temperature_c':temp_c,'temperature_f':round(temp_c*9/5+32,1) if temp_c is not None else None,'uptime_seconds':round(uptime),'network':net,'throttled':throttled,'sampled_at':time.time()}
    except Exception as e:
        return {'error':str(e),'sampled_at':time.time()}

def sense_snapshot():
    with SENSE_LOCK: return dict(SENSE_CACHE)

def set_sense_mode(mode, payload=None):
    payload = payload or {}; mode = normalize_mode(mode)
    st=read_state(); st['sense_mode']=mode; st['sense_mode_updated_at']=time.time()
    if 'message' in payload: st['sense_message'] = str(payload.get('message') or '')[:96]
    if 'brightness' in payload: st['sense_brightness'] = payload.get('brightness')
    if 'brightnessLevel' in payload: st['sense_brightness_level'] = payload.get('brightnessLevel')
    if 'routeProgress' in payload: st['route_progress'] = payload.get('routeProgress')
    if 'routeDistanceMiles' in payload: st['route_distance_miles'] = payload.get('routeDistanceMiles')
    if 'scrollSpeed' in payload: st['sense_scroll_speed'] = payload.get('scrollSpeed')
    if 'senseColor' in payload: st['sense_color'] = str(payload.get('senseColor') or '#00aa55')[:16]
    if 'borderOnly' in payload: st['sense_border_only'] = bool(payload.get('borderOnly'))
    if 'hydrationAlarm' in payload and isinstance(payload.get('hydrationAlarm'), dict): st['hydration_alarm'] = payload.get('hydrationAlarm')
    if 'features' in payload and isinstance(payload.get('features'), dict): st['features'] = payload.get('features')
    write_state(st)
    with SENSE_LOCK:
        SENSE_CACHE['mode'] = mode; SENSE_CACHE['message'] = f'Sense HAT mode set to {mode}'; SENSE_CACHE['updated'] = time.time()
    return {'ok': True, 'sense_mode': mode, 'available_modes': SENSE_MODES, 'sense': sense_snapshot(), 'state': st}

def calibrate(target):
    target = (target or 'all').lower(); st=read_state(); st.setdefault('calibration', {})[target] = {'requested_at': time.time(), 'status': 'requested'}; write_state(st)
    messages = {'compass':'Rotate the whole Pi/Sense HAT slowly in a figure-eight, away from metal/magnets. Compare heading to a real compass before hiking.','sense':'Lay the Sense HAT level for 3 seconds, then tilt forward/back/left/right so roll and pitch move smoothly.','gps':'Take the GPS outside or to a clear window. Wait for mode 2/3 fix and multiple satellites; indoors mode 1 is normal.','all':'Compass: figure-eight away from metal. Sense: level then tilt. GPS: clear sky until mode 2/3 fix.'}
    return {'ok': True, 'target': target, 'message': messages.get(target, messages['all']), 'state': st.get('calibration', {})}

def put_pixels(sense, coords, color=(0,140,30)):
    pixels = [[0,0,0] for _ in range(64)]
    for x,y in coords:
        if 0 <= x < 8 and 0 <= y < 8: pixels[y*8+x] = list(color)
    sense.set_pixels(pixels)

def sense_scroll_speed(st):
    try: return max(0.025, min(0.2, float(st.get('sense_scroll_speed') or 0.055)))
    except Exception: return 0.055

def sense_brightness(st):
    levels=[16,32,56,88,120,160,205,255]
    try:
        level=int(st.get('sense_brightness_level') or 0)
        if 1 <= level <= 8: return levels[level-1]
    except Exception: pass
    try: return max(8, min(255, int(st.get('sense_brightness') or 120)))
    except Exception: return 120

def scale_color(color, brightness):
    factor=max(0.03, min(1.0, float(brightness)/255.0))
    return tuple(max(0, min(255, int(c*factor))) for c in color)

def text_once(sense, text, color=(0,160,60), speed=0.06):
    try: sense.show_message(str(text)[:96], text_colour=list(color), scroll_speed=speed)
    except Exception: pass

def draw_compass(sense, yaw, st=None):
    labels = ['N','NE','E','SE','S','SW','W','NW']; name = labels[int(((float(yaw or 0) + 22.5) % 360) // 45)]
    put_pixels(sense, COMPASS_PATTERNS.get(name, COMPASS_PATTERNS['N']), scale_color((0,120,20), sense_brightness(st or {})))

def draw_liquid(sense, orientation, tick):
    roll = max(-1, min(1, float(orientation.get('roll', 0)) / 45.0)); pitch = max(-1, min(1, float(orientation.get('pitch', 0)) / 45.0))
    pixels = [[0,0,0] for _ in range(64)]
    for i in range(20):
        base_x=(i%5)+1; base_y=(i//5)+2
        x=int(round(max(0,min(7,base_x + roll*(1.4+base_y/5.0)+math.sin((tick+i)/5.0)*0.2))))
        y=int(round(max(0,min(7,base_y + pitch*(1.4+base_x/6.0)+math.cos((tick+i)/6.0)*0.2))))
        pixels[y*8+x]=[0,70,140]
    sense.set_pixels(pixels)

def draw_fire(sense, tick):
    pixels=[]
    for y in range(8):
        for x in range(8):
            heat=max(0, 7-y + random.randint(-2,3) - abs(x-3.5)/2)
            pixels.append([min(180,int(heat*32)), min(90,int(heat*14)), 0])
    sense.set_pixels(pixels)

def draw_flashlight(sense, st):
    b = sense_brightness(st); sense.clear(b,b,b)

def draw_sos(sense, tick):
    frame = SOS_FRAMES[(tick//3) % len(SOS_FRAMES)]
    if frame in ('...','---'):
        color=(180,0,0) if frame=='...' else (180,180,180); sense.clear(*color)
    else: text_once(sense, frame, (180,0,0), 0.045)

def draw_weather(sense, temp, humidity, pressure):
    msg=f'{temp:.0f}F {humidity:.0f}% {pressure:.0f}mb' if pressure else f'{temp:.0f}F {humidity:.0f}%'
    text_once(sense, msg, (0,120,180), 0.055)

def draw_sun(sense, st):
    text_once(sense, st.get('sun_message') or 'SUNRISE / SUNSET CHECK APP', (220,100,0), 0.055)

def draw_gps(sense, gps, st=None):
    mode=int(gps.get('mode') or 0); sats=int(gps.get('satellites') or 0); color=scale_color((180,0,0) if mode<2 else ((180,120,0) if mode==2 else (0,150,0)), sense_brightness(st or {}))
    pixels=[[0,0,0] for _ in range(64)]
    for i in range(min(8,max(0,sats))): pixels[56+i]=list(color)
    for y in range(2,6):
        for x in range(2,6): pixels[y*8+x]=list(color)
    sense.set_pixels(pixels)

def draw_bar(sense, value, color):
    n=max(0,min(64,int(value))); pixels=[[0,0,0] for _ in range(64)]
    for i in range(n): pixels[63-i]=list(color)
    sense.set_pixels(pixels)

def draw_route_progress(sense, st):
    brightness=sense_brightness(st)
    progress=max(0.0, min(1.0, float(st.get('route_progress') or 0)))
    distance=max(0.0, float(st.get('route_distance_miles') or 0))
    complete=max(0, min(63, int(round(progress*63))))
    remaining=scale_color((255,255,255), brightness)
    done=scale_color((255,0,0), brightness)
    finish=scale_color((0,255,0), brightness)
    pixels=[]
    for i in range(64):
        if i == 63:
            pixels.append(list(finish))
        elif i <= complete and progress > 0:
            pixels.append(list(done))
        else:
            pixels.append(list(remaining))
    sense.set_pixels(pixels)
    with SENSE_LOCK:
        SENSE_CACHE['progress_meter']={'progress':progress,'percent':round(progress*100),'distance_miles':distance,'completed_leds':complete+1 if progress > 0 else 0,'finish_led':'green','remaining_leds':'white','completed_leds_color':'red'}

def parse_color(value, default=(0,140,80)):
    try:
        s=str(value or '').strip()
        if s.startswith('#') and len(s)==7: return tuple(int(s[i:i+2],16) for i in (1,3,5))
    except Exception: pass
    return default

def draw_border(sense, color):
    pixels=[[0,0,0] for _ in range(64)]
    for y in range(8):
        for x in range(8):
            if x in (0,7) or y in (0,7): pixels[y*8+x]=list(color)
    sense.set_pixels(pixels)

def draw_water_icon(sense, color=(0,80,220)):
    put_pixels(sense, [(3,0),(4,0),(2,1),(5,1),(2,2),(5,2),(1,3),(6,3),(1,4),(6,4),(2,5),(5,5),(3,6),(4,6),(3,7),(4,7)], color)

def draw_snake_frame(sense, tick, color=(0,220,70)):
    pixels=[[0,0,0] for _ in range(64)]
    path=[(x,1) for x in range(1,7)] + [(6,y) for y in range(2,7)] + [(x,6) for x in range(5,0,-1)] + [(1,y) for y in range(5,1,-1)]
    for i in range(7):
        x,y=path[(tick+i)%len(path)]; pixels[y*8+x]=list(color)
    hx,hy=path[(tick+6)%len(path)]; pixels[hy*8+hx]=[255,255,255]
    sense.set_pixels(pixels)

def sense_alarm_due(st):
    alarm=st.get('hydration_alarm') or {}
    if not alarm.get('enabled'): return False
    now=time.time(); last=float(alarm.get('lastFiredAt') or 0); minutes=float(alarm.get('intervalMinutes') or 0)
    return minutes > 0 and now-last >= minutes*60

def sense_loop():
    tick=0; last_text=0
    try:
        from sense_hat import SenseHat
        sense=SenseHat(); sense.low_light=True; sense.clear(); text_once(sense, 'MAPPI3 WELCOME TO THE WILDERNESS', (0,120,20), 0.05)
        with SENSE_LOCK: SENSE_CACHE.update({'ok': True, 'message': 'Sense HAT display loop active', 'updated': time.time()})
        while True:
            st=read_state(); mode=normalize_mode(st.get('sense_mode') or 'compass')
            try:
                orient=sense.get_orientation(); yaw=orient.get('yaw',0); temp_c=sense.get_temperature(); temp_f=temp_c*9/5+32; hum=sense.get_humidity(); pressure=sense.get_pressure(); gps=gps_status()
                if mode=='liquid': draw_liquid(sense, orient, tick)
                elif mode=='compass': draw_compass(sense, yaw, st)
                elif mode=='weather':
                    if time.time()-last_text>8: text_once(sense, f'{temp_f:.0f}F {hum:.0f}% {pressure:.0f}mb', (0,120,180), sense_scroll_speed(st)); last_text=time.time()
                elif mode=='fire': draw_fire(sense,tick)
                elif mode=='flashlight': draw_flashlight(sense,st)
                elif mode=='sos': draw_sos(sense,tick)
                elif mode=='message':
                    if time.time()-last_text>6: text_once(sense, st.get('sense_message') or 'MAPPI3', (0,150,80), sense_scroll_speed(st)); last_text=time.time()
                elif mode=='boot':
                    if time.time()-last_text>10: text_once(sense, st.get('boot_message') or 'WELCOME TO THE WILDERNESS', (0,120,20), sense_scroll_speed(st)); last_text=time.time()
                elif mode=='sun':
                    if time.time()-last_text>8: draw_sun(sense,st); last_text=time.time()
                elif mode=='gps': draw_gps(sense,gps,st)
                elif mode=='clock':
                    if time.time()-last_text>5: text_once(sense, time.strftime('%I:%M %p'), (80,80,180), sense_scroll_speed(st)); last_text=time.time()
                elif mode=='progress': draw_route_progress(sense, st)
                elif mode=='beacon': sense.clear(0, 0 if tick%2 else 80, 0 if tick%2 else 120)
                elif mode=='stars':
                    pixels=[[0,0,0] for _ in range(64)]
                    for _ in range(10): pixels[random.randrange(64)]=[random.choice([40,80,140]),random.choice([40,80,140]),random.choice([80,160,220])]
                    sense.set_pixels(pixels)
                elif mode=='temp': draw_bar(sense, max(0,min(64,(temp_f-20)/80*64)), (180 if temp_f>80 else 0,120,180 if temp_f<50 else 0))
                elif mode=='humidity': draw_bar(sense, hum/100*64, (0,60,180))
                elif mode=='pressure': draw_bar(sense, max(0,min(64,(pressure-970)/80*64)), (120,80,180))
                elif mode=='custom':
                    color=parse_color(st.get('sense_color'), (0,170,85)); draw_border(sense,color) if st.get('sense_border_only') else sense.clear(*color)
                elif mode=='border': draw_border(sense, parse_color(st.get('sense_color'), (0,170,85)))
                elif mode=='magic8':
                    if time.time()-last_text>7: text_once(sense, random.choice(['YES','NO','MAYBE','TRAIL SAYS YES','ASK AGAIN','WATCH WEATHER','DRINK WATER']), parse_color(st.get('sense_color'), (80,0,180)), sense_scroll_speed(st)); last_text=time.time()
                elif mode=='water': draw_water_icon(sense, parse_color(st.get('sense_color'), (0,90,220)))
                elif mode=='snake': draw_snake_frame(sense,tick,parse_color(st.get('sense_color'), (0,220,70)))
                if sense_alarm_due(st):
                    draw_water_icon(sense, (0,120,255)); text_once(sense, 'DRINK 8OZ WATER', (0,120,255), sense_scroll_speed(st)); alarm=st.get('hydration_alarm') or {}; alarm['lastFiredAt']=time.time(); st['hydration_alarm']=alarm; write_state(st)
                with SENSE_LOCK: SENSE_CACHE.update({'ok': True, 'mode': mode, 'available_modes': SENSE_MODES, 'orientation': orient, 'compass': yaw, 'temp': temp_f, 'humidity': hum, 'pressure': pressure, 'gps': gps, 'message': f'{mode} display active', 'updated': time.time()})
            except Exception as e:
                with SENSE_LOCK: SENSE_CACHE.update({'ok': False, 'mode': mode, 'message': f'Sense HAT read/display error: {e}', 'updated': time.time()})
            tick+=1; time.sleep(0.35 if mode in ('liquid','fire','stars','beacon') else 0.75)
    except Exception as e:
        with SENSE_LOCK: SENSE_CACHE.update({'ok': False, 'message': f'Sense HAT unavailable: {e}', 'updated': time.time()})

def joystick_loop():
    while True:
        try:
            link=pathlib.Path('/dev/input/by-path/platform-3f804000.i2c-platform-3f804000.i2c:sensehat@46:joystick-event'); path=str(link.resolve()) if link.exists() else '/dev/input/event0'
            with open(path,'rb') as f:
                flags=fcntl.fcntl(f,fcntl.F_GETFL); fcntl.fcntl(f,fcntl.F_SETFL,flags|os.O_NONBLOCK)
                while True:
                    try:
                        data=f.read(24)
                        if not data or len(data)<24: time.sleep(0.05); continue
                        _sec,_usec,etype,code,value=struct.unpack('llHHI',data)
                        if etype==1 and value==1 and code in KEY_NAMES:
                            direction=KEY_NAMES[code]; st=read_state(); current=normalize_mode(st.get('sense_mode') or 'compass')
                            if direction in ('left','right','press','up','down'):
                                i=SENSE_MODES.index(current) if current in SENSE_MODES else 0
                                next_mode='compass' if direction=='left' else 'liquid' if direction=='right' else SENSE_MODES[(i+1)%len(SENSE_MODES)] if direction in ('press','down') else SENSE_MODES[(i-1)%len(SENSE_MODES)]
                                st['sense_mode']=next_mode; st['sense_mode_updated_at']=time.time(); write_state(st)
                            with SENSE_LOCK:
                                js=dict(SENSE_CACHE.get('joystick') or {}); js.update({'seq': int(js.get('seq') or 0)+1,'direction':direction,'pressed':direction=='press','updated':time.time()}); SENSE_CACHE['joystick']=js
                                if direction in ('left','right','press','up','down'): SENSE_CACHE.update({'mode': next_mode, 'message': f'Joystick set Sense HAT mode to {next_mode}'})
                    except BlockingIOError: time.sleep(0.05)
        except Exception as e:
            with SENSE_LOCK:
                js=dict(SENSE_CACHE.get('joystick') or {}); js.update({'error':str(e),'updated':time.time()}); SENSE_CACHE['joystick']=js
            time.sleep(2)


FIELD_AI_ROOT = pathlib.Path('/var/lib/mappi3/field-ai')
FIELD_AI_DB = FIELD_AI_ROOT / 'field_guide.db'
FIELD_AI_UPLOADS = FIELD_AI_ROOT / 'uploads'
BUILTIN_MODEL_DIR = pathlib.Path('/opt/mappi3/models')
BUILTIN_JSON_MODELS = {
    'cloud-color-prototypes-v1.json': {
        'id':'cloud-color-prototypes-v1','kind':'prototype-classifier','version':'1.0','features':['green_ratio','blue_ratio','orange_ratio','dark_ratio','bright_ratio','edge_mean_scaled'],
        'labels':[
            {'name':'Cumulus / bright fair-weather cloud','vector':[0.02,0.25,0.02,0.04,0.45,0.25],'safety':'Cloud observation only; not a forecast.'},
            {'name':'Cumulonimbus / storm cloud caution','vector':[0.01,0.10,0.02,0.42,0.18,0.55],'safety':'Storm cues possible. Watch thunder, wind, pressure; leave exposed ridges/water early.'},
            {'name':'Stratus / overcast layer','vector':[0.02,0.10,0.01,0.18,0.28,0.14],'safety':'Low cloud/overcast observation. Forecast needs more data.'},
            {'name':'Fog / low visibility','vector':[0.02,0.08,0.01,0.10,0.52,0.05],'safety':'Low visibility risk; navigation caution.'}
        ]
    },
    'plant-green-prototypes-v1.json': {
        'id':'plant-green-prototypes-v1','kind':'prototype-classifier','version':'1.0','features':['green_ratio','blue_ratio','orange_ratio','dark_ratio','bright_ratio','edge_mean_scaled'],
        'labels':[
            {'name':'Leaf/green plant feature match','vector':[0.45,0.04,0.02,0.18,0.15,0.35],'safety':'Possible plant features only. Do not eat based on this.'},
            {'name':'Bark/woody texture feature match','vector':[0.08,0.03,0.16,0.38,0.08,0.48],'safety':'Tree/bark cue only; need whole tree/leaf/habitat.'},
            {'name':'Flower/bright plant feature match','vector':[0.20,0.08,0.22,0.08,0.35,0.30],'safety':'Flower cue only; confirm all field marks.'}
        ]
    },
    'fungi-color-prototypes-v1.json': {
        'id':'fungi-color-prototypes-v1','kind':'prototype-classifier','version':'1.0','features':['green_ratio','blue_ratio','orange_ratio','dark_ratio','bright_ratio','edge_mean_scaled'],
        'labels':[
            {'name':'Orange/yellow mushroom-like color cue','vector':[0.04,0.03,0.32,0.14,0.24,0.36],'safety':'Never consume mushrooms from app/photo ID.'},
            {'name':'Pale mushroom-like color cue','vector':[0.03,0.04,0.04,0.12,0.48,0.28],'safety':'Deadly mushrooms can be pale. Need underside, stem, base, spore print, expert ID.'},
            {'name':'Dark/woodland fungi-like cue','vector':[0.08,0.03,0.08,0.45,0.10,0.42],'safety':'Mushroom/wood texture cue only; do not consume.'}
        ]
    },
    'animal-track-prototypes-v1.json': {
        'id':'animal-track-prototypes-v1','kind':'prototype-classifier','version':'1.0','features':['green_ratio','blue_ratio','orange_ratio','dark_ratio','bright_ratio','edge_mean_scaled'],
        'labels':[
            {'name':'Animal/fur/low-light texture cue','vector':[0.10,0.04,0.10,0.42,0.12,0.44],'safety':'Wildlife cue only. Keep distance and verify with tracks/sound/context.'},
            {'name':'Track/scat contrast cue','vector':[0.06,0.03,0.12,0.36,0.18,0.58],'safety':'Track/scat cue only; use scale, stride, habitat, and freshness.'},
            {'name':'Bird/sky silhouette cue','vector':[0.03,0.30,0.02,0.25,0.30,0.50],'safety':'Bird/silhouette cue only; do not disturb nests or wildlife.'}
        ]
    },
    'insect-closeup-prototypes-v1.json': {
        'id':'insect-closeup-prototypes-v1','kind':'prototype-classifier','version':'1.0','features':['green_ratio','blue_ratio','orange_ratio','dark_ratio','bright_ratio','edge_mean_scaled'],
        'labels':[
            {'name':'Bug/spider close-up texture cue','vector':[0.12,0.04,0.16,0.35,0.12,0.70],'safety':'Bite/sting risk varies; do not handle unknown bugs/spiders.'},
            {'name':'Tick-like dark small-object cue','vector':[0.04,0.02,0.04,0.55,0.05,0.62],'safety':'If attached tick: remove properly, save/photo, monitor symptoms.'}
        ]
    },
    'rock-mineral-prototypes-v1.json': {
        'id':'rock-mineral-prototypes-v1','kind':'prototype-classifier','version':'1.0','features':['green_ratio','blue_ratio','orange_ratio','dark_ratio','bright_ratio','edge_mean_scaled'],
        'labels':[
            {'name':'Gray rock/mineral texture cue','vector':[0.05,0.05,0.04,0.28,0.22,0.50],'safety':'Geology cue only. Do not rely on app for mine/slope/cave safety.'},
            {'name':'Quartz/light mineral cue','vector':[0.02,0.04,0.02,0.08,0.58,0.42],'safety':'Light mineral cue only; verify hardness/streak/context.'},
            {'name':'Iron/orange mineral cue','vector':[0.04,0.03,0.34,0.18,0.18,0.40],'safety':'Oxide/rust cue only; do not taste/ingest minerals.'}
        ]
    },
    'barcode-ocr-prototypes-v1.json': {
        'id':'barcode-ocr-prototypes-v1','kind':'prototype-classifier','version':'1.0','features':['green_ratio','blue_ratio','orange_ratio','dark_ratio','bright_ratio','edge_mean_scaled'],
        'labels':[
            {'name':'High-contrast code/text-like cue','vector':[0.01,0.01,0.01,0.48,0.42,0.80],'safety':'Barcode/OCR cue only until ZXing/Tesseract plugin is installed.'},
            {'name':'Low-contrast label/text cue','vector':[0.02,0.02,0.02,0.22,0.35,0.55],'safety':'Text cue only; verify labels manually.'}
        ]
    },
    'injury-safety-prototypes-v1.json': {
        'id':'injury-safety-prototypes-v1','kind':'safety-router','version':'1.0','features':['green_ratio','blue_ratio','orange_ratio','dark_ratio','bright_ratio','edge_mean_scaled'],
        'labels':[
            {'name':'Skin/injury image safety router','vector':[0.02,0.02,0.22,0.18,0.26,0.36],'safety':'Do not diagnose from image. Use first aid decision tree and seek care for serious symptoms.'},
            {'name':'Bite/sting/rash safety router','vector':[0.04,0.02,0.18,0.24,0.22,0.42],'safety':'Monitor swelling, breathing, fever, spreading redness; emergency care if severe.'}
        ]
    }
}

def ensure_builtin_models():
    try:
        BUILTIN_MODEL_DIR.mkdir(parents=True, exist_ok=True)
        for name, payload in BUILTIN_JSON_MODELS.items():
            p=BUILTIN_MODEL_DIR/name
            if not p.exists(): p.write_text(json.dumps(payload, indent=2))
    except Exception: pass

FIELD_AI_CATEGORIES = [
    {'id':'auto','name':'Identify automatically','model':'router-lite','input':'image','ready':True},
    {'id':'plant','name':'Plant / tree / leaf / flower','model':'mobilenetv3-small-int8-plants-ne-v1.tflite','input':'image','ready':False},
    {'id':'mushroom','name':'Mushroom / fungi','model':'mobilenetv3-small-int8-fungi-ne-v1.tflite','input':'image','ready':False},
    {'id':'animal','name':'Animal / bird / mammal','model':'mobilenetv3-small-int8-fauna-ne-v1.tflite','input':'image','ready':False},
    {'id':'bug','name':'Bug / insect / spider','model':'mobilenetv3-small-int8-insects-ne-v1.tflite','input':'image','ready':False},
    {'id':'track','name':'Animal track / scat','model':'track-router-ne-v1.tflite','input':'image','ready':False},
    {'id':'cloud','name':'Cloud / weather observation','model':'mobilenetv3-small-int8-clouds-v1.tflite','input':'image','ready':False},
    {'id':'injury','name':'Bite, burn, rash, wound, sting','model':'fixed-decision-tree','input':'image+questions','ready':True},
    {'id':'firstaid','name':'First aid decision tree','model':'fixed-reference','input':'questions','ready':True},
    {'id':'survival','name':'Survival guide lookup','model':'sqlite-reference','input':'text','ready':True},
    {'id':'rock','name':'Rock / mineral','model':'future-specialist','input':'image','ready':False},
    {'id':'barcode','name':'Barcode / QR / OCR','model':'future-zxing-tesseract','input':'image','ready':False}
]
FIELD_GUIDE_SEED = [
    ('cattail','Cattail','Typha latifolia','edible wild plants','Wetland plant with flat blade leaves and brown cigar-shaped seed head.','Look for dense wetland stands, flat leaves, brown cylindrical seed head in season.','Wetlands, pond edges, marshes.','Maine/New England wetlands.','Spring shoots; summer/fall seed heads.','Low when correctly identified and from clean water; pollution risk is major.','Edible parts are used only after positive ID and proper preparation.','Yellow iris, other wetland plants, polluted lookalike habitat.','Do not harvest from polluted water or roadside runoff.','If illness after eating wild plants occurs, stop eating and seek medical help.','Survival food only with expert ID; clean water matters.','Photograph whole plant, seed head, leaf base, habitat.','0.82','MapPI3 offline seed guide; verify with local field guide.'),
    ('dandelion','Dandelion','Taraxacum officinale','edible wild plants','Common yellow composite flower with basal toothed leaves and milky sap.','Single yellow flower head, hollow stem, basal rosette, toothed leaves.','Lawns, fields, disturbed soil.','Common in New England.','Spring/fall leaves are less bitter; flowers in warm months.','Generally low when pesticide-free and correctly identified.','Leaves/flowers/roots used as food; avoid treated lawns.','Catsear and other yellow composites; pesticide contamination.','Avoid roadsides and treated lawns.','GI upset possible; seek help for severe reaction.','Useful common plant but not enough calories alone.','Photo flower, leaves, stem, entire plant, surrounding area.','0.78','MapPI3 offline seed guide.'),
    ('poison-ivy','Poison ivy','Toxicodendron radicans','poisonous plants','Plant that can cause severe allergic contact dermatitis.','Leaves of three, variable edge, vine/shrub forms, oily urushiol exposure.','Edges, woods, fields, trailsides.','Common in New England.','All seasons; leafless vines still hazardous.','Contact toxin; burning smoke can injure lungs.','Not edible.','Virginia creeper, boxelder seedlings, brambles.','Do not touch; wash skin/gear; never burn.','Trouble breathing or facial/throat swelling after smoke/exposure is emergency.','Know before brushing through vegetation.','Photo leaf cluster, vine/stem, growth form from distance.','0.70','MapPI3 offline safety guide.'),
    ('water-hemlock','Water hemlock','Cicuta maculata','poisonous plants','Deadly wetland carrot-family plant.','Umbel flowers, wet habitat, compound leaves, chambered root.','Wet meadows, stream banks, marshes.','New England and North America.','Spring through fall.','Extremely poisonous if ingested.','Not edible.','Wild carrot, angelica, elderberry, other umbel plants.','Never sample wild carrot-family roots/stems without expert ID.','Suspected ingestion is emergency; call poison control/EMS.','Avoid unknown wetland umbel plants.','Photo whole plant, leaf, stem, flower, habitat; do not handle bare-handed.','0.60','MapPI3 offline safety guide.'),
    ('amanita-warning','Amanita / deadly mushroom warning','Amanita spp.','mushrooms and fungi','Some Amanita species are deadly and can resemble edible mushrooms.','Look for cap, gills, ring, volva/base, spore color, habitat; many features hidden.','Woods, lawns, near host trees depending species.','New England has dangerous Amanita species.','Summer/fall common.','Potentially deadly.','Never treat as edible from photo ID.','Edible mushrooms can be confused with deadly Amanita/Galerina/Lepiota.','MapPI3 never certifies mushrooms safe to eat.','Suspected mushroom poisoning: save specimen/photos and seek emergency/poison control help.','Photo top, underside, full stem, base/volva, nearby trees, bruising.','Need multiple photos and expert ID.','0.95','MapPI3 mushroom safety rule.'),
    ('black-bear','Black bear','Ursus americanus','mammals','Large omnivore; usually avoids humans but food-conditioned bears are dangerous.','Large body, rounded ears, tracks with five toes/claws.','Forests, mountains, campsites.','Maine/New England.','Active spring-fall; denning winter.','Danger if surprised, cubs nearby, or food-conditioned.','Not applicable.','Large dog/coyote tracks can confuse track photos.','Do not approach; secure food; back away calmly.','Attack/injury requires emergency care.','Make noise, keep dog controlled, store food properly.','Photo tracks with scale, scat, or distant animal only.','0.75','MapPI3 wildlife safety seed.'),
    ('cumulonimbus','Cumulonimbus cloud','Cumulonimbus','clouds','Tall thunderstorm cloud associated with lightning, heavy rain, hail, gusts.','Vertical tower/anvil shape, dark base, rapid growth.','Sky observation.','Global.','Warm season common; can occur any storm season.','Weather hazard: lightning/wind/heavy rain.','Not applicable.','Cumulus congestus, dark stratus.','Cloud photo alone is not a forecast; leave ridges/open water if thunder/lightning risk.','Lightning injury/burn/shock are emergencies.','Watch sky, pressure, wind, thunder; seek shelter early.','Wide sky photo and horizon context.','0.70','MapPI3 cloud safety guide.'),
    ('first-aid-red-flags','Emergency warning signs','Fixed decision tree','first aid','Red flags requiring urgent care or emergency services.','Trouble breathing, facial/throat swelling, confusion, fainting, uncontrolled bleeding, severe burns, rapidly spreading redness, venomous snakebite, shock, severe allergic reaction.','Any field setting.','Universal.','Any time.','High danger.','Not applicable.','Mild symptoms can worsen; do not delay for app analysis.','Call emergency services/use real first-aid training; app is reference only.','Emergency warning signs require immediate help.','Use as fixed offline checklist.','No photo required; answer safety questions first.','1.0','Curated MapPI3 first-aid red flags.')
]

def field_ai_db():
    FIELD_AI_ROOT.mkdir(parents=True, exist_ok=True); FIELD_AI_UPLOADS.mkdir(parents=True, exist_ok=True)
    conn=sqlite3.connect(str(FIELD_AI_DB)); conn.row_factory=sqlite3.Row
    conn.execute('''CREATE TABLE IF NOT EXISTS species (id TEXT PRIMARY KEY, common_name TEXT, scientific_name TEXT, category TEXT, description TEXT, identification_features TEXT, habitat TEXT, geographic_range TEXT, seasonal_information TEXT, toxicity TEXT, edibility TEXT, dangerous_lookalikes TEXT, handling_warnings TEXT, first_aid_instructions TEXT, survival_notes TEXT, additional_photo_requirements TEXT, confidence_threshold REAL, source TEXT)''')
    conn.execute('''CREATE TABLE IF NOT EXISTS observations (id TEXT PRIMARY KEY, created_at REAL, category TEXT, image_path TEXT, result_json TEXT, notes TEXT)''')
    conn.execute('''CREATE TABLE IF NOT EXISTS corrections (id TEXT PRIMARY KEY, created_at REAL, observation_id TEXT, category TEXT, ai_guess TEXT, correction TEXT, evidence TEXT, source TEXT, votes INTEGER DEFAULT 0, public INTEGER DEFAULT 0)''')
    conn.execute('''CREATE TABLE IF NOT EXISTS plugins (id TEXT PRIMARY KEY, kind TEXT, label TEXT, path TEXT, enabled INTEGER, config_json TEXT)''')
    for row in FIELD_GUIDE_SEED:
        conn.execute('INSERT OR IGNORE INTO species VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)', row)
    for cat in FIELD_AI_CATEGORIES:
        conn.execute('INSERT OR IGNORE INTO plugins VALUES (?,?,?,?,?,?)', (cat['id'], 'model' if cat.get('input')!='questions' else 'reference', cat['name'], '/opt/mappi3/models/'+cat['model'], 1 if cat['ready'] else 0, json.dumps(cat)))
    conn.commit(); return conn

def field_ai_categories():
    conn=field_ai_db(); rows=[dict(r) for r in conn.execute('SELECT * FROM plugins ORDER BY label')]; conn.close()
    return {'ok': True, 'categories': FIELD_AI_CATEGORIES, 'plugins': rows, 'offline': True, 'model_policy': 'load-one-specialist-at-a-time; TensorFlow Lite/NCNN INT8 preferred; current build uses safe offline reference fallback until model files are installed'}

def field_ai_status():
    ensure_builtin_models(); conn=field_ai_db(); species=conn.execute('SELECT COUNT(*) c FROM species').fetchone()['c']; obs=conn.execute('SELECT COUNT(*) c FROM observations').fetchone()['c']; corrections=conn.execute('SELECT COUNT(*) c FROM corrections').fetchone()['c']; plugins=[dict(r) for r in conn.execute('SELECT * FROM plugins ORDER BY id')]; conn.close()
    model_dir=pathlib.Path('/opt/mappi3/models')
    installed=[]
    if model_dir.exists(): installed=[p.name for p in model_dir.glob('*') if p.is_file()]
    return {'ok': True, 'offline': True, 'database': str(FIELD_AI_DB), 'species_records': species, 'observations': obs, 'corrections': corrections, 'model_dir': str(model_dir), 'installed_models': installed, 'plugins': plugins, 'memory_policy': 'Zero 2 W: one model loaded at a time; image resize target 224/320; avoid PyTorch on Pi'}

def _species_by_category(conn, category):
    if category in ('auto','survival'):
        rows=conn.execute('SELECT * FROM species LIMIT 8').fetchall()
    elif category=='plant':
        rows=conn.execute("SELECT * FROM species WHERE category LIKE '%plant%' OR category LIKE '%tree%' OR category LIKE '%edible%' LIMIT 8").fetchall()
    elif category=='mushroom':
        rows=conn.execute("SELECT * FROM species WHERE category LIKE '%mushroom%' OR category LIKE '%fungi%' LIMIT 8").fetchall()
    elif category in ('animal','bug','track'):
        rows=conn.execute("SELECT * FROM species WHERE category LIKE '%mammal%' OR category LIKE '%animal%' LIMIT 8").fetchall()
    elif category=='cloud':
        rows=conn.execute("SELECT * FROM species WHERE category LIKE '%cloud%' LIMIT 8").fetchall()
    elif category in ('injury','firstaid'):
        rows=conn.execute("SELECT * FROM species WHERE category LIKE '%first aid%' LIMIT 8").fetchall()
    else:
        rows=conn.execute('SELECT * FROM species LIMIT 8').fetchall()
    return [dict(r) for r in rows]


def basic_image_model(image_path, category):
    try:
        from PIL import Image, ImageStat, ImageFilter
        img=Image.open(image_path).convert('RGB'); w,h=img.size
        thumb=img.resize((96,96)); stat=ImageStat.Stat(thumb); mean=stat.mean
        gray=thumb.convert('L'); edges=gray.filter(ImageFilter.FIND_EDGES); edge_mean=ImageStat.Stat(edges).mean[0]
        pixels=list(thumb.getdata()); total=len(pixels)
        green=sum(1 for r,g,b in pixels if g>r*1.08 and g>b*1.08 and g>55)/total
        blue=sum(1 for r,g,b in pixels if b>r*1.05 and b>g*.95 and b>70)/total
        orange=sum(1 for r,g,b in pixels if r>120 and g>70 and b<90)/total
        dark=sum(1 for r,g,b in pixels if r+g+b<120)/total
        bright=sum(1 for r,g,b in pixels if r+g+b>610)/total
        cloud_guess='Cumulus' if bright>0.22 and blue>0.18 else ('Cumulonimbus / storm cloud caution' if dark>0.35 and edge_mean>18 else ('Fog/stratus' if edge_mean<10 and bright>0.12 else 'Cloud observation'))
        if category=='cloud':
            return {'engine':'pillow-feature-model-v0','features':{'mean_rgb':[round(x,1) for x in mean],'green_ratio':round(green,3),'blue_ratio':round(blue,3),'orange_ratio':round(orange,3),'dark_ratio':round(dark,3),'bright_ratio':round(bright,3),'edge_mean':round(edge_mean,2),'width':w,'height':h},'guess':cloud_guess,'confidence':58 if 'Cumul' in cloud_guess else 45}
        if category in ('plant','auto') and green>0.18:
            return {'engine':'pillow-feature-model-v0','features':{'green_ratio':round(green,3),'edge_mean':round(edge_mean,2),'width':w,'height':h},'guess':'Plant/leaf-like image features detected','confidence':52}
        if category=='mushroom' and (orange>0.08 or bright>0.2):
            return {'engine':'pillow-feature-model-v0','features':{'orange_ratio':round(orange,3),'bright_ratio':round(bright,3),'edge_mean':round(edge_mean,2),'width':w,'height':h},'guess':'Mushroom-like color/shape cue possible; safety fallback required','confidence':38}
        return {'engine':'pillow-feature-model-v0','features':{'mean_rgb':[round(x,1) for x in mean],'green_ratio':round(green,3),'blue_ratio':round(blue,3),'dark_ratio':round(dark,3),'edge_mean':round(edge_mean,2),'width':w,'height':h},'guess':'No specialist match; use reference fallback','confidence':30}
    except Exception as e:
        return {'engine':'unavailable','error':str(e),'guess':'Image stored; install Pillow/TFLite model for feature inference','confidence':0}


def prototype_model_match(category, vision):
    ensure_builtin_models()
    fmap={'cloud':'cloud-color-prototypes-v1.json','plant':'plant-green-prototypes-v1.json','auto':'plant-green-prototypes-v1.json','mushroom':'fungi-color-prototypes-v1.json','animal':'animal-track-prototypes-v1.json','track':'animal-track-prototypes-v1.json','bug':'insect-closeup-prototypes-v1.json','rock':'rock-mineral-prototypes-v1.json','barcode':'barcode-ocr-prototypes-v1.json','ocr':'barcode-ocr-prototypes-v1.json','injury':'injury-safety-prototypes-v1.json'}
    name=fmap.get(category)
    if not name or not vision or not isinstance(vision.get('features'), dict): return None
    try:
        model=json.loads((BUILTIN_MODEL_DIR/name).read_text())
        f=vision.get('features') or {}; vec=[float(f.get('green_ratio') or 0), float(f.get('blue_ratio') or 0), float(f.get('orange_ratio') or 0), float(f.get('dark_ratio') or 0), float(f.get('bright_ratio') or 0), min(1.0, float(f.get('edge_mean') or 0)/60.0)]
        best=None
        for label in model.get('labels',[]):
            lv=[float(x) for x in label.get('vector',[])]
            d=sum((a-b)**2 for a,b in zip(vec,lv))**0.5
            score=max(12, min(82, round(82 - d*95)))
            item={**label,'distance':round(d,4),'confidence':score,'model_id':model.get('id'),'features':model.get('features')}
            if best is None or item['confidence']>best['confidence']: best=item
        return best
    except Exception as e:
        return {'name':'Prototype model unavailable','confidence':0,'error':str(e)}

def field_ai_analyze(payload):
    category=str(payload.get('category') or 'auto').lower(); notes=str(payload.get('notes') or '')[:500]
    image_data=payload.get('image') or ''
    image_path=''
    image_info={'received': False}
    if image_data:
        if ',' in image_data: image_data=image_data.split(',',1)[1]
        raw=base64.b64decode(image_data + '='*((4-len(image_data)%4)%4), validate=False)
        if len(raw) > 7_000_000: return {'ok': False, 'error': 'Image too large. Use a smaller photo under ~7 MB.'}
        obs_id='obs-'+uuid.uuid4().hex[:12]
        image_path=str(FIELD_AI_UPLOADS/(obs_id+'.jpg'))
        FIELD_AI_UPLOADS.mkdir(parents=True, exist_ok=True); pathlib.Path(image_path).write_bytes(raw)
        image_info={'received': True, 'bytes': len(raw), 'stored': image_path, 'resize_target': '224x224 or 320x320 when specialist model is installed'}
    else:
        obs_id='obs-'+uuid.uuid4().hex[:12]
    conn=field_ai_db(); candidates=_species_by_category(conn, category)
    vision = basic_image_model(image_path, category) if image_path else {'engine':'none','guess':'No image supplied','confidence':0}
    prototype = prototype_model_match(category, vision) if image_path else None
    primary=candidates[0] if candidates else {}
    model_ready=any(c['id']==category and c.get('ready') for c in FIELD_AI_CATEGORIES)
    confidence=42 if category not in ('injury','firstaid','survival') else 100
    if category=='mushroom': confidence=36
    alternatives=[{'id':c['id'],'name':c['common_name'],'confidence':max(5, confidence-(i+1)*9),'category':c['category']} for i,c in enumerate(candidates[1:4])]
    warnings=['Possible identification only. Do not consume any wild plant or mushroom based only on this result.','Offline model files are not installed yet; this response uses the safe reference/database fallback.']
    if category in ('injury','firstaid'):
        warnings=['This app cannot diagnose bites, burns, rashes, wounds, infections, poisoning, or allergic reactions from an image.','Emergency signs: trouble breathing, facial/throat swelling, confusion, fainting, uncontrolled bleeding, severe burns, rapidly spreading redness, suspected venomous bite, shock, severe allergic reaction.']
    if category=='cloud': warnings=['Cloud photo only: not a reliable forecast. Use pressure, wind, radar/weather source when available, and leave exposed areas early if thunder/lightning threatens.']
    result={'ok': True,'observation_id': obs_id,'category': category,'router': {'selected_category': category, 'model_ready': model_ready, 'plugin': next((c for c in FIELD_AI_CATEGORIES if c['id']==category), FIELD_AI_CATEGORIES[0])},'image': image_info,'possible_identification': {'id': primary.get('id','reference'), 'name': primary.get('common_name','Offline reference guidance'), 'scientific_name': primary.get('scientific_name',''), 'confidence': confidence, 'confirmed': False},'alternatives': alternatives,'vision_model': vision, 'prototype_model': prototype, 'visible_features': [f"Local image model: {vision.get('guess')} ({vision.get('engine')})", primary.get('identification_features','Collect multiple angles and habitat context.') if primary else 'Collect additional photos.'],'dangerous_lookalikes': primary.get('dangerous_lookalikes','Unknown lookalikes require expert/local confirmation.') if primary else 'Unknown','safety_warnings': warnings,'additional_photos_requested': (primary.get('additional_photo_requirements') if primary else 'Top, underside, stem/base, whole organism, habitat, scale reference.'),'recommended_next_steps': ['Take 2-4 more photos from different angles with scale/context.','Compare against offline field-guide record and dangerous lookalikes.','Prototype JSON models are active now; install/enable specialist INT8/TFLite model next for stronger inference.'],'field_guide': primary,'offline_reference_matches': candidates[:5],'history_saved': True,'limitations': 'This is an offline-first plugin scaffold and safety/reference fallback until specialist model files are added.'}
    conn.execute('INSERT OR REPLACE INTO observations VALUES (?,?,?,?,?,?)', (obs_id, time.time(), category, image_path, json.dumps(result), notes)); conn.commit(); conn.close()
    return result

def field_ai_history():
    conn=field_ai_db(); rows=[dict(r) for r in conn.execute('SELECT id, created_at, category, image_path, notes FROM observations ORDER BY created_at DESC LIMIT 50')]; conn.close(); return {'ok': True, 'history': rows}

def field_ai_corrections():
    conn=field_ai_db(); rows=[dict(r) for r in conn.execute('SELECT * FROM corrections ORDER BY votes DESC, created_at DESC LIMIT 100')]; conn.close(); return {'ok': True, 'corrections': rows, 'policy': 'Local first. Public/wiki sync later should require source/evidence, votes, and review flags.'}

def field_ai_add_correction(payload):
    conn=field_ai_db(); cid='corr-'+uuid.uuid4().hex[:12]
    row=(cid,time.time(),str(payload.get('observation_id') or '')[:80],str(payload.get('category') or 'unknown')[:40],str(payload.get('ai_guess') or '')[:200],str(payload.get('correction') or '')[:1000],str(payload.get('evidence') or '')[:1000],str(payload.get('source') or 'local user note')[:200],0,1 if payload.get('public') else 0)
    conn.execute('INSERT INTO corrections VALUES (?,?,?,?,?,?,?,?,?,?)', row); conn.commit(); conn.close()
    return {'ok': True, 'correction_id': cid, 'message': 'Correction saved locally; future public sync can publish it as a fact-check note.'}

def field_ai_vote_correction(payload):
    cid=str(payload.get('id') or '')[:80]; delta=1 if int(payload.get('delta') or 0)>0 else -1
    conn=field_ai_db(); conn.execute('UPDATE corrections SET votes=COALESCE(votes,0)+? WHERE id=?', (delta,cid)); conn.commit(); conn.close()
    return field_ai_corrections()

def field_ai_clear_history():
    conn=field_ai_db(); conn.execute('DELETE FROM observations'); conn.commit(); conn.close(); return {'ok': True, 'message': 'Field AI observation history cleared.'}

def status():
    gps=gps_status(); sense=sense_snapshot(); ip=sh('hostname -I || true',timeout=5)['output'].strip(); w=wifi_info(); mode='hotspot' if w['hotspot_active'] else ('home-wifi' if w['home_wifi_ssid'] else 'local-pi')
    sense_text=sense.get('message') or ('sense-hat ok' if sense.get('ok') else 'sense-hat unavailable')
    if sense.get('ok') and sense.get('orientation'):
        o=sense.get('orientation') or {}; sense_text='sense-hat ok roll={:.1f} pitch={:.1f} yaw={:.1f} mode={}'.format(o.get('roll',0),o.get('pitch',0),o.get('yaw',0),sense.get('mode','compass'))
    return {'ok': True, 'host': socket.gethostname(), 'port': PORT, 'ip': ip, 'connection_mode': mode, **w, 'gps_device': gps.get('device'), 'gps': gps, 'sense_hat': sense_text, 'sense': sense, 'system': system_stats(), 'state': read_state(), 'time': time.time()}

def connect_home_wifi(payload):
    ssid=(payload.get('ssid') or '').strip(); password=payload.get('password') or ''
    if not ssid: return {'ok': False, 'error': 'SSID is required'}
    st=read_state(); st['home_wifi_ssid']=ssid; st['home_wifi_saved_at']=time.time(); write_state(st)
    if not pathlib.Path('/usr/bin/nmcli').exists(): return {'ok': False, 'error': 'nmcli/NetworkManager not installed yet; saved SSID locally only'}
    cmd = "nmcli radio wifi on; rfkill unblock wifi || true; nmcli device wifi rescan || true; nmcli connection delete MapPI3-home >/dev/null 2>&1 || true; "
    cmd += "nmcli connection add type wifi ifname wlan0 con-name MapPI3-home ssid " + json.dumps(ssid) + "; "
    cmd += "nmcli connection modify MapPI3-home connection.autoconnect yes wifi-sec.key-mgmt wpa-psk wifi-sec.psk " + json.dumps(password) + "; "
    cmd += "nmcli connection up MapPI3-home || nmcli device wifi connect " + json.dumps(ssid) + " password " + json.dumps(password)
    return sh(cmd, timeout=45)



def pi_weather(payload):
    try:
        lat=float(payload.get('lat') or 44.1004); lon=float(payload.get('lon') or -70.2148); days=max(1,min(10,int(payload.get('days') or 10))); tz=urllib.parse.quote(str(payload.get('timezone') or 'auto'))
        url=f'https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&current=temperature_2m,relative_humidity_2m,weather_code&hourly=temperature_2m,relative_humidity_2m,precipitation_probability,weather_code&daily=temperature_2m_max,temperature_2m_min,precipitation_probability_max,weather_code&forecast_days={days}&temperature_unit=fahrenheit&timezone={tz}'
        last_err=None
        for attempt in range(3):
            try:
                with urllib.request.urlopen(url, timeout=18) as r:
                    data=json.loads(r.read().decode())
                break
            except Exception as e:
                last_err=e
                time.sleep(1.5)
        else:
            raise last_err
        daily=[{'date':d,'maxF':data.get('daily',{}).get('temperature_2m_max',[None]*days)[i],'minF':data.get('daily',{}).get('temperature_2m_min',[None]*days)[i],'precip':data.get('daily',{}).get('precipitation_probability_max',[None]*days)[i],'code':data.get('daily',{}).get('weather_code',[None]*days)[i]} for i,d in enumerate((data.get('daily',{}).get('time') or [])[:days])]
        hourly=[{'time':t,'tempF':data.get('hourly',{}).get('temperature_2m',[None])[i],'humidity':data.get('hourly',{}).get('relative_humidity_2m',[None])[i],'precip':data.get('hourly',{}).get('precipitation_probability',[None])[i],'code':data.get('hourly',{}).get('weather_code',[None])[i]} for i,t in enumerate((data.get('hourly',{}).get('time') or [])[:min(72,days*24)])]
        return {'ok': True, 'source':'Pi internet Open-Meteo live', 'lat':lat, 'lon':lon, 'days':days, 'current':data.get('current',{}), 'daily':daily, 'hourly':hourly, 'fetched_at':time.time()}
    except Exception as e:
        return {'ok': False, 'source':'Pi weather unavailable/offline', 'error':str(e), 'fetched_at':time.time()}

def setup_vnc(payload=None):
    payload=payload or {}; password=str(payload.get('password') or '4Walls')
    pw_hash=hashlib.sha256(('mappi3-vnc:'+password).encode()).hexdigest()
    path=pathlib.Path('/etc/mappi3'); path.mkdir(parents=True, exist_ok=True)
    (path/'vnc-password.sha256').write_text(pw_hash+'\n')
    os.chmod(path/'vnc-password.sha256', 0o600)
    install=sh('DEBIAN_FRONTEND=noninteractive apt-get update && DEBIAN_FRONTEND=noninteractive apt-get install -y x11vnc || true', timeout=180)
    if pathlib.Path('/usr/bin/x11vnc').exists():
        sh('x11vnc -storepasswd '+json.dumps(password)+' /etc/mappi3/x11vnc.pass >/dev/null 2>&1 || true', timeout=20)
        service="""[Unit]\\nDescription=MapPI3 debug VNC (disabled by default)\\nAfter=network.target\\n\\n[Service]\\nType=simple\\nExecStart=/usr/bin/x11vnc -forever -shared -rfbauth /etc/mappi3/x11vnc.pass -rfbport 5900 -display :0\\nRestart=on-failure\\n\\n[Install]\\nWantedBy=multi-user.target\\n"""
        pathlib.Path('/etc/systemd/system/mappi3-debug-vnc.service').write_text(service)
        sh('systemctl daemon-reload; systemctl disable --now mappi3-debug-vnc.service || true', timeout=20)
        return {'ok': True, 'installed': True, 'enabled': False, 'message':'x11vnc installed/configured but disabled. Enable only for debugging.', 'install_output':install.get('output','')[-1000:]}
    return {'ok': False, 'installed': False, 'enabled': False, 'message':'VNC password hash saved, but x11vnc is not installed. Pi likely has no internet or package install failed. Service left disabled/not created.', 'install_output':install.get('output','')[-2000:]}

def disable_vnc():
    r=sh('systemctl disable --now mappi3-debug-vnc.service vncserver-x11-serviced.service wayvnc.service x11vnc.service 2>/dev/null || true', timeout=20)
    return {'ok': True, 'message':'VNC services disabled for field mode.', 'output':r.get('output','')}


def gps_diagnose():
    dev=gps_device()
    checks={
        'device': dev,
        'serial0': sh('ls -l /dev/serial0 2>&1 || true', timeout=3).get('output','').strip(),
        'gpsd_active': sh('systemctl is-active gpsd 2>/dev/null || true', timeout=3).get('output','').strip(),
        'gpsd_enabled': sh('systemctl is-enabled gpsd 2>/dev/null || true', timeout=3).get('output','').strip(),
        'devices_file': sh('cat /etc/default/gpsd 2>/dev/null || true', timeout=3).get('output','')[-1200:],
        'sample': gps_status(),
    }
    if not dev:
        checks['recommendation']='No serial GPS device path found. Check wiring/HAT/USB and enable serial.'
    elif not checks['sample'].get('fix'):
        checks['recommendation']='GPS path exists but gpsd has no fix/device report. Try clear sky 5-15 min, then restart gpsd; if DEVICES is empty, set /dev/serial0 in /etc/default/gpsd.'
    else:
        checks['recommendation']='GPS fix present.'
    return {'ok': True, 'diagnostics': checks}

def field_ai_verify(payload=None):
    payload=payload or {}; ensure_builtin_models()
    status_info=field_ai_status()
    colors={'plant':(30,180,45),'cloud':(245,245,245),'mushroom':(220,130,35),'animal':(55,48,42),'bug':(18,18,18),'track':(85,70,55),'rock':(145,145,145),'barcode':(0,0,0),'injury':(205,115,95)}
    def sample_png(color):
        try:
            from PIL import Image, ImageDraw
            img=Image.new('RGB',(24,24),color)
            draw=ImageDraw.Draw(img)
            if color==(0,0,0):
                img=Image.new('RGB',(24,24),(255,255,255)); draw=ImageDraw.Draw(img)
                for x in range(0,24,4): draw.rectangle([x,0,x+1,23], fill=(0,0,0))
            else:
                draw.line((0,0,23,23), fill=tuple(max(0,c-45) for c in color), width=2)
                draw.line((23,0,0,23), fill=tuple(min(255,c+45) for c in color), width=2)
            buf=io.BytesIO(); img.save(buf, format='PNG')
            return base64.b64encode(buf.getvalue()).decode()
        except Exception:
            return 'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAIAAACQd1PeAAAADElEQVR4nGNgaGD4DwABBAEAgh1Y6QAAAABJRU5ErkJggg=='
    samples={k:sample_png(v) for k,v in colors.items()}
    requested=payload.get('category')
    cats=[requested] if requested and requested!='all' else list(samples.keys())
    results={}
    for cat in cats:
        result=field_ai_analyze({'category': cat, 'image': samples.get(cat) or samples['plant'], 'notes':'MapPI3 multi-model self-test observation'})
        results[cat]={'ok': bool(result.get('ok')), 'vision_model': result.get('vision_model'), 'prototype_model': result.get('prototype_model'), 'possible_identification': result.get('possible_identification'), 'observation_id': result.get('observation_id')}
    return {'ok': all(v.get('ok') and v.get('prototype_model') for v in results.values()), 'status': status_info, 'results': results, 'sample': next(iter(results.values()), {})}

NOAA_CACHE = pathlib.Path('/var/lib/mappi3/noaa-weather-cache.json')

def _http_json(url, timeout=15):
    req=urllib.request.Request(url, headers={'User-Agent':'MapPI3 Trail Buddy (github.com/real-CAK3D/MapPI3; offline field weather cache)', 'Accept':'application/geo+json, application/json'})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode())

def noaa_weather(payload=None):
    payload=payload or {}
    lat=float(payload.get('lat') or 44.1004); lon=float(payload.get('lon') or -70.2148)
    force=bool(payload.get('force'))
    cache={'ok':False}
    if NOAA_CACHE.exists():
        try: cache=json.loads(NOAA_CACHE.read_text())
        except Exception: cache={'ok':False}
    age=time.time()-float(cache.get('fetched_at') or 0)
    if cache.get('ok') and not force and age < 1800 and abs(float(cache.get('lat',lat))-lat)<0.02 and abs(float(cache.get('lon',lon))-lon)<0.02:
        cache['cached']=True; cache['age_seconds']=round(age); return cache
    try:
        point=_http_json(f'https://api.weather.gov/points/{lat:.4f},{lon:.4f}')
        props=point.get('properties') or {}
        forecast_url=props.get('forecast'); hourly_url=props.get('forecastHourly')
        zone_url=props.get('forecastZone') or props.get('county')
        forecast=_http_json(forecast_url) if forecast_url else {}
        hourly=_http_json(hourly_url) if hourly_url else {}
        alerts=_http_json(f'https://api.weather.gov/alerts/active?point={lat:.4f},{lon:.4f}')
        periods=(forecast.get('properties') or {}).get('periods') or []
        hourly_periods=(hourly.get('properties') or {}).get('periods') or []
        alert_items=[]
        for f in (alerts.get('features') or [])[:12]:
            p=f.get('properties') or {}; alert_items.append({'event':p.get('event'),'headline':p.get('headline'),'severity':p.get('severity'),'urgency':p.get('urgency'),'certainty':p.get('certainty'),'area':p.get('areaDesc'),'instruction':p.get('instruction'),'description':(p.get('description') or '')[:1500],'effective':p.get('effective'),'expires':p.get('expires')})
        out={'ok':True,'source':'NOAA/NWS weather.gov live','lat':lat,'lon':lon,'cached':False,'fetched_at':time.time(),'office':props.get('cwa'),'grid':{'x':props.get('gridX'),'y':props.get('gridY')},'zone_url':zone_url,'forecast_url':forecast_url,'hourly_url':hourly_url,'periods':[{'name':p.get('name'),'startTime':p.get('startTime'),'temperature':p.get('temperature'),'temperatureUnit':p.get('temperatureUnit'),'windSpeed':p.get('windSpeed'),'windDirection':p.get('windDirection'),'shortForecast':p.get('shortForecast'),'detailedForecast':p.get('detailedForecast')} for p in periods[:14]],'hourly':[{'startTime':p.get('startTime'),'temperature':p.get('temperature'),'shortForecast':p.get('shortForecast'),'windSpeed':p.get('windSpeed'),'probabilityOfPrecipitation':(p.get('probabilityOfPrecipitation') or {}).get('value')} for p in hourly_periods[:36]],'alerts':alert_items,'alert_count':len(alert_items),'note':'NWS text forecasts/alerts cache for offline field reference. Satellite/radar imagery is a future plugin layer.'}
        NOAA_CACHE.parent.mkdir(parents=True, exist_ok=True); NOAA_CACHE.write_text(json.dumps(out))
        return out
    except Exception as e:
        if cache.get('ok'):
            cache['cached']=True; cache['offline_error']=str(e); cache['age_seconds']=round(age); cache['source']='NOAA/NWS cached fallback'; return cache
        return {'ok':False,'source':'NOAA/NWS unavailable','lat':lat,'lon':lon,'error':str(e),'hint':'Connect Pi to internet via online maintenance to refresh NOAA/NWS cache.'}

def start_online_maintenance(payload=None):
    payload=payload or {}
    ssid=str(payload.get('ssid') or payload.get('homeWifiSsid') or '').strip()[:64]
    password=str(payload.get('password') or payload.get('homeWifiPassword') or '').strip()[:128]
    lat=str(payload.get('lat') or '44.1004')[:32]; lon=str(payload.get('lon') or '-70.2148')[:32]
    days=str(payload.get('days') or '5')[:4]; tz=str(payload.get('timezone') or 'America/New_York')[:64]
    if not ssid or not password: return {'ok': False, 'error':'ssid and password required'}
    script=pathlib.Path('/tmp/mappi3-online-maintenance-from-app.sh')
    log=pathlib.Path('/var/lib/mappi3/app-online-maintenance.log')
    body=f"""#!/bin/bash
set -u
LOG={str(log)!r}
exec >>"$LOG" 2>&1
echo "=== app online maintenance $(date -Is) ==="
restore() {{
  echo "restoring MapPI3 hotspot"
  nmcli radio wifi on || true
  rfkill unblock wifi || true
  nmcli connection modify MapPI3-hotspot connection.autoconnect yes connection.autoconnect-priority 100 802-11-wireless.powersave 2 ipv4.method shared || true
  nmcli connection up MapPI3-hotspot || true
  iw dev wlan0 set power_save off 2>/dev/null || true
  echo "final active:"; nmcli -t -f NAME,TYPE,DEVICE connection show --active || true
  echo "=== done $(date -Is) ==="
}}
trap restore EXIT
nmcli radio wifi on || true
rfkill unblock wifi || true
nmcli connection modify MapPI3-home 802-11-wireless.ssid {json.dumps(ssid)} 802-11-wireless-security.key-mgmt wpa-psk 802-11-wireless-security.psk {json.dumps(password)} connection.autoconnect yes connection.autoconnect-priority 50 ipv4.method auto ipv4.ignore-auto-dns yes ipv4.dns '1.1.1.1 8.8.8.8' || true
nmcli connection down MapPI3-hotspot || true
sleep 2
nmcli connection up MapPI3-home || true
sleep 24
echo "active:"; nmcli -t -f NAME,TYPE,DEVICE connection show --active || true
echo "routes:"; ip route || true
echo "dns:"; cat /etc/resolv.conf || true; getent hosts api.open-meteo.com || true; getent hosts deb.debian.org || true
python3 - <<'PY' || true
import urllib.request
for url in ['https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&current=temperature_2m','https://api.github.com']:
    try:
        r=urllib.request.urlopen(url,timeout=10); print(url, r.status)
    except Exception as e: print(url, 'ERR', repr(e))
PY
echo "weather:"; curl -sS --max-time 20 'http://127.0.0.1:{PORT}/api/weather?lat={urllib.parse.quote(lat)}&lon={urllib.parse.quote(lon)}&days={urllib.parse.quote(days)}&timezone={urllib.parse.quote(tz)}' || true; echo
echo "noaa weather:"; curl -sS --max-time 30 'http://127.0.0.1:{PORT}/api/noaa-weather?lat={urllib.parse.quote(lat)}&lon={urllib.parse.quote(lon)}&force=1' || true; echo
echo "ai verify:"; curl -sS --max-time 20 -H 'Content-Type: application/json' -d '{{"category":"plant"}}' http://127.0.0.1:{PORT}/api/command/field-ai-verify || true; echo
echo "vnc:"; curl -sS --max-time 10 http://127.0.0.1:{PORT}/api/vnc/status || true; echo
"""
    script.write_text(body); os.chmod(script,0o700)
    r=sh(f'systemd-run --unit=mappi3-app-online-maintenance --collect {script}', timeout=10)
    st=read_state(); st['online_maintenance_started_at']=time.time(); st['online_maintenance_log']=str(log); st['online_maintenance_ssid']=ssid; write_state(st)
    return {'ok': r.get('ok'), 'message':'Started online maintenance. The hotspot will drop briefly, then restore automatically. Reconnect to MapPI3 in about 60-120 seconds.', 'log': str(log), 'output': r.get('output','')[-1200:]}

def online_maintenance_log():
    p=pathlib.Path('/var/lib/mappi3/app-online-maintenance.log')
    try: content=p.read_text()[-6000:]
    except Exception as e: content=str(e)
    return {'ok': p.exists(), 'log': str(p), 'content': content}

def harden_hotspot():
    cmds = [
        "nmcli connection modify MapPI3-hotspot connection.autoconnect yes connection.autoconnect-priority 100 802-11-wireless.powersave 2 ipv4.method shared || true",
        "iw dev wlan0 set power_save off 2>/dev/null || true",
        "mkdir -p /etc/NetworkManager/conf.d && printf '[connection]\nwifi.powersave = 2\n' > /etc/NetworkManager/conf.d/99-mappi3-wifi-powersave.conf",
        "rfkill unblock wifi || true",
        "nmcli radio wifi on || true"
    ]
    out=[]
    for c in cmds: out.append(sh(c, timeout=15)['output'])
    st=read_state(); st['hotspot_hardened_at']=time.time(); write_state(st)
    return {'ok': True, 'message': 'Hotspot hardened: autoconnect priority raised and Wi-Fi power-save disabled.', 'output': '\n'.join(out)[-4000:], 'state': st}

def vnc_status():
    services=['vncserver-x11-serviced.service','wayvnc.service','x11vnc.service']
    found=[]
    for svc in services:
        r=sh(f'systemctl is-enabled {svc} 2>/dev/null; systemctl is-active {svc} 2>/dev/null', timeout=5)['output'].strip().splitlines()
        found.append({'service': svc, 'enabled': r[0] if r else 'unknown', 'active': r[1] if len(r)>1 else 'unknown'})
    bins=sh('command -v vncserver-x11 || command -v wayvnc || command -v x11vnc || true', timeout=5)['output'].strip().splitlines()
    active=[f for f in found if f.get('active')=='active']
    return {'ok': True, 'installed_bins': bins, 'services': found, 'summary': ('active: '+', '.join(f['service'] for f in active)) if active else ('installed but not active' if bins else 'not installed yet')}

def plugin_update(payload):
    st=read_state(); features=st.get('features') if isinstance(st.get('features'),dict) else {}
    key=str(payload.get('key') or '').strip(); enabled=bool(payload.get('enabled'))
    if not key: return {'ok': False, 'error': 'key required'}
    features[key]=enabled; st['features']=features; st['features_updated_at']=time.time(); write_state(st)
    return {'ok': True, 'features': features}

PLUGIN_ROOTS = [pathlib.Path('/opt/mappi3/plugins'), pathlib.Path('/var/lib/mappi3/plugins-src'), pathlib.Path('/boot/mappi3/plugins')]
PLUGIN_STATE = pathlib.Path('/var/lib/mappi3/plugins')

def _safe_plugin_id(value):
    raw=str(value or '').strip().lower()
    return ''.join(c for c in raw if c.isalnum() or c in ('-','_'))[:80]

def plugin_registry():
    packs={}
    for root in PLUGIN_ROOTS:
        if not root.exists(): continue
        for meta in root.glob('*/plugin.json'):
            try:
                data=json.loads(meta.read_text())
                pid=_safe_plugin_id(data.get('id') or meta.parent.name)
                if not pid: continue
                marker=PLUGIN_STATE/pid/'installed.json'
                installed={}
                if marker.exists():
                    try: installed=json.loads(marker.read_text())
                    except Exception: installed={'status':'installed'}
                packs[pid]={**data,'id':pid,'source':str(meta.parent),'installed':marker.exists(),'installed_marker':str(marker),'installed_state':installed}
            except Exception as e:
                packs[meta.parent.name]={'id':meta.parent.name,'source':str(meta.parent),'error':str(e),'installed':False}
    return packs

def plugin_status(payload=None):
    packs=plugin_registry()
    return {'ok': True, 'root_candidates':[str(x) for x in PLUGIN_ROOTS], 'installed_root':str(PLUGIN_STATE), 'count':len(packs), 'installed_count':sum(1 for p in packs.values() if p.get('installed')), 'packs':packs, 'time':time.time()}

def _run_plugin_script(pid, script_name):
    packs=plugin_registry(); pack=packs.get(pid)
    if not pack: return {'ok': False, 'id':pid, 'error':'plugin not found'}
    source=pathlib.Path(pack.get('source') or '')
    script=source/script_name
    if not script.exists(): return {'ok': False, 'id':pid, 'error':f'{script_name} missing', 'source':str(source)}
    if not str(script.resolve()).startswith(str(source.resolve())): return {'ok': False, 'id':pid, 'error':'unsafe script path'}
    os.chmod(script, os.stat(script).st_mode | 0o755)
    out=sh(f'cd {json.dumps(str(source))} && bash {json.dumps(str(script))}', timeout=180)
    st=read_state(); installed=st.get('installed_plugins') if isinstance(st.get('installed_plugins'),dict) else {}
    installed[pid]={'installed': script_name=='install.sh', 'updated_at':time.time(), 'source':str(source), 'output':out.get('output','')[-1200:]}
    st['installed_plugins']=installed; write_state(st)
    return {'ok': out.get('ok'), 'id':pid, 'script':script_name, 'source':str(source), 'output':out.get('output','')[-2500:], 'status':plugin_status().get('packs',{}).get(pid,{})}

def plugin_install(payload=None):
    payload=payload or {}; pid=_safe_plugin_id(payload.get('id') or payload.get('key'))
    if not pid: return {'ok': False, 'error':'id required'}
    return _run_plugin_script(pid, 'install.sh')

def plugin_uninstall(payload=None):
    payload=payload or {}; pid=_safe_plugin_id(payload.get('id') or payload.get('key'))
    if not pid: return {'ok': False, 'error':'id required'}
    return _run_plugin_script(pid, 'uninstall.sh')

def plugin_install_all(payload=None):
    payload=payload or {}; packs=plugin_registry(); ids=payload.get('ids') or payload.get('queue') or list(packs.keys())
    ids=[_safe_plugin_id(x) for x in ids if _safe_plugin_id(x)]
    results=[]
    for pid in ids:
        results.append(plugin_install({'id':pid}))
    ok=all(r.get('ok') for r in results)
    return {'ok': ok, 'requested':ids, 'installed':sum(1 for r in results if r.get('ok')), 'failed':[r for r in results if not r.get('ok')], 'results':results, 'status':plugin_status()}

def captive_status():
    active=sh('systemctl is-active mappi3-captive.service 2>/dev/null || true', timeout=5)['output'].strip()
    enabled=sh('systemctl is-enabled mappi3-captive.service 2>/dev/null || true', timeout=5)['output'].strip()
    port=sh("ss -lntp | grep ':80 ' || true", timeout=5)['output'].strip()
    return {'ok': active == 'active', 'active': active or 'unknown', 'enabled': enabled or 'unknown', 'port80': bool(port), 'summary': 'phone stay-connected portal active' if active=='active' else 'not active'}

def setup_captive(payload=None):
    script=pathlib.Path('/usr/local/bin/mappi3-captive.py')
    script.write_text('#!/usr/bin/env python3\nimport http.server, urllib.parse, time\nAPP=\'http://10.42.0.1:5050/\'\nPROBES={\'/generate_204\':(204,\'text/plain\',\'\'),\'/gen_204\':(204,\'text/plain\',\'\'),\'/hotspot-detect.html\':(200,\'text/html\',\'<HTML><HEAD><TITLE>Success</TITLE></HEAD><BODY>Success<br><a href="%s">Open MapPI3</a></BODY></HTML>\'%APP),\'/connecttest.txt\':(200,\'text/plain\',\'Microsoft Connect Test\'),\'/ncsi.txt\':(200,\'text/plain\',\'Microsoft NCSI\'),\'/canonical.html\':(200,\'text/html\',\'<meta http-equiv="refresh" content="0; url=%s">\'%APP)}\nclass H(http.server.BaseHTTPRequestHandler):\n    def _send(self,code,ctype,body):\n        raw=body.encode(); self.send_response(code); self.send_header(\'Content-Type\',ctype); self.send_header(\'Cache-Control\',\'no-store\'); self.send_header(\'Content-Length\',str(len(raw))); self.end_headers(); self.wfile.write(raw)\n    def do_GET(self):\n        p=urllib.parse.urlparse(self.path).path\n        if p in PROBES:\n            code,ctype,body=PROBES[p]; self._send(code,ctype,body); return\n        if p in (\'/\',\'/index.html\',\'/map\',\'/login\'):\n            self._send(200,\'text/html\',\'<!doctype html><meta name="viewport" content="width=device-width,initial-scale=1"><title>MapPI3</title><style>body{font-family:sans-serif;background:#07130d;color:#eaffef;padding:24px}a{color:#70f0a0;font-size:1.2rem}</style><h1>MapPI3 Trail Buddy</h1><p>No internet required. Stay on this Wi-Fi and open the trail app.</p><p><a href="\'+APP+\'">Open MapPI3 app</a></p><small>\'+time.ctime()+\'</small>\'); return\n        self.send_response(302); self.send_header(\'Location\',APP); self.end_headers()\n    def log_message(self,*a): pass\nhttp.server.ThreadingHTTPServer((\'0.0.0.0\',80),H).serve_forever()\n')
    os.chmod(script,0o755)
    service=pathlib.Path('/etc/systemd/system/mappi3-captive.service')
    service.write_text('[Unit]\nDescription=MapPI3 phone stay-connected captive helper\nAfter=network-online.target NetworkManager.service\nWants=network-online.target\n\n[Service]\nType=simple\nExecStartPre=/bin/sh -c \'for i in $(seq 1 45); do ip addr show wlan0 | grep -q "10.42.0.1" && exit 0; sleep 1; done; exit 0\'\nExecStart=/usr/bin/python3 /usr/local/bin/mappi3-captive.py\nRestart=always\nRestartSec=3\n\n[Install]\nWantedBy=multi-user.target\n')
    out=sh('systemctl daemon-reload && systemctl enable --now mappi3-captive.service && systemctl status --no-pager mappi3-captive.service | sed -n "1,12p"', timeout=30)
    st=read_state(); st['captive_portal_enabled_at']=time.time(); write_state(st)
    return {'ok': out.get('ok'), 'message':'Phone stay-connected captive portal enabled on port 80', 'status': captive_status(), 'output': out.get('output','')[-1200:]}

def setup_gps_pps(payload=None):
    backup = sh('STAMP=$(date +%Y%m%d-%H%M%S); mkdir -p /var/backups/mappi3-pps-setup; for f in /boot/firmware/cmdline.txt /boot/cmdline.txt /boot/firmware/config.txt /etc/default/gpsd; do [ -f "$f" ] && cp -a "$f" "/var/backups/mappi3-pps-setup/$(echo $f|tr / _).$STAMP.bak"; done', timeout=20)
    cmdline_script = r"""
python3 - <<'PY'
from pathlib import Path
src = Path('/proc/cmdline').read_text().strip().split()
bad = ('console=ttyAMA','console=ttyS','console=serial','kgdboc=ttyAMA','kgdboc=ttyS','kgdboc=serial')
parts = [t for t in src if not t.startswith(bad)]
if not any(x.startswith('root=') for x in parts):
    parts += ['console=tty1','root=/dev/mmcblk0p2','rootfstype=ext4','rootwait']
if not any(x.startswith('cfg80211.ieee80211_regdom=') for x in parts):
    parts.append('cfg80211.ieee80211_regdom=US')
seen = []
for part in parts:
    if part not in seen:
        seen.append(part)
Path('/tmp/mappi3-clean-cmdline.txt').write_text(' '.join(seen) + '\n')
PY
for f in /boot/firmware/cmdline.txt /boot/cmdline.txt; do [ -f "$f" ] && cp /tmp/mappi3-clean-cmdline.txt "$f" || true; done
"""
    cmdline = sh(cmdline_script, timeout=20)
    config = sh("CFG=/boot/firmware/config.txt; [ -f $CFG ] || CFG=/boot/config.txt; grep -q '^enable_uart=1' $CFG || echo 'enable_uart=1' >> $CFG; grep -q '^dtoverlay=pps-gpio,gpiopin=18' $CFG || echo 'dtoverlay=pps-gpio,gpiopin=18' >> $CFG", timeout=10)
    gpsd_script = r"""
python3 - <<'PY'
from pathlib import Path
p = Path('/etc/default/gpsd')
s = p.read_text() if p.exists() else 'START_DAEMON="true"\nUSBAUTO="false"\n'
lines = []
for line in s.splitlines():
    if line.startswith('DEVICES='):
        lines.append('DEVICES="/dev/serial0 /dev/pps0"')
    elif line.startswith('GPSD_OPTIONS='):
        lines.append('GPSD_OPTIONS="-n"')
    else:
        lines.append(line)
if not any(x.startswith('DEVICES=') for x in lines):
    lines.append('DEVICES="/dev/serial0 /dev/pps0"')
if not any(x.startswith('GPSD_OPTIONS=') for x in lines):
    lines.append('GPSD_OPTIONS="-n"')
p.write_text('\n'.join(lines) + '\n')
PY
"""
    gpsd = sh(gpsd_script, timeout=10)
    services = sh('systemctl mask serial-getty@ttyAMA0.service serial-getty@serial0.service || true; systemctl disable --now serial-getty@ttyAMA0.service serial-getty@serial0.service || true; systemctl daemon-reload; systemctl restart gpsd.socket gpsd || true', timeout=30)
    return {'ok': True, 'message':'GPS UART console disabled; GPIO18 PPS overlay configured. Reboot required for boot cmdline/overlay persistence.', 'backup': backup.get('output','')[-800:], 'cmdline': cmdline.get('output','')[-800:], 'config': config.get('output','')[-800:], 'gpsd': gpsd.get('output','')[-800:], 'services': services.get('output','')[-1200:]}

def disable_captive():
    out=sh('systemctl disable --now mappi3-captive.service || true', timeout=20)
    return {'ok': True, 'message':'Phone stay-connected captive portal disabled', 'status': captive_status(), 'output': out.get('output','')[-800:]}

def command(name, payload=None):
    payload=payload or {}
    if name not in ALLOWED: return {'ok': False, 'error': 'unknown command'}
    if name=='status': return status()
    if name=='gps-sample': return gps_sample()
    if name=='sense-mode': return set_sense_mode(payload.get('mode') or payload.get('sense_mode') or payload.get('orientationMode') or 'compass', payload)
    if name=='calibrate': return calibrate(payload.get('target') or 'all')
    if name=='harden-hotspot': return harden_hotspot()
    if name=='plugin-update': return plugin_update(payload)
    if name=='plugin-status': return plugin_status(payload)
    if name=='plugin-install': return plugin_install(payload)
    if name=='plugin-uninstall': return plugin_uninstall(payload)
    if name=='plugin-install-all': return plugin_install_all(payload)
    if name=='vnc-setup': return setup_vnc(payload)
    if name=='vnc-disable': return disable_vnc()
    if name=='weather-refresh': return pi_weather(payload)
    if name=='noaa-refresh': return noaa_weather(payload)
    if name=='online-maintenance': return start_online_maintenance(payload)
    if name=='gps-diagnose': return gps_diagnose()
    if name=='field-ai-verify': return field_ai_verify(payload)
    if name=='captive-setup': return setup_captive(payload)
    if name=='captive-disable': return disable_captive()
    if name=='captive-status': return captive_status()
    if name=='gps-pps-setup': return setup_gps_pps(payload)
    if name=='restart-web': return sh('systemctl restart mappi3-web.service', timeout=10)
    if name=='reboot': return sh('systemctl reboot', timeout=3)
    if name=='shutdown': return sh('systemctl poweroff', timeout=3)
    if name=='update-app': return sh('/usr/local/bin/mappi3-update-app.sh', timeout=120)
    if name=='connect-home-wifi': return connect_home_wifi(payload)
    if name=='toggle-hotspot':
        st=read_state(); st['hotspot_enabled']=not st.get('hotspot_enabled', True); write_state(st); return sh('/usr/local/bin/mappi3-hotspot.sh', timeout=40)


MEDIA_ROOT = pathlib.Path('/var/lib/mappi3/media')
MEDIA_EXTS = {'.mp3':'audio/mpeg','.ogg':'audio/ogg','.wav':'audio/wav','.m4a':'audio/mp4','.flac':'audio/flac','.mp4':'video/mp4','.webm':'video/webm','.mov':'video/quicktime'}

def media_library_status():
    MEDIA_ROOT.mkdir(parents=True, exist_ok=True)
    items=[]; total=0
    for p in MEDIA_ROOT.rglob('*'):
        try:
            if not p.is_file() or p.suffix.lower() not in MEDIA_EXTS: continue
            st=p.stat(); total += st.st_size
            rel=p.relative_to(MEDIA_ROOT).as_posix()
            kind='video' if MEDIA_EXTS[p.suffix.lower()].startswith('video') else 'audio'
            items.append({'id': hashlib.sha1(rel.encode()).hexdigest()[:12], 'name': p.stem.replace('_',' ').replace('-',' '), 'file': rel, 'url': '/media/'+urllib.parse.quote(rel), 'kind': kind, 'size_bytes': st.st_size, 'size_mb': round(st.st_size/1024/1024,2), 'modified': st.st_mtime, 'content_type': MEDIA_EXTS[p.suffix.lower()]})
        except Exception: pass
    items=sorted(items, key=lambda x:(x['kind'], x['name'].lower()))[:500]
    return {'ok': True, 'root': str(MEDIA_ROOT), 'count': len(items), 'total_mb': round(total/1024/1024,2), 'items': items, 'supported': sorted(MEDIA_EXTS.keys()), 'hint': 'Copy music/videos to /var/lib/mappi3/media on larger SD cards; stream them over the MapPI3 hotspot.'}

def media_manifest():
    data=media_library_status()
    if not data['items']:
        data['starter_collections']=[
            {'name':'Ambient starters','items':['rain','creek','forest','night insects','campfire','white noise'], 'note':'Generated in browser until real audio loops are installed.'},
            {'name':'Trail media folder','path':str(MEDIA_ROOT), 'note':'Add MP3/OGG/WAV/MP4/WEBM files here.'}
        ]
    return data

GAME_ROOT = pathlib.Path('/var/lib/mappi3/games')

def game_library_status():
    GAME_ROOT.mkdir(parents=True, exist_ok=True)
    games=[]
    for d in sorted([x for x in GAME_ROOT.iterdir() if x.is_dir()]):
        try:
            index=d/'index.html'
            if not index.exists(): continue
            meta={}
            mp=d/'mappi3-game.json'
            if mp.exists():
                try: meta=json.loads(mp.read_text())
                except Exception: meta={}
            rel=d.name
            size=0
            for f in d.rglob('*'):
                try:
                    if f.is_file(): size += f.stat().st_size
                except Exception: pass
            games.append({'id':rel,'title':meta.get('title') or rel.replace('-',' ').replace('_',' ').title(),'url':'/games/'+urllib.parse.quote(rel)+'/index.html','folder':str(d),'offline':True,'size_mb':round(size/1024/1024,2),'note':meta.get('note') or 'Local HTML5 game pack served offline from the MapPI3 hotspot.'})
        except Exception: pass
    return {'ok': True, 'root': str(GAME_ROOT), 'count': len(games), 'games': games, 'hint':'Place legal HTML5 game folders at /var/lib/mappi3/games/<game-id>/index.html. Example: /var/lib/mappi3/games/playmario/index.html. MapPI3 will serve them at /games/<game-id>/index.html offline over the hotspot.'}

class Handler(http.server.SimpleHTTPRequestHandler):
    def translate_path(self, path):
        path=urllib.parse.urlparse(path).path
        if path.startswith('/api/'): return str(APP_DIR/'index.html')
        if path.startswith('/media/'):
            rel=urllib.parse.unquote(path[len('/media/'):]).lstrip('/'); target=(MEDIA_ROOT/rel).resolve()
            try:
                if str(target).startswith(str(MEDIA_ROOT.resolve())) and target.is_file(): return str(target)
            except Exception: pass
            return str(APP_DIR/'index.html')
        if path.startswith('/games/'):
            rel=urllib.parse.unquote(path[len('/games/'):]).lstrip('/'); target=(GAME_ROOT/rel).resolve()
            try:
                if str(target).startswith(str(GAME_ROOT.resolve())) and target.is_file(): return str(target)
            except Exception: pass
            return str(APP_DIR/'index.html')
        p=APP_DIR/path.lstrip('/')
        if p.is_dir(): p=p/'index.html'
        if not p.exists(): p=APP_DIR/'index.html'
        return str(p)
    def end_headers(self):
        self.send_header('Access-Control-Allow-Origin','*'); self.send_header('Access-Control-Allow-Headers','Content-Type'); self.send_header('Access-Control-Allow-Methods','GET,POST,OPTIONS'); self.send_header('Cache-Control','no-store' if self.path.startswith('/api/') else 'public, max-age=60'); super().end_headers()
    def do_OPTIONS(self): self.send_response(204); self.end_headers()
    def json_response(self, data):
        raw=json.dumps(data).encode(); self.send_response(200); self.send_header('Content-Type','application/json'); self.send_header('Content-Length',str(len(raw))); self.end_headers(); self.wfile.write(raw)
    def read_json(self):
        try:
            length=int(self.headers.get('Content-Length','0') or 0); return json.loads(self.rfile.read(length).decode() or '{}') if length else {}
        except Exception: return {}
    def do_GET(self):
        if self.path.startswith('/api/status'): self.json_response(status()); return
        if self.path.startswith('/api/field-ai/categories'): self.json_response(field_ai_categories()); return
        if self.path.startswith('/api/field-ai/status'): self.json_response(field_ai_status()); return
        if self.path.startswith('/api/field-ai/history'): self.json_response(field_ai_history()); return
        if self.path.startswith('/api/field-ai/corrections'): self.json_response(field_ai_corrections()); return
        if self.path.startswith('/api/vnc/status'): self.json_response(vnc_status()); return
        if self.path.startswith('/api/captive/status'): self.json_response(captive_status()); return
        if self.path.startswith('/api/noaa-weather'):
            qs=urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query); self.json_response(noaa_weather({k:v[-1] for k,v in qs.items()})); return
        if self.path.startswith('/api/weather'):
            qs=urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query); self.json_response(pi_weather({k:v[-1] for k,v in qs.items()})); return
        if self.path.startswith('/api/online-maintenance/log'): self.json_response(online_maintenance_log()); return
        if self.path.startswith('/api/media/library'): self.json_response(media_manifest()); return
        if self.path.startswith('/api/games/library'): self.json_response(game_library_status()); return
        if self.path.startswith('/api/plugins'): self.json_response(plugin_status()); return
        if self.path.startswith('/api/sense'): self.json_response({'ok': True, 'sense': sense_snapshot(), 'state': read_state(), 'available_modes': SENSE_MODES, 'time': time.time()}); return
        return super().do_GET()
    def do_DELETE(self):
        if self.path.startswith('/api/field-ai/history'): self.json_response(field_ai_clear_history()); return
        self.send_error(404)
    def do_POST(self):
        payload=self.read_json()
        if self.path.startswith('/api/wifi-home'): self.json_response(connect_home_wifi(payload)); return
        if self.path.startswith('/api/sense-mode'): self.json_response(set_sense_mode(payload.get('mode') or payload.get('sense_mode') or 'compass', payload)); return
        if self.path.startswith('/api/calibrate'): self.json_response(calibrate(payload.get('target') or 'all')); return
        if self.path.startswith('/api/field-ai/analyze'): self.json_response(field_ai_analyze(payload)); return
        if self.path.startswith('/api/field-ai/corrections/vote'): self.json_response(field_ai_vote_correction(payload)); return
        if self.path.startswith('/api/field-ai/corrections'): self.json_response(field_ai_add_correction(payload)); return
        if self.path.startswith('/api/command/'): self.json_response(command(self.path.rsplit('/',1)[-1], payload)); return
        self.send_error(404)

if __name__ == '__main__':
    threading.Thread(target=sense_loop, daemon=True).start(); threading.Thread(target=joystick_loop, daemon=True).start()
    os.chdir(str(APP_DIR)); http.server.ThreadingHTTPServer(('0.0.0.0', PORT), Handler).serve_forever()
