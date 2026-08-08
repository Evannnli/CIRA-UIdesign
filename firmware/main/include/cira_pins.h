#ifndef CIRA_PINS_H
#define CIRA_PINS_H
/* =========================================================================
 * CIRA Device Runtime v0.8.0 — 硬件引脚单一事实源
 * 来源: HARDWARE.md (Waveshare ESP32-S3-Touch-LCD-1.85C-BOX, HW V2 已确认)
 *       引脚号取自 Waveshare 官方示例源码 (非手册猜测)
 * ⚠️ 改动此处需回证 HARDWARE.md; 任何 GPIO 误配都会在板子上表现为难查的硬件 bug
 * ========================================================================= */

#include "driver/gpio.h"
#include "driver/i2c.h"

#ifdef __cplusplus
extern "C" {
#endif

/* --- 屏幕: ST77916 (QSPI, 360x360 圆屏, RGB565) --- */
/* 注: 复位走 TCA9554 扩展器 EXIO2 (非直连 ESP32 GPIO), 见 cira_display.c */
#define CIRA_LCD_QSPI_SCK      GPIO_NUM_40
#define CIRA_LCD_QSPI_DATA0    GPIO_NUM_46   /* D0 / MOSI */
#define CIRA_LCD_QSPI_DATA1    GPIO_NUM_45   /* D1 */
#define CIRA_LCD_QSPI_DATA2    GPIO_NUM_42   /* D2 */
#define CIRA_LCD_QSPI_DATA3    GPIO_NUM_41   /* D3 / MISO */
#define CIRA_LCD_QSPI_CS       GPIO_NUM_21
#define CIRA_LCD_TE            GPIO_NUM_18   /* Tearing effect */
#define CIRA_LCD_BACKLIGHT     GPIO_NUM_5    /* 背光 PWM (LEDC) */
#define CIRA_LCD_EXIO_RST      2             /* TCA9554 物理 pin → EXIO2 (见 cira_display.c 映射) */
#define CIRA_LCD_H_RES         360
#define CIRA_LCD_V_RES         360

/* --- 触摸: CST816T (I2C, 单点+手势) --- */
#define CIRA_TOUCH_I2C_PORT    I2C_NUM_0
#define CIRA_TOUCH_SDA         GPIO_NUM_10
#define CIRA_TOUCH_SCL         GPIO_NUM_11
#define CIRA_TOUCH_INT         GPIO_NUM_4    /* 中断 (下降沿=有触摸) */
#define CIRA_TOUCH_RST_EXIO    1             /* TCA9554 EXIO1 */
#define CIRA_TOUCH_ADDR        0x15          /* 7-bit */

/* --- 音频: ES8311 (DAC) + ES7210 (ADC) + NS4150B (功放) --- */
#define CIRA_AUDIO_I2C_PORT    I2C_NUM_0     /* 与触摸共用 I2C0 (SDA=10/SCL=11) */
#define CIRA_ES8311_ADDR       0x18          /* 7-bit */
#define CIRA_AUDIO_I2S_PORT    I2S_NUM_0
#define CIRA_AUDIO_MCLK         GPIO_NUM_2
#define CIRA_AUDIO_BCK          GPIO_NUM_48
#define CIRA_AUDIO_LRCK         GPIO_NUM_38
#define CIRA_AUDIO_DOUT         GPIO_NUM_47  /* ESP32 → ES8311 (播放) */
#define CIRA_AUDIO_DIN          GPIO_NUM_39  /* ES7210 → ESP32 (采集) */
#define CIRA_AUDIO_PA_EN        GPIO_NUM_15  /* 功放使能 (高有效) */

/* --- I2C 扩展器: TCA9554 (LCD/触摸复位经它输出) --- */
#define CIRA_EXIO_I2C_PORT     I2C_NUM_0
#define CIRA_EXIO_SDA          GPIO_NUM_10
#define CIRA_EXIO_SCL          GPIO_NUM_11
#define CIRA_EXIO_ADDR         0x20          /* 7-bit (TCA9554) */

/* --- 电源 / 其他 --- */
#define CIRA_BAT_ADC           GPIO_NUM_8    /* 电池电压 ADC (需回证) */
#define CIRA_BOOT_BTN          GPIO_NUM_0    /* BOOT 键 (可选: 进配网/恢复) */
#define CIRA_RGB_LED           GPIO_NUM_7    /* WS2812 (状态指示灯, 可选) */

/* --- I2C 总线参数 (触摸/ES8311/EXIO 共用 I2C0) --- */
#define CIRA_I2C_CLK_HZ        400000
#define CIRA_I2C_TIMEOUT_MS    100

#ifdef __cplusplus
}
#endif
#endif /* CIRA_PINS_H */
