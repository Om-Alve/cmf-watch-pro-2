/* Auto-generated: high-confidence stock API entries (Thumb bit set).
 * Addresses are Thumb-2 entry points in app_073.bin, base 0x10000000.
 * Evidence per symbol is in re/notes/lvgl.md. */
/* ---- LVGL 8.3 (Actions fork): core ---- */
/* __func__ string 1023d09c ref'd at 10127ce4 */
lv_init = 0x10127c60|1;
/* 6-byte getter: ldr r3,=g */
lv_disp_get_default = 0x10138dcc|1;
/* __func__ 1023cb4b ref'd at 1012560c */
lv_disp_get_scr_act = 0x101255e0|1;
/* __func__ 1023cb74 */
lv_disp_get_layer_top = 0x10125648|1;
/* __func__ 1023cb8a */
lv_disp_get_layer_sys = 0x1012567c|1;
/* __func__ 1023cba0 */
lv_disp_set_bg_color = 0x101256b0|1;
/* __func__ 1023cbb5 */
lv_disp_set_bg_opa = 0x1012570c|1;
/* calls lv_obj_class_create_obj(&lv_obj_class@0x101fb27c) then lv_obj_class_init_obj(0x101c5534) */
lv_obj_create = 0x10127cfc|1;
/* __func__ 1023d703 ref'd at 1012c864 */
lv_obj_del = 0x1012c774|1;
/* __func__ 1023d70e */
lv_obj_clean = 0x1012c880|1;
/* __func__ 1023d35c */
lv_obj_set_pos = 0x1012926c|1;
/* __func__ 1023d36b */
lv_obj_set_x = 0x101290cc|1;
/* __func__ 1023d378 */
lv_obj_set_y = 0x1012919c|1;
/* __func__ 1023d396 */
lv_obj_set_size = 0x101294c8|1;
/* __func__ 1023d3a6 */
lv_obj_set_width = 0x10129328|1;
/* __func__ 1023d3b7 */
lv_obj_set_height = 0x101293f8|1;
/* calls lv_obj_set_style_align stub(0x101c72fe) then tail-calls lv_obj_set_pos */
lv_obj_align = 0x101c5de4|1;
/* __func__ 1023d3ee */
lv_obj_align_to = 0x1012a87c|1;
/* __func__ 1023d385 */
lv_obj_refr_size = 0x1012a248|1;
/* __func__ 1023d3c9 */
lv_obj_set_layout = 0x101295b8|1;
/* __func__ 1023d3db */
lv_layout_register = 0x10129680|1;
/* __func__ 1023d0a4 */
lv_obj_add_flag = 0x10128d38|1;
/* __func__ 1023d0b4 */
lv_obj_clear_flag = 0x10127e7c|1;
/* __func__ 1023d0f3 */
lv_obj_add_state = 0x10128244|1;
/* __func__ 1023d104 */
lv_obj_clear_state = 0x10128310|1;
/* __func__ 1023d117 */
lv_obj_has_flag = 0x101283dc|1;
/* __func__ 1023d13b */
lv_obj_get_state = 0x1012855c|1;
/* __func__ 1023d14c */
lv_obj_has_state = 0x10128610|1;
/* __func__ 1023d15d */
lv_obj_get_group = 0x101286d0|1;
/* __func__ 1023d752 */
lv_obj_get_parent = 0x1012c19c|1;
/* __func__ 1023d764 */
lv_obj_get_child = 0x1012c3dc|1;
/* __func__ 1023d775 */
lv_obj_get_child_cnt = 0x1012c4ac|1;
/* __func__ 1023d78a (lv_obj_get_child_id inlines to this) */
lv_obj_get_index = 0x1012c564|1;
/* __func__ 1023d413 */
lv_obj_get_coords = 0x10129718|1;
/* __func__ 1023d44d */
lv_obj_get_width = 0x10129994|1;
/* __func__ 1023d45e */
lv_obj_get_height = 0x10129a4c|1;
/* __func__ 1023d4d4 */
lv_obj_invalidate = 0x10129fd8|1;
/* __func__ 1023d4bd */
lv_obj_invalidate_area = 0x10129ef0|1;
/* __func__ 1023d4e6 */
lv_obj_is_visible = 0x1012a0b0|1;
/* __func__ 1023d4f8 */
lv_obj_set_ext_click_area = 0x1012a188|1;
/* __func__ 1023d54f */
lv_obj_set_scrollbar_mode = 0x1012ad38|1;
/* __func__ 1023d582 */
lv_obj_get_scroll_left = 0x1012af4c|1;
/* __func__ 1023d599 */
lv_obj_get_scroll_right = 0x1012b0b0|1;
/* __func__ 1023cc94 */
lv_event_send = 0x101259c4|1;
/* __func__ 1023cca2 */
lv_obj_add_event_cb = 0x10125a94|1;
/* __func__ 1023ccb6 */
lv_obj_remove_event_cb = 0x10125bd4|1;
/* 4-byte: ldr r0,[r0,#0] */
lv_event_get_target = 0x101c4c92|1;
/* 4-byte: ldr r0,[r0,#4] */
lv_event_get_current_target = 0x101c4c96|1;
/* 6-byte: ldrb r0,[r0,#8] */
lv_event_get_code = 0x101c4c9a|1;
/* 4-byte: ldr r0,[r0,#16] */
lv_event_get_param = 0x101c4ca2|1;
/* 4-byte: ldr r0,[r0,#12] */
lv_event_get_user_data = 0x101c4ca6|1;
/* body = get_local_style(0x1012b7e8) + lv_style_set_prop(0x1013b0a4) + lv_obj_refresh_style(0x1012b908) */
lv_obj_set_local_style_prop = 0x101c6f9a|1;
/* __func__ 1023d601 */
lv_obj_add_style = 0x1012bb14|1;
/* __func__ 1023d612 */
lv_obj_remove_style = 0x1012bd5c|1;
/* __func__ 1023d626 */
lv_obj_refresh_style = 0x1012b908|1;
/* __func__ 1023fcf5 */
lv_style_init = 0x1013a8e4|1;
/* __func__ 1023fd03 */
lv_style_reset = 0x1013a924|1;
/* stub -> lv_obj_set_local_style_prop, prop id 1 */
lv_obj_set_style_width = 0x101c72cc|1;
/* stub -> lv_obj_set_local_style_prop, prop id 4 */
lv_obj_set_style_height = 0x101c72d6|1;
/* stub -> lv_obj_set_local_style_prop, prop id 6 */
lv_obj_set_style_max_height = 0x101c72e0|1;
/* stub -> lv_obj_set_local_style_prop, prop id 7 */
lv_obj_set_style_x = 0x101c72ea|1;
/* stub -> lv_obj_set_local_style_prop, prop id 8 */
lv_obj_set_style_y = 0x101c72f4|1;
/* stub -> lv_obj_set_local_style_prop, prop id 9 */
lv_obj_set_style_align = 0x101c72fe|1;
/* stub -> lv_obj_set_local_style_prop, prop id 107 */
lv_obj_set_style_translate_x = 0x101c7308|1;
/* stub -> lv_obj_set_local_style_prop, prop id 108 */
lv_obj_set_style_translate_y = 0x101c7312|1;
/* stub -> lv_obj_set_local_style_prop, prop id 16 */
lv_obj_set_style_pad_top = 0x101c731c|1;
/* stub -> lv_obj_set_local_style_prop, prop id 17 */
lv_obj_set_style_pad_bottom = 0x101c7326|1;
/* stub -> lv_obj_set_local_style_prop, prop id 18 */
lv_obj_set_style_pad_left = 0x101c7330|1;
/* stub -> lv_obj_set_local_style_prop, prop id 19 */
lv_obj_set_style_pad_right = 0x101c733a|1;
/* stub -> lv_obj_set_local_style_prop, prop id 20 */
lv_obj_set_style_pad_row = 0x101c7344|1;
/* stub -> lv_obj_set_local_style_prop, prop id 21 */
lv_obj_set_style_pad_column = 0x101c734e|1;
/* stub -> lv_obj_set_local_style_prop, prop id 32 */
lv_obj_set_style_bg_color = 0x101c7358|1;
/* stub -> lv_obj_set_local_style_prop, prop id 33 */
lv_obj_set_style_bg_opa = 0x101c7378|1;
/* stub -> lv_obj_set_local_style_prop, prop id 34 */
lv_obj_set_style_bg_grad_color = 0x101c7382|1;
/* stub -> lv_obj_set_local_style_prop, prop id 40 */
lv_obj_set_style_bg_img_src = 0x101c73a2|1;
/* stub -> lv_obj_set_local_style_prop, prop id 48 */
lv_obj_set_style_border_color = 0x101c73b6|1;
/* stub -> lv_obj_set_local_style_prop, prop id 50 */
lv_obj_set_style_border_width = 0x101c73d6|1;
/* stub -> lv_obj_set_local_style_prop, prop id 53 */
lv_obj_set_style_outline_width = 0x101c73e0|1;
/* stub -> lv_obj_set_local_style_prop, prop id 54 */
lv_obj_set_style_outline_color = 0x101c73ea|1;
/* stub -> lv_obj_set_local_style_prop, prop id 55 */
lv_obj_set_style_outline_opa = 0x101c740a|1;
/* stub -> lv_obj_set_local_style_prop, prop id 70 */
lv_obj_set_style_img_opa = 0x101c7414|1;
/* stub -> lv_obj_set_local_style_prop, prop id 71 */
lv_obj_set_style_img_recolor = 0x101c741e|1;
/* stub -> lv_obj_set_local_style_prop, prop id 72 */
lv_obj_set_style_img_recolor_opa = 0x101c743e|1;
/* stub -> lv_obj_set_local_style_prop, prop id 80 */
lv_obj_set_style_arc_width = 0x101c7448|1;
/* stub -> lv_obj_set_local_style_prop, prop id 81 */
lv_obj_set_style_arc_rounded = 0x101c7452|1;
/* stub -> lv_obj_set_local_style_prop, prop id 82 */
lv_obj_set_style_arc_color = 0x101c7470|1;
/* stub -> lv_obj_set_local_style_prop, prop id 83 */
lv_obj_set_style_arc_opa = 0x101c7490|1;
/* stub -> lv_obj_set_local_style_prop, prop id 84 */
lv_obj_set_style_arc_img_src = 0x101c749a|1;
/* stub -> lv_obj_set_local_style_prop, prop id 85 */
lv_obj_set_style_text_color = 0x101c74a4|1;
/* stub -> lv_obj_set_local_style_prop, prop id 86 */
lv_obj_set_style_text_opa = 0x101c74c4|1;
/* stub -> lv_obj_set_local_style_prop, prop id 87 */
lv_obj_set_style_text_font = 0x101c74ce|1;
/* stub -> lv_obj_set_local_style_prop, prop id 89 */
lv_obj_set_style_text_line_space = 0x101c74d8|1;
/* stub -> lv_obj_set_local_style_prop, prop id 91 */
lv_obj_set_style_text_align = 0x101c74e2|1;
/* stub -> lv_obj_set_local_style_prop, prop id 11 */
lv_obj_set_style_radius = 0x101c74ec|1;
/* stub -> lv_obj_set_local_style_prop, prop id 96 */
lv_obj_set_style_opa = 0x101c74f6|1;
/* stub -> lv_obj_set_local_style_prop, prop id 102 */
lv_obj_set_style_anim_speed = 0x101c7500|1;
/* stub -> lv_obj_set_local_style_prop, prop id 10 */
lv_obj_set_style_layout = 0x101c750a|1;
/* stub -> lv_obj_set_local_style_prop, prop id 22 */
lv_obj_set_style_base_dir = 0x101c7514|1;
/* class 0x101fb7b0 (base=lv_obj_class, ctor=lv_label_constructor, instance=0x600>>4=96) */
lv_label_create = 0x1013f5f0|1;
/* __func__ 10240600 */
lv_label_set_text = 0x101400a4|1;
/* __func__ 10240612 */
lv_label_set_text_fmt = 0x10140238|1;
/* __func__ 10240628 */
lv_label_set_text_static = 0x10140368|1;
/* __func__ 10240671 */
lv_label_set_long_mode = 0x1014051c|1;
/* __func__ 10240688 */
lv_label_get_text = 0x1013f6c0|1;
/* class 0x101fb730 == lv_btn_class (base=lv_obj_class, w/h=LV_SIZE_CONTENT, group_def=TRUE, instance=44) - exact */
lv_btn_create = 0x1013d388|1;
/* __func__ 1023ffd7 */
lv_arc_set_value = 0x1013c108|1;
/* __func__ 10240079 */
lv_bar_set_value = 0x1013ceb8|1;
/* __func__ 10240502 */
lv_img_set_src = 0x1013ed50|1;
/* __func__ 1023f029 */
lv_chart_set_next_value = 0x1013662c|1;
/* __func__ 1023fe5d */
lv_timer_create = 0x1013b10c|1;
/* __func__ 1023fe6d */
lv_timer_del = 0x1013b1a4|1;
/* __func__ 1023fe4c */
lv_timer_handler = 0x1013b1d0|1;
/* 6-byte getter returning global @0x3802aed8 */
lv_indev_get_act = 0x101262d4|1;
/* __func__ 1023cf27 */
lv_indev_get_read_timer = 0x10126394|1;
/* __func__ 1023cdfb */
lv_group_add_obj = 0x10126028|1;
/* __func__ 1023ce0c */
lv_group_remove_obj = 0x10125efc|1;
/* thin wrapper -> Actions UI heap dispatcher 0x10188234(heap_id=1, size, caller) */
lv_mem_alloc = 0x1013a14c|1;
/* thin wrapper -> 0x10188380 */
lv_mem_free = 0x1013a160|1;
/* called by every LV_LOG_*ASSERT site with r0=level r1=file r2=line r3=func [sp]=fmt */
_lv_log_add = 0x1013a098|1;
/* varargs thunk: spills r0-r3, r0=fmt, r1=va_list -> vprintk 0x100f65e0 */
printk = 0x101ba194|1;
/* varargs thunk -> vsnprintf 0x100edec4 */
snprintf = 0x101ba1ae|1;
/* builds cbprintf_package then cbvprintf 0x101ba438 */
vsnprintf = 0x100edec4|1;
/* ROM-API stub table+0x44 */
memset = 0x101bf3b2|1;
/* ROM-API stub table+0x40 */
memcpy = 0x101bf3aa|1;

/* ---- no symbol: inlined / absent in this image ----
 * lv_scr_act()          -> lv_disp_get_scr_act(lv_disp_get_default())
 * lv_layer_top()        -> lv_disp_get_layer_top(lv_disp_get_default())
 * lv_obj_center(o)      -> lv_obj_align(o, LV_ALIGN_CENTER (9), 0, 0)
 * lv_group_create / lv_group_focus_obj / lv_indev_set_group: dead-stripped
 * built-in fonts: none, fonts are runtime objects (lvgl_bitmap_font_open @0x10185c30)
 * k_msleep/k_sleep/k_uptime_get/k_work_xxx / k_timer_xxx / k_malloc/strlen: not identified
 */
