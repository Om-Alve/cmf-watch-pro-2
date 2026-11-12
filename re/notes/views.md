# View registration, view stack and the app list (CMF Watch Pro 2, fw 1.0.0.73)

Reverse-engineering notes for `app_073.bin` (load base `0x10000000`, so
`file offset = addr - 0x10000000`). Everything below was obtained from static
analysis (`arm-none-eabi-objdump`) plus scripted runs of the QEMU emulator
(`tools/emu.py`, `re/agent-views/trace2.py`) and the resource tooling
(`fwkit sty-tree` on `cmf-watch-utils/dumps/samples/bt_watch.sty`).
Nothing touched a real watch.

Confidence tags: **[V]** verified (code read + trace/screenshot or an
independent cross-check), **[I]** inferred from code shape, **[?]** open.

Scratch artefacts (safe to delete): `re/agent-views/*.py`, `*.json`,
`views_table.tsv`, `applist_table.tsv`, `table.md`; emulator output in
`runs/views-*`.

---

## 0. TL;DR

* The view registry is a **162-entry static array of 24-byte `view_entry_t`
  records at file `0x4b8`** (`0x100004b8`..`0x100013e8`). Layout is the
  upstream Actions SDK `view_entry_t`: `{app_id, proc, proc2, key_map, id,
  default_order, type, width, height}`. **[V]**
* Each view's `proc2` is a 7-instruction trampoline that loads its **per-view
  descriptor struct** (56 bytes, `.rodata` near `0x101eb000`-`0x101f2b40`)
  and jumps to the shared `ui_view_creater` at `0x100d587c`. **[V]**
* `ui_view_creater(reg, view_id, view_data, msg_id, msg_data)` dispatches the
  Actions `MSG_VIEW_*` lifecycle through 9 function pointers inside `reg`. **[V]**
* Opening a view = **`FUN_101898bc(view_id, arg)`**; it validates the id against
  the registry, builds a 16-byte request `{0,0,arg,id}` and pushes it on a
  10-deep view stack (`0x10189398`). Back = `0x101897fc` (pop one). **[V]**
* The app list is **`applist_view` (id `0x12`)**; it delegates drawing to a
  style view chosen from a setting (`0x2c`), on this device
  `applist_list_view`. Its **25 entries are a static 12-byte-record table at
  `0x101eaf40`** `{icon_node_id, label_node_id, action}` where `action` is
  either a view id (≤ `0xF4`) or a small handler function. A tap calls
  `FUN_101898bc(action, 0)`. Labels/icons come from scene
  `0xc18487B4` in `/NAND:A/bt_watch.sty` → text indices into
  `bt_watch.<lang>` and pictures in `bt_watch.res`. **[V]**
* Least invasive way to add a "Faceclaw remote" entry: **overwrite one
  app-list record's action field (4 bytes)** and open an id that already
  exists in the registry (e.g. take the `alipay_main_view` slot `0x2c`, which
  is unreachable without the phone-side payment app, for the new screen).
  Growing the list to 26 entries is possible but needs 3 loop-bound patches, a
  bigger per-view context and a relocated table — see §3.7.

---

## 1. Question 1 — the view registry

### 1.1 Location, bounds and count — verified

`FUN_1018bc04` is `view_manager_get_view_entry(view_id)`:

```
1018bc04: ldr r3,=0x100004b8     ; __view_entry_table
1018bc06: ldr r1,=0x100013e8     ; __view_entry_end
1018bc0a: cmp r3,r1 ; bcs -> return NULL
1018bc0e: r0=r3
1018bc12: add r0,#24             ; stride 0x18
1018bc18: ldrh r3,[r0,#16]       ; view id at entry+0x10
1018bc1a: cmp r3,r2 ; bne loop
1018bc1e: bx lr                  ; -> entry pointer
```

**[V]** table starts at `0x100004b8` (file `0x4b8`), ends at `0x100013e8`,
stride 24 → `(0x13e8-0x4b8)/24 = 162` entries. The id field is the `u16` at
entry `+0x10`. This matches the linker section `.view_entry`
(`KEEP(*(.view_entry))`, `__view_entry_table`/`__view_entry_end` in
`action_technology_sdk/bootloader/soc/arm/actions/leopard/linker.ld`).

The registry starts exactly at `0x100004b8` (entry 0 name
`0x10203a4b` = `"applist_view"`); the words just before it belong to a
different table.

### 1.2 Entry layout (24 bytes) — verified

Matches `view_entry_t` in
`action_technology_sdk/framework/display/include/view_manager.h`, except that
this build has the `key_map` slot that the public header calls `.key_map` in
the simulator variant:

| off | type | field | observed |
|---|---|---|---|
| `+0x00` | `char *` | `app_id` | rodata string, e.g. `"applist_view"` |
| `+0x04` | `u32` | `proc` (deprecated, `VIEW_DEFINE`) | 0 except the 11 legacy entries below |
| `+0x08` | `u32` | `proc2` | Thumb code pointer (odd) or 0 |
| `+0x0c` | `u32` | `key_map` | 0 in all 162 |
| `+0x10` | `u16` | `id` | view id |
| `+0x12` | `u8` | `default_order` | 0,1,2 |
| `+0x13` | `u8` | `type` | 1 (`UI_VIEW_LVGL`) in all 162 |
| `+0x14` | `u16` | `width` | `0x01d2` = 466 |
| `+0x16` | `u16` | `height` | `0x01d2` = 466 |

The "sentinel" `0x01d201d2` in older notes is simply `width|height<<16`
(466×466, the panel resolution) — **[V]** every entry has it.

11 entries carry their callback in the **deprecated `proc` slot (`+0x04`)**
instead of `proc2`, i.e. they are written to the old
`int (*)(uint16_t view_id, uint8_t msg_id, void *msg_data)` shape and are
dispatched by the closed `display.lib` part of the framework rather than by
`ui_view_creater`: `goodbye_view` `0x10060a55`, `welcome_view` `0x10060bbd`,
`power_saving_view` `0x10076929`, `alipay_bind/pay/unbind/main`
`0x100b2d21/0x100b3145/0x100b3569/0x100b3b1d`,
`wxpay_bind/pay/unbind/main` `0x100b3f29/0x100b434d/0x100b4771/0x100b4d25`.
So all 162 entries are implemented; none is a placeholder. **[V]** for the
pointers, **[I]** for the dispatch path (the `proc` call itself lives in the
prebuilt display library).
The registry itself is untouched by this: `proc` is non-zero, `proc2` is zero,
and `key_map` is zero for every entry. **[V]**

Every `proc2` is a trampoline (uniform shape, `0x1005e91c` is the app list's):

```
1005e91c: push {r0,r1,r2,lr}      ; b507
1005e91e: str  r3,[sp,#0]         ; msg_data (5th arg) to the stack
1005e920: mov  r3,r2              ; msg_id    -> r3
1005e922: mov  r2,r1              ; view_data -> r2
1005e924: mov  r1,r0              ; view_id   -> r1
1005e926: ldr  r0,=reg            ; reg struct
1005e928: bl   0x100d587c         ; ui_view_creater
1005e92c: add sp,#12 ; pop {...}
```

137 of the 151 views with a `proc2` use this trampoline. The other **14 are
self-contained `proc2` functions** that implement the `MSG_VIEW_*` switch
themselves and have no `reg` struct: `effect_wheel_wheel 0x3d`,
`effect_wheel 0xc3`, `sport_setcalu 0x72`, `sport_setdistance 0x70`,
`sport_settime 0x71`, `sport_unrecorded 0x6e`, `guid_view 0x75`,
`bloodoxygen 0x73`, `measure_view 0x77`, `blood_oxygen_note_view 0x74`,
`war_view 0x76`, `cubebox 0x35`, `face_wheel 0x3c`, `notify_cont 0x3e`
(e.g. `0x10061ddc` starts with `cmp r0,#0x3d` then has its own `tbh` over
`msg_id-2`). The 11 remaining entries have `proc2 == 0`.

### 1.3 Per-view descriptor (`reg`) — 56 bytes, `.rodata`

**[V]** `ui_view_creater(reg, view_id, view_data, msg_id, msg_data)` — its log
line is the one you see in the UART log
(`0x102233a7`: `"\n----->view:%u, reg:%p, ev:[%s], view_data:%p, user_data:%p, msg_data:%p\n"`),
and a trace of the app-list open shows exactly
`----->view:18, reg:0x101eb07c, ev:[preload]`.

`reg` layout (all 137 populated views fit this; **[V]** for +0..+0x2c by code,
**[V]** for +4/+8 by cross-checks below):

| off | type | meaning | evidence |
|---|---|---|---|
| `+0x00` | `u8` | create-flag bits; `0x00` normally, `0x08` for 15 views (ctrl_center, sleep*, weather_*, activity_record*, heart*, flash_light, chatgpt) | tested in the focus handler: `ldrb r3,[reg]; ands r3,#8` at `0x100d5a2a` |
| `+0x01` | `u8` | second flag byte; always `0x02` here, bit0 = "no preload" (`lsls r3,#31; bmi` at `0x100d5624`) | never set in this image |
| `+0x02` | `u16` | view id (redundant copy of the registry id) | e.g. `0x0012` for applist |
| `+0x04` | `u16` | **size of the per-view RAM context** (`0x230` = 560 for applist) | `ldrh r0,[reg,#4]; bl <alloc>` + `memset(ctx,0,size)` at `0x100d594a..0x100d595e`; sizes fit the arrays exactly (§3.5) |
| `+0x06` | `u16` | 0 | — |
| `+0x08` | `u32` | **`.sty` scene id** (opaque builder id, see `formats/style.md`) | stored in the jx view object and passed to the scene loader; **all 137 ids exist in `bt_watch.sty`** (checked with `fwkit`, 0 misses) |
| `+0x0c` | fn | `create_a(obj)` — called right after inflate | `0x100d59a6` |
| `+0x10` | fn | `create_b(obj)` — ditto | `0x100d59ae` |
| `+0x14` | fn | `focus(obj, focused)` — called with 1 on focus, 0 on defocus | `0x100d59b2` (1), `0x100d5a9a` (0) |
| `+0x18` | fn | `get_res_dsc(view_id, dsc[2])` — fills a 8-byte resource descriptor before the scene load | `0x100d5642` (preload) |
| `+0x1c` | fn | `inflate(obj)` — build the widget tree; return 0, non-NULL required | `0x100d56d2` (`_ui_view_layout`) |
| `+0x20` | fn | `destroy(obj)` — called on MSG_VIEW_DELETE before the ctx is freed | `0x100d5bfe` |
| `+0x24` | fn | `lang_change(obj, 1)` — MSG 0x81 | `0x100d5af0` |
| `+0x28` | fn | `key(obj, event) -> bool done` | `0x100d5cba` |
| `+0x2c` | fn | generic `event(obj, msg_id)` for paint/refresh/pause/resume and user msgs | `0x100d590e` |
| `+0x30` | `reg *` | optional variant/sub-view regs (applist: list/waterfall) | applist only |

Reg structs are packed back-to-back in `.rodata` from about `0x101eb000` to
`0x101f2b40`, followed immediately by each view's id arrays/strings (e.g.
`about_view` has its 13 node ids at `0x101f2a04` and its reg at `0x101f2a38`).

### 1.4 jx view object (28 bytes, RAM) — `_ui_view_preload`

`0x100d5600` = `_ui_view_preload(reg, view_data)` (alloc name
`0x102234f1` = `"_ui_view_preload"`, size 0x1c):

| off | field |
|---|---|
| `+0x00` | `u32 scene_id` (from `reg+8`) |
| `+0x04` | `void *scene_ctx` — output of the scene loader |
| `+0x08` | ? (never written here) |
| `+0x0c` | ? |
| `+0x10` | `view_data_t *view_data` |
| `+0x14` | `void *ctx` — the per-view RAM context (`reg+4` bytes, zeroed) |
| `+0x18` | `u16 view_id` |
| `+0x1a` | `u8 flags` — bit1 = focused, bit2 = layout inflated, bit0 = ? |

The pointer to this object is stored in **`view_data_t + 0x0c`**
(`view_data` = `{display, surface, presenter, user_data}` from
`view_manager.h`, so `user_data` holds the jx view object).

Preload also keeps a **"scene already loaded" bitmap** at `0x3801ad28`
(1 bit per view id) and logs `"--->_view_load:%u, %u\n"` (`0x102232d5`) around
the load.

### 1.5 Event ids and the dispatch table — verified

`0x100d5710` maps a message id to a name string; its string table
(`0x100d573c`, `0x100d5820`) yields **[V]**:

| id | name | id | name |
|---|---|---|---|
| 2 | `preload` | 12 | `display_resume` |
| 3 | `layout` | 13 | `key` |
| 4 | `delete` | 19 | `scroll begin` |
| 5 | `paint` | 20 | `scroll end` |
| 6 | `refresh` | 25 | `popup popup` |
| 7 | `focus` | 26 | `popup close` |
| 8 | `defocus` | 27 | `popup cancel` |
| 9..10 | (unnamed) | 28 | `popup paint` |
| 11 | `update` | 129 | `lang_change` |
| | | 130/131 | `user suspend` / `user resume` |
| | | 134 | `msgbox switch` |

This is the upstream `enum UI_MSG_ID` with `MSG_VIEW_PRELOAD = 2`.

`ui_view_creater` dispatch (`tbh` at `0x100d58de`, targets):

| msg | target | what it does |
|---|---|---|
| 2 preload | `0x100d591a` | `_ui_view_preload(reg, view_data)` — alloc object, load the view's `.sty` scene |
| 3 layout | `0x100d5928` | alloc `reg+4` ctx, `obj->ctx = ctx`, load scene if needed, then `reg+0x1c(obj)`, `reg+0x0c(obj)`, `reg+0x10(obj)`, and `reg+0x14(obj,1)` if already focused |
| 4 delete | `0x100d5bd2` | `reg+0x20(obj)`; `free(ctx)`; release scene (`0x101d779c`, `0x101d770e`); `free(obj)`; clear focus globals |
| 5 paint | `0x100d59d4` | `0x101b617e(reg, &view_data->obj)` — presenter repaint |
| 6/9/10 | `0x100d5902` | if `obj && obj->ctx && reg+0x2c` → `reg+0x2c(obj, msg_id)` |
| 7 focus | `0x100d59e0` | `obj->flags |= 2`, global focused-view = obj, log `_view_focus:%u, vid:%u, d:%p`, maybe notify presenter / touch scene |
| 8 defocus | `0x100d5a66` | `obj->flags &= ~2`, global cleared, `reg+0x14(obj, 0)` |
| 11 update | `0x100d59ca` | `0x101b6136(reg, &view_data->obj)` |
| 12 display_resume | `0x100d5ba8` | repaint + `0x10101b2c(1000)` |
| 13 key | `0x100d5c78` | checks msg_data, then `done = reg+0x28(obj, event)` and stores it at `msg_data+4` |
| 0x81 (129) | `0x100d5adc` | `reg+0x24(obj, 1)` then resource reload |
| 16 (SET_ORDER) w/ data 5 | `0x100d5894` | special case → `0x101b617e` |

Callback signature (all `reg` fns): first argument is the **jx view object**
(`obj`), not `view_data`. `view_data` is reachable as `obj+0x10`.

---

## 2. Question 2 — opening a view and going back

### 2.1 `FUN_101898bc(view_id, arg)` — "push view"

```
101898bc: r4 = view_id, r5 = arg
101898c4: memset(sp, 0, 16)          ; the request
101898d0: str  r5,[sp,#8]            ; arg -> req+8
101898d2: strh r4,[sp,#12]           ; id  -> req+12
101898d6: bl   0x1018bc04            ; registry lookup
101898da: cbnz r0 -> ok
          log "view(%u) entry not registered\n" (0x1024f3df) ; return -1
101898fc: movs r1,#1                 ; push = 1
101898fe: r0 = sp
10189900: bl   0x10189398            ; view_stack_push(req, 1)
```

**[V]** (log string `0x1024f3df` = `"view(%u) entry not registered\n"`; the
registry lookup is the only caller of `0x1018bc04`).

So: `int ui_view_open(uint16_t view_id, void *arg)` — returns 0 / negative
(`-1` unknown id, `-28` when the stack is full — `mvn #27` at `0x101893d6`,
`-3` when the stack is not initialised — `mvn #2` at `0x10189416`).

`arg` is stored in the stack entry and handed to the created view (the app
list passes `0x101eb06c`, its model struct; most callers pass 0).

### 2.2 The view stack

Base `0x380438e4` (RAM), 10 entries × 16 bytes, then `u8 depth` at `+0xa0`
(0xa0 = 10*16) and `u8 flags` at `+0xa1`. Guarded by the UI
mutex at `0x38004238` (`0x101be218` lock / `0x101be274` unlock); `0x10189148`
kicks the UI thread through `0x10199df4`.

Entry (16 bytes):

| off | type | field |
|---|---|---|
| `+0x00` | `void *` | jx view object (0 = "not created yet") |
| `+0x04` | `void *` | view group descriptor (`{u8 count; u16 ids[]; fn}`) — used by multi-page views |
| `+0x08` | `void *` | `arg` from `FUN_101898bc` |
| `+0x0c` | `u16` | view id |
| `+0x0e` | `u16` | aux/last id |

API (all in the block `0x10189148`..`0x101898bc`):

| addr | role |
|---|---|
| `0x10189398(req, push)` | push / replace-top; `depth > 9` → `-28` |
| `0x101891f8(entry, other)` | **realise a switch**: resolve the view id, (re)attach the surfaces, run the slide/fade animation. `other` is the outgoing entry on a pop and the pending request on a push (both are 16-byte structs with the same `+0/+0xc` layout) **[I]** |
| `0x10189148()` | request a redraw (`0x10199df4`) |
| `0x101894a8()` | commit/leave the top entry and return its view id (or the object if already created); does **not** change `depth` **[I]** |
| `0x101895a0(presenter, view_id)` | push with an existing presenter object (used for the watch face, `id 0x10`) |
| `0x101897fc()` | **back / pop one** — `0x101891f8(&entry[d-1], &entry[d-2])`, then `depth--` |
| `0x101897d0()` | clear the whole stack |
| `0x10189844(id)` | pop until the entry with view id `id` |
| `0x101896b8(id, arg, new_id)` | back-to `id` **and** replace it with `new_id` |
| `0x10189638(n)` | drop `n` entries |
| `0x10189794(n)` | peek the id of the entry `n` below the top |

### 2.3 Emulator evidence

Script `re/agent-views/s3.json` (boot, crown press at 12 s, tap "Exercise",
swipe back, tap "Heart Rate"), traced with
`re/agent-views/trace2.py`:

```
HIT 0x101898bc $r0=0x12 $r1=0x101eb06c        <- crown press: open applist, arg = model struct
HIT 0x10189398 *(unsigned int*)($r0+8)=0x101eb06c *(unsigned short*)($r0+12)=0x12 $r1=0x1
HIT 0x1005ed7e *(unsigned short*)($r0+16)=0              <- tap item 0
HIT 0x101898bc $r0=0x6a $r1=0
HIT 0x10189398 *(unsigned int*)($r0+8)=0 *(unsigned short*)($r0+12)=0x6a $r1=0x1
HIT 0x1005ed7e *(unsigned short*)($r0+16)=0x2            <- tap item 2
HIT 0x10189398 *(unsigned int*)($r0+8)=0 *(unsigned short*)($r0+12)=0xb2 $r1=0x1
```

and the matching UART log:

```
----->view:18, reg:0x101eb07c, ev:[preload]   (18 = 0x12 applist_view)
... sportlist 106 (0x6a) preload/focus/layout, then defocus/delete after the swipe
----->view:18 ... ev:[preload]                (back returned to the app list)
----->view:178, reg:0x101ed008, ev:[preload]  (178 = 0xb2 app_heart_view)
```

Back-swipe (`re/agent-views/s4.json`, trace7) hits `0x101897fc` exactly once
and the log shows the heart view `defocus` + `delete` followed by the app
list `preload/focus/layout` — **[V]** back = pop one stack entry and
re-realise the previous one.

Note the heart entry pushed **three** views (178 + 137 + 138) through a *group*
stored in the stack entry `+0x04`, i.e. one stack slot can own a horizontal
page group.

---

## 3. Question 3 — the app list

### 3.1 Which view is it

`applist_view`, id `0x12`, registry index 0 at file `0x4b8`, create
trampoline `0x1005e91d`, `reg = 0x101eb07c` (ctx 560 bytes, scene
`0xc18487b4`). Entries 1..3 (`applist_grid_view`, `applist_list_view`,
`applist_waterfall_view`) **share id `0x12`** and are not reachable through the
registry (`view_manager_get_view_entry` returns the first match); they are
reached only through `applist_view`'s style table.

`applist_view->reg+0x1c` (`0x1005e848`) is a dispatcher:

```
index = styles[applist_style()]          ; styles @0x101eb0ac = {list, waterfall}
if (index > 1 || styles[index] == NULL) index = 0   ; default = list
*(u32*)(0x38019434 + 0x22c) = styles[index]          ; remember the style reg
call styles[index]->reg+0x1c(obj)                    ; do that style's layout
```

`applist_style()` = `0x101ad184` = `settings_get(0x2c, &byte, 4, 0)` — the
list style is a **setting** (item `0x2c`), not a compile-time choice.

Confirmed in the emulator: the app list renders the vertical wheel list
(`applist_list_view`, `reg 0x101eb154`, layout `0x1005ec9c`) — see
`runs/views-applist1/applist.png`.

### 3.2 The entry table — verified

`applist_list_view`'s layout (`0x1005ec9c`) does, before anything else:

```
r6 = obj->ctx
for k in 0..24:   ids[k] = *(u32*)(0x101eaf40 + 12*k)          ; icon nodes
ctx->count = 25
0x101848d4(obj+4, ids, ctx+0x0c, 0, 25)      ; load 25 image nodes -> 12-byte records
for k in 0..24:   ids[k] = *(u32*)(0x101eaf40 + 12*k + 4)      ; label nodes
0x10184a5c(obj+4, ids, ctx+0x138, 25)        ; load 25 text nodes  -> 8-byte records
0x100df9a0(ctx+0x20c, <string>)              ; per-view something
```

**[V]** The table is a **static flash table at `0x101eaf40` (file
`0x1eaf40`), 25 records × 12 bytes** (`0x101eaf40..0x101eb06c`). Record:

| off | type | meaning |
|---|---|---|
| `+0x00` | `u32` | **icon scene-node id** in scene `0xc18487b4` (an image node) |
| `+0x04` | `u32` | **label scene-node id** in the same scene (a text node → `bt_watch.<lang>` index) |
| `+0x08` | `u32` | **action**: `≤ 0xF4` → view id for `FUN_101898bc`; `> 0xF4` → function pointer called with no args |

Immediately after it, at `0x101eb0e4`, is a **5 × 8-byte remap table**
`{icon_node_id → alternate_icon_node_id}` (`0xbcacd03c→0xace35d07`, …) used
only by the *grid* style builder `0x1005e938` (it swaps 5 icons for the
160×160 variants and rotates the first five slots); the list style does **not**
apply it.

### 3.3 Tap handling — verified

Item widgets are created by `0x1005a014` (custom LVGL class `0x101eadc4`);
the click callback registered on each item is `0x1005eba0` (grid) /
`0x1005ed74` (list):

```
bl 0x101c4c96                 ; event -> per-item object
index = *(u16*)(obj+0x10)
activate = *(u32*)(0x101eb06c + 0x0c)
return activate(index)
```

`0x101eb06c` is the app-list **model struct**: `{0x101ad185 (style getter),
0x1005e7e9 (get scroll pos), 0x1005e785 (set scroll pos), 0x1005e791
(activate)}`.

`0x1005e791(index)`:

```
if (index > 24) return;
action = *(u32*)(0x101eaf40 + 12*index + 8);
if (action == 0) return;
if (action <= 0xF4) ui_view_open(action, 0);   // b.w 0x101898bc
else                ((void(*)(void))action)(); // small per-item wrapper
```

**[V]** — traced: `HIT 0x1005ed7e [obj+16]=0` → `HIT 0x101898bc $r0=0x6a`;
`[obj+16]=2` → push `0xb2`.

The 11 wrapper functions add state checks before opening, e.g.
`0x101af65a` (Exercise Records): if `0x100e082c(0x3e,&p)` returns non-NULL →
open `0x6d` (sport_record_view) else `0x6e` (sport_unrecorded_view, the "No
record" screen we saw in `runs/views-trace3/item1.png`).

### 3.4 The 25 entries, resolved

`icon`/`label` are the scene node ids (same value appears in `bt_watch.sty`,
scene `0xC18487B4`); `action` is decoded. Labels in the last column are what
the emulator shows (`runs/views-scroll*/`).

| # | file addr | icon node | label node | action | → | label |
|---:|---|---|---|---|---|---|
| 0 | `0x1eaf40` | `0xbcacd03c` | `0x1a521ce6` | `0x6a` | view `0x6a` sportlist_view | Exercise |
| 1 | `0x1eaf4c` | `0xa620b0f2` | `0x4d4729ad` | `0x101af65b` | wrapper → `0x6d`/`0x6e` | Exercise Records |
| 2 | `0x1eaf58` | `0xe91b08c3` | `0xad5f7cc4` | `0x1006f1e5` | wrapper → `0xb2` app_heart_view | Heart Rate |
| 3 | `0x1eaf64` | `0x1395bc7d` | `0x6c82b520` | `0x73` | view `0x73` bloodoxygen | Blood Oxygen |
| 4 | `0x1eaf70` | `0x1cc71f33` | `0x2eeb823a` | `0x100872f9` | wrapper → `0xe8` vitality_data_view | Active Score |
| 5 | `0x1eaf7c` | `0xf3d51854` | `0x93383812` | `0x10081319` | wrapper → `0x79` appactivity_record_view | Activity |
| 6 | `0x1eaf88` | `0x87f0c448` | `0xb95b9371` | `0x10074739` | wrapper → `0xe9` sleep_data_view | Sleep |
| 7 | `0x1eaf94` | `0x89969737` | `0x586b9972` | `0x101b30c9` | wrapper → `0x9b` pressure_detecting_view | Stress |
| 8 | `0x1eafa0` | `0x1c590053` | `0xc7610a30` | `0x101ad225` | wrapper → `0xda`/`0xd9` female_main/guide | Cycles |
| 9 | `0x1eafac` | `0x477b5bdd` | `0x56e9c9e6` | `0x101b05cf` | wrapper → `0xeb`/`0xac` world_clock* | World clock |
| 10 | `0x1eafb8` | `0xe63447f4` | `0xdb9dc6cf` | `0xdc` | view `0xdc` todo_list_view | Reminders |
| 11 | `0x1eafc4` | `0x44be7545` | `0xaa4bf859` | `0xc5` | view `0xc5` call_tag_view | Calls |
| 12 | `0x1eafd0` | `0x8f3d514c` | `0xc07dea21` | `0x90` | view `0x90` music_main_view | Music |
| 13 | `0x1eafdc` | `0x9b68bf24` | `0x7699a044` | `0x88` | view `0x88` photograph_view | Camera/Photos |
| 14 | `0x1eafe8` | `0xe807b751` | `0xb0041c84` | `0x1007f699` | wrapper → `0x5a` weather_main_view | Weather |
| 15 | `0x1eaff4` | `0x33e5775b` | `0xd0e50dc3` | `0x8c` | view `0x8c` breath_view | Breath |
| 16 | `0x1eb000` | `0x6538d2e9` | `0xdfc8ea0f` | `0xcf` | view `0xcf` voice_assistant_view | Voice Assistant |
| 17 | `0x1eb00c` | `0x95975ee8` | `0xa006afc1` | `0x1c` | view `0x1c` stopwatch_view | Stopwatch |
| 18 | `0x1eb018` | `0x04a8df21` | `0x1cbfe55b` | `0x61` | view `0x61` timer_home_view | Timers |
| 19 | `0x1eb024` | `0x1298aa59` | `0xa83b03c7` | `0x81` | view `0x81` alarm_clock_view | Alarms |
| 20 | `0x1eb030` | `0x877aaa6f` | `0xead9137f` | `0xcd` | view `0xcd` calc_view | Calculator |
| 21 | `0x1eb03c` | `0x661ab355` | `0x2043ea82` | `0xce` | view `0xce` calendar_view | Calendar |
| 22 | `0x1eb048` | `0x6af1ebb1` | `0x7f7e87a6` | `0x86` | view `0x86` flash_light_view | Flashlight |
| 23 | `0x1eb054` | `0x64582bf0` | `0xa31d5609` | `0x43` | view `0x43` findphone_view | Find phone |
| 24 | `0x1eb060` | `0xdefbe0d9` | `0x22f3be00` | `0x44` | view `0x44` setlist_view | Settings |

Order in the table == order on screen (checked by scrolling:
Exercise, Exercise Records, Heart Rate, Blood Oxygen, Active Score, Activity,
Sleep, Stress, Cycles, World clock, Reminders … Timers, Alarms, Calculator,
Calendar; Voice Assistant, Stopwatch, Timers, Alarms — **[V]** screenshots in
`runs/views-scroll1..3`).

### 3.5 The scene behind it (resources)

`fwkit sty-tree bt_watch.sty 0xc18487b4` → scene 29, **56 top-level nodes**:

* 25 image nodes 96×96 bpp3, ids `BCACD03C..1CC71F33`, `pic=544..568`
  (the icons; the *action* table's `+0x00` matches these ids exactly);
* 5 image nodes 160×160 bpp2, ids `ACE35D07, 5781AEFA, 13273DB6, 9F474F43,
  2DDE8D18` — the alternates named by the remap table at `0x101eb0e4`;
* 26 text nodes, ids `1A521CE6..2EEB823A` (the labels; the action table's
  `+0x04` matches the first 25), plus one **unused spare** `0x947D3668`
  (`text=514`).

Text nodes hold only an index into `bt_watch.<lang>` (`formats/style.md` §3);
image nodes hold a 1-based picture index into `bt_watch.res`. So **entry text
and icons are resource data, not code**: changing a label means editing
`bt_watch.sty` (text index, in place, 4 bytes) and/or the string pool
`bt_watch.<lang>`; changing the icon means editing the image node / `.res`.

Consistency check for the label pipeline: table entries 0 and 1 use text
indices 161 and 162, and the two strings are adjacent in the English pool
(`…\0Excellent\0Exercise\0Exercise Records\0…` at file `0x18dfbba`). **[V]**

### 3.6 Context layout of the list style (`reg+4 = 0x22c` = 556)

| off | field |
|---|---|
| `+0x00` | `lv_obj_t *screen` (`0x101255e0` = `lv_scr_act`) |
| `+0x04` | container object |
| `+0x08` | `u8 count` = 25 |
| `+0x0c` | 25 × 12-byte records (icon node data) = 300 B → ends at `0x138` |
| `+0x138` | 25 × 8-byte records (text node data) = 200 B → ends at `0x200` |
| `+0x20c` | `0x100df9a0` state |

This is why 25 is the hard limit for this style: `12 + 25*12 = 0x138` exactly,
and the next array starts there.

### 3.7 Adding one entry — options, least invasive first

**A. Repoint an existing entry's action (4 bytes, no size change)** — open a
new view id from an existing row. Keeps that row's icon and label.

* record `k`, action field at **file `0x1eaf40 + 12*k + 8`** (little-endian
  `u32`). e.g. `k=4` ("Active Score") → file `0x1eaf78`; `k=8` ("Cycles") →
  `0x1eafa8`; `k=24` ("Settings") → `0x1eb068`.
* value must be **≤ `0xF4`** to be treated as a view id; ids are `u16`-sized
  in practice. The id must already exist in the registry (or you add it, see D).
* if the id you want to open needs a precondition, point the action at a
  wrapper function instead (`> 0xF4`), like `0x101af65a` does.

**B. A. plus a new label (no size change)** —
point the record's label field (`file 0x1eaf40 + 12*k + 4`) at the spare text
node `0x947D3668`, then patch that node's text index in `bt_watch.sty` to a
string you add/overwrite in `bt_watch.<lang>` (`fwkit sty-*` / `res-set` /
`edit-res`). Icons can be pointed at any existing image node the same way.

**C. A real 26th entry (bigger patch, do not start here)** — needs all of:

| what | where |
|---|---|
| `cmp r3,#25` → `#26` in the list builder | `0x1005ecb8` and `0x1005ed02` |
| `cmp r3,#25` → `#26` in the grid builder | `0x1005e97e` (and drop the first-five rotation at `0x1005e950`) |
| `cmp r4,#24` → `#25` in `activate` | `0x1005e7b0` |
| list ctx size `0x22c` → `>= 0x240` | `reg+4` at `0x101eb158` (and grid/waterfall regs) |
| the 25-entry table itself | must be **relocated** (it is followed immediately by other rodata at `0x101eb06c`), then patch the four `=0x101eaf40` literals: `0x1005e7b6` (activate), `0x1005e93c` (grid), `0x1005ecae` + `0x1005ecfa` (list, both passes) |
| the `.sty` scene | must gain a 26th icon+label node pair (`fwkit sty-add-scene` clones a whole scene, not a node) |

Also note the count is hard-coded in the *scene* side too: only 25 icons/25
labels exist.

**D. Adding a new view id** (needed by A/B/C):

* the registry is a fixed 162-entry array (`0x100004b8..0x100013e8`); entry 161
  is followed by other rodata, so appending in place is impossible.
* **clean option**: copy the 162 entries (3,888 B) to a free flash region, add
  the 163rd entry at the end, and patch the two literals in the lookup function
  `0x1018bc04`: `0x100004b8` at `0x1018bc24` and `0x100013e8` at `0x1018bc28`
  (8 bytes total). Nothing else reads the table. Candidate caves (long
  zero-filled runs; verify they are unreferenced first): `0x101e5bb2`
  (`0x2A4E` B), `0x101e8604` (`0xFBD` B), `0x101e98d3` (`0xB05` B),
  `0x1025507e` (`0x2E0` B).
* **minimal option**: overwrite one existing entry in place (24 bytes at
  `0x100004b8 + 24*idx`) — name pointer, `proc2`, id, order, type, size — and
  reuse its id. The cheapest ids to sacrifice are the payment views
  (`0x2c..0x33`): they are implemented (legacy `proc`, §1.2) but cannot be
  reached without the phone-side Alipay/WeChat-Pay integration, so they are
  dead weight on a stock watch. Note `0x2c ≤ 0xF4`, so it can be used directly
  as an app-list action. Do **not** pick `welcome/goodbye/power_saving`
  (`0x2a`, `0x2b`, `0xa9`) — they are on the boot / power-off paths.
* incompatible third option: pick one of the 85 unused ids in `1..0xF4`
  (`0x02..0x0f`, `0x13`, `0x17..0x1a`, `0x1d`, …) — only works together with
  the registry relocation above.

---

## 4. Question 4 — `about_view` (id `0x4e`) as a template

Registry index 155, file `0x1340`: name `"about_view"`, `proc2 = 0x100bf9f9`,
`reg = 0x101f2a38`.

| reg field | value |
|---|---|
| id / order / type | `0x4e` / 2 / 1 |
| ctx size (`+4`) | `0x124` = 292 |
| scene id (`+8`) | `0x811150a2` |
| `+0x0c` | `0x100bfbf4` — creates the screen + 4 LVGL sub-objects |
| `+0x10` | `0x100bf8e4` — logging stub |
| `+0x14` | `0x100bfab8` — focus |
| `+0x18` | `0x101b55f3` — resource descriptor |
| `+0x1c` | `0x100bf90c` — **inflate** |
| `+0x20` | `0x100bfb7c` — **destroy** |
| `+0x24` | `0x100bfa60` — reload the 13 text nodes on `lang_change` |
| `+0x28` | `0x100bfa14` — key handler (only reacts to event `0x04000001`, returns 1) |
| `+0x2c` | 0 (no generic event handler) |

The **factory-mode 5-tap** trigger is not in `reg`: `0x100bf9bc` is attached as a
*widget click callback* by the About view's build code
(`ldr r1,=0x100bf9bd; bl 0x10125a94(widget, cb, 7, ctx)` at `0x100bff7c`), and it
does `0x101cb8a2(now) < 0x14c` → counter++ , `>4` → `FUN_101898bc(0x87, 0)`.
That confirms the hardware.md note and shows the widget-level event hook. **[V]**

`reg` is immediately preceded by the 13 node ids the view binds:
`0x101f2a04` (13 × u32 = the scene's 13 text node ids, in scene order —
**[V]** compared against `fwkit sty-tree`).

### Inflate `0x100bf90c` (`+0x1c`)

```
ctx = obj->ctx
if (!ctx->loaded28) { 0x100df9a0(ctx+0xe0, "/NAND:A/font28M.font"); ctx->loaded28 = 1 }
if (!ctx->loaded32) { 0x100df9a0(ctx+0x100, "/NAND:A/font32M.font"); ctx->loaded32 = 1 }
0x10184a5c(obj+4, ids=0x101f2a04, out=ctx+0x48, n=13)   ; load 13 text nodes (8-byte records)
log "load resource succeed"
return 0
```

So the whole widget tree comes from the scene: `0x10184a5c` instantiates the
nodes into the view's scene context (`obj+4`, produced by the loader
`0x1018566c` with `/NAND:A/bt_watch.sty` + `/NAND:A/bt_watch.res`) and writes
per-node handles into `ctx+0x48`. Per-view fonts are loaded into
`ctx+0xe0`/`ctx+0x100` (`ctx->0x120`/`0x121` are the "loaded" flags).

`+0x0c` `0x100bfbf4` is the only place that touches LVGL directly:
`0x101255e0` (`lv_scr_act`), `0x1013a8e4` (obj create), `0x101cc792/0x101cc78a/
0x101cc770` (style/flag setters, colour `0xad55`) for four 12-byte objects at
`ctx+0xb0/0xbc/0xc8/0xd4`.

### Teardown `0x100bfb7c` (`+0x20`, MSG_VIEW_DELETE)

Called by `ui_view_creater` at `0x100d5bfe` **before** the context is freed:

```
for (p = ctx+0xb0; p != ctx+0xe0; p += 12) 0x1013a924(p)   ; delete 4 objects
if (ctx->screen) { 0x1012c880(ctx->screen); ctx->screen = 0 }
if (ctx->0x120) { 0x101b9914(ctx+0xe0);  ctx->0x120 = 0 }  ; unload font28M
if (ctx->0x121) { 0x101b9914(ctx+0x100); ctx->0x121 = 0 }  ; unload font32M
0x101d777a(ctx+0x48, 13)                                    ; release 13 node records
```

Then the generic delete path (`0x100d5bd2`) does the rest: clear the focus
globals, `free(obj->ctx)`, drop the scene (`0x101d779c`, `0x101d770e`),
`free(obj)`, `view_data->obj = 0`. Verified in the log: `ev:[delete]` on
`reg:0x101f2a38`.

### What a new view must provide

From the call sites, **`reg+0x0c`, `+0x10`, `+0x14`, `+0x1c`, `+0x20`, `+0x24`
are called without a NULL check**, so a hand-written view needs at least
`bx lr`/`movs r0,#0; bx lr` stubs for the unused ones (`+0x2c` and `+0x28` are
checked). `+0x1c` must return 0 and set `obj->flags bit2`.

Two layouts are possible:

1. **scene-driven (what every shipped view does)**: give `reg+8` a `.sty` scene
   id and write an `+0x1c` that calls `0x10184a5c(obj+4, ids, out, n)` with
   your node ids. Clone a scene with `fwkit sty-add-scene ... --fresh-node-ids`
   (About's scene `0x811150a2`, 13 text nodes, is a good donor), then either
   patch an `app.bin` scene-id literal or point the new `reg+8` at it.
2. **code-driven (`reg+8 == 0`)**: `_ui_view_preload` returns early and the
   layout path calls `reg+0x1c` directly (the `cbnz r3` at `0x100d5962`).
   Your inflate then builds `lv_*` widgets itself using
   `obj->view_data->display` (`obj+0x10` → `+0x00`) — no `.sty` scene, no
   resource partition change. Not used by any shipped view, so untested.

---

## 5. Recommended way to add "Faceclaw remote" to the app list

Short version: **reuse id `0x2c` and one app-list row's action field.**

1. **New screen** — write a view with `reg+8 = 0` (code-driven, no `.sty`
   change) or point it at a fresh clone of the About scene. Provide
   `+0x1c` (inflate), `+0x20` (destroy) and stubs for `+0x0c/+0x10/+0x14/+0x24`.
   Place the `reg` struct + trampoline (`ldr r0,=reg; bl 0x100d587c`) in a code
   cave and, if you want, a `char *` name string next to it.
2. **Registry** — overwrite the `alipay_main_view` entry (index 115, file
   `0x4b8 + 24*115 = 0xf80`) with our name pointer / `proc2`; keep
   `id = 0x2c`, `order = 2`, `type = 1`, `w = h = 0x1d2`. Nothing else in the
   table moves, the array stays 162 entries.
3. **App-list row** — pick a row you can live without (e.g. `k = 4`
   "Active Score", or `k = 8` "Cycles") and store `0x2c` at file
   `0x1eaf40 + 12*k + 8`. Now that row opens the new screen; label and icon
   are still the old ones.
4. **Label/icon (optional, resource-side)** — point the row's label node
   (`+4`) at the spare text node `0x947D3668` and patch that node's text index
   in `bt_watch.sty` to a string you add to `bt_watch.<lang>` (`fwkit sty-*`,
   `res-set`/`edit-res`); or clone a scene and use fresh node ids. This is the
   only part that touches the resource partitions, and it can be done later
   without re-patching `app.bin`.

Why not append a 26th row: the count 25 is compiled into the list builder
(`0x1005ecb8`, `0x1005ed02`), the activate bound (`0x1005e7b0`), the grid
builder (`0x1005e97e`), the context size (`reg+4 = 0x22c`, arrays end at
`0x138`+`0xC8`) and the scene (only 25 icon/label nodes exist). Repointing one
row is 4 bytes and cannot break the layout.

---

## 6. Reproduction

```
# from the repo root; the re/agent-views scripts are local probes, not committed
python3 re/agent-views/parse_views.py      # registry + entry dump
python3 re/agent-views/parse_regs.py       # reg structs (partial heuristics)
python3 re/agent-views/gen_tables.py       # views_table.tsv + applist_table.tsv
python3 re/agent-views/trace2.py --output runs/views-x --script re/agent-views/s3.json \
        --seconds 25 --break 0x101898bc:'$r0','$r1' --break 0x10189398:'*(unsigned short*)($r0+12)'
uv run --project ../cmf-watch-utils python tools/emu.py --output runs/views-x \
        --script re/agent-views/s2.json --seconds 27
../cmf-watch-utils/.venv/bin/fwkit sty-tree ../cmf-watch-utils/dumps/samples/bt_watch.sty 0xc18487b4
```

`tools/trace.py` was not usable as-is here (it swallows gdb stderr and the
`--break` parse drops extra expressions); `re/agent-views/trace2.py` is the
same idea with working multi-expression prints.

## 7. Appendix — full view table (162 entries)

`create` = `proc2` (trampoline into `ui_view_creater`), `reg` = descriptor
address, `ctx` = per-view RAM context size, `scene` = `.sty` scene id.

| # | id | ord | name | proc2 (create) | reg struct | ctx | scene id |
|---:|---|---:|---|---|---|---:|---|
| 0 | 0x0012 | 2 | `applist_view` | 0x1005e91d | 0x101eb07c | 560 | 0xc18487b4 |
| 1 | 0x0012 | 2 | `applist_grid_view` | 0x1005ebc5 | 0x101eb0b4 | 412 | 0xc18487b4 |
| 2 | 0x0012 | 2 | `applist_list_view` | 0x1005eec9 | 0x101eb154 | 556 | 0xc18487b4 |
| 3 | 0x0012 | 2 | `applist_waterfall_view` | 0x1005f101 | 0x101eb184 | 348 | 0xc18487b4 |
| 4 | 0x00d9 | 2 | `female_guide_view` | 0x1005f489 | 0x101eb1b4 | 76 | 0xc4ce09c6 |
| 5 | 0x00da | 2 | `female_main_view` | 0x1005fbd1 | 0x101eb1ec | 492 | 0xed533927 |
| 6 | 0x00ce | 2 | `calendar_view` | 0x10060061 | 0x101eb298 | 356 | 0xc053763b |
| 7 | 0x001b | 2 | `power_view` | 0x100607b1 | 0x101eb2f8 | 116 | 0xb9590a4a |
| 8 | 0x002b | 0 | `goodbye_view` | – | – | – | – |
| 9 | 0x002a | 0 | `welcome_view` | – | – | – | – |
| 10 | 0x001c | 2 | `stopwatch_view` | 0x10060f25 | 0x101eb354 | 428 | 0xa80dd9e8 |
| 11 | 0x003d | 2 | `effect_wheel_wheel` | 0x10061ddd | *self-contained proc* | – | – |
| 12 | 0x00c3 | 2 | `effect_wheel` | 0x100624ad | *self-contained proc* | – | – |
| 13 | 0x0085 | 2 | `alarm_clock_edit_repeat_view` | 0x10062f0d | 0x101eb3c4 | 308 | 0xf5a2d62d |
| 14 | 0x0084 | 2 | `alarm_clock_edit_time_view` | 0x100638f5 | 0x101eb41c | 280 | 0x1aba7bce |
| 15 | 0x0082 | 2 | `alarm_clock_edit_view` | 0x1006402d | 0x101eb458 | 100 | 0x3ad26fe2 |
| 16 | 0x0083 | 2 | `alarm_reedit_view` | 0x100644bd | 0x101eb4ec | 380 | 0xc6b0eabf |
| 17 | 0x0081 | 2 | `alarm_clock_view` | 0x10064ec5 | 0x101eb588 | 460 | 0xa4309a67 |
| 18 | 0x0010 | 2 | `clock_view` | 0x1006e3f5 | 0x101ecd68 | 8 | 0x067e8cbc |
| 19 | 0x0001 | 1 | `ctrl_center_view` | 0x1006e45d | 0x101ece54 | 524 | 0x3384061c |
| 20 | 0x0089 | 2 | `heart_report_view` | 0x1006f489 | 0x101eceb0 | 328 | 0xd4bca7fa |
| 21 | 0x008a | 2 | `heart_resting_heart_rate_view` | 0x1006f925 | 0x101ecf3c | 540 | 0x5e50ecc8 |
| 22 | 0x00b2 | 2 | `app_heart_view` | 0x100701c9 | 0x101ed008 | 552 | 0xa91c026f |
| 23 | 0x0014 | 2 | `heart_view` | 0x100701ad | 0x101ed050 | 552 | 0xa91c026f |
| 24 | 0x0015 | 2 | `heart_warn_view` | 0x10070ba1 | 0x101ed0a8 | 108 | 0x58c85760 |
| 25 | 0x0016 | 1 | `messagelist_view` | 0x10071b6d | 0x101ed118 | 536 | 0x8ceb47c2 |
| 26 | 0x0090 | 2 | `music_main_view` | 0x10073f59 | 0x101ed228 | 276 | 0xfea9f514 |
| 27 | 0x00e9 | 2 | `sleep_data_view` | 0x1007480d | 0x101ed298 | 852 | 0xc76e8d15 |
| 28 | 0x0060 | 2 | `sleepdetails_view` | 0x10074ddd | 0x101ed2e0 | 936 | 0x28801a8b |
| 29 | 0x005e | 2 | `sleep_view` | 0x100756a1 | 0x101ed378 | 1176 | 0xb63da608 |
| 30 | 0x00a9 | 2 | `power_saving_view` | – | – | – | – |
| 31 | 0x0064 | 2 | `sport1_view` | 0x10078a15 | 0x101ed554 | 1284 | 0x6880ae34 |
| 32 | 0x00e6 | 2 | `sport_details_note_view` | 0x1007a445 | 0x101ed584 | 72 | 0xf3aed6f1 |
| 33 | 0x006b | 2 | `sport_prepartion_view` | 0x1007aec1 | 0x101ed6d8 | 1152 | 0xfedd130c |
| 34 | 0x00a5 | 2 | `sport_prompt_sel_view` | 0x1007c705 | 0x101ed840 | 72 | 0x86d1ba13 |
| 35 | 0x006d | 2 | `sport_record_view` | 0x1007c8d1 | 0x101edaf8 | 756 | 0x1a36b89f |
| 36 | 0x006c | 2 | `sport_report_view` | 0x1007cf6d | 0x101edb40 | 864 | 0x8fc60074 |
| 37 | 0x0072 | 2 | `sport_setcalu_view` | 0x1007db79 | *self-contained proc* | – | – |
| 38 | 0x0070 | 2 | `sport_setdistance_view` | 0x1007dfe1 | *self-contained proc* | – | – |
| 39 | 0x006f | 2 | `sport_setlist_object_view` | 0x1007e315 | 0x101edcc4 | 160 | 0xbf2d9f3c |
| 40 | 0x0071 | 2 | `sport_settime_view` | 0x1007e665 | *self-contained proc* | – | – |
| 41 | 0x006e | 2 | `sport_unrecorded` | 0x1007e965 | *self-contained proc* | – | – |
| 42 | 0x006a | 2 | `sportlist_view` | 0x1007eee1 | 0x101ee234 | 1008 | 0xd0535bb9 |
| 43 | 0x005d | 2 | `weather_sub3_view` | 0x1007f855 | 0x101ee4a8 | 2308 | 0xa0d10dab |
| 44 | 0x005c | 2 | `weather_sub2_view` | 0x1007f839 | 0x101ee478 | 2308 | 0x0fcc7bbc |
| 45 | 0x005b | 2 | `weather_sub_view` | 0x1007f81d | 0x101ee4d8 | 2308 | 0x1aabfa35 |
| 46 | 0x005a | 2 | `weather_main_view` | 0x10080ae5 | 0x101ee574 | 640 | 0x9cfcff9f |
| 47 | 0x007b | 2 | `activity_record_calories_view` | 0x1008147d | 0x101ee6c4 | 248 | 0xf3ad4171 |
| 48 | 0x0079 | 2 | `appactivity_record_view` | 0x10081df5 | 0x101ee730 | 132 | 0x9f49b479 |
| 49 | 0x0078 | 2 | `activity_record_view` | 0x10081dd9 | 0x101ee700 | 132 | 0x9f49b479 |
| 50 | 0x0080 | 2 | `act_note_info_view` | 0x10081fcd | 0x101ee760 | 156 | 0x91833bda |
| 51 | 0x007a | 2 | `activity_record_one_view` | 0x10082659 | 0x101ee7cc | 280 | 0xec0e498b |
| 52 | 0x007d | 2 | `activity_record_stands_view` | 0x100827c9 | 0x101ee81c | 276 | 0x0e406130 |
| 53 | 0x007e | 2 | `activity_record_steps_view` | 0x10082e31 | 0x101ee864 | 240 | 0xe666c1d4 |
| 54 | 0x007c | 2 | `activity_record_strenght_view` | 0x10083419 | 0x101ee8b8 | 308 | 0x76532fd8 |
| 55 | 0x0098 | 2 | `common_warn_view` | 0x10083c7d | 0x101ee93c | 252 | 0xaddbf35d |
| 56 | 0x0075 | 2 | `guid_view` | 0x1004b121 | *self-contained proc* | – | – |
| 57 | 0x0073 | 2 | `bloodoxygen` | 0x100844e5 | *self-contained proc* | – | – |
| 58 | 0x0077 | 2 | `measure_view` | 0x10084bb5 | *self-contained proc* | – | – |
| 59 | 0x0074 | 2 | `blood_oxygen_note_view` | 0x10085045 | *self-contained proc* | – | – |
| 60 | 0x0076 | 2 | `war_view` | 0x10085905 | *self-contained proc* | – | – |
| 61 | 0x00eb | 2 | `world_clock_connect_view` | 0x10085af1 | 0x101eea10 | 80 | 0x7e51a197 |
| 62 | 0x00ae | 2 | `world_clock_details_view` | 0x10085d65 | 0x101eec74 | 1772 | 0x4c973f0b |
| 63 | 0x00ad | 2 | `world_clock_setting_view` | 0x10086739 | 0x101eedd8 | 796 | 0x2ad0364d |
| 64 | 0x00ac | 2 | `world_clock_view` | 0x10086c71 | 0x101ef034 | 1400 | 0xb5957026 |
| 65 | 0x00e8 | 2 | `vitality_data_view` | 0x1008749d | 0x101ef0ac | 504 | 0x46c88460 |
| 66 | 0x0046 | 2 | `vitality_details_view` | 0x10087da1 | 0x101ef104 | 608 | 0xcc2d2d62 |
| 67 | 0x0047 | 2 | `vitality_info_view` | 0x10088645 | 0x101ef140 | 132 | 0x397f0944 |
| 68 | 0x0045 | 2 | `vitality_view` | 0x10088a91 | 0x101ef184 | 404 | 0xb91750b3 |
| 69 | 0x0043 | 2 | `findphone_view` | 0x10089259 | 0x101ef1d8 | 168 | 0xf6a2acbe |
| 70 | 0x0086 | 2 | `flash_light_view` | 0x10089bbd | 0x101ef22c | 208 | 0x94f02ab4 |
| 71 | 0x008f | 2 | `breath_result_view` | 0x1008a1e9 | 0x101ef288 | 228 | 0x82640ffa |
| 72 | 0x008d | 2 | `breath_set_view` | 0x1008a7a1 | 0x101ef2dc | 212 | 0x29ed3eb5 |
| 73 | 0x008c | 2 | `breath_view` | 0x1008abbd | 0x101ef324 | 188 | 0x2f9e936e |
| 74 | 0x008e | 2 | `breath_training_view` | 0x1008b1a5 | 0x101ef510 | 288 | 0x61f1cd9a |
| 75 | 0x0062 | 2 | `timer_customize_view` | 0x1008b6d5 | 0x101ef564 | 180 | 0x5bbe3e12 |
| 76 | 0x0061 | 2 | `timer_home_view` | 0x1008bd65 | 0x101ef5a4 | 180 | 0x86cec314 |
| 77 | 0x0063 | 2 | `timer_running_view` | 0x1008c3ed | 0x101ef600 | 300 | 0x30f87622 |
| 78 | 0x00a4 | 2 | `lang_select_view` | 0x1008cda9 | 0x101ef690 | 1180 | 0x30c7c8f2 |
| 79 | 0x00a7 | 2 | `band_poweron_view` | 0x1008d2c1 | 0x101ef6fc | 328 | 0xeb7923c3 |
| 80 | 0x0087 | 2 | `factory_test_view` | 0x10093fb9 | 0x101ef734 | 184 | 0x113bb602 |
| 81 | 0x00e7 | 0 | `user_test_view` | 0x10095afd | 0x101ef76c | 76 | 0xc4ce09c6 |
| 82 | 0x0094 | 2 | `call_contacts_view` | 0x10097e29 | 0x101ef880 | 268 | 0x43a4f4c7 |
| 83 | 0x00a8 | 2 | `call_dial_view` | 0x10098991 | 0x101ef8f0 | 288 | 0xde570484 |
| 84 | 0x0095 | 2 | `call_records_view` | 0x1009933d | 0x101ef968 | 384 | 0x7ce5e6fc |
| 85 | 0x00c5 | 2 | `call_tag_view` | 0x10099d09 | 0x101ef9b0 | 196 | 0x53c6e91e |
| 86 | 0x0088 | 2 | `photograph_view` | 0x1009b389 | 0x101efc58 | 300 | 0xc7b9a9e7 |
| 87 | 0x00d7 | 2 | `card_widget8_view` | 0x1009b9cd | 0x101eff34 | 148 | 0xe6eb202d |
| 88 | 0x00d6 | 2 | `card_widget7_view` | 0x1009b9b1 | 0x101eff04 | 148 | 0xe6eb202d |
| 89 | 0x00d5 | 2 | `card_widget6_view` | 0x1009b995 | 0x101efed4 | 148 | 0xe6eb202d |
| 90 | 0x00d4 | 2 | `card_widget5_view` | 0x1009b979 | 0x101efea4 | 148 | 0xe6eb202d |
| 91 | 0x00d3 | 2 | `card_widget4_view` | 0x1009b95d | 0x101efe74 | 148 | 0xe6eb202d |
| 92 | 0x00d2 | 2 | `card_widget3_view` | 0x1009b941 | 0x101efe44 | 148 | 0xe6eb202d |
| 93 | 0x00d1 | 2 | `card_widget2_view` | 0x1009b925 | 0x101efe14 | 148 | 0xe6eb202d |
| 94 | 0x00d0 | 2 | `card_widget_view` | 0x1009b909 | 0x101eff64 | 148 | 0xe6eb202d |
| 95 | 0x00cf | 2 | `voice_assistant_view` | 0x100ad571 | 0x101f1424 | 172 | 0x30bd0452 |
| 96 | 0x009b | 2 | `pressure_detecting_view` | 0x100adae9 | 0x101f156c | 84 | 0xb5e0a55e |
| 97 | 0x009d | 2 | `pressure_note_view` | 0x100ae075 | 0x101f15a8 | 124 | 0x7c9c3853 |
| 98 | 0x009a | 2 | `pressure_ratio_view` | 0x100ae091 | 0x101f1608 | 316 | 0xf6cdc8b8 |
| 99 | 0x0099 | 2 | `pressure_view` | 0x100ae701 | 0x101f167c | 448 | 0x4acf7586 |
| 100 | 0x009c | 2 | `pressure_war_view` | 0x100aeddd | 0x101f16c0 | 120 | 0x5eada54f |
| 101 | 0x00cd | 2 | `calc_view` | 0x100af135 | 0x101f1740 | 344 | 0x5de238b4 |
| 102 | 0x00e1 | 2 | `todo_no_message_view` | 0x100af491 | 0x101f1778 | 164 | 0x3ac5dbe3 |
| 103 | 0x00dc | 2 | `todo_list_view` | 0x100af7a5 | 0x101f17bc | 200 | 0x49ad01b6 |
| 104 | 0x00df | 2 | `todo_type_detail2_view` | 0x100afd41 | 0x101f180c | 428 | 0x5061d9ec |
| 105 | 0x00e0 | 2 | `todo_type_detail_view` | 0x100afd25 | 0x101f183c | 428 | 0x5061d9ec |
| 106 | 0x00dd | 2 | `todo_type_list2_view` | 0x100b03c5 | 0x101f1884 | 416 | 0x2f7c30f0 |
| 107 | 0x00de | 2 | `todo_type_list_view` | 0x100b03a9 | 0x101f18b4 | 416 | 0x2f7c30f0 |
| 108 | 0x00ed | 2 | `chatgpt_deal_view` | 0x100b07cd | 0x101f1900 | 564 | 0xea85bb4b |
| 109 | 0x00ec | 2 | `chatgpt_view` | 0x100b0f69 | 0x101f1b90 | 96 | 0x506906d8 |
| 110 | 0x0011 | 2 | `clock_selector_view` | 0x100b1799 | 0x101f1bc0 | 360 | 0x2bf8054f |
| 111 | 0x00db | 2 | `clock_edit_view` | 0x100b21d9 | 0x101f1c08 | 640 | 0x01828fde |
| 112 | 0x002d | 2 | `alipay_bind_view` | – | – | – | – |
| 113 | 0x002e | 2 | `alipay_pay_view` | – | – | – | – |
| 114 | 0x002f | 2 | `alipay_unbind_view` | – | – | – | – |
| 115 | 0x002c | 2 | `alipay_main_view` | – | – | – | – |
| 116 | 0x0031 | 2 | `wxpay_bind_view` | – | – | – | – |
| 117 | 0x0032 | 2 | `wxpay_pay_view` | – | – | – | – |
| 118 | 0x0033 | 2 | `wxpay_unbind_view` | – | – | – | – |
| 119 | 0x0030 | 2 | `wxpay_main_view` | – | – | – | – |
| 120 | 0x0044 | 2 | `setlist_view` | 0x100b530d | 0x101f1eb8 | 488 | 0xf2e0e0d7 |
| 121 | 0x00a0 | 2 | `desktop_style_view` | 0x100b5661 | 0x101f1f10 | 196 | 0xb772a179 |
| 122 | 0x00c0 | 2 | `switch_effect_style_view` | 0x100b5ce1 | 0x101f1fb4 | 232 | 0xf99b5d7e |
| 123 | 0x00bf | 2 | `anim_effect_style_view` | 0x100b5cc5 | 0x101f1f84 | 232 | 0xf99b5d7e |
| 124 | 0x00a6 | 2 | `time_setting_view` | 0x100b6579 | 0x101f2000 | 236 | 0xbafa54b3 |
| 125 | 0x009e | 2 | `band_view` | 0x100b67bd | 0x101f2030 | 8 | 0xec990fd1 |
| 126 | 0x003f | 2 | `power_restart_view` | 0x100b69e5 | 0x101f2068 | 84 | 0x048a2816 |
| 127 | 0x0040 | 2 | `poweroff_view` | 0x100b6c7d | 0x101f20a0 | 84 | 0x641e9778 |
| 128 | 0x004c | 2 | `sysmenulist_view` | 0x100b6e15 | 0x101f20f0 | 196 | 0xef82acb9 |
| 129 | 0x00ca | 2 | `aod_end_time_view` | 0x100b72fd | 0x101f2140 | 276 | 0xdabaa2ab |
| 130 | 0x00c7 | 2 | `aod_onoff_view` | 0x100b7b9d | 0x101f21a0 | 288 | 0x6f7a5f7a |
| 131 | 0x00cb | 2 | `aod_select_view` | 0x100b8041 | 0x101f2200 | 228 | 0xbf581e20 |
| 132 | 0x00c6 | 2 | `aod_set_view` | 0x100b8371 | 0x101f2248 | 176 | 0x336729da |
| 133 | 0x00c8 | 2 | `aod_setting_time_view` | 0x100b883d | 0x101f2290 | 188 | 0xc0808538 |
| 134 | 0x00c9 | 2 | `aod_start_time_view` | 0x100b8ce9 | 0x101f22e0 | 276 | 0x41051548 |
| 135 | 0x0048 | 2 | `dislist_view` | 0x100b93fd | 0x101f23a4 | 448 | 0x3da45b3b |
| 136 | 0x00aa | 2 | `set_light_time_list_view` | 0x100b98c5 | 0x101f2404 | 240 | 0xd4db342d |
| 137 | 0x00d8 | 2 | `setbrg_custom_view` | 0x100b9d6d | 0x101f2448 | 76 | 0x9e3116d3 |
| 138 | 0x0049 | 2 | `setbrg_view` | 0x100ba03d | 0x101f248c | 160 | 0x8c93b557 |
| 139 | 0x004b | 2 | `setlighttime_view` | 0x100ba5f9 | 0x101f24d4 | 216 | 0x51cd0520 |
| 140 | 0x004a | 2 | `setcreentime_view` | 0x100ba945 | 0x101f251c | 216 | 0x41101ad3 |
| 141 | 0x00a3 | 2 | `ring_switch_view` | 0x100bad19 | 0x101f2568 | 168 | 0xfb5e6141 |
| 142 | 0x0050 | 2 | `setvol_view` | 0x100bae91 | 0x101f2598 | 52 | 0x73f473dd |
| 143 | 0x004f | 2 | `vollist_view` | 0x100bb301 | 0x101f2600 | 256 | 0xfcb46733 |
| 144 | 0x0056 | 2 | `setvib_view` | 0x100bbaf1 | 0x101f264c | 328 | 0xea8d7813 |
| 145 | 0x004d | 2 | `userguid_view` | 0x100bbca9 | 0x101f2680 | 68 | 0xa21d69ff |
| 146 | 0x00af | 2 | `power_saving_onoff_view` | 0x100bbfd1 | 0x101f26c4 | 136 | 0x35c7f690 |
| 147 | 0x0057 | 2 | `disturb_view` | 0x100bc2a5 | 0x101f272c | 360 | 0x99389282 |
| 148 | 0x0058 | 2 | `starttime_view` | 0x100bd025 | 0x101f277c | 276 | 0x44daa792 |
| 149 | 0x0059 | 2 | `stoptime_view` | 0x100bd61d | 0x101f27cc | 276 | 0x3c04ca04 |
| 150 | 0x00e2 | 2 | `sport_detection_switch_view` | 0x100bd88d | 0x101f281c | 200 | 0x47fc3a95 |
| 151 | 0x00e5 | 2 | `gestures_setting_view` | 0x100bdd71 | 0x101f28c0 | 448 | 0x0766e82e |
| 152 | 0x00e3 | 2 | `gestures_switch_guide_view` | 0x100be72d | 0x101f2938 | 320 | 0x520bf641 |
| 153 | 0x00e4 | 2 | `gestures_tutorial_view` | 0x100bf235 | 0x101f2990 | 196 | 0xce14c158 |
| 154 | 0x00ea | 2 | `return_watch_view` | 0x100bf4e1 | 0x101f29d4 | 164 | 0xa9d02df7 |
| 155 | 0x004e | 2 | `about_view` | 0x100bf9f9 | 0x101f2a38 | 292 | 0x811150a2 |
| 156 | 0x00ab | 2 | `lawinfo_com_view` | 0x100c042d | 0x101f2a80 | 132 | 0x598e5e19 |
| 157 | 0x00a2 | 2 | `lawinfo_view` | 0x100c0609 | 0x101f2abc | 152 | 0x2e0c018b |
| 158 | 0x00a1 | 2 | `reguinfo_view` | 0x100c086d | 0x101f2b18 | 200 | 0xcb48d73c |
| 159 | 0x0035 | 2 | `cubebox` | 0x100c09fd | *self-contained proc* | – | – |
| 160 | 0x003c | 2 | `face_wheel` | 0x100c1085 | *self-contained proc* | – | – |
| 161 | 0x003e | 0 | `notify_cont` | 0x100d8a61 | *self-contained proc* | – | – |

---

## 8. Confidence / open points

| claim | confidence | evidence |
|---|---|---|
| registry at `0x100004b8`, 162 × 24 B, id at `+0x10` | **verified** | `view_manager_get_view_entry` code (`0x1018bc04`) with the two literal pointers |
| entry fields `{app_id,0,proc2,0,id,order,type,466,466}` | **verified** | dump + `view_manager.h` `view_entry_t`/`VIEW_DEFINE2` |
| `reg` layout (+0 flags, +2 id, +4 ctx size, +8 scene id, 9 fn pointers, +0x30/34 variants) | **verified** for +2/+4/+8/+0xc..+0x2c | traced call order on the app list: `+0x18` (preload), `+0x1c` → style, `+0x0c`, `+0x10`, `+0x14(obj,1)`; code for `+0x20` (delete), `+0x24` (msg 0x81), `+0x28` (key), `+0x2c` (generic) |
| `reg+8` = `.sty` scene id | **verified** | 137/137 non-zero values exist as scene ids in `bt_watch.sty`; About's 13 id array matches its scene exactly |
| `reg+4` = context size | **verified** | allocated by `0x101ce046` and `memset` in the layout path; the list-style arrays fill the alloc exactly |
| event numbering 2..13/19/20/25..28/129..134 | **verified** | name table at `0x100d5710` + `tbh` targets |
| `FUN_101898bc(view_id, arg)` opens a view | **verified** | traced on navigation; error string `view(%u) entry not registered` |
| 16-byte request `{0,0,arg,id}` | **verified** | `FUN_101898bc` stores `arg` at +8 and `strh id` at +12; the same values show up in the stack entry |
| depth limit 10 | **verified** | `cmp r0,#9` / `-28` in `0x10189398`; array 10×16 then depth at `+0xa0` |
| back = `0x101897fc` | **verified** | hit exactly once per back-swipe; log then shows the previous view re-preloaded |
| app-list table `0x101eaf40`, 25 × 12 B `{icon,label,action}` | **verified** | list builder reads `+0`/`+4` into the two scene loads; `activate` reads `+8`; every value cross-checks with the scene nodes / with what the screen shows |
| action `≤ 0xF4` = view id, else function | **verified** | `0x1005e7bc..0x1005e7d0` |
| item order == table order | **verified** | screenshots after scrolling |
| labels/icons are scene/`bt_watch.<lang>`/`.res` data | **verified** (.sty) / **verified** (index 161/162 adjacent in the English pool) | `fwkit sty-tree`, string pool dump |
| list style comes from setting `0x2c` | **verified** | `0x101ad184` calls `0x100e096c(0x2c,&b,4,0)`; `0x1005e848` indexes the 2-entry style table |
| which setting selects grid vs list vs waterfall | **[?]** | only two styles are in the dispatch table (`0x101eb0ac`); `applist_grid_view` is not referenced by it — probably a legacy/alternate build path |
| meaning of `reg+0x00` bit3 | **[?]** | tested in the focus handler; correlates with paged/scrollable views but not proven |
| `reg+0x30`/`+0x34` on applist | **[I]** | both are pointers to the sibling style regs (list, waterfall) — the same addresses as the style table entries |
| `0x101891f8` argument roles | **[I]** | push passes (new entry, pending request), pop passes (top, below); exact roles not resolved |
| 11 no-`proc2` entries are unreachable through the registry | **[I]** | they have no callback; the payment views are not in this firmware |

Open questions worth a follow-up if the patch goes ahead:

* what `0x10184a5c` writes per node (8-byte record) and how to update a text
  node's string at runtime (needed for a dynamic "Faceclaw" status line);
* whether `0x100e096c` setting `0x2c` also gates the grid layout (try values
  `0..2` in the emulator and screenshot);
* the `0x1018a808`/`0x1018a4e0`/`0x10189a04` trio (display commit path) — only
  needed if we want to push views without `FUN_101898bc`.
