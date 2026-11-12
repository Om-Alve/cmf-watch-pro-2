# CMF Watch Pro 2 (1.0.0.73) — crown & touch input path into the bt_watch UI

Target: `re/app_073.bin`, Thumb-2, base `0x10000000`. All addresses are load addresses.
Scratch tools used: `re/agent-input/xr.py` (BL-xref index), `re/agent-input/who.py` (addr → function_map),
`re/agent-input/full.dis` (full disassembly), `re/agent-input/sdk/` (lv_port_actions_technology @26f51e5, sparse).

Confidence tags: **[V]** = verified at runtime in QEMU (breakpoint hit / log / screenshot),
**[C]** = verified by code reading (address quoted), **[I]** = inference.

---

## 0. TL;DR

| Input | Transport into the UI | Lands on | Event code / value |
|---|---|---|---|
| Crown rotation (detent) | MT3511 encoder driver → `input_dev` type **4 (ENCODER)** → LVGL indev "knob" glue | the **display's knob object** (`lv_disp->[0x268]`) | either `lv_obj_scroll_by`-style scroll of that object **[V]**, or LVGL event **code 45** with param `int32_t = ±30 × detent` **[C]** |
| Crown press | PMU ONOFF key → `MSG_KEY_INPUT` → `view_manager_dispatch_key_event` | focused view proc2, msg **13** `MSG_VIEW_KEY` | `event` = `0x20000001` short-down, `0x04000001` short-up, `0x10000001` long-down, `0x02000001` long-up **[V]**, `0x40000001` double-click **[C]** |
| Touch tap / long press | CST820 → `input_dispatcher` → LVGL `LV_INDEV_TYPE_POINTER` | LVGL object under the finger | `LV_EVENT_PRESSED(1)`, `SHORT_CLICKED(4)`, `CLICKED(7)`, `LONG_PRESSED(5)` **[V]** |
| Touch swipe | same touch stream, second consumer = ui-service **gesture manager** | view stack / view drag (`GESTURE_DROP_*`) | view scroll / slide anim, not a view message **[C]** |

The knob is **not** delivered through `MSG_KEY_INPUT` and the SDK key codes `KEY_KONB_CLOCKWISE(30)` /
`KEY_KONB_ANTICLOCKWISE(31)`: rotating the crown produced **no** hits in
`view_manager_dispatch_key_event` and no `0x1e/0x1f` key events in any run **[V]**. The vendor replaced that
path with a patched LVGL "knob object" mechanism.

---

## 1. The three input sources

### 1.1 Crown rotation — MT3511 encoder on I2C2

Driver (app code, `os` module log lines 300–760):

| addr | what |
|---|---|
| `0x1014a9a0`–`0x1014b1xx` | `mt3511` I2C driver: `mt3511_get_cali_factor` (log `mt3511_get_cali_factor,len=-2,factor=320`), `mt3511_set_res_to_reg`, `mt3511_init` (`mt3511_init_ok fail 1 !!!` — the emulator always prints this, harmless) |
| `0x1014b244` | `knob_cali` — `knob_cali data=%d,lock=%d` (fmt @ `0x102425e3`) |
| `0x1014b438` | `knob_displacement_value =%d,lock=%d` (fmt @ `0x102425fe`) |
| `0x1014b5ac` / `0x1014b648` | `knob_displacement_value=%d` / `input_knob_device_init()` ("cannot found key dev knobencoder") |

The encoder is registered as an **input device of type 4** (`INPUT_DEV_TYPE_ENCODER`; enum in
`framework/system/include/input_manager.h`: NONE=0, POINTER=1, KEYPAD=2, BUTTON=3, ENCODER=4).

Reading path (all **[C]**):

* `0x1014a8c8(4)` = `input_manager_get_input_dev(INPUT_DEV_TYPE_ENCODER)` — scans 4 slots of 0x58 bytes,
  matches `slot->driver.type` (`+4`).
* `0x1014a810(dev, data)` = `input_dev_read_data()`: for `type==1` fills point, for `type==2` fills key,
  then calls `dev->read_cb` (`dev+0xc`).
* `0x101457b0(0, out)` — wrapper used by the display layer: gets the encoder dev via `0x101457d8`, calls
  `0x1014a810`, returns `{int16 value @ out+16, u8 state @ out+18}`.
* `0x10138f94(indev, lv_indev_data_t *data)` — LVGL indev read: for `type==1` copies `indev->[0x28]/[0x2c]`
  into `data->x/y` and calls the driver `read_cb`; finally `0x101457b0` result is stored as a **u16 at
  `data+16`**.

So the knob delta reaches the display layer as a **signed 16-bit value, ±1 per detent**, alongside a state
byte. Measured **[V]**: breakpoint at `0x101268b2` printing `*(short*)($sp+36)` (which is `data+16`)
produced `KNOBDELTA -1` for `r 80` (one "clockwise" detent as the emulator injects it) and `KNOBDELTA 1`
for `r -80`.

### 1.2 Crown press — PMU ONOFF key

`c 1` / `c 0` in the emulator toggles the PMU ONOFF key, which is reported as key code **`KEY_POWER` = 1**
with the standard keypad type bits (`framework/system/include/input_manager_type.h`):

```
KEY_TYPE_LONG_DOWN   0x10000000   KEY_TYPE_SHORT_DOWN  0x20000000
KEY_TYPE_DOUBLE_CLICK 0x40000000  KEY_TYPE_SHORT_UP    0x04000000
KEY_TYPE_LONG_UP     0x02000000
```

Path: keypad driver → `sys_event_report_input(key_event)` (`framework/system/sys_event.c:72`, sends
`MSG_KEY_INPUT` = **7** to app `"main"`) → app main loop → `ui_manager_dispatch_key_event()`
(`framework/display/ui_manager.c:389`, re-sends `MSG_KEY_INPUT` to `"ui_service"`) →

**`0x1018b2ec` → `0x1018e314` = `view_manager_dispatch_key_event(uint32_t key_event)`**

which builds `ui_key_msg_data_t { int32_t event; uint8_t done; }` and calls the **focused view's proc2**
with `(view_id, &view_data, 13, &key_msg_data)`.

### 1.3 Touch — CST820

| addr | what |
|---|---|
| `0x10115f21` | `tpkey_jx07003_cst820` driver init (log `z_sys_init dev(tpkey_jx07003_cst820)`) |
| `0x1014ad90` | cst820 report state machine (`input type %d not support` for non-type-1) |
| `0x1018e948` / `0x1018e974` | `input_dispatcher_init` / "input pointer dev not found" |
| `input_dispatcher_read_task` | prebuilt in `libdisplay.a` (`framework/display/ui_service/input_dispatcher.c`), reads the POINTER indev, subtracts last point, calls the registered GUI callback |
| `lvgl_input_dev.c` (`_lvgl_pointer_put`/`_lvgl_pointer_read_cb`) | pushes every touch sample into a ring buffer consumed by an `LV_INDEV_TYPE_POINTER` indev (`lvgl_input_pointer_init`) |

Two consumers of the same touch stream:
1. **LVGL** — normal object input (press/click/long-press/scroll).
2. **ui-service gesture manager** (`framework/display/ui_service/gesture.c`, prebuilt twins `0x1018b1fc`
   `input_dispatcher`, `0x10188e68` "gesture end %d, view %u, ...", `0x1018ec34` "gesture dir %x") — turns
   swipes into view scroll/slide animations (`gesture_scroll_begin` / `gesture_scroll` /
   `gesture_scroll_end`), plus `MSG_VIEW_SCROLL_BEGIN/END` (20/21) to the view.

---

## 2. Q1 — Crown rotation path in detail

### 2.1 Where the delta is consumed: the patched LVGL "knob object"

The vendor patched LVGL with a per-display *knob object*:

| addr | function | log |
|---|---|---|
| `0x10127dac` | `lv_disp_add_knob_obj(lv_obj_t *obj)` — public form (log name) | `knob_obj*:%p -> %p` (fmt `0x1023d04c`) |
| `0x10127e7c` | variant that also re-parents/moves the knob aux object | `knob_obj+:%p -> %p` (`0x1023d089`) |
| `0x10127d14` | `lv_disp_remove_knob_obj(obj)` | `knob_obj-:%p -> %p` (`0x1023d039`) |
| `0x10127e14` | clear all knob objects of a display | `knob_obj/:%p -> %p` (`0x1023d05f`) |
| `0x10128c50` | `lv_obj_register_knob(obj)` — called from `lv_obj_add_event_cb` | sets `disp->[0x268] = obj`, appends to list at `disp->[0x26c]` |
| `0x10128b28` | allocates the small "knob aux" child object used for the scroll anchor | |

Display struct: **knob object pointer at `lv_disp_t + 0x268`** (616), knob list at `+0x26c` (620) **[C]**.

Registration is automatic:

```
0x10125a94 lv_obj_add_event_cb(lv_obj_t *obj, cb, uint32_t filter, void *user_data)
   ...
   0x10125b10: r0 = obj; bl 0x10128b28          ; ensure knob aux object
   0x10125b16: cmp r5, #45                      ; r5 = filter
   0x10125b1a: if (filter == 45) bl 0x10128c50  ; <-- also registers obj as the display knob object
```

So **`lv_obj_add_event_cb(obj, cb, 45, ud)` is the whole API**: install a knob handler *and* make `obj` the
display's knob target. On teardown `0x10125bd4` calls `lv_disp_remove_knob_obj` (`0x10127d14`).

`ui_view_creater_1` also calls `0x10127e14` (clear all knob objects) on every `MSG_VIEW_LAYOUT` **[C:
`0x100d5944`]**, so a view must (re)register its knob object in its layout callback.

### 2.2 What happens on a detent

Function `0x10126754` (the knob branch of the indev processing; the delta it just read is at
`indev+0x60`, `ldrsh` at `0x101268b2`):

```
0x101268b4  bne 0x1012691a        ; delta != 0 -> rotation branch
...
0x10126994  ... resolve display, walk to knob object
0x101269ee  r0 = knob_obj
0x101269f6  lv_obj_check_type(obj, 0x101eae24)   ; class A = vendor list/carousel widget class
0x10126a6a  lv_obj_check_type(obj, 0x101fb7d0)   ; class B = a stock LVGL widget class (roller-like)
0x10126a04  lv_obj_has_flag(obj, 0x40000000)     ; LV_OBJ_FLAG_USER_4
0x10126a36  -> SCROLL path   (obj kind = "other", has USER_4)
0x10126a78  -> ACC path      (class A/B, has USER_4)
0x10126ade  -> EV45 path     (no USER_4)
0x10126ab8  movs r1,#45 ; r3 = 30 * delta ; lv_event_send(knob_obj, 45, &r3)
```

* **SCROLL path** (`0x10126a36`…`0x10126a64`): sets the indev's scroll fields (`indev_ctx+0x30/0x34/0x44/
  0x4c/0x50`) from `delta × tick` and calls `0x10127598` (vis-object scroll). Net effect: **the knob object
  (a scrollable container) scrolls by ~one item per few detents**.
* **EV45 path** (`0x10126ade` → `0x10126ab8`): `lv_event_send(knob_obj, 45, &int32)` with
  `int32 = 30 × delta` — i.e. **±30 per detent**, sign = rotation direction. A second variant
  (`0x10126a78`…) accumulates 4 same-direction detents before sending the same event.
* There is also an "idle" `EV45` with value **0** (`0x101268fe`→`0x10126910`) sent ~300 ms after the last
  detent.

`lv_event_send` = `0x101259c4(lv_obj_t *obj, lv_event_code_t code, void *param)`.

`lv_event_t` (firmware) offsets, derived from the getter thunks **[C]**:

| off | field | getter |
|---|---|---|
| +0x00 | `target` (obj) | `0x101c4c92` |
| +0x04 | `current_target` | `0x101c4c96` |
| +0x08 | `code` (u8, `&0x7f`) | `0x101c4c9a` = `lv_event_get_code` |
| +0x0c | `user_data` | `0x101c4ca6` = `lv_event_get_user_data` |
| +0x10 | `param` | `0x101c4ca2` = `lv_event_get_param` |

`lv_obj_t.flags` is at **`+0x24`** (`0x101283dc` = `lv_obj_has_flag`: `(obj->[0x24] & flag) == flag`);
`LV_OBJ_FLAG_USER_4 = 0x40000000`, `LV_OBJ_FLAG_SCROLLABLE = 0x10`.

### 2.3 Runtime evidence

| run | breakpoint | output |
|---|---|---|
| `runs/input-t8` | `0x10126a36` (scroll path) | `BR_SCROLL obj=0x3806793c delta=-1` ×4 then `SCROLLFN indev=0x38067408` — watch-face knob object scrolled by detents **[V]** |
| `runs/input-t12` | `0x10126a36` | `SCROLLPATH obj=0x38067984 flags=0x40003b76 delta=-1` — app-list knob object (USER_4 + scrollable) scrolls **[V]** |
| `runs/input-t3` | screenshots | `d.png` (app list) vs `e.png` after 3 detents: scrollbar appeared / list moved **[V]** |
| `runs/input-t17` | screenshots | rotating inside Settings (`sysmenulist_view`) changed nothing — no knob object registered for that view **[V]** |
| `runs/input-t2`,`-t5`,`-t7` | `0x1018e314` | only `0x20000001` / `0x04000001` (crown press); **never** an `0x1e/0x1f` key event **[V]** |

No `EV45` was ever observed on the stock screens we could reach — every reachable stock knob object
(watch face, app list, alarm) carries `USER_4`, so it takes the scroll route. `EV45` delivery itself is
established from code (send site + 13 registered handlers, §5), not from a live hit. **[C]**

### 2.4 Answer to Q1

Rotation is **not** an LVGL encoder indev + `lv_group`, and **not** a view-manager message. It is a vendor
patch: the delta is pulled from the encoder `input_dev` each frame and handed to **the single "knob object"
registered for the display**:
* if that object is a scrollable, `USER_4`-flagged container → it is **scrolled** (this is what all stock
  list screens do);
* otherwise LVGL sends **`LV_EVENT` code 45** to that object with `param = int32 (30 × delta)`
  (sign: `r 80` ⇒ delta `-1` ⇒ `-30`; `r -80` ⇒ `+1` ⇒ `+30`).

---

## 3. Q2 — Crown press path in detail

`0x1018e314` `view_manager_dispatch_key_event(uint32_t key_event)` **[C]**:

```
0x1018e31c  r4 = ctx->[0x44]                ; current (focused) view context
0x1018e324  r2 = r4->[4]                   ; view_entry*
0x1018e328  r9 = *(u16*)(r2+0x10)          ; view id
0x1018e33a  call ctx->[0x48](0, 29, &keymsg)   ; "key filter" callback (ui_service callback id 29)
0x1018e34c  mem_manager_set_user_info(view_id)
0x1018e352  view_gui_set_default(view)
0x1018e358  r7 = *(void**)(entry+8)        ; proc2
0x1018e366  blx r7  (view_id, &view_data /*ctx+0x1c*/, 13, &keymsg)
0x1018e378  if (!keymsg.done) call ctx->[0x54](view_id, key_event)   ; global fallback
0x1018e39e  log "view %u done key 0x%x"     ; when the view set done=1
```

Measured **[V]** (`runs/input-t9`, `runs/input-t2`, breakpoint at `0x1018e366` printing
`r0`=view id, `r2`=msg id, `*(int*)r3`=event):

```
VIEWPROC view=16 msg=13 event=0x20000001     <- crown short press, watch face (clock_view)
VIEWPROC view=16 msg=13 event=0x4000001      <- release
VIEWPROC view=16 msg=13 event=0x10000001     <- long press (3.5 s hold)
VIEWPROC view=16 msg=13 event=0x2000001      <- release after long press
VIEWPROC view=18 msg=13 event=0x20000001     <- app list (applist_view) gets the same, after focus moved
```

So:

| gesture | key value |
|---|---|
| short press | `0x20000001` (SHORT_DOWN) then `0x04000001` (SHORT_UP) |
| long press | `0x10000001` (LONG_DOWN, ~400 ms) then `0x02000001` (LONG_UP) |
| double press | `0x40000001` (DOUBLE_CLICK) — the type bits come from the Actions keypad driver state machine
(`framework/system/input/input_keypad.c`, `QUICKLY_CLICK_DURATION 300 ms`, `click_num==2` → `KEY_TYPE_DOUBLE_CLICK`;
SDK source, the vendor build may differ in timing). **Not observed** in the emulator: the harness defers
every crown release by ≥100 ms virtual and consumes input lines every 6 ms, so two presses came out as two
separate SHORT_DOWN/SHORT_UP pairs (`runs/input-t9`). **[C]** / needs hardware or a tighter input script. |

* Only the **focused** view receives `MSG_VIEW_KEY` (13). It gets the first chance; if it leaves
  `key_msg_data.done == 0`, the ui-service callback registered at `view_manager_context+0x54` runs
  (`0x1018e378`).
* The vendor app-level view handler **does not receive the key value**: `ui_view_creater_1` calls
  `descriptor[0x2c](view_data, msg_id)` — a 2-argument call (`0x100d590e`–`0x100d5916`), msg_data is
  dropped. Apps that want the event value must implement their own `ui_view_proc2_t` (see §6) or hook
  `0x1018e314` / the app's `ui_manager_dispatch_key_event`.
* Global behaviour seen: with the watch face focused, short press opens the app list (`view 18` created and
  focused, `runs/input-t9`, `runs/input-t3` d.png). Long press on the watch face does nothing visible.

---

## 4. Q3 — Touch

### 4.1 Tap / long press — plain LVGL object events **[V]**

`runs/input-t9`, breakpoint `0x101259c4` (lv_event_send) filtered on codes:

```
EV1 obj=0x380684ec     LV_EVENT_PRESSED
EV4 obj=0x380684ec     LV_EVENT_SHORT_CLICKED
EV7 obj=0x380684ec     LV_EVENT_CLICKED
```

i.e. the stock views are ordinary LVGL object trees and taps arrive as standard LVGL events on the object
under the finger (code numbering matches LVGL 8: 1 PRESSED, 4 SHORT_CLICKED, 5 LONG_PRESSED,
6 LONG_PRESSED_REPEAT, 7 CLICKED, 8 RELEASED, 12 SCROLL).

`LV_EVENT_LONG_PRESSED` (5) is produced by LVGL itself after `long_press_time` (default 400 ms) — no stock
view needed to opt in.
**Double tap does not exist as an LVGL event** — implement it from two `LV_EVENT_CLICKED` with `lv_tick_get()`
(only the *crown* has a hardware double-click type).

### 4.2 Swipe — view-level gesture, not an object event

The same touch stream also feeds the ui-service gesture manager (`gesture.c`): a drag > `GESTURE_DROP_START_THRESHOLD`
(400 px, or 100 with `CONFIG_VIEW_SCROLL_TRACKING_FINGER`) starts a scroll of the focused view
(`view_manager_get_draggable_view(dir, ...)`), and release either snaps back or animates to the neighbour view
(`GESTURE_DROP_UP/DOWN/LEFT/RIGHT` = 2/1/4/3 in `input_manager.h`'s `GESTURE_TYPE`… the framework uses
`GESTURE_DROP_DOWN=1, UP=2, LEFT=3, RIGHT=4` via `opposite_gestures[]` in `gesture.c`).

So a swipe is **not** delivered to a view as a message by default: it scrolls/slides views (the "back"
gesture for the app list is a swipe → view-stack pop, `0x101891f8` "view_stack: jump %d -> %d"). A view that
wants raw swipes must either be the draggable view (drag attributes: `ui_view_set_drag_attribute`,
`UI_DRAG_*`) or use LVGL scroll events on its own scrollable object.

If the target object is scrollable, LVGL also emits `LV_EVENT_SCROLL`/`SCROLL_BEGIN`/`SCROLL_END` on it, and
the pointer indev is shared, so both consumers see the same finger.

---

## 5. Existing views that already handle knob + touch

13 app views register a knob handler with `lv_obj_add_event_cb(obj, cb, 45, user_data)` (call site →
callback → owning view, by view table neighbourhood) **[C]**:

| call site | callback | view (id) |
|---|---|---|
| `0x100baf86` | `0x100bb031` | `setvol_view` (80) — Settings ▸ Volume |
| `0x100bba82` | `0x100bb859` | `vollist_view` (79) |
| `0x100b9d32` | `0x100b9d89` | `set_light_time_list_view` (170) / `setbrg_custom_view` (216) region |
| `0x100b2430` | `0x101b3d09` | `clock_edit_view` (219) — hour/minute columns |
| `0x100b1f26` | `0x101b3aad` | `clock_selector_view` (17) |
| `0x10097200` | `0x10096e75` = **`_knob_event_handler`** | `user_test_view` (231) / volume view code |
| `0x10074534` | `0x10074581` | `music_main_view` (144) — volume |
| `0x10078868` | `0x10078fe5` | `sport1_view` (100) |
| `0x10089e86` | `0x10089f6d` | `flash_light_view` (134) (`_flash_light_knob_event_handler` string @ `0x10219c4a`) |
| `0x10090896` | `0x10092f9d` | `band_poweron_view` (167) |
| `0x1005ff74` | `0x1005fabd` | `applist_view` variants (18) |
| `0x100602e0` | `0x101ad511` | `calendar_view` (206) |
| `0x100df5bc` | `0x100df16d` | late view (face/notify area) |

**Best model to imitate: `setvol_view` (id 80, descriptor `0x101f2598`, proc2 thunk `0x100bae90`) or its
sibling `vollist_view` (id 79, proc2 `0x100bb300`)** — small, full-screen, knob + touch only:

```
0x100bae90  push {r0,r1,r2,lr} ; str r3,[sp] ; mov r3,r2 ; mov r2,r1 ; mov r1,r0
0x100bae9a  ldr r0,=0x101f2598          ; view descriptor
0x100bae9c  bl 0x100d587c               ; ui_view_creater_1(desc, view_id, view_data, msg_id, msg_data)
0x100baf86  movs r3,#0                  ; user_data
0x100baf88  ldr r1,=0x100bb031          ; knob event callback
0x100baf8a  ldr r0,[r4,#4]              ; the view's root/scroll object
0x100baf8c  movs r2,#45
0x100baf8e  bl 0x10125a94               ; lv_obj_add_event_cb(obj, cb, 45, NULL)  (+ knob registration)
```

The canonical handler body is `_knob_event_handler` (`0x10096e74`, log `_knob_event_handler event %d  coord %d`
@ `0x1021b3e0`) — the shape every app knob handler copies:

```
r0 = lv_event_t*
code   = lv_event_get_code(e)          ; 0x101c4c9a  -> must be 45
target = lv_event_get_target(e)        ; 0x101c4c92
param  = lv_event_get_param(e)         ; 0x101c4ca2
ud     = lv_event_get_user_data(e)     ; 0x101c4ca6
delta  = *(int32_t*)param              ; sign = direction, magnitude 30/detent
if (code != 45 || !target) return;
acc = ((int8_t*)ud)[0xe0];             ; per-view accumulator 0..2
if (delta > 0) { if (++acc > 2) { acc = 0; ...act "up"... } else store acc; }
else           { if (--acc < 0) { acc = 0; ...act "down"... } else store acc; }
```

i.e. **3 detents = 1 logical step** in the app handlers. Actions are dispatched through the vendor
"ux2sys" command table: `0x100e08b8(id, &payload, len)` (id ≤ 158, table `0x101f4274`, 12-byte entries
`{fn; u16 pad; u16 max_len}`); the volume view uses id **0x26 (38)** with payload `{8}` and
`0x100978f0` = `volume_view_create_vol_bar` / `0x10097878` = `volume_view_updata_vol_bar`.

`knob_ctrl` (`0x100e01b8`, log `knob_ctrl:%u` @ `0x10224871`) is the "knob state changed" notifier: called
from the LVGL knob code (`0x101269ae`) and from `ui_view_creater_1` (`0x100d5a90`); it forwards the value
through `0x101b98b0` → `0x100e08b8(0x56, …)`.

---

## 6. Q4 — What a NEW view must do

### 6.1 Pick a slot: repurpose an existing view (recommended)

The app's view table is a linker-section array in flash:

```
.view_entry  0x100004b8 .. 0x100013e8   162 entries × 24 bytes
```

Lookup routine `0x1018bc04`: `for (e = 0x100004b8; e < 0x100013e8; e += 24) if (*(u16*)(e+0x10) == id) return e;`
(the start/end are plain literals, also referenced at `0x1018df3c` and `0x101461ac`) **[C]**.

Firmware `struct view_entry` (24 B) **[V — dumped at runtime, `runs/input-t10`]**:

| off | field |
|---|---|
| +0x00 | `const char *app_id` (e.g. `"clock_view"` @ `0x102193b9`) |
| +0x04 | `ui_view_proc_t proc` (deprecated, 0) |
| +0x08 | `ui_view_proc2_t proc2` (e.g. `0x1006e3f5`) |
| +0x0c | `key_map` (0 in all stock entries) |
| +0x10 | `uint16_t id` |
| +0x12 | `uint8_t default_order` |
| +0x13 | `uint8_t type` (1) |
| +0x14 | `uint16_t width` (466) |
| +0x16 | `uint16_t height` (466) |

Because the table bounds are hard-coded literals, the cheap route is **not** to append an entry but to
retarget one existing entry's `proc2` (4 bytes at `entry+8`) to a thunk in the code cave — exactly the
"BL/pointer redirect into a cave" pattern already used by `patch/`. Then reuse an app-list item that already
exists (e.g. Calculator `calc_view` 205) so the resource-pack app list needs no change.

### 6.2 Implement our own `proc2` (skip `ui_view_creater_1`)

`ui_view_proc2_t` (`framework/display/include/view_manager.h:292`):

```c
int (*)(uint16_t view_id, struct view_data *view_data, uint8_t msg_id, void *msg_data)
```

If we implement it ourselves instead of calling `0x100d587c`, we get the **full** key payload
(`ui_key_msg_data_t*{int32 event; u8 done;}`) which the vendor wrapper drops.

Message ids we care about (`framework/display/include/view_manager.h`, `enum UI_MSG_ID`):

| id | name | use |
|---|---|---|
| 1 | `MSG_VIEW_CREATE` | |
| 3 | `MSG_VIEW_LAYOUT` | build the LVGL tree here |
| 4 | `MSG_VIEW_DELETE` | |
| 7/8 | `MSG_VIEW_FOCUS` / `DEFOCUS` | |
| 13 | `MSG_VIEW_KEY` | **crown press** (`ui_key_msg_data_t`) |
| 20/21 | `MSG_VIEW_SCROLL_BEGIN/END` | swipe started/finished |
| ≥128 | `MSG_VIEW_USER_OFFSET` | our own messages |

`view_data_t` (firmware `view+0x1c`): `{ void *display; struct surface *surface; const void *presenter;
void *user_data; }`.

### 6.3 Receiving each input

| input | what to do | addresses |
|---|---|---|
| **crown rotation** | create a plain container object, do **not** set `LV_OBJ_FLAG_USER_4` on it, then `lv_obj_add_event_cb(obj, knob_cb, 45, ud)` — this also registers it as the display's knob object. In `knob_cb`: `delta = *(int32_t*)lv_event_get_param(e)`; sign = direction, ±30 per detent (3 detents per step is the vendor convention). | `0x10125a94` add_event_cb, `0x10128c50` auto knob-register, `0x101c4ca2` get_param, `0x101c4c9a` get_code |
| **crown press** | handle `msg_id == 13` in your `proc2`; read `((ui_key_msg_data_t*)msg_data)->event`: `0x20000001` short-down, `0x04000001` short-up, `0x10000001` long-down, `0x02000001` long-up, `0x40000001` double. Set `done = 1` to stop the global fallback. | dispatch `0x1018e314`, fallback `ctx+0x54` |
| **tap** | normal LVGL: `lv_obj_add_event_cb(btn, cb, LV_EVENT_CLICKED(7), ud)`; also `PRESSED(1)`, `SHORT_CLICKED(4)`, `RELEASED(8)` | `0x101259c4` |
| **double tap** | two `LV_EVENT_CLICKED` within your own window (`lv_tick_get`, `0x101cb89a`) — no LVGL double-click event | — |
| **long press** | `LV_EVENT_LONG_PRESSED(5)` / `LONG_PRESSED_REPEAT(6)` (LVGL default `long_press_time` 400 ms); tune with `lv_indev_set_long_press_time` | — |
| **swipe** | make the view the draggable/scrollable one (`ui_view_set_drag_attribute`, `UI_DRAG_*`) or put a scrollable object in the view and watch `LV_EVENT_SCROLL(12)`/`SCROLL_END(11)`; the gesture manager will otherwise consume swipes as view transitions | `gesture.c` twins `0x10188e68`, `0x1018ec34` |

Caveat on rotation: **whether you get `EV45` or a scroll depends on flags/class** (see §2.2). Both stock knob
objects we inspected were scroll containers with `USER_4` (`flags = 0x40003b76` observed), so they scroll.
A plain object without `USER_4` takes the `EV45` branch (`0x10126ade` → `0x10126ab8`); a plain object **with**
`USER_4` scrolls (`0x10126a36`, observed twice). A freshly created `lv_obj` has no `USER_4`, so the default
is already the behaviour we want — do not set that bit.

### 6.4 Blockers / risks for adding such a view

1. `EV45` delivery is proven by code, not by a live hit: every stock screen we reached registers a
   *scrollable, USER_4* knob object, so none of them ever exercises the `EV45` branch. First step of the
   implementation should be a `trace.py --break 0x10126ab8` run against our own screen to confirm ±30 per
   detent (and to measure whether the 4-detent accumulator path at `0x10126a78` is taken instead).
2. `ui_view_creater_1` (`0x100d587c`) throws away `msg_data` for all "default" messages, including
   `MSG_VIEW_KEY` → must implement our own `proc2` (or hook `0x1018e314`).
3. View table start/end are hard-coded literals (`0x100004b8`/`0x100013e8`): appending an entry needs those
   patched; easier to retarget an existing entry's `proc2`.
4. App-list item (icon, label, target view id) is not in this image's code — it comes from the
   `bt_watch.res` resource pack (`/NAND:A/bt_watch.res`). Repurposing an existing app item avoids touching it.
5. Structure offsets above are for **this** firmware; the public SDK snapshot at commit 26f51e5 is *not*
   the same build (`view_manager_dispatch_key_event` differs: it uses `entry+0xc` for the view id and
   callback ids 31/13, while the firmware uses `entry+0x10` and 29/13). Do not compile against the SDK
   headers for anything that must match the running image.
6. `lv_obj_add_event_cb(...,45,...)` installs a per-display singleton; `ui_view_creater_1` clears knob
   objects on every layout (`0x10127e14`), and deleting `obj` removes it again — re-register in
   `MSG_VIEW_LAYOUT`, and unregister/delete on `MSG_VIEW_DELETE` or the next view inherits the knob target.
7. Crown **double press** could not be produced in the emulator (§3); if it matters, verify on real
   hardware or with a tighter input script.

---

## 7. Evidence index (runs in `runs/input-*`)

| run | script | purpose / result |
|---|---|---|
| `input-t1`,`input-t2`,`input-t5` | `s1.json`,`s3.json` | first trace: only `0x20000001`/`0x04000001` at `0x1018e314`; rotation gives no key event |
| `input-t3` | `s2.json` | screenshots: app list scrolls with `r`; `mt3511 init_ok fail 1` is normal |
| `input-t4`,`-t5` | `s3.json` | `IND3 delta=-1` for `r 80`, `+1` for `r -80` (delta at `indev+0x60`) |
| `input-t6` | `s3.json` | `ADDKNOB obj=0x38067d6c class=0x101eade4` when the app list opens |
| `input-t7` | `s4.json` | 8 detents on the watch face: only `KNOBDELTA ±1`, no `EV45` |
| `input-t8` | `s4.json` | `BR_SCROLL obj=0x3806793c delta=-1` ×4 + `SCROLLFN` → **rotation = scroll of the knob object** |
| `input-t9` | `s5.json` | `VIEWPROC view=16 msg=13 event=…` for short/long press; `EV1/EV4/EV7` for a tap |
| `input-t10` | `s5.json` | view context/entry dump → view table layout, `entry+0x10` = view id |
| `input-t11`,`-t16` | `s6.json`,`s10.json` | app-list inventory screenshots (Exercise…Settings) |
| `input-t12` | `s7.json` | `SCROLLPATH obj=0x38067984 flags=0x40003b76` (USER_4 + scrollable) |
| `input-t17` | `s11.json` | Settings list: rotation has no effect (no knob object) |
| `input-t18` | `s12.json` | Settings ▸ Watch face settings requires the phone app |

UART interesting lines (`runs/input-t3/uart0.log`):

```
z_sys_init dev(knob) func:0x10115579
[3210][os][I][389]: mt3511_get_cali_factor,len=-2,factor=320
[3210][os][I][754]: mt3511 mt3511_init_ok fail 1 !!!
[18228][os][I][348]: knob_obj+:0x0 -> 0x3806793c
[18463][os][I][379]: knob_obj-:0x3806793c -> 0x0
[20704][os][I][1354]: knob_ctrl:0
```

---

## 8. Address cheat-sheet

```
0x10096e74  _knob_event_handler(event)                 app knob handler (event 45), volume view
0x100978f0  volume_view_create_vol_bar
0x10097878  volume_view_updata_vol_bar
0x100e01b8  knob_ctrl(uint32)
0x100e08b8  ux2sys command dispatch (id <= 158, table 0x101f4274)
0x10125a94  lv_obj_add_event_cb(obj, cb, filter, ud)   (filter 45 => knob object)
0x101259c4  lv_event_send(obj, code, param)
0x10125bd4  event-dsc removal (drops knob object)
0x10126754  indev knob translation (delta at indev+0x60)
0x10126ab8  lv_event_send(knob_obj, 45, &(30*delta))
0x10127598  knob scroll-by helper
0x10127dac  lv_disp_add_knob_obj     0x10127d14 lv_disp_remove_knob_obj
0x10127e7c  lv_disp_add_knob_obj2    0x10127e14 knob objects clear-all
0x10128c50  lv_obj_register_knob (called from add_event_cb when filter==45)
0x101283dc  lv_obj_has_flag           (obj->[0x24] & flag)
0x101c4c9a  lv_event_get_code  0x101c4ca2 lv_event_get_param
0x101c4c92  lv_event_get_target 0x101c4ca6 lv_event_get_user_data
0x101c54b6  lv_obj_check_type   0x101c54c2 lv_obj_has_class
0x101457b0  knob value pull (-> input_manager_get_input_dev(4) -> 0x1014a810)
0x1014a810  input_dev_read_data   0x1014a8c8 input_manager_get_input_dev(type)
0x1018b2ec  ui-service msg dispatch -> key path
0x1018e314  view_manager_dispatch_key_event(key)
0x1018d7b4  view delete   0x1018dafc view layout   0x1018e15c view_manager_init
0x1018bc04  view table lookup (0x100004b8..0x100013e8, 24 B/entry)
0x100d587c  ui_view_creater_1(desc, view_id, view_data, msg_id, msg_data)
0x100dcc6c  app "current UI msg" -> per-view handler table dispatch
0x1014c818  log
```
