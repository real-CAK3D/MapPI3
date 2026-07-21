# Low-power Whisplay / Sense HAT game additions

Design target: Pi Zero/field-safe, readable on Whisplay, optional Sense HAT mirror, works with one button now and joystick later. Games must pause/yield to safety/navigation/weather alerts.

## Best additions

1. **Snake Trail**
   - Input: left/right/press; joystick later for direct turns.
   - Whisplay: 240×280 grid with high-contrast snake + apple.
   - Sense HAT: existing 8×8 snake mode can mirror head/body/apple.
   - Events: apple eaten, level up, crash.

2. **Trail Memory Tiles**
   - Input: press to reveal/select; joystick later moves cursor.
   - Low CPU: static card grid, timed pattern recall.
   - Field flavor: match icons for water, blaze, camp, ridge, dog stop.
   - Events: streak, miss, new pattern.

3. **Compass Catch**
   - Input: rotate/tilt Sense HAT or phone heading; press to lock.
   - Gameplay: point toward prompted cardinal/bearing before timer ends.
   - Doubles as compass calibration practice.
   - Events: bearing hit, near miss, calibration warning.

4. **Weather Dodge**
   - Input: one-button lane swap; joystick later up/down.
   - Gameplay: avoid storm/wind icons, collect water/sun icons.
   - Can use real weather risk chips to skin difficulty but not for safety decisions.
   - Events: water collected, storm hit, safe streak.

5. **Waypoint Runner**
   - Input: press/joystick to choose next marker.
   - Gameplay: pick correct trail marker sequence from active route POIs.
   - Reinforces route familiarity before hiking.
   - Events: marker found, wrong turn, route complete.

6. **Beacon Tapper**
   - Input: press in Morse/rhythm windows.
   - Gameplay: tap SOS / trail code pattern with forgiving timing.
   - Sense HAT mirror: flashes current beat.
   - Events: pattern complete, missed beat.

## Avoid / defer

- Physics-heavy games, scrolling tilemaps, particle storms, large sprites, audio-first games, network-required multiplayer.
- Anything that teaches unsafe navigation behavior or hides public-safety disclaimers.

## Shared game/event contract

Each game should emit tiny events compatible with the Pac-Man bridge:

```json
{
  "id": "game-name-ms-seq",
  "seq": 1,
  "type": "apple_eaten",
  "label": "Apple +5",
  "score_delta": 5,
  "score": 25,
  "created_at": 1784670000.123
}
```

Whisplay Dash can de-dupe by `id` and render a short popup without knowing game internals.
