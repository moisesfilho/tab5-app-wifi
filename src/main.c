/**
 * @file main.c
 * @brief Aplicativo Gerenciador de Wi-Fi para Tab5 OS
 */

#include "tab5_sdk.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static void update_wifi_view(void)
{
    tab5_wifi_info_t info = {0};
    tab5_err_t err = tab5_system_get_wifi_status(&info);

    char buf[512];
    if (err == TAB5_OK && info.is_connected) {
        snprintf(buf, sizeof(buf),
                 "====================================\n"
                 "       STATUS DE CONECTIVIDADE     \n"
                 "====================================\n\n"
                 " Status:     CONECTADO\n"
                 " SSID:       %s\n"
                 " Endereco:   %s\n"
                 " Sinal RSSI: %d dBm\n\n"
                 " Pressione Atualizar para novo scan.\n",
                 info.ssid[0] ? info.ssid : "Desconhecido",
                 info.ip_addr[0] ? info.ip_addr : "0.0.0.0",
                 info.rssi);
    } else {
        snprintf(buf, sizeof(buf),
                 "====================================\n"
                 "       STATUS DE CONECTIVIDADE     \n"
                 "====================================\n\n"
                 " Status:     DESCONECTADO\n\n"
                 " Nenhuma rede Wi-Fi ativa no momento.\n"
                 " Configure o arquivo wifi.cfg ou utilize\n"
                 " o modo de emparelhamento rapido.\n");
    }

    tab5_ui_obj_t ta = tab5_ui_get_main_textarea();
    if (ta != NULL) {
        tab5_ui_textarea_set_text(ta, buf);
    }
}

static void on_refresh_clicked(void *user_data)
{
    (void)user_data;
    tab5_sound_play_beep(1200, 30);
    update_wifi_view();
    tab5_ui_show_toast("Status Wi-Fi atualizado", 1500);
}

static void app_init(void)
{
    tab5_system_log(2, "tab5_wifi", "Aplicativo Wi-Fi iniciado");
    tab5_ui_app_bar_set_title("Gerenciador Wi-Fi");
    tab5_ui_app_bar_add_action_button("LV_SYMBOL_REFRESH", on_refresh_clicked, NULL);
    update_wifi_view();
}

static void app_resume(void)
{
    tab5_system_log(2, "tab5_wifi", "Wi-Fi retomado");
    update_wifi_view();
}

static void app_pause(void)
{
    tab5_system_log(2, "tab5_wifi", "Wi-Fi pausado");
}

static void app_destroy(void)
{
    tab5_system_log(2, "tab5_wifi", "Wi-Fi finalizado");
}

TAB5_APP_EXPORT int main(int argc, char **argv)
{
    (void)argc;
    (void)argv;

    tab5_lifecycle_callbacks_t cbs = {
        .on_init = app_init,
        .on_resume = app_resume,
        .on_pause = app_pause,
        .on_destroy = app_destroy,
        .on_open_file = NULL,
    };

    tab5_lifecycle_register(&cbs);
    app_init();
    return 0;
}
