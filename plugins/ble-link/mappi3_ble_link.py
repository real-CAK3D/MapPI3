#!/usr/bin/env python3
"""MapPI3 Bluetooth LE link.

Lets a paired phone read GPS, compass, pressure, battery and Herbie's state from the MapPI3 over
Bluetooth Low Energy, so the phone can keep its Wi-Fi off (or on another network) on the trail.

GATT service 6d617069-3301-4c6e-9b5e-6d6170693300 ("mapi" + 3301):
  status  ...3301  read (encrypted) + notify : compact JSON snapshot, refreshed every 2 s
  command ...3302  write (encrypted)         : {"cmd":"herbie-event","event":"...","ttl":20,"reason":"..."}

Security: every characteristic needs an encrypted (bonded) link, and the adapter is only pairable
while a pairing window is open (touch /run/mappi3/ble-pair-window, done by the agent command
"ble-pair-window"). Data comes from the local MapPI3 agent at http://127.0.0.1:5050.
"""
import json
import os
import time
import urllib.request

import dbus
import dbus.exceptions
import dbus.mainloop.glib
import dbus.service
from gi.repository import GLib

BLUEZ = 'org.bluez'
GATT_MANAGER = 'org.bluez.GattManager1'
ADV_MANAGER = 'org.bluez.LEAdvertisingManager1'
DBUS_OM = 'org.freedesktop.DBus.ObjectManager'
DBUS_PROP = 'org.freedesktop.DBus.Properties'
SERVICE_UUID = '6d617069-3301-4c6e-9b5e-6d6170693300'
STATUS_UUID = '6d617069-3301-4c6e-9b5e-6d6170693301'
COMMAND_UUID = '6d617069-3301-4c6e-9b5e-6d6170693302'
AGENT = os.environ.get('MAPPI3_AGENT', 'http://127.0.0.1:5050')
PAIR_FLAG = '/run/mappi3/ble-pair-window'
PAIR_SECONDS = 120


def log(*a):
    print('[mappi3-ble]', *a, flush=True)


def agent_get(path, timeout=3):
    with urllib.request.urlopen(AGENT + path, timeout=timeout) as r:
        return json.loads(r.read().decode('utf-8'))


def agent_post(path, body, timeout=4):
    req = urllib.request.Request(AGENT + path, data=json.dumps(body).encode('utf-8'), headers={'Content-Type': 'application/json'})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode('utf-8'))


def snapshot():
    """Small JSON (well under 512 bytes) with what the phone needs on the trail."""
    try:
        s = agent_get('/api/status')
    except Exception as e:  # agent restarting
        return json.dumps({'ok': False, 'err': str(e)[:60], 't': int(time.time())}, separators=(',', ':'))
    g, se, p = s.get('gps') or {}, s.get('sense') or {}, s.get('power') or {}
    ev = (s.get('state') or {}).get('herbie_event') or {}
    cal = s.get('herbie_calendar') or {}
    def num(v, nd=6):
        try:
            return round(float(v), nd)
        except (TypeError, ValueError):
            return None
    out = {
        'ok': True, 't': int(time.time()),
        'g': {'f': bool(g.get('fix')), 'la': num(g.get('lat')), 'lo': num(g.get('lon')), 'al': num(g.get('alt'), 1), 's': g.get('satellites'), 'e': num(g.get('eph'), 1), 'm': g.get('mode')},
        's': {'ok': bool(se.get('ok')), 'h': num(se.get('compass'), 1), 'c': se.get('compass_cardinal'), 'p': num(se.get('pressure'), 1), 'hu': num(se.get('humidity'), 0)},
        'b': {'p': num(p.get('percent'), 0), 'c': bool(p.get('charging'))},
        'h': {'n': ev.get('name'), 'u': ev.get('until'), 'r': (ev.get('reason') or '')[:40], 'cal': (cal.get('reason') or '')[:40]},
    }
    return json.dumps(out, separators=(',', ':'))


class Application(dbus.service.Object):
    def __init__(self, bus):
        self.path = '/org/mappi3/ble'
        self.services = []
        dbus.service.Object.__init__(self, bus, self.path)

    @dbus.service.method(DBUS_OM, out_signature='a{oa{sa{sv}}}')
    def GetManagedObjects(self):
        resp = {}
        for s in self.services:
            resp[s.get_path()] = s.get_properties()
            for c in s.characteristics:
                resp[c.get_path()] = c.get_properties()
        return resp


class Service(dbus.service.Object):
    def __init__(self, bus, index, uuid):
        self.path = f'/org/mappi3/ble/service{index}'
        self.uuid = uuid
        self.characteristics = []
        dbus.service.Object.__init__(self, bus, self.path)

    def get_path(self):
        return dbus.ObjectPath(self.path)

    def get_properties(self):
        return {'org.bluez.GattService1': {'UUID': self.uuid, 'Primary': True, 'Characteristics': dbus.Array([c.get_path() for c in self.characteristics], signature='o')}}


class Characteristic(dbus.service.Object):
    def __init__(self, bus, index, uuid, flags, service):
        self.path = f'{service.path}/char{index}'
        self.uuid, self.flags, self.service = uuid, flags, service
        dbus.service.Object.__init__(self, bus, self.path)

    def get_path(self):
        return dbus.ObjectPath(self.path)

    def get_properties(self):
        return {'org.bluez.GattCharacteristic1': {'Service': self.service.get_path(), 'UUID': self.uuid, 'Flags': self.flags, 'Descriptors': dbus.Array([], signature='o')}}

    @dbus.service.method(DBUS_PROP, in_signature='s', out_signature='a{sv}')
    def GetAll(self, interface):
        return self.get_properties()['org.bluez.GattCharacteristic1']

    @dbus.service.signal(DBUS_PROP, signature='sa{sv}as')
    def PropertiesChanged(self, interface, changed, invalidated):
        pass


class StatusChar(Characteristic):
    def __init__(self, bus, index, service):
        super().__init__(bus, index, STATUS_UUID, ['encrypt-read', 'notify'], service)
        self.notifying = False
        self.value = snapshot().encode('utf-8')
        GLib.timeout_add_seconds(2, self.refresh)

    def refresh(self):
        self.value = snapshot().encode('utf-8')
        if self.notifying:
            self.PropertiesChanged('org.bluez.GattCharacteristic1', {'Value': dbus.Array([dbus.Byte(b) for b in self.value], signature='y')}, [])
        return True

    @dbus.service.method('org.bluez.GattCharacteristic1', in_signature='a{sv}', out_signature='ay')
    def ReadValue(self, options):
        offset = int(options.get('offset', 0))
        return dbus.Array([dbus.Byte(b) for b in self.value[offset:]], signature='y')

    @dbus.service.method('org.bluez.GattCharacteristic1')
    def StartNotify(self):
        self.notifying = True
        log('phone subscribed')

    @dbus.service.method('org.bluez.GattCharacteristic1')
    def StopNotify(self):
        self.notifying = False
        log('phone unsubscribed')


class CommandChar(Characteristic):
    def __init__(self, bus, index, service):
        super().__init__(bus, index, COMMAND_UUID, ['encrypt-write'], service)

    @dbus.service.method('org.bluez.GattCharacteristic1', in_signature='aya{sv}')
    def WriteValue(self, value, options):
        try:
            msg = json.loads(bytes(value).decode('utf-8'))
        except Exception:
            raise dbus.exceptions.DBusException('org.bluez.Error.InvalidValueLength', 'bad json')
        if msg.get('cmd') != 'herbie-event' or not str(msg.get('event', '')).replace('-', '').isalnum():
            raise dbus.exceptions.DBusException('org.bluez.Error.NotPermitted', 'only herbie-event is allowed over Bluetooth')
        try:
            agent_post('/api/command/herbie-event', {'event': msg['event'], 'ttl': max(5, min(600, int(msg.get('ttl', 20)))), 'reason': str(msg.get('reason', ''))[:60]})
        except Exception as e:
            log('herbie-event failed', e)


class Advertisement(dbus.service.Object):
    PATH = '/org/mappi3/ble/advert0'

    def __init__(self, bus):
        dbus.service.Object.__init__(self, bus, self.PATH)

    @dbus.service.method(DBUS_PROP, in_signature='s', out_signature='a{sv}')
    def GetAll(self, interface):
        return {'Type': 'peripheral', 'ServiceUUIDs': dbus.Array([SERVICE_UUID], signature='s'), 'LocalName': dbus.String('MapPI3'), 'Includes': dbus.Array(['tx-power'], signature='s')}

    @dbus.service.method('org.bluez.LEAdvertisement1')
    def Release(self):
        log('advertisement released')


def find_adapter(bus):
    objs = dbus.Interface(bus.get_object(BLUEZ, '/'), DBUS_OM).GetManagedObjects()
    for path, ifaces in objs.items():
        if GATT_MANAGER in ifaces and ADV_MANAGER in ifaces:
            return path
    return None


def pair_window_watch(bus, adapter_path):
    """Pairable only while a window is open; never permanently discoverable."""
    props = dbus.Interface(bus.get_object(BLUEZ, adapter_path), DBUS_PROP)
    state = {'open_until': 0}

    def tick():
        now = time.time()
        if os.path.exists(PAIR_FLAG):
            try:
                os.remove(PAIR_FLAG)
            except OSError:
                pass
            state['open_until'] = now + PAIR_SECONDS
            log(f'pairing window open for {PAIR_SECONDS} s')
        want = now < state['open_until']
        try:
            props.Set('org.bluez.Adapter1', 'Pairable', dbus.Boolean(want))
            props.Set('org.bluez.Adapter1', 'Discoverable', dbus.Boolean(want))
            if want:
                props.Set('org.bluez.Adapter1', 'PairableTimeout', dbus.UInt32(PAIR_SECONDS))
                props.Set('org.bluez.Adapter1', 'DiscoverableTimeout', dbus.UInt32(PAIR_SECONDS))
        except dbus.exceptions.DBusException as e:
            log('adapter property', e)
        return True

    tick()
    GLib.timeout_add_seconds(2, tick)


def main():
    dbus.mainloop.glib.DBusGMainLoop(set_as_default=True)
    bus = dbus.SystemBus()
    adapter = find_adapter(bus)
    if not adapter:
        log('no Bluetooth LE adapter found; is Bluetooth enabled?')
        raise SystemExit(1)
    dbus.Interface(bus.get_object(BLUEZ, adapter), DBUS_PROP).Set('org.bluez.Adapter1', 'Powered', dbus.Boolean(True))
    app = Application(bus)
    svc = Service(bus, 0, SERVICE_UUID)
    svc.characteristics = [StatusChar(bus, 0, svc), CommandChar(bus, 1, svc)]
    app.services = [svc]
    adv = Advertisement(bus)
    loop = GLib.MainLoop()
    gatt = dbus.Interface(bus.get_object(BLUEZ, adapter), GATT_MANAGER)
    advm = dbus.Interface(bus.get_object(BLUEZ, adapter), ADV_MANAGER)
    gatt.RegisterApplication(app.path, {}, reply_handler=lambda: log('GATT service registered'), error_handler=lambda e: (log('GATT register failed', e), loop.quit()))
    advm.RegisterAdvertisement(Advertisement.PATH, {}, reply_handler=lambda: log('advertising as MapPI3'), error_handler=lambda e: log('advertise failed', e))
    pair_window_watch(bus, adapter)
    loop.run()


if __name__ == '__main__':
    main()
