# MapPI3 Discord telemetry

MapPI3 telemetry is intentionally run from the Garden/Oracle side by default, not from the Pi. That keeps Discord credentials off the field Pi while still letting Maple/Ganja-style automation post a truthful status snapshot through the existing Oracle → NukeBox → MapPI3 hotspot bridge.

## Source

- Script: `scripts/mappi3-discord-telemetry.py`
- Default bridge: `ssh nukebox` then `ssh mappi3@10.42.0.1`
- Default Discord destination: Maple channel `1517340758238036108`; override with `--channel-id` or `MAPPI3_DISCORD_CHANNEL_ID`
- Runtime state/cache: `~/.cache/mappi3-discord-telemetry-state.json`

## Fields posted

- Host, connection mode, uptime, core service states.
- Clock status and skew warning. This matters because the Pi can be hotspot-only with no internet/NTP, and GPS time may be invalid until the receiver has a real fix.
- GPS mode/fix/satellite count and location according to privacy mode.
- CPU/load/RAM/disk/temp/throttling.
- Power/PiSugar status when MapPI3 reports it.
- Sense HAT mode, fallback state, heading/cardinal, humidity, pressure.
- Optional next hike/location from env or `/var/lib/mappi3/state.json`.

## Privacy

Default location privacy is `rounded`: if there is a real GPS fix, coordinates are rounded to ~0.001°. Other supported modes:

- `disabled` — never post coordinates.
- `trail-name` — only say hidden/trail-name mode.
- `rounded` — coarse coordinates only.
- `exact` — exact coordinates; use only after explicit CAK3D approval for the target channel.

Set with:

```bash
MAPPI3_TELEMETRY_LOCATION_PRIVACY=rounded
MAPPI3_NEXT_HIKE="Grafton Notch scouting / next trail card TBD"
MAPPI3_DISCORD_CHANNEL_ID=1517340758238036108
```

The script reads env from `~/.hermes/profiles/maple/.env`, then `~/.hermes/.env`, plus process env. It accepts either `DISCORD_BOT_TOKEN` or `MAPPI3_DISCORD_BOT_TOKEN`.

## Dry run

```bash
python3 scripts/mappi3-discord-telemetry.py --dry-run
```

## Post once

```bash
python3 scripts/mappi3-discord-telemetry.py
```

## Suggested schedule

Use Hermes cron or systemd on the Garden/Oracle VM. Do **not** place Discord bot tokens on the trail Pi unless there is a specific, approved reason.

Hourly Hermes/systemd pattern:

```bash
python3 /home/ubuntu/MapPi3/scripts/mappi3-discord-telemetry.py --json
```

By default each telemetry run also corrects the Pi wall clock from the trusted Garden/Oracle collector clock when the Pi is reachable and skew is greater than 60 seconds. Disable that with:

```bash
MAPPI3_TELEMETRY_SYNC_PI_CLOCK=0
```

## Clock safety note

The Pi may currently think it is around July 18, 2026 while the real date is September 23, 2026, and gpsd can report a bogus 2019 TPV/SKY time indoors/no-fix. Telemetry therefore labels large skew and uses the collector/Garden time for Discord freshness. MapPI3 should not rely on Pi absolute wall-clock time for schedule decisions until NTP, a valid GPS TPV time, or a trusted maintenance bridge sets it.
