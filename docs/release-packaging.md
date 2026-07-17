# MapPI3 release packaging lanes

MapPI3 is Pi-first: the primary deliverable is a Raspberry Pi image/app that boots into the hotspot trail OS. The Vercel/PWA app remains the no-Pi fallback and uses browser/phone sensors plus web data where Pi hardware APIs are unavailable.

## Package lanes

1. **mappi3-base** — base Pi image/app: hotspot, local app, GPS/PPS hooks, Sense HAT hardware/simulator surface, Wi-Fi/Tailscale onboarding, core route/offline shell.
2. **mappi3-plugins** — base plus optional plugins: NOAA/weather, Sense HAT games, GPS voice nav, Bluetooth sensors, debug VNC, themes.
3. **mappi3-plugins-data** — plugins plus data packs: offline library, forage media, regional maps/tiles, field AI starter assets.

The live package manifest scaffold is `public/releases/mappi3-packages.json`. Artifact URLs are placeholders until CI/image build publishing is wired to GitHub Releases/packages.

## Offline map pack policy

Default map/data planning radius is 300 miles around the user's saved home/account origin, with phone/Pi GPS fallback. The app should show what will be downloaded before fetching large packs.

## Safety/recovery

Wi-Fi credentials are saved on the Pi via NetworkManager and are not returned by APIs or committed. Any Wi-Fi join flow must keep hotspot restore instructions visible, because switching `wlan0` from AP to client mode can drop the phone connection.
