# LVGL / Zephyr API map for CMF Watch Pro 2 app 1.0.0.73 (`re/app_073.bin`)

Thumb-2 Cortex-M4, load base `0x10000000` (file offset = addr - base).
Method: static analysis (string/`__func__`-literal xrefs, class-object decode, call-graph
shapes, ROM-stub decode) + QEMU/gdb breakpoint confirmation. No real device was touched.

## LVGL version

**LVGL 8.3.x, Actions-patched fork** (not upstream-clean):

* Source paths embedded in the image are `WEST_TOPDIR/thirdparty/lib/gui/lvgl/src/...` with
  `src/core`, `src/draw/sw`, `src/extra/...`, `src/font`, `src/misc`, `src/widgets`,
  `porting/gpu/vglite`, `porting/gpu/lv_gpu_acts*.c`, `porting/decoder/lv_img_decoder_acts_basic.c`.
  `src/extra` + `src/lv_api_map.h` + `lv_obj_get_child_cnt` ⇒ v8.3 API, not v9.
* Style-prop numbering is v8.3 (`WIDTH=1, HEIGHT=4, RADIUS=11, BG_COLOR=32, TEXT_COLOR=85,
  TEXT_FONT=87, OPA=96, ANIM_SPEED=102, TRANSLATE_X=107`), **not** v9.
* The fork adds three numeric props in unused v8.3 slots: **45, 92, 93** (setters at
  `0x101c73ac`, `0x101c745c`, `0x101c7466`). Everything else matches upstream 8.3.
* Actions extensions visible in the build: `lv_obj_auto_align_to` (0x1012acc4),
  `lv_disp_add_knob_obj` (0x10128c50), `lv_disp_remove_knob_obj` (0x10127d14),
  a `Knob_%s` display-object trace log, bitmap-font loader (`lvgl_bitmap_font_open` 0x10185c30).
* Exact patch release (8.3.0 … 8.3.11) cannot be pinned from the image; ABI/API is 8.3.
* Built with GCC with **LTO**: several small public functions have no standalone copy
  (`lv_obj_center`, `lv_scr_act`, `lv_layer_top`), and functions from one `.c` file are not
  contiguous. That is why LTO code has to be matched by shape, not by source order.

## ABI facts that matter for calling it (all verified statically)

| fact | value | where seen |
|---|---|---|
| `lv_coord_t` | **int32_t** (`LV_USE_LARGE_COORD=1`) | `lv_obj_set_size` stores 4-byte coords; `LV_SIZE_CONTENT` = `0x200007d1` (= `LV_COORD_SET_SPEC(2001)`) seen in args and in class defaults |
| `lv_color_t` | **uint16_t RGB565** (`LV_COLOR_DEPTH=16`) | colour setters are `bfi r2,r1,#0,#16`; emulator saw `r1=0x2966` |
| `lv_style_value_t` | 4-byte union | passed in r2 to `lv_obj_set_local_style_prop` |
| `sizeof(lv_obj_t)` | **44** (`instance_size` = `0x2ca>>4`) | `lv_obj_class` @ `0x101fb27c` |
| `lv_obj_class_t` | base@0, ctor@4, dtor@8, **user_data@12** (`LV_USE_USER_DATA=1`), event_cb@16, width_def@20, height_def@24, bits@28 (`editable:2, group_def:2, instance_size:16` = bits 4..19) | `lv_obj_class_create_obj` does `ubfx r2,r3,#4,#16` |
| widget instance sizes | label 96, btn 44, img 80, canvas 92, chart 180, bar 112, arc 72, roller 72, btnmatrix 64, imgbtn 120 | class objects |
| `lv_event_t` | target@0, current_target@4, code@8 (u8, bit7 = PREPROCESS), user_data@12, param@16, prev@20, flags@24 | the 4-byte event getters |
| `lv_timer_t` | period@0, last_run@4, timer_cb@8, user_data@12, repeat_count@16, flags@20 | `lv_timer_create` stores |
| logging | `LV_USE_LOG=1`, level **WARN** (INFO strings like `"begin"`/`"finished"` are absent) | no INFO strings, WARN strings present |
| asserts | `LV_ASSERT_*` **enabled**: on failure `_lv_log_add()` → ``printk("\tLVGL fail\n")`` → hook `0x100eeb30(file,line)` | every LVGL function's error path |
| style setters | take a **selector** argument: `(obj, value, lv_style_selector_t selector)`; `LV_PART_MAIN|LV_STATE_DEFAULT = 0` | every wrapper passes r3 straight through |

`lv_scr_act()` / `lv_layer_top()` are `static inline` in `lv_disp.h` and were fully inlined:
call `lv_disp_get_scr_act(lv_disp_get_default())` / `lv_disp_get_layer_top(lv_disp_get_default())`.
`lv_obj_center()` likewise has no symbol: it is `lv_obj_align(obj, LV_ALIGN_CENTER, 0, 0)`
(observed in the emulator as `lv_obj_align(obj, 9, 0, 0)`).

## How each entry was confirmed

* `__func__`-based: LVGL's `LV_LOG_WARN`/`LV_ASSERT` pass `__func__` as the 4th argument to
  `_lv_log_add` (`0x1013a098`). Each function that logs therefore has its own name string in
  `.rodata` (e.g. `"lv_obj_set_size"` @ `0x1023d396`), referenced only from that function's
  literal pool. That yields the address directly.
* Object-create functions: `ldr r0,=<lv_obj_class_t>; bl lv_obj_class_create_obj; bl
  lv_obj_class_init_obj` — the class object then gives base class, constructor, default size
  and instance size (which identifies the widget unambiguously, e.g. `lv_btn_class`).
* Style setters: they are 10-byte (num) or 32-byte (colour) tail-call stubs into
  `lv_obj_set_local_style_prop` @ `0x101c6f9a`, with the prop id in `r1`.
* Emulator (QEMU `ats3089c-wp2` + gdb), runs under `runs/lvgl-s*` and `runs/lvgl-t*`:
  `lv_obj_create` (r0=0 for screens, obj for children), `lv_label_create`, `lv_label_set_text`
  (r1 = text pointer), `lv_obj_set_size` (466×466, `LV_SIZE_CONTENT`), `lv_obj_align`
  (r1=9=LV_ALIGN_CENTER), `lv_event_get_code` (r0 = stack `lv_event_t`), `lv_indev_get_act`,
  `lv_obj_add_flag` (bitmask), `lv_obj_add_event_cb` (cb/filter/user_data),
  `lv_event_send` (obj/code/param), `lv_timer_create` (r0=`_lv_disp_refr_timer`),
  bg_color (`r1=0x2966`), text_opa (`0xff`), printk (r0 = format string),
  snprintf (buf/size/fmt), memset (r1=0,r2=size), memcpy (dst/src/len).

## Table

Columns: address | C signature (LVGL 8.3) | evidence | confidence.
All addresses are function entry points (Thumb bit = addr|1 when used in a linker script).

### LVGL core / object tree

| addr | name | signature | evidence | conf |
|---|---|---|---|---|

### LVGL core / display / object tree

| addr | name | signature | evidence | conf |
|---|---|---|---|---|
| `0x10127c60` | **lv_init** | `void lv_init(void)` | __func__ string 1023d09c ref'd at 10127ce4; also logs "lv_init: already inited" | high |
| `0x10138dcc` | **lv_disp_get_default** | `lv_disp_t * lv_disp_get_default(void)` | 6-byte getter: ldr r3,=g; ldr r0,[r3]; bx lr; called by every lv_disp_get_* at +6 and by lv_obj_class_create_obj (15 callers) | high |
| `0x101255e0` | **lv_disp_get_scr_act** | `lv_obj_t * lv_disp_get_scr_act(lv_disp_t * disp)` | __func__ 1023cb4b ref'd at 1012560c; 164 BL callers, fires in emulator | high |
| `0x10125648` | **lv_disp_get_layer_top** | `lv_obj_t * lv_disp_get_layer_top(lv_disp_t * disp)` | __func__ 1023cb74 | high |
| `0x1012567c` | **lv_disp_get_layer_sys** | `lv_obj_t * lv_disp_get_layer_sys(lv_disp_t * disp)` | __func__ 1023cb8a | high |
| `0x101256b0` | **lv_disp_set_bg_color** | `void lv_disp_set_bg_color(lv_disp_t*, lv_color_t)` | __func__ 1023cba0 | high |
| `0x1012570c` | **lv_disp_set_bg_opa** | `void lv_disp_set_bg_opa(lv_disp_t*, lv_opa_t)` | __func__ 1023cbb5 | high |
| `0x10127cfc` | **lv_obj_create** | `lv_obj_t * lv_obj_create(lv_obj_t * parent)` | calls lv_obj_class_create_obj(&lv_obj_class@0x101fb27c) then lv_obj_class_init_obj(0x101c5534); 491 BL callers; emulator: r0=0 for screens, r0=obj for children | high |
| `0x1012c774` | **lv_obj_del** | `void lv_obj_del(lv_obj_t * obj)` | __func__ 1023d703 ref'd at 1012c864 | high |
| `0x1012c880` | **lv_obj_clean** | `void lv_obj_clean(lv_obj_t * obj)` | __func__ 1023d70e | high |
| `0x1012c19c` | **lv_obj_get_parent** | `lv_obj_t * lv_obj_get_parent(const lv_obj_t*)` | __func__ 1023d752 | high |
| `0x1012c3dc` | **lv_obj_get_child** | `lv_obj_t * lv_obj_get_child(const lv_obj_t*, int32_t id)` | __func__ 1023d764 | high |
| `0x1012c4ac` | **lv_obj_get_child_cnt** | `uint32_t lv_obj_get_child_cnt(const lv_obj_t*)` | __func__ 1023d775 | high |
| `0x1012c564` | **lv_obj_get_index** | `uint32_t lv_obj_get_index(const lv_obj_t*)` | __func__ 1023d78a (lv_obj_get_child_id inlines to this) | high |

### Geometry

| addr | name | signature | evidence | conf |
|---|---|---|---|---|
| `0x1012926c` | **lv_obj_set_pos** | `void lv_obj_set_pos(lv_obj_t*, lv_coord_t x, lv_coord_t y)` | __func__ 1023d35c; 116 BL callers | high |
| `0x101290cc` | **lv_obj_set_x** | `void lv_obj_set_x(lv_obj_t*, lv_coord_t)` | __func__ 1023d36b | high |
| `0x1012919c` | **lv_obj_set_y** | `void lv_obj_set_y(lv_obj_t*, lv_coord_t)` | __func__ 1023d378 | high |
| `0x101294c8` | **lv_obj_set_size** | `void lv_obj_set_size(lv_obj_t*, lv_coord_t w, lv_coord_t h)` | __func__ 1023d396; 1426 BL callers; emulator r1/r2 = 466,466 and 0x200007d1 (LV_SIZE_CONTENT) | high |
| `0x10129328` | **lv_obj_set_width** | `void lv_obj_set_width(lv_obj_t*, lv_coord_t)` | __func__ 1023d3a6 | high |
| `0x101293f8` | **lv_obj_set_height** | `void lv_obj_set_height(lv_obj_t*, lv_coord_t)` | __func__ 1023d3b7 | high |
| `0x101c5de4` | **lv_obj_align** | `void lv_obj_align(lv_obj_t*, lv_align_t, lv_coord_t x_ofs, lv_coord_t y_ofs)` | calls lv_obj_set_style_align stub(0x101c72fe) then tail-calls lv_obj_set_pos; 1620 BL callers; emulator r1=9 (LV_ALIGN_CENTER) r2=r3=0 | high |
| `0x1012a87c` | **lv_obj_align_to** | `void lv_obj_align_to(lv_obj_t*, const lv_obj_t * base, lv_align_t, lv_coord_t, lv_coord_t)` | __func__ 1023d3ee; calls ALIGN stub at +0x1c6 | high |
| `0x1012a248` | **lv_obj_refr_size** | `bool lv_obj_refr_size(lv_obj_t*)` | __func__ 1023d385 | high |
| `0x101295b8` | **lv_obj_set_layout** | `void lv_obj_set_layout(lv_obj_t*, uint32_t)` | __func__ 1023d3c9 | high |
| `0x10129680` | **lv_layout_register** | `uint32_t lv_layout_register(lv_layout_update_cb_t, void*)` | __func__ 1023d3db | high |
| `0x10129718` | **lv_obj_get_coords** | `void lv_obj_get_coords(const lv_obj_t*, lv_area_t*)` | __func__ 1023d413 | high |
| `0x10129994` | **lv_obj_get_width** | `lv_coord_t lv_obj_get_width(const lv_obj_t*)` | __func__ 1023d44d | high |
| `0x10129a4c` | **lv_obj_get_height** | `lv_coord_t lv_obj_get_height(const lv_obj_t*)` | __func__ 1023d45e | high |

### Flags / state

| addr | name | signature | evidence | conf |
|---|---|---|---|---|
| `0x10128d38` | **lv_obj_add_flag** | `void lv_obj_add_flag(lv_obj_t*, lv_obj_flag_t)` | __func__ 1023d0a4; 1006 BL callers; emulator r1 = flag bits 0x4000/0x10000 | high |
| `0x10127e7c` | **lv_obj_clear_flag** | `void lv_obj_clear_flag(lv_obj_t*, lv_obj_flag_t)` | __func__ 1023d0b4 | high |
| `0x10128244` | **lv_obj_add_state** | `void lv_obj_add_state(lv_obj_t*, lv_state_t)` | __func__ 1023d0f3 | high |
| `0x10128310` | **lv_obj_clear_state** | `void lv_obj_clear_state(lv_obj_t*, lv_state_t)` | __func__ 1023d104 | high |
| `0x101283dc` | **lv_obj_has_flag** | `bool lv_obj_has_flag(const lv_obj_t*, lv_obj_flag_t)` | __func__ 1023d117 | high |
| `0x1012855c` | **lv_obj_get_state** | `lv_state_t lv_obj_get_state(const lv_obj_t*)` | __func__ 1023d13b | high |
| `0x10128610` | **lv_obj_has_state** | `bool lv_obj_has_state(const lv_obj_t*, lv_state_t)` | __func__ 1023d14c | high |
| `0x101286d0` | **lv_obj_get_group** | `void * lv_obj_get_group(const lv_obj_t*)` | __func__ 1023d15d; 14 callers incl. lv_obj_destructor | high |
| `0x10129fd8` | **lv_obj_invalidate** | `void lv_obj_invalidate(const lv_obj_t*)` | __func__ 1023d4d4 | high |
| `0x10129ef0` | **lv_obj_invalidate_area** | `void lv_obj_invalidate_area(const lv_obj_t*, const lv_area_t*)` | __func__ 1023d4bd | high |
| `0x1012a0b0` | **lv_obj_is_visible** | `bool lv_obj_is_visible(const lv_obj_t*)` | __func__ 1023d4e6 | high |
| `0x1012a188` | **lv_obj_set_ext_click_area** | `void lv_obj_set_ext_click_area(lv_obj_t*, lv_coord_t)` | __func__ 1023d4f8 | high |
| `0x1012ad38` | **lv_obj_set_scrollbar_mode** | `void lv_obj_set_scrollbar_mode(lv_obj_t*, lv_scrollbar_mode_t)` | __func__ 1023d54f | high |
| `0x1012af4c` | **lv_obj_get_scroll_left** | `lv_coord_t lv_obj_get_scroll_left(const lv_obj_t*)` | __func__ 1023d582 | high |
| `0x1012b0b0` | **lv_obj_get_scroll_right** | `lv_coord_t lv_obj_get_scroll_right(const lv_obj_t*)` | __func__ 1023d599 | high |

### Events

| addr | name | signature | evidence | conf |
|---|---|---|---|---|
| `0x101259c4` | **lv_event_send** | `lv_res_t lv_event_send(lv_obj_t*, lv_event_code_t, void * param)` | __func__ 1023cc94; emulator r0=obj r1=code(0x2a,0x13) r2=param | high |
| `0x10125a94` | **lv_obj_add_event_cb** | `lv_obj_t * lv_obj_add_event_cb(...)` | __func__ 1023cca2; emulator r1=cb addr, r2=filter(4,5,7), r3=user_data; 458 callers | high |
| `0x10125bd4` | **lv_obj_remove_event_cb** | `bool lv_obj_remove_event_cb(lv_obj_t*, lv_event_cb_t)` | __func__ 1023ccb6 | high |
| `0x101c4c92` | **lv_event_get_target** | `lv_obj_t * lv_event_get_target(lv_event_t*)` | 4-byte: ldr r0,[r0,#0]; bx lr (e->target) | high |
| `0x101c4c96` | **lv_event_get_current_target** | `lv_obj_t * lv_event_get_current_target(lv_event_t*)` | 4-byte: ldr r0,[r0,#4] | high |
| `0x101c4c9a` | **lv_event_get_code** | `lv_event_code_t lv_event_get_code(lv_event_t*)` | 6-byte: ldrb r0,[r0,#8]; and r0,#0x7f; bx lr; emulator fires with r0=stack event | high |
| `0x101c4ca2` | **lv_event_get_param** | `void * lv_event_get_param(lv_event_t*)` | 4-byte: ldr r0,[r0,#16] | high |
| `0x101c4ca6` | **lv_event_get_user_data** | `void * lv_event_get_user_data(lv_event_t*)` | 4-byte: ldr r0,[r0,#12] | high |

### Styles

| addr | name | signature | evidence | conf |
|---|---|---|---|---|
| `0x101c6f9a` | **lv_obj_set_local_style_prop** | `void lv_obj_set_local_style_prop(lv_obj_t*, lv_style_prop_t, lv_style_value_t, lv_style_selector_t)` | body = get_local_style(0x1012b7e8) + lv_style_set_prop(0x1013b0a4) + lv_obj_refresh_style(0x1012b908); all lv_obj_set_style_* are 10/32-byte tails into it | high |
| `0x1012bb14` | **lv_obj_add_style** | `void lv_obj_add_style(lv_obj_t*, lv_style_t*, lv_style_selector_t)` | __func__ 1023d601; 590 callers | high |
| `0x1012bd5c` | **lv_obj_remove_style** | `void lv_obj_remove_style(lv_obj_t*, lv_style_t*, lv_style_selector_t)` | __func__ 1023d612 | high |
| `0x1012b908` | **lv_obj_refresh_style** | `void lv_obj_refresh_style(lv_obj_t*, lv_style_selector_t, lv_style_prop_t)` | __func__ 1023d626 | high |
| `0x1013a8e4` | **lv_style_init** | `void lv_style_init(lv_style_t*)` | __func__ 1023fcf5 | high |
| `0x1013a924` | **lv_style_reset** | `void lv_style_reset(lv_style_t*)` | __func__ 1023fd03 | high |

### Timers / indev / group / memory

| addr | name | signature | evidence | conf |
|---|---|---|---|---|
| `0x1013b10c` | **lv_timer_create** | `lv_timer_t * lv_timer_create(lv_timer_cb_t cb, uint32_t period, void * user_data)` | __func__ 1023fe5d; stores r1->[t+0] period, r0->[t+8] cb, r2->[t+12] user_data, -1 in repeat_count; emulator r0=0x1012d571 (_lv_disp_refr_timer) | high |
| `0x1013b1a4` | **lv_timer_del** | `void lv_timer_del(lv_timer_t*)` | __func__ 1023fe6d | high |
| `0x1013b1d0` | **lv_timer_handler** | `uint32_t lv_timer_handler(void)` | __func__ 1023fe4c | high |
| `0x101262d4` | **lv_indev_get_act** | `lv_indev_t * lv_indev_get_act(void)` | 6-byte getter returning global @0x3802aed8; 20 BL callers, all widget event handlers; emulator hit | high |
| `0x10126394` | **lv_indev_get_read_timer** | `lv_timer_t * lv_indev_get_read_timer(lv_indev_t*)` | __func__ 1023cf27 | high |
| `0x10126028` | **lv_group_add_obj** | `void lv_group_add_obj(lv_group_t*, lv_obj_t*)` | __func__ 1023cdfb; called from lv_obj_class_init_obj when class group_def set | high |
| `0x10125efc` | **lv_group_remove_obj** | `void lv_group_remove_obj(lv_obj_t*)` | __func__ 1023ce0c | high |
| `0x1013a14c` | **lv_mem_alloc** | `void * lv_mem_alloc(size_t)` | thin wrapper -> Actions UI heap dispatcher 0x10188234(heap_id=1, size, caller) | high |
| `0x1013a160` | **lv_mem_free** | `void lv_mem_free(void*)` | thin wrapper -> 0x10188380 | high |
| `0x1013a178` | **lv_mem_realloc** | `void * lv_mem_realloc(void*, size_t)` | __func__ lv_mem_realloc_debug; -> 0x101883c4 | medium |
| `0x1013a098` | **_lv_log_add** | `void _lv_log_add(level, const char* file, int line, const char* func, const char* fmt, ...)` | called by every LV_LOG_*/*ASSERT site with r0=level r1=file r2=line r3=func [sp]=fmt; 508 callers | high |

### Widgets

| addr | name | signature | evidence | conf |
|---|---|---|---|---|
| `0x1013f5f0` | **lv_label_create** | `lv_obj_t * lv_label_create(lv_obj_t * parent)` | class 0x101fb7b0 (base=lv_obj_class, ctor=lv_label_constructor, instance=0x600>>4=96); 533 BL callers; emulator r0=parent | high |
| `0x101400a4` | **lv_label_set_text** | `void lv_label_set_text(lv_obj_t*, const char * txt)` | __func__ 10240600; emulator r1=string ptr (flash/RAM) | high |
| `0x10140238` | **lv_label_set_text_fmt** | `void lv_label_set_text_fmt(lv_obj_t*, const char * fmt, ...)` | __func__ 10240612 | high |
| `0x10140368` | **lv_label_set_text_static** | `void lv_label_set_text_static(lv_obj_t*, const char*)` | __func__ 10240628 | high |
| `0x1014051c` | **lv_label_set_long_mode** | `void lv_label_set_long_mode(lv_obj_t*, lv_label_long_mode_t)` | __func__ 10240671 | high |
| `0x1013f6c0` | **lv_label_get_text** | `const char * lv_label_get_text(const lv_obj_t*)` | __func__ 10240688 | high |
| `0x1013d388` | **lv_btn_create** | `lv_obj_t * lv_btn_create(lv_obj_t * parent)` | class 0x101fb730 == lv_btn_class (base=lv_obj_class, w/h=LV_SIZE_CONTENT, group_def=TRUE, instance=44) - exact v8.3 lv_btn_class layout | high |
| `0x1013c108` | **lv_arc_set_value** | `void lv_arc_set_value(lv_obj_t*, int32_t)` | __func__ 1023ffd7 | high |
| `0x1013ceb8` | **lv_bar_set_value** | `void lv_bar_set_value(lv_obj_t*, int32_t, lv_anim_enable_t)` | __func__ 10240079 | high |
| `0x1013ed50` | **lv_img_set_src** | `void lv_img_set_src(lv_obj_t*, const void*)` | __func__ 10240502 | high |
| `0x1013662c` | **lv_chart_set_next_value** | `void lv_chart_set_next_value(lv_obj_t*, lv_chart_series_t*, lv_coord_t)` | __func__ 1023f029 | high |

### `lv_obj_set_style_*` (all are stubs that tail-call `lv_obj_set_local_style_prop` @ `0x101c6f9a`)

`lv_obj_set_style_<name>(lv_obj_t * obj, <value>, lv_style_selector_t selector)`.
Value/selector are already in r1/r2 at the stub, so a plain C call works — these are real
functions, you do not need the prop ids. The prop ids are listed only as evidence.

| addr | name | prop id | conf |
|---|---|---|---|
| `0x101c72cc` | **lv_obj_set_style_width** | 1 | high |
| `0x101c72d6` | **lv_obj_set_style_height** | 4 | high |
| `0x101c72e0` | **lv_obj_set_style_max_height** | 6 | high |
| `0x101c72ea` | **lv_obj_set_style_x** | 7 | high |
| `0x101c72f4` | **lv_obj_set_style_y** | 8 | high |
| `0x101c72fe` | **lv_obj_set_style_align** | 9 | high |
| `0x101c7308` | **lv_obj_set_style_translate_x** | 107 | high |
| `0x101c7312` | **lv_obj_set_style_translate_y** | 108 | high |
| `0x101c731c` | **lv_obj_set_style_pad_top** | 16 | high |
| `0x101c7326` | **lv_obj_set_style_pad_bottom** | 17 | high |
| `0x101c7330` | **lv_obj_set_style_pad_left** | 18 | high |
| `0x101c733a` | **lv_obj_set_style_pad_right** | 19 | high |
| `0x101c7344` | **lv_obj_set_style_pad_row** | 20 | high |
| `0x101c734e` | **lv_obj_set_style_pad_column** | 21 | high |
| `0x101c7358` | **lv_obj_set_style_bg_color** | 32 | high |
| `0x101c7378` | **lv_obj_set_style_bg_opa** | 33 | high |
| `0x101c7382` | **lv_obj_set_style_bg_grad_color** | 34 | high |
| `0x101c73a2` | **lv_obj_set_style_bg_img_src** | 40 | high |
| `0x101c73ac` | **lv_obj_set_style_<prop 45>** | 45 | medium |
| `0x101c73b6` | **lv_obj_set_style_border_color** | 48 | high |
| `0x101c73d6` | **lv_obj_set_style_border_width** | 50 | high |
| `0x101c73e0` | **lv_obj_set_style_outline_width** | 53 | high |
| `0x101c73ea` | **lv_obj_set_style_outline_color** | 54 | high |
| `0x101c740a` | **lv_obj_set_style_outline_opa** | 55 | high |
| `0x101c7414` | **lv_obj_set_style_img_opa** | 70 | high |
| `0x101c741e` | **lv_obj_set_style_img_recolor** | 71 | high |
| `0x101c743e` | **lv_obj_set_style_img_recolor_opa** | 72 | high |
| `0x101c7448` | **lv_obj_set_style_arc_width** | 80 | high |
| `0x101c7452` | **lv_obj_set_style_arc_rounded** | 81 | high |
| `0x101c745c` | **lv_obj_set_style_<prop 92>** | 92 | medium |
| `0x101c7466` | **lv_obj_set_style_<prop 93>** | 93 | medium |
| `0x101c7470` | **lv_obj_set_style_arc_color** | 82 | high |
| `0x101c7490` | **lv_obj_set_style_arc_opa** | 83 | high |
| `0x101c749a` | **lv_obj_set_style_arc_img_src** | 84 | high |
| `0x101c74a4` | **lv_obj_set_style_text_color** | 85 | high |
| `0x101c74c4` | **lv_obj_set_style_text_opa** | 86 | high |
| `0x101c74ce` | **lv_obj_set_style_text_font** | 87 | high |
| `0x101c74d8` | **lv_obj_set_style_text_line_space** | 89 | high |
| `0x101c74e2` | **lv_obj_set_style_text_align** | 91 | high |
| `0x101c74ec` | **lv_obj_set_style_radius** | 11 | high |
| `0x101c74f6` | **lv_obj_set_style_opa** | 96 | high |
| `0x101c7500` | **lv_obj_set_style_anim_speed** | 102 | high |
| `0x101c750a` | **lv_obj_set_style_layout** | 10 | high |
| `0x101c7514` | **lv_obj_set_style_base_dir** | 22 | high |

Props **45, 92, 93 are Actions additions** (not in upstream 8.3, not `CLIP_CORNER`).

## Zephyr / libc

| addr | name | signature | evidence | conf |
|---|---|---|---|---|
| `0x101ba194` | **printk** | `void printk(const char * fmt, ...)` | varargs thunk: spills r0-r3, r0=fmt, r1=va_list -> vprintk 0x100f65e0; 2268 call sites; emulator r0 = string ptr | high |
| `0x101ba1ae` | **snprintf** | `int snprintf(char * buf, size_t n, const char * fmt, ...)` | varargs thunk -> vsnprintf 0x100edec4; emulator r0=buf r1=size(0x100) r2=fmt | high |
| `0x100edec4` | **vsnprintf** | `int vsnprintf(char * buf, size_t n, const char * fmt, va_list ap)` | builds cbprintf_package then cbvprintf 0x101ba438 | high |
| `0x101bf3b2` | **memset** | `void * memset(void * dst, int c, size_t n)` | ROM-API stub table+0x44; emulator r1=0, r2=size (lv_obj_class_create_obj zero-fills new objects); 1193 call sites | high |
| `0x101bf3aa` | **memcpy** | `void * memcpy(void * dst, const void * src, size_t n)` | ROM-API stub table+0x40; emulator r0=dst r1=src(flash or RAM) r2=len, dst!=src | high |
| `0x101bf3ba` | **memchr** | `void * memchr(const void*, int c, size_t n)` | ROM-API stub table+0x48; emulator r1='s'/0 as byte, r2=count | medium |

Not found / not present in this image:

* `k_msleep`, `k_sleep`, `k_uptime_get`, `k_work_init`, `k_work_submit`, `k_timer_init`,
  `k_timer_start`, `k_malloc`, `k_free`, `strlen` — not identified with confidence here.
  Zephyr's kernel work-queue code *is* in the image (`zephyr/kernel/work.c` assert strings at
  `0x10250daa`-`0x10250e9d`, functions `0x1019a31c`-`0x1019a890`), but the fork is old enough
  that matching source order does not pin individual entry points, so no addresses are claimed.
  For allocation use `lv_mem_alloc`/`lv_mem_free` (`0x1013a14c`/`0x1013a160`), which route to the
  same Actions UI heap the whole UI uses (`0x10188234` alloc / `0x10188380` free,
  heap id 1; the UART logger prints `UI-%s alloc %u failed` on failure).
* `memcpy`/`memset`/`snprintf`/`printk` are reached through Actions ROM-API stubs
  (`movw r3,#0x7030; ldr r3,[r3,#imm]; bx r3`). Calling the stub addresses above is correct and
  is what all stock code does.

## Fonts

There are **no `lv_font_montserrat_*` objects** in the image (no `.data` word references
`lv_font_get_bitmap_fmt_txt` @ `0x101383cc` or `lv_font_get_glyph_dsc_fmt_txt` @ `0x1013864c`).
Text fonts are built at runtime by the Actions bitmap-font loader
`lvgl_bitmap_font_open` @ `0x10185c30` (`bitmap_font_init` @ `0x1018287c`). For new UI, read the
font off an existing label with `lv_obj_get_style_text_font(obj, LV_PART_MAIN)` and pass that
pointer to `lv_obj_set_style_text_font`, or just inherit it (labels already have the right font).

## Group API

`lv_group_add_obj`/`lv_group_remove_obj` exist and are wired: `lv_obj_class_init_obj` adds every
new object whose class has `group_def == LV_OBJ_CLASS_GROUP_DEF_TRUE` (e.g. `lv_btn_class`,
`0x101fb730`). `lv_group_create`, `lv_group_focus_obj` and `lv_indev_set_group` were **not found**
— they are dead-stripped in this image, so the app must already own a group (or the fork's
`knob_obj` mechanism @ `lv_disp_add_knob_obj` `0x10128c50` handles crown navigation).

## Calling it from new code

```c
typedef struct _lv_obj_t lv_obj_t;
extern lv_obj_t * lv_disp_get_scr_act(void *);      /* 0x101255e1 */
extern void *     lv_disp_get_default(void);        /* 0x10138dcd */
extern lv_obj_t * lv_obj_create(lv_obj_t *);        /* 0x10127cfd */
...
```
Addresses in `stock_api.ld` are already OR-ed with 1.
