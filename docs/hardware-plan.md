# Hardware Plan

## Target

- Raspberry Pi Zero 2 WH
- GPS module or USB GPS dongle using `gpsd`
- Raspberry Pi Sense HAT with LED matrix and IMU/environment sensors
- Phone browser as primary screen

## Sense HAT compass behavior

The LED matrix can be enabled from the app. When enabled, it points north using a calibrated compass/IMU heading.

### Calibration flow

1. Open Field Kit.
2. Tap Calibrate Sense HAT.
3. Hold Pi flat and away from metal/magnets.
4. Rotate slowly in a figure-eight.
5. Turn 360° once.
6. Save calibration and show quality: Good / Okay / Retry.

### Bag mode

Because the Pi may be tossed in a bag, MapPi3 should support:

- smoothing heading changes
- detecting magnetic interference
- falling back to GPS-derived heading while moving
- warning when stopped heading is unreliable

## LED colors

- Blue/white: north
- Green: next waypoint direction
- Yellow: weak GPS / caution
- Red: off-route or urgent alert
