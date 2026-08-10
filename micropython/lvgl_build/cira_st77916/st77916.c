/*
 * st77916.c — CIRA 的 ST77916 圆屏 QSPI 驱动（MicroPython USER_C_MODULE）
 * ===================================================================
 * 目标：在 lv_micropython 固件里提供 `import st77916; st77916.ST77916(...)`
 *       得到一个带 .blit/.on/.off/.fill/.set_nit 的对象，供 cira_lvgl_display
 *       作为 LVGL 的 flush 目标。
 *
 * 设计：
 *   - 只用 ESP-IDF 自带 esp_lcd（panel_io QSPI），不依赖外部 esp_lcd_st77916 组件。
 *   - 初始化序列直接来自 micropython/st77916_init.py（st77916_init_data.h，自动生成），
 *     即原 waveshare esp_lcd_st77916.c 抽取的 181 条寄存器，已在本板验证可用。
 *   - 引脚硬编码为本板（ESP32-S3-Touch-LCD-1.85C-BOX V2），与 cira_pins.py 一致：
 *       PCLK=40 CS=21 D0=46 D1=45 D2=42 D3=41 BL=5  RST=NC(走 TCA9554 EXIO2)
 *   - 背光走 GPIO5 的 LEDC PWM（set_nit 调光），与 frozen 驱动的 set_nit 对应。
 *
 * ⚠ 本文件在沙盒无法编译（需 ESP-IDF 工具链 + 硬件）。若编译/运行报错，把报错
 *   贴回给 AI，据此修正后重编。常见坑：颜色字节序（RGB565 高低字节）、max_transfer_sz
 *   超限（已做分带）、MP_DEFINE_CONST_OBJ_TYPE 宏名（旧版为 MP_DEFINE_CONST_TYPE）。
 *   ⚠ micropython 1.24 起已删除 STATIC 宏，必须用小写 static（本文件已改）。
 */

#include "py/runtime.h"
#include "py/obj.h"
#include "py/mperrno.h"   // MP_ENOMEM 等 errno 常量
#include "stdint.h"
#include "string.h"

#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "freertos/semphr.h"

#include "driver/spi_master.h"
#include "driver/ledc.h"
#include "esp_lcd_panel_io.h"
#include "esp_lcd_panel_ops.h"
#include "esp_heap_caps.h"
#include "esp_cache.h"

#include "st77916_init_data.h"

/* ---- 全局状态 ---- */
static esp_lcd_panel_io_handle_t g_io = NULL;
static bool g_bl_inited = false;
static int  g_bl_pin = -1;
static int  g_max_sz = 0;          // 单次 SPI 传输上限（字节），blit 分带用
static bool g_blit_logged = false; // 首次 blit 只打印一次，便于 spike 诊断
static SemaphoreHandle_t g_dma_sem = NULL; // 像素 DMA 完成信号量（ISR give / 任务 take）

/* ---- 对象 ---- */
typedef struct _st77916_obj_t {
    mp_obj_base_t base;
    int width;
    int height;
} st77916_obj_t;

/* ---- 辅助：init 命令软检查（首次 bring-up 不让单条失败直接 hard-abort 重启）---- */
static void init_check(esp_err_t e, uint8_t cmd) {
    if (e != ESP_OK) {
        printf("[st77916] init cmd 0x%02X 返回 0x%04X（继续，不中止）\n", cmd, (unsigned)e);
    }
}

/* 像素 DMA 完成后由 ESP-IDF SPI 的 post-trans 回调（ISR 上下文）触发，
   给出"本次传输完成"的信号，供 blit/fill 在释放或覆盖源缓冲前同步等待。 */
static void cira_dma_done_cb(esp_lcd_panel_io_handle_t io, void *edata, void *user_ctx) {
    xSemaphoreGiveFromISR(g_dma_sem, NULL);
}

/* 等"当前这一笔"像素 DMA 真正完成再返回。
   关键点：esp_lcd_panel_io_tx_color 是「入队即返回」的异步路径——上一笔若还在飞，
   tx_color 开头会先 drain 等它完成（其回调已给过信号量），故返回时只有"当前这笔"还在飞。
   先 take(0) 清掉残留（上一笔 / drain 期间给的），再 take 等当前这笔完成，
   避免「释放/覆盖缓冲时 DMA 还在读」的竞态（这是之前屏刚亮就静默看门狗重启的根因）。 */
static void wait_dma_done(void) {
    xSemaphoreTake(g_dma_sem, 0);                   // 清残留信号（非阻塞）
    xSemaphoreTake(g_dma_sem, pdMS_TO_TICKS(500));  // 等当前这笔完成
}

/* ---- 辅助：设置绘制窗口 (x,y)..(x+w-1,y+h-1) ---- */
static void send_window(int x, int y, int w, int h) {
    uint8_t col[4] = {
        (uint8_t)((x >> 8) & 0xFF), (uint8_t)(x & 0xFF),
        (uint8_t)(((x + w - 1) >> 8) & 0xFF), (uint8_t)((x + w - 1) & 0xFF),
    };
    uint8_t row[4] = {
        (uint8_t)((y >> 8) & 0xFF), (uint8_t)(y & 0xFF),
        (uint8_t)(((y + h - 1) >> 8) & 0xFF), (uint8_t)((y + h - 1) & 0xFF),
    };
    esp_lcd_panel_io_tx_param(g_io, 0x2A, col, 4);   // CASET
    esp_lcd_panel_io_tx_param(g_io, 0x2B, row, 4);   // RASET
}

/* 把缓冲拷到 DMA 可达的内部 SRAM 再发 RAMWR，并等 DMA 真正完成才返回。
   ① MicroPython 的 bytearray 默认在 Octal PSRAM，且可缓存；拷贝到内部 SRAM
      并 msync 清 D$ 后再 DMA，避免「DMA 读 PSRAM 缓存未回写」导致的花屏/错位。
   ② esp_lcd_panel_io_tx_color 是「入队即返回」的异步路径，必须等完成再释放/覆盖
      源缓冲（wait_dma_done），否则 DMA 还在读缓冲就被回收 → 堆损坏 → 静默看门狗重启。 */
static void blit_dma_safe(const uint8_t *src, size_t size) {
    uint8_t *dma = heap_caps_malloc(size, MALLOC_CAP_DMA | MALLOC_CAP_INTERNAL);
    if (dma == NULL) {
        /* 极端内存不足：退回直发（仍走同步等待，避免释放/覆盖竞态） */
        esp_lcd_panel_io_tx_color(g_io, 0x2C, src, size);
        wait_dma_done();
        return;
    }
    memcpy(dma, src, size);
    esp_cache_msync(dma, size, ESP_CACHE_MSYNC_FLAG_DIR_C2M);
    esp_lcd_panel_io_tx_color(g_io, 0x2C, dma, size);
    wait_dma_done();
    heap_caps_free(dma);
}

/* ---- 构造 ---- */
static mp_obj_t st77916_make_new(const mp_obj_type_t *type, size_t n_args, size_t n_kw,
                                 const mp_obj_t *args) {
    enum { ARG_w, ARG_h, ARG_cs, ARG_pclk, ARG_d0, ARG_d1, ARG_d2, ARG_d3,
           ARG_rst, ARG_bl, ARG_madctl, ARG_invert };
    static const mp_arg_t allowed_args[] = {
        { MP_QSTR_w,      MP_ARG_REQUIRED | MP_ARG_INT, {.u_int = 360} },
        { MP_QSTR_h,      MP_ARG_REQUIRED | MP_ARG_INT, {.u_int = 360} },
        { MP_QSTR_cs,     MP_ARG_REQUIRED | MP_ARG_INT, {.u_int = 21} },
        { MP_QSTR_pclk,   MP_ARG_REQUIRED | MP_ARG_INT, {.u_int = 40} },
        { MP_QSTR_d0,     MP_ARG_REQUIRED | MP_ARG_INT, {.u_int = 46} },
        { MP_QSTR_d1,     MP_ARG_REQUIRED | MP_ARG_INT, {.u_int = 45} },
        { MP_QSTR_d2,     MP_ARG_REQUIRED | MP_ARG_INT, {.u_int = 42} },
        { MP_QSTR_d3,     MP_ARG_REQUIRED | MP_ARG_INT, {.u_int = 41} },
        /* rst：保留参数，当前**故意不使用**。本板 LCD 复位线接在 TCA9554 的
           EXIO2 上（不是 SoC GPIO），所以复位由 Python 侧 cira_expander.init()
           负责。传任何值都不会碰 GPIO，cira_pins.LCD_RST=3 只是占位。 */
        { MP_QSTR_rst,    MP_ARG_INT,                   {.u_int = -1} },
        { MP_QSTR_bl,     MP_ARG_INT,                   {.u_int = 5} },
        { MP_QSTR_madctl, MP_ARG_INT,                   {.u_int = 0} },
        { MP_QSTR_invert, MP_ARG_BOOL,                  {.u_bool = false} },
    };
    mp_arg_val_t vals[MP_ARRAY_SIZE(allowed_args)];
    mp_arg_parse_all_kw_array(n_args, n_kw, args, MP_ARRAY_SIZE(allowed_args), allowed_args, vals);

    int w      = vals[ARG_w].u_int;
    int h      = vals[ARG_h].u_int;
    int cs     = vals[ARG_cs].u_int;
    int pclk   = vals[ARG_pclk].u_int;
    int d0     = vals[ARG_d0].u_int;
    int d1     = vals[ARG_d1].u_int;
    int d2     = vals[ARG_d2].u_int;
    int d3     = vals[ARG_d3].u_int;
    int bl     = vals[ARG_bl].u_int;
    int madctl = vals[ARG_madctl].u_int & 0xFF;
    bool invert = vals[ARG_invert].u_bool;

    if (g_io == NULL) {
        /* 像素 DMA 完成信号量（ISR give / 任务 take），保证释放/覆盖缓冲前 DMA 已结束 */
        if (g_dma_sem == NULL) {
            g_dma_sem = xSemaphoreCreateBinary();
        }
        /* QSPI 总线（数据线 D0..D3 + 时钟） */
        spi_bus_config_t bus_config = {
            .data0_io_num = d0,
            .data1_io_num = d1,
            .sclk_io_num  = pclk,
            .data2_io_num = d2,
            .data3_io_num = d3,
            .max_transfer_sz = w * 80 * 2,
        };
        ESP_ERROR_CHECK(spi_bus_initialize(SPI2_HOST, &bus_config, SPI_DMA_CH_AUTO));
        g_max_sz = w * 80 * 2;

        esp_lcd_panel_io_spi_config_t io_config = {
            .cs_gpio_num = cs,
            .dc_gpio_num = -1,
            .spi_mode = 0,
            .pclk_hz = 40 * 1000 * 1000,
            .trans_queue_depth = 1,  /* 串行、同步完成，避免 360 次快速 blit 后 QSPI 异步队列卡死→中断看门狗重启 */
            .on_color_trans_done = cira_dma_done_cb,  /* DMA 完成→给信号量，blit/fill 据此同步等待 */
            .user_ctx = NULL,
            .lcd_cmd_bits = 8,    // ST77916 QSPI 命令为 1 字节（曾误写 32 → 每条命令都错）
            .lcd_param_bits = 8,
            .flags = { .quad_mode = true },
        };
        ESP_ERROR_CHECK(esp_lcd_new_panel_io_spi((esp_lcd_spi_bus_handle_t)SPI2_HOST,
                                                  &io_config, &g_io));

        /* 发送初始化序列（软检查：单条失败仅打印，不 hard-abort） */
        for (int i = 0; i < ST77916_INIT_N; i++) {
            const uint8_t *row = st77916_init_tbl[i];
            uint8_t cmd   = row[0];
            uint8_t len   = row[1];
            uint8_t delay = row[2];
            const uint8_t *data = &row[3];
            if (len > 0) {
                init_check(esp_lcd_panel_io_tx_param(g_io, cmd, data, len), cmd);
            } else {
                init_check(esp_lcd_panel_io_tx_param(g_io, cmd, NULL, 0), cmd);
            }
            if (delay > 0) {
                vTaskDelay(delay / portTICK_PERIOD_MS);
            }
        }
        /* DISPON 后留一点稳定时间（部分面板需要） */
        vTaskDelay(50 / portTICK_PERIOD_MS);

        /* 方向 (MADCTL) + 反色 (INVON/INVOFF) */
        uint8_t mc[1] = { (uint8_t)madctl };
        init_check(esp_lcd_panel_io_tx_param(g_io, 0x36, mc, 1), 0x36);
        init_check(esp_lcd_panel_io_tx_param(g_io, invert ? 0x21 : 0x20, NULL, 0),
                   invert ? 0x21 : 0x20);

        /* 背光 LEDC */
        g_bl_pin = bl;
        ledc_timer_config_t ledc_timer = {
            .speed_mode = LEDC_LOW_SPEED_MODE,
            .duty_resolution = LEDC_TIMER_8_BIT,
            .timer_num = LEDC_TIMER_0,
            .freq_hz = 5000,
            .clk_cfg = LEDC_AUTO_CLK,
        };
        ESP_ERROR_CHECK(ledc_timer_config(&ledc_timer));
        ledc_channel_config_t ledc_ch = {
            .gpio_num = bl,
            .speed_mode = LEDC_LOW_SPEED_MODE,
            .channel = LEDC_CHANNEL_0,
            .timer_sel = LEDC_TIMER_0,
            .duty = 0,
            .hpoint = 0,
        };
        ESP_ERROR_CHECK(ledc_channel_config(&ledc_ch));
        g_bl_inited = true;
        printf("[st77916] init 完成 w=%d h=%d cs=%d pclk=%d d0..3=%d/%d/%d/%d bl=%d\n",
               w, h, cs, pclk, d0, d1, d2, d3, bl);
    }

    st77916_obj_t *self = m_new_obj(st77916_obj_t);
    self->base.type = type;
    self->width = w;
    self->height = h;
    return MP_OBJ_FROM_PTR(self);
}

/* ---- blit(buf, x, y, w, h)：把 RGB565 缓冲画到屏上指定矩形 ---- */
static mp_obj_t st77916_blit(size_t n_args, const mp_obj_t *args) {
    (void)n_args;
    mp_obj_t buf_in = args[1];
    int x = mp_obj_get_int(args[2]);
    int y = mp_obj_get_int(args[3]);
    int w = mp_obj_get_int(args[4]);
    int h = mp_obj_get_int(args[5]);
    if (g_io == NULL) {
        mp_raise_ValueError(MP_ERROR_TEXT("st77916 not initialized"));
    }
    mp_buffer_info_t bufinfo;
    mp_get_buffer_raise(buf_in, &bufinfo, MP_BUFFER_READ);

    if (!g_blit_logged) {
        printf("[st77916] blit 首次调用 x=%d y=%d w=%d h=%d buf=%p\n", x, y, w, h, bufinfo.buf);
        g_blit_logged = true;
    }

    if ((size_t)(w * h * 2) <= (size_t)g_max_sz) {
        send_window(x, y, w, h);
        blit_dma_safe(bufinfo.buf, (size_t)(w * h * 2));
    } else {
        /* 超过单次传输上限：按水平条带分块（每条带高度 rows_per） */
        int rows_per = g_max_sz / (w * 2);
        if (rows_per < 1) rows_per = 1;
        for (int yy = 0; yy < h; yy += rows_per) {
            int hh = (yy + rows_per > h) ? (h - yy) : rows_per;
            send_window(x, y + yy, w, hh);
            const uint8_t *p = (const uint8_t *)bufinfo.buf + (size_t)yy * w * 2;
            blit_dma_safe(p, (size_t)(w * hh * 2));
        }
    }
    return mp_const_none;
}
static MP_DEFINE_CONST_FUN_OBJ_VAR_BETWEEN(st77916_blit_obj, 6, 6, st77916_blit);

/* ---- fill(color)：整屏填充单色（color 为 RGB565 uint16） ---- */
static mp_obj_t st77916_fill(size_t n_args, const mp_obj_t *args) {
    st77916_obj_t *self = MP_OBJ_TO_PTR(args[0]);
    int color = mp_obj_get_int(args[1]) & 0xFFFF;
    if (g_io == NULL) {
        mp_raise_ValueError(MP_ERROR_TEXT("st77916 not initialized"));
    }
    int w = self->width, h = self->height;
    uint8_t *line = malloc((size_t)w * 2);
    if (!line) {
        mp_raise_OSError(MP_ENOMEM);
    }
    for (int i = 0; i < w; i++) {
        line[i * 2]     = (uint8_t)(color & 0xFF);
        line[i * 2 + 1] = (uint8_t)((color >> 8) & 0xFF);
    }
    /* 关键修复：每行重新设置窗口 (0,y,w,1)，再发 RAMWR。
       原代码只在循环外 send_window(0,0,w,h) 一次，循环内反复发 0x2C
       会让 GRAM 指针每次重置到窗口起点 → 实际只有第 0 行被写、其余行黑。
       每行发完必须等 DMA 完成（wait_dma_done）再覆盖 line，否则异步 DMA 读已释放/覆盖的缓冲。 */
    for (int y = 0; y < h; y++) {
        send_window(0, y, w, 1);
        esp_lcd_panel_io_tx_color(g_io, 0x2C, line, (size_t)(w * 2));
        wait_dma_done();
    }
    free(line);
    return mp_const_none;
}
static MP_DEFINE_CONST_FUN_OBJ_VAR_BETWEEN(st77916_fill_obj, 2, 2, st77916_fill);

/* ---- on() / off()：显示开关 + 背光 ---- */
static mp_obj_t st77916_on(mp_obj_t self_in) {
    if (g_io) ESP_ERROR_CHECK(esp_lcd_panel_io_tx_param(g_io, 0x29, NULL, 0));  // DISPON
    if (g_bl_inited) {
        ledc_set_duty(LEDC_LOW_SPEED_MODE, LEDC_CHANNEL_0, 200);
        ledc_update_duty(LEDC_LOW_SPEED_MODE, LEDC_CHANNEL_0);
    }
    return mp_const_none;
}
static MP_DEFINE_CONST_FUN_OBJ_1(st77916_on_obj, st77916_on);

static mp_obj_t st77916_off(mp_obj_t self_in) {
    if (g_io) ESP_ERROR_CHECK(esp_lcd_panel_io_tx_param(g_io, 0x28, NULL, 0));  // DISPOFF
    if (g_bl_inited) {
        ledc_set_duty(LEDC_LOW_SPEED_MODE, LEDC_CHANNEL_0, 0);
        ledc_update_duty(LEDC_LOW_SPEED_MODE, LEDC_CHANNEL_0);
    }
    return mp_const_none;
}
static MP_DEFINE_CONST_FUN_OBJ_1(st77916_off_obj, st77916_off);

/* ---- set_nit(nit)：背光亮度（0..~400 → duty 0..255） ---- */
static mp_obj_t st77916_set_nit(mp_obj_t self_in, mp_obj_t nit_in) {
    int nit = mp_obj_get_int(nit_in);
    if (!g_bl_inited) return mp_const_none;
    int duty = (nit * 255) / 400;
    if (duty < 0) duty = 0;
    if (duty > 255) duty = 255;
    ledc_set_duty(LEDC_LOW_SPEED_MODE, LEDC_CHANNEL_0, (uint32_t)duty);
    ledc_update_duty(LEDC_LOW_SPEED_MODE, LEDC_CHANNEL_0);
    return mp_const_none;
}
static MP_DEFINE_CONST_FUN_OBJ_2(st77916_set_nit_obj, st77916_set_nit);

/* ---- locals / type / module ---- */
static const mp_rom_map_elem_t st77916_locals_dict_table[] = {
    { MP_ROM_QSTR(MP_QSTR_blit),    MP_ROM_PTR(&st77916_blit_obj) },
    { MP_ROM_QSTR(MP_QSTR_fill),    MP_ROM_PTR(&st77916_fill_obj) },
    { MP_ROM_QSTR(MP_QSTR_on),      MP_ROM_PTR(&st77916_on_obj) },
    { MP_ROM_QSTR(MP_QSTR_off),     MP_ROM_PTR(&st77916_off_obj) },
    { MP_ROM_QSTR(MP_QSTR_set_nit), MP_ROM_PTR(&st77916_set_nit_obj) },
};
static MP_DEFINE_CONST_DICT(st77916_locals_dict, st77916_locals_dict_table);

MP_DEFINE_CONST_OBJ_TYPE(
    st77916_type,
    MP_QSTR_ST77916,
    MP_TYPE_FLAG_NONE,
    make_new, st77916_make_new,
    locals_dict, &st77916_locals_dict
);

static const mp_rom_map_elem_t st77916_module_globals_table[] = {
    { MP_ROM_QSTR(MP_QSTR___name__), MP_ROM_QSTR(MP_QSTR_st77916) },
    { MP_ROM_QSTR(MP_QSTR_ST77916),  MP_ROM_PTR(&st77916_type) },
};
static MP_DEFINE_CONST_DICT(st77916_module_globals, st77916_module_globals_table);

const mp_obj_module_t st77916_module = {
    .base = { &mp_type_module },
    .globals = (mp_obj_dict_t *)&st77916_module_globals,
};
MP_REGISTER_MODULE(MP_QSTR_st77916, st77916_module);
