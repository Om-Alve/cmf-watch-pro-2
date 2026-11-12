# Faceclaw remote for CMF Watch Pro 2 (stock-firmware patch)

Adds a "Faceclaw remote" screen to the stock CMF Watch Pro 2 firmware (1.0.0.73, JX402) that sends
crown, touch and swipe gestures to Faceclaw on Android as Classic Bluetooth HID consumer keys
(read by [g2-ring-remote](https://github.com/Om-Alve/g2-ring-remote)), while all stock features
keep working. It replaces the Voice Assistant row in the app list.

Status: developed in the QEMU emulator from `cmf-watch-utils`, then flashed to a real watch over
BLE with the stock OTA service (see "Real watch" below). Flashing can brick a watch; there is no
proven BLE-only recovery.

Not in this repo: the stock firmware (`re/app_073.bin`), built apps and OTA packages
(`patch/build/`, `dist/`), emulator runs (`runs/`), hardware logs (they hold pairing keys) and
the one-off probe scripts and SDK checkouts under `re/agent-*`. Their findings are in `re/notes/`.
Get the stock 1.0.0.73 firmware via `cmf-watch-utils`, extract the app partition to
`re/app_073.bin`, then build with the commands below.

## Layout

- `tools/emu.py` scripted QEMU run: boot a stock or patched app, inject input, take screenshots.
  Input events: `t DOWN X Y` touch, `c 0|1` crown press, `r DELTA` crown rotation (80 = one step).
- `patch/` code cave built with arm-none-eabi-gcc, linked at `0x1025A100` (after the stock image),
  plus BL redirects into it. `python3 patch/build.py STOCK_APP OUT_APP`.
- `re/` reverse-engineering helpers (`xrefs.py` finds BL callers of an address); `re/notes/` findings.
- `tools/trace.py` emulator + gdb: logs register values at code addresses during a scripted run.
- `sim/` simulated phone: `sim/run_phone.sh RUN_DIR` replays the keys the emulated watch requested
  (`faceclaw-remote: key N` in uart0.log) through g2-ring-remote's real Router + FaceclawSender
  (`sim/watch.conf`) into a mock Faceclaw input API; gestures land in RUN_DIR/faceclaw-gestures.jsonl.
  The Bluetooth radio link itself is not simulated (no phone in QEMU, so the stock HID code sees no connection).

## Setup (once)

Emulator runtime and fixtures live in `../cmf-watch-utils` (runtime/, fixtures/). See its docs:
emulator installation + first boot. Requires git-lfs, uv, Homebrew glib pixman dtc tcl-tk
arm-none-eabi-gcc arm-none-eabi-gdb.

```
python3 patch/build.py ../cmf-watch-utils/dumps/binaries/app/app_073.bin patch/build/app_patched.bin   # add --debug for the boot log hook (never flash)
python3 patch/build.py re/app_073.bin patch/build/app_icon.bin --icon patch/icon/faceclaw_icon.bin       # same + Faceclaw app-list icon
uv run --project ../cmf-watch-utils python tools/emu.py --app patch/build/app_patched.bin --output runs/NAME --seconds 20
```

## Findings

- ACTH header: `+0x18` data size (from 0x200), `+0x1C` makes `sum32(data)+x == 0xFFFFFFFF`,
  `+0x20` makes `sum32(header[0:0x200]) == 0xFFFFFFFF`. Stock 1.0.0.73 satisfies both, matching
  the SDK scheme used by firmware-wp2-badapple. build.py regenerates them.
- App partition (NOR) is 0x34B000; stock uses 0x25A080, so ~0.98 MB is free for new code.
- `0x1014C818` is the Zephyr log call: `(ids, fmt, arg)`.
- Gate 1 passed in QEMU: cave code ran at boot (hooked BL at `0x10054882` -> `system_app_launch`),
  logged, returned to stock; UI identical to stock afterwards.

- Stock HID (Classic BT, L2CAP): report id 2 = 8-bit consumer bitmask, bit0..7 =
  0xEA VOLUMEDOWN, 0xE9 VOLUMEUP, 0xE2 MUTE, 0xCD PLAYPAUSE, 0xB6 PREVIOUSSONG, 0xB5 NEXTSONG,
  0x83 LAST, 0xB4 REWIND (descriptor at 0x10247029).
  `0x1015EE8C(report_id)`: if HID connected, sends `[id, 0x01]` then `[id, 0x00]` (bit0 only);
  otherwise starts HID connect (`0x101D5E22`) and sends after connect (2 s timer).
  `0x1015EDAC(conn, 1, buf, len)` sends an arbitrary report (length checked per report id).
  `0x101D5C60()` returns the phone connection; `0x1015BA2C(conn)` its HID state (`+9` bit2 = connected).
  Camera shutter = `0x101D0E60` -> `0x1015EE8C(2)` (Volume Down).

- Remote screen (`patch/remote_view.c`): registered in the unused `alipay_main_view` registry slot
  (id 0x2C, entry 115), opened from the app list's Voice Assistant row (action word at 0x101EB008).
  Borrows the Voice Assistant scene id (0x30BD0452) because the stock layout step only runs after a
  scene load; it builds its own LVGL widgets on top. Notes from agents: `re/notes/{views,input,lvgl}.md`,
  callable stock API in `re/notes/stock_api.ld` (spot-checked; `0x10127E7C` is lv_obj_clear_flag).
- Remote UI (design 2 "Dot matrix", picked from `design/remote-concepts.html`, 2026-11-11):
  link LED at the top (white = phone connection up, accent = none), two-line clock in the watch's
  dot font `/NAND:A/nm104N.font` (digits only), one status word in `/NAND:A/font36N.font` (dot font
  with letters): READY (grey) / NO LINK (accent) / the command just sent (accent, ~1.5 s).
  `nm48N` has almost no glyphs; `/NAND:C/sans32.font` is not a 64-byte bitmap font (loading it into
  a small buffer crashed); `lv_mem_alloc` from patch code faulted, so fonts live in the view ctx.
  Stock calls: time `0x100C14B4(rtc_time*)` (local time: {sec,min,hour,mday,mon,wday,u16 year}),
  phone link `0x101D5C60()` (the connection HID keys go out on; self-locking), vibration
  `0x100E08B8(38, &pattern, 4)` = ux2sys "vibrate at the user's strength" (pattern 6 = 60 ms per
  command, 8 = 20 ms per crown step, same as stock list haptics; level "off" gives no buzz).
  A 500 ms lv_timer refreshes clock, link and the status word. Verified: `runs/dot-ui2` (states,
  vibration calls), `runs/dot-ui3` (linked state forced via gdb), `runs/dot-e2e1` (all 8 gestures
  reach the simulated phone), `runs/dot-min1` (minimal build). 24-hour clock only for now.
- Input on the remote screen: crown turn = LVGL event 45 on the registered knob object
  (param int32, +-30 per detent; emulator `r -80` = +30 = down the list, same as the stock app list);
  crown press = view key callback values 0x20000001/0x04000001 (consumed); swipe right = stock back.
- Row label: `patch/applist_label.c` wraps the app list's text-node loader (`0x10184A5C`, called at
  `0x1005ED18` list style and `0x1005EBFE` grid style). After the stock load it rewrites the
  Voice Assistant label (node `0xDFC8EA0F`) in place to "Faceclaw" (only if the loaded string is at
  least as long, so the heap buffer is never overrun or replaced). Works for any language; the icon
  is unchanged. Verified in the list style (`runs/e2e3`); grid style is untested.
- Mapping: crown down/up -> LAST/VOLUMEUP (scroll-down/up), tap -> PLAYPAUSE (click),
  double tap -> REWIND (double-click/back), hold -> NEXTSONG (long-press), tap-then-hold ->
  PREVIOUSSONG (short-then-long-press), crown press -> MUTE (voice-toggle). VOLUMEDOWN is left to
  the stock camera shutter (g2-ring-remote passes it back to Android). Crown long-press opens the
  stock Voice Assistant (view 0xCF), whose app-list row the remote took over.
- Review fixes (Fable 5.2 review, 2026-11-10):
  - HID idle disconnect disabled: tbb case 3 at 0x1015EF7D 0x13 -> 0x17 (state 3 resets to 0
    instead of calling the HID disconnect 0x101D5E2C after the 5 s idle timer).
  - The remote primes the HID link when it opens (`remote_prime`, param 0x20, sends nothing).
  - Keys that would be sent from the reconnect path (`0x1015EF88`, after a fresh connect) are
    dropped for remote keys (`hid_press_after_connect`), so a key never reaches Android before
    g2-ring-remote can grab the new input node. The camera parameter (2) is still sent.
  - Boot hook only in `--debug` builds; flash builds run cave code only from the app list, the
    remote screen and HID sends.
  - Tap state resets if a second press never resolved (tap then drag); crown short press only
    counts when this screen saw the press start (wake press guard).
  - Verified with `tools/hid_force.py` (gdb fakes a connected phone): exact report bytes for all
    8 keys, camera shutter unchanged ({02 01},{02 00}), prime sends nothing, reconnect path drops
    remote keys and still sends the camera report.

- App-list icon (optional, `--icon`): the image loader `0x101848D4(scene, ids, out, sizes, count)`
  fills 12-byte LVGL image descriptors `{header, data_size, data}`. The Voice Assistant icon (node
  `0x6538D2E9`) is header `0x0C018005` (cf 5 TRUE_COLOR_ALPHA = RGB565 LE + A8, 96x96),
  0x6C00 bytes, data in resource-manager RAM (`0x38137BC0` in the emulator). Unload
  (`0x101D775A` -> `0x101866D4`) releases `data` back to the resource cache, so the pointer must
  not be replaced. `patch/icon/applist_icon.c` hooks the list (`0x1005ECD0`) and grid
  (`0x1005E996`) calls and copies 27,648 bytes of pixels over that buffer in place, only when
  node, header, size and pointer all match. The icon (`patch/icon/faceclaw_icon.bin`, 27.6 KB in the
  cave) comes from `tools/make_icon.py`: the glyph of faceclaw/images/faceclaw-logo.png in white on
  the stock circle (the alpha edge is taken from the dumped stock icon `re/icon/stock16.bin`).
  Verified in the list style (`runs/icon-boot1..3`: icon shows, survives back + reopen, remote and
  1 s crown hold -> Voice Assistant still work; a 2.5 s hold opens the stock power menu). Grid style untested.
  Hardware risk: if the GPU reads the buffer through a stale data cache the icon could look
  wrong (cosmetic); the LVGL GPU driver has its own `lv_gpu_acts_flush_dcache`.

## Status (emulator)

- End-to-end simulation passes (`runs/e2e2`): every gesture reaches the mock Faceclaw as the right
  gesture through g2-ring-remote's real Router/FaceclawSender. Five open/close cycles leave no faults
  and stock apps still open afterwards (`runs/repeat1`).
- Not covered by the emulator: the Bluetooth HID link to a phone, physical crown direction, screen
  timeout/sleep while the remote is open (emulator keeps the screen awake), battery.

## Packages (nothing here talks to a watch)

```
python3 patch/build.py re/app_073.bin patch/build/app_patched.bin
python3 patch/build.py re/app_073.bin patch/build/app_icon.bin --icon patch/icon/faceclaw_icon.bin
python3 tools/package.py            # dist/stock73-temp-only.bin (rehearsal), dist/remote-temp-only.bin
                                    # (minimal: remote + label), dist/remote-icon-temp-only.bin (+ icon)
python3 tools/verify_package.py dist/stock73-temp-only.bin --stock-app re/app_073.bin
python3 tools/verify_package.py dist/remote-temp-only.bin --stock-app re/app_073.bin \
        --allow-diff-from dist/allowed-diff-remote.json
python3 tools/verify_package.py dist/remote-icon-temp-only.bin --stock-app re/app_073.bin \
        --allow-diff-from dist/allowed-diff-remote-icon.json
python3 tools/verify_selftest.py    # corrupted variants must all fail
```

- TEMP-only outer AOTA (ota.xml + TEMP.bin id 254) + the stock AGPS trailer, same shape as the
  Bad Apple package the stock receiver accepted. The rehearsal package's TEMP is byte-identical to
  stock 1.0.0.73.
- `verify_package.py` is the only gate for the bootloader's ACTH checks (the emulator ignores
  them): header/data sums, image size, vectors, container CRCs and limits, AGPS and sdfs identity,
  and a byte-diff gate against the stock app (stock package: zero differences; remote: only the
  hook sites, data patches, header words and the cave).
- Emulator: both packages pass `emu preflight` and boot with `emu run --ota-image`.
- Virtual Bluetooth OTA (2026-11-10, netsimd from /opt/homebrew/share/android-commandlinetools/emulator):
  stock -> stock73 package, stock -> remote package, and remote -> stock73 (rollback) all transferred
  over simulated Bluetooth with the stock CMF OTA client (A041 01, end ack, ~4 min each), the guest
  rebooted, the modeled install wrote the expected app (sha256 match), and the installed result
  booted. The remote install passed the full gesture + simulated-phone test (`runs/vota-boot-remote`).
  Notes: guests must stay awake (`tools/emu.py` sets STOCK_AWAKE; the toolkit's headless mode lets
  the guest deep-sleep, which the compat ROM cannot run), and `emu recover` needs stock in the
  captured NOR to read the staged update, so the rollback install used a reader copy of the NOR with
  stock in the app area. The real install is done by the watch's bootloader, which is not modeled.
- Virtual Bluetooth OTA of the icon package (2026-11-11): stock -> dist/remote-icon-temp-only.bin
  transferred (A041 01, end sent), the modeled install wrote app sha256 87ffa988... (== app_icon.bin),
  and the installed watch booted with the Faceclaw icon, opened the remote, survived back + reopen
  and the 1 s crown hold (`runs/vota-boot-icon`).
- Virtual Bluetooth OTA of the minimal package with the dot-matrix UI (2026-11-11): transferred
  (A041 01, end sent), installed app sha256 1104de45... (== app_patched.bin), and the installed
  watch passed the 8-gesture simulated-phone test (`runs/vota-boot-dot`).

- **Real watch, stock rehearsal (2026-11-12):** Mac (Bleak, MTU 247) -> `dist/stock73-temp-only.bin`
  with `tools/ota_client.py --version 0100005a`. Pair OK (fw `01000049`), handshake A052 01 / A040 01,
  then the full run: the watch requested 1,318,788 bytes (51.5% of the package) in ~1.5 min, sent
  A041 01, END acked; afterwards `AT GETVERSION` = 1.0.0.73. Logs in `runs/hw/` (contain session data,
  keep local).

- **Real watch, minimal remote (2026-11-12):** `dist/remote-temp-only.bin` (sha256 277e4b96..., app
  1104de45...), same client and version. A052 01 / A040 01, 1,320,164 bytes served in ~70 s, A041 01,
  END acked, watch rebooted, `AT GETVERSION` = 1.0.0.73, and the user confirmed the remote works on
  the watch. Rollback = flash `dist/stock73-temp-only.bin` the same way.

- **Real-watch feedback (2026-11-12) -> build 2:** crown direction felt inverted (now: the turn that
  scrolls the stock list down sends VOLUMEUP/scroll-up), and the screen slept while the remote was
  open. Fix: `stock_screen_hold(0x2c)` (`0x101B59A8` = `0x100C1634(1, 0, id)`, per-id hold that takes
  a FULL wake lock for the JX user) in inflate and `stock_screen_release(0x2c)` (`0x100C1858`) in
  destroy, the same pairing stock views use with their view id (e.g. `0x10089E92`/`0x10089C2C`);
  `AT SETWAKELOCK 1/0` uses id 0x11F. Emulator (`runs/keepon2`): hold(0x2c) on open, release(0x2c)
  on swipe back, keys VOLUMEUP x2 / LAST for r -80 x2 / r +80, all other gestures unchanged, no
  faults. The emulator does not model the screen timeout, so the hold itself is checked on the watch.
  Packages rebuilt: remote-temp-only.bin sha256 bb1243d5... (app d6015fe9...), 193 checks.

- **Build 3 (2026-11-12): idle limit + touchscreen swipes.**
  - Screen hold ends after 10 min without a gesture (`IDLE_TICKS`), any gesture takes it again;
    checked with a 2 s test build (`runs/keepon3`: hold, idle release, re-hold per gesture, release on exit).
  - Swipes: focus(1) calls `0x10182238(0)` (ui-service view swiping off; stock views do the same) and
    focus(0) restores 30. The root clears GESTURE_BUBBLE and handles `LV_EVENT_GESTURE` (12):
    `lv_indev_get_gesture_dir` `0x101C4F7C`, `lv_indev_wait_release` `0x101C4FD4`,
    `lv_indev_get_point` `0x101C4F56` (32-bit coords). The touch controller also reports swipes as view
    keys `0xFFFF006E/6F/70/71` (down/up/left/right); unclaimed, 0x71 makes the global key fallback
    (`0x1005DD7E`) call view-back `0x101897FC`, so the remote's key handler claims all four.
  - Swipe right starting < 80 px from the left edge exits (one-shot timer -> `0x101897FC`).
    Long presses that moved > 40 px are ignored (slow swipes).
  - HID: swipes are two keys in one report (LAST + VOLUMEUP / MUTE / PREVIOUSSONG / NEXTSONG,
    `patch/hid.c` `key_bits`); g2-ring-remote reads keys per report for profiles that map
    `key.A+B` (`key.CODE_0x195+VOLUMEUP=swipe-up` etc.).
  - Emulator: `runs/swipe2`/`runs/swipe3` (all four swipes, edge exit, app-list swipe-back works
    afterwards), `runs/swipe-e2e` (8 original gestures unchanged), and `sim/run_phone.sh` delivers
    swipe-up/down/left/right to the mock Faceclaw through the real Router.
  - Package: remote-temp-only.bin sha256 2f0c63f9... (app 4e7fd3fa...), 193 checks.

- **Real watch, build 3 (2026-11-12):** flashed `dist/remote-temp-only.bin` sha256 2f0c63f9...
  First attempt: watch not advertising (phone connected). Second: A052 then no A040 and a link drop,
  because Nothing X had re-bound the watch and replaced the Mac's authkey; `cmf_watch.py pair` fixed
  it. Third: A040 01, 1,320,564 bytes in ~70 s, A041 01, END, reboot, GETVERSION 1.0.0.73.
  So: re-pair the Mac before each flash if the phone app reconnected in between.
- Phone: g2-ring-remote installed to /data/local/tmp/g2-ring-remote (token + Deepgram key copied
  on-device from the old ring-grab dir), config = repo default + the watch block
  (match.name = full BT name, swipe chords). Status: watch node grabbed (profile watch),
  Faceclaw ping ok.

Virtual OTA recipe (three terminals; ports as in the toolkit docs):
```
netsimd --instance 70 --hci-port 17310 --no-cli-ui --no-web-ui --no-shutdown
uv run --project ../cmf-watch-utils python tools/emu.py --nor ../cmf-watch-utils/local/paired-nor.bin \
    --allow-reboot --ota-snapshot --hci-port 17310 --qmp-port 17320 --seconds 600 --output runs/STAGE
(cd ../cmf-watch-utils && uv run cmf-watch-utils emu recover --fixtures fixtures --qemu runtime/qemu-system-arm \
    --rom runtime/compat.bin --reader runtime --gdb arm-none-eabi-gdb --qmp-port 17320 \
    --pending-nand ../wp2-remote/runs/STAGE/nand-staged.bin --reset-timeout 600 --output ../wp2-remote/runs/INSTALL)
(cd ../cmf-watch-utils && uv run cmf-watch-utils emu ota --protocol stock --hci-port 17310 \
    --image ../wp2-remote/dist/remote-temp-only.bin --transfer --output ../wp2-remote/runs/transfer.json)
uv run --project ../cmf-watch-utils python tools/emu.py --nor runs/INSTALL/nor.bin --output runs/BOOT ...
```
`local/paired-nor.bin` comes from `emu pair-fixture` against a guest started with
`tools/emu.py --hci-port 17310 --qmp-port 17320`.

## Plan

1. [done] Code cave + hook + valid header, boot in emulator.
2. [done in emulator] Remote screen reachable from the app list (Voice Assistant row) with crown/touch input.
3. [done in emulator, link untested] Send events as Classic Bluetooth HID consumer keys through the stock HID device (the one
   the camera shutter uses). Phone side: ~/boat/oss/g2-ring-remote grabs the watch's input
   node (match.name = the watch's BT name) and maps keys to Faceclaw gestures over the
   127.0.0.1:8791 input API. Needs per-device key maps in g2-ring-remote if the K02 is also used.
4. Zero-risk hardware check first: stock camera shutter on the watch + `adb shell getevent -il`
   to see the watch's HID node name and key.
   [done 2026-11-12] The watch appears as `<BT name> Consumer Control` (BT name is
   `CMF Watch Pro 2-XXXX`, last four hex digits of its address); the shutter sends usage 0x0C00EA =
   KEY_VOLUMEDOWN, down/up ~5-20 ms apart. The stock watch dropped the HID device a few seconds
   after the last press (the idle disconnect the patch disables). g2-ring-remote's match.name must
   be the full BT name (`CMF Watch Pro 2-XXXX`); the bare `CMF Watch Pro 2` does not match.
5. Before any flash: confirm the physical watch runs 1.0.0.73 (Settings > About) [done 2026-11-12:
   Nothing X > About shows 1.0.0.73]; build an AOTA
   with only TEMP changed; emulator virtual OTA + boot; then ask before touching hardware.
