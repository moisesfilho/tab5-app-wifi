/**
 * @file main.c
 * @brief Aplicativo Gerenciador de Wi-Fi Desacoplado para Tab5 OS
 */

#include "tab5_sdk.h"
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define MAX_APS 16

static tab5_wifi_ap_t s_aps[MAX_APS] = {0};
static tab5_ui_obj_t s_ap_btn_handles[MAX_APS] = {0};
static uint32_t s_ap_count = 0;
static char s_selected_ssid[33] = {0};

static tab5_ui_obj_t s_sw_wifi = TAB5_UI_INVALID_OBJ;
static tab5_ui_obj_t s_lbl_status = TAB5_UI_INVALID_OBJ;
static tab5_ui_obj_t s_btn_scan = TAB5_UI_INVALID_OBJ;
static tab5_ui_obj_t s_lbl_selected_ssid = TAB5_UI_INVALID_OBJ;
static tab5_ui_obj_t s_ta_password = TAB5_UI_INVALID_OBJ;
static tab5_ui_obj_t s_btn_toggle_eye = TAB5_UI_INVALID_OBJ;
static tab5_ui_obj_t s_btn_connect = TAB5_UI_INVALID_OBJ;
static tab5_ui_obj_t s_btn_disconnect = TAB5_UI_INVALID_OBJ;
static tab5_ui_obj_t s_btn_forget = TAB5_UI_INVALID_OBJ;
static tab5_ui_obj_t s_list_networks = TAB5_UI_INVALID_OBJ;

static bool s_pwd_visible = false;

static void update_wifi_status_view(void)
{
    tab5_wifi_info_t info = {0};
    tab5_err_t err = tab5_system_get_wifi_status(&info);

    if (s_lbl_status != TAB5_UI_INVALID_OBJ) {
        if (err == TAB5_OK && info.is_connected) {
            char status_buf[128];
            snprintf(status_buf, sizeof(status_buf), "Conectado: %s | IP: %s (%d dBm)",
                     info.ssid[0] ? info.ssid : "Ativo",
                     info.ip_addr[0] ? info.ip_addr : "0.0.0.0",
                     info.rssi);
            tab5_ui_label_set_text(s_lbl_status, status_buf);
            tab5_ui_obj_set_style_text_color(s_lbl_status, 0x22C55E, 255);
        } else {
            tab5_ui_label_set_text(s_lbl_status, "Status: Desconectado");
            tab5_ui_obj_set_style_text_color(s_lbl_status, 0x94A3B8, 255);
        }
    }

    if (s_lbl_selected_ssid != TAB5_UI_INVALID_OBJ) {
        if (s_selected_ssid[0]) {
            char sel_buf[64];
            snprintf(sel_buf, sizeof(sel_buf), "Rede: %s", s_selected_ssid);
            tab5_ui_label_set_text(s_lbl_selected_ssid, sel_buf);
        } else {
            tab5_ui_label_set_text(s_lbl_selected_ssid, "Rede: Nenhuma selecionada");
        }
    }
}

static void scan_wifi_networks(void)
{
    if (s_list_networks == TAB5_UI_INVALID_OBJ) {
        return;
    }
    tab5_ui_obj_clean(s_list_networks);
    s_ap_count = 0;

    tab5_ui_show_toast("Buscando redes Wi-Fi...", 1200);

    tab5_err_t err = tab5_wifi_scan(s_aps, MAX_APS, &s_ap_count);
    if (err == TAB5_OK && s_ap_count > 0) {
        for (uint32_t i = 0; i < s_ap_count; i++) {
            char label_buf[96];
            const char *sec_str = (s_aps[i].authmode > 0) ? "[Protegida]" : "[Aberta]";
            snprintf(label_buf, sizeof(label_buf), "%s (%d dBm)  %s", s_aps[i].ssid, s_aps[i].rssi, sec_str);

            tab5_ui_obj_t btn = tab5_ui_list_add_btn(s_list_networks, LV_SYMBOL_WIFI, label_buf);
            if (btn != TAB5_UI_INVALID_OBJ) {
                s_ap_btn_handles[i] = btn;
            }
        }
    } else {
        const char *message = "Nenhuma rede encontrada no alcance";
        if (!tab5_wifi_is_enabled()) {
            message = "Wi-Fi desabilitado";
        } else if (err == TAB5_ERR_TIMEOUT) {
            message = "Tempo esgotado ao buscar redes Wi-Fi";
        } else if (err != TAB5_OK) {
            message = "Falha ao buscar redes Wi-Fi";
        }
        tab5_ui_list_add_btn(s_list_networks, LV_SYMBOL_CLOSE, message);
    }
}

static void on_select_ap(uint32_t index)
{
    if (index >= s_ap_count) {
        return;
    }
    strncpy(s_selected_ssid, s_aps[index].ssid, sizeof(s_selected_ssid) - 1);
    update_wifi_status_view();
    tab5_sound_play_beep(1200, 30);

    if (s_ta_password != TAB5_UI_INVALID_OBJ) {
        tab5_ui_textarea_set_text(s_ta_password, "");
        tab5_ui_keyboard_show(s_ta_password);
    }
    tab5_ui_show_toast("Digite a senha para conectar", 1500);
}

static void on_connect_clicked(void)
{
    if (s_selected_ssid[0] == '\0') {
        tab5_ui_show_toast("Selecione uma rede Wi-Fi primeiro", 1500);
        return;
    }

    char pwd[256] = {0};
    if (s_ta_password != TAB5_UI_INVALID_OBJ) {
        if (tab5_ui_textarea_copy_text(s_ta_password, pwd, sizeof(pwd)) < 0) {
            return;
        }
    }

    tab5_ui_keyboard_hide();
    tab5_ui_show_toast("Conectando a rede...", 2000);
    tab5_wifi_connect(s_selected_ssid, pwd);
    tab5_sound_play_beep(1000, 30);
    update_wifi_status_view();
}

static void on_disconnect_clicked(void)
{
    tab5_wifi_disconnect();
    tab5_sound_play_beep(800, 30);
    tab5_ui_show_toast("Desconectado do Wi-Fi", 1000);
    update_wifi_status_view();
}

static void on_forget_clicked(void)
{
    if (s_selected_ssid[0] != '\0') {
        tab5_wifi_forget(s_selected_ssid);
        tab5_sound_play_beep(600, 40);
        tab5_ui_show_toast("Rede esquecida do microSD", 1200);
        s_selected_ssid[0] = '\0';
        update_wifi_status_view();
    }
}

static void on_toggle_eye_clicked(void)
{
    s_pwd_visible = !s_pwd_visible;
    if (s_ta_password != TAB5_UI_INVALID_OBJ) {
        tab5_ui_textarea_set_password_mode(s_ta_password, !s_pwd_visible);
    }
    if (s_btn_toggle_eye != TAB5_UI_INVALID_OBJ) {
        tab5_ui_label_set_text(s_btn_toggle_eye, s_pwd_visible ? LV_SYMBOL_EYE_CLOSE : LV_SYMBOL_EYE_OPEN);
    }
}

static void build_wifi_ui(void)
{
    uint32_t pal_surface = tab5_ui_theme_get_color(TAB5_UI_COLOR_SURFACE);
    uint32_t pal_surface_alt = tab5_ui_theme_get_color(TAB5_UI_COLOR_SURFACE_ALT);
    uint32_t pal_border = tab5_ui_theme_get_color(TAB5_UI_COLOR_BORDER);
    uint32_t pal_text = tab5_ui_theme_get_color(TAB5_UI_COLOR_TEXT);
    uint32_t pal_text_muted = tab5_ui_theme_get_color(TAB5_UI_COLOR_TEXT_MUTED);
    uint32_t pal_accent = tab5_ui_theme_get_color(TAB5_UI_COLOR_ACCENT);

    tab5_ui_obj_t scr = tab5_ui_get_screen();

    tab5_ui_obj_t main_cont = tab5_ui_container_create(scr);
    tab5_ui_obj_set_size(main_cont, TAB5_UI_PCT(100), TAB5_UI_SIZE_CONTENT);
    tab5_ui_obj_set_align(main_cont, TAB5_UI_ALIGN_TOP_MID, 0, 104);
    tab5_ui_obj_set_flex_flow(main_cont, TAB5_UI_FLEX_FLOW_COLUMN);
    tab5_ui_obj_set_style_bg(main_cont, 0, 0);
    tab5_ui_obj_set_style_border(main_cont, 0, 0);
    tab5_ui_obj_set_pad(main_cont, 14);
    tab5_ui_obj_set_gap(main_cont, 14);

    // 1. Card Status & Hardware
    tab5_ui_obj_t card_stat = tab5_ui_container_create(main_cont);
    tab5_ui_obj_set_size(card_stat, TAB5_UI_PCT(100), TAB5_UI_SIZE_CONTENT);
    tab5_ui_obj_set_flex_flow(card_stat, TAB5_UI_FLEX_FLOW_COLUMN);
    tab5_ui_obj_set_style_bg(card_stat, pal_surface, 255);
    tab5_ui_obj_set_style_border(card_stat, pal_border, 1);
    tab5_ui_obj_set_style_radius(card_stat, 12);
    tab5_ui_obj_set_pad(card_stat, 16);
    tab5_ui_obj_set_gap(card_stat, 12);

    tab5_ui_obj_t row_sw = tab5_ui_container_create(card_stat);
    tab5_ui_obj_set_size(row_sw, TAB5_UI_PCT(100), TAB5_UI_SIZE_CONTENT);
    tab5_ui_obj_set_flex_flow(row_sw, TAB5_UI_FLEX_FLOW_ROW);
    tab5_ui_obj_set_style_bg(row_sw, 0, 0);
    tab5_ui_obj_set_style_border(row_sw, 0, 0);

    tab5_ui_obj_t lbl_h_title = tab5_ui_label_create(row_sw, LV_SYMBOL_WIFI "  CONECTIVIDADE WI-FI");
    tab5_ui_obj_set_style_text_color(lbl_h_title, pal_accent, 255);
    tab5_ui_obj_set_flex_grow(lbl_h_title, 1);

    s_sw_wifi = tab5_ui_switch_create(row_sw);
    tab5_ui_switch_set_state(s_sw_wifi, tab5_wifi_is_enabled());

    s_lbl_status = tab5_ui_label_create(card_stat, "Status: Verificando...");
    tab5_ui_obj_set_style_text_color(s_lbl_status, pal_text_muted, 255);

    s_btn_scan = tab5_ui_btn_create(card_stat, LV_SYMBOL_REFRESH "  Escanear Redes Proximas");
    tab5_ui_obj_set_style_bg(s_btn_scan, pal_surface_alt, 255);
    tab5_ui_obj_set_style_text_color(s_btn_scan, pal_text, 255);

    // 2. Card Conectar à Rede
    tab5_ui_obj_t card_conn = tab5_ui_container_create(main_cont);
    tab5_ui_obj_set_size(card_conn, TAB5_UI_PCT(100), TAB5_UI_SIZE_CONTENT);
    tab5_ui_obj_set_flex_flow(card_conn, TAB5_UI_FLEX_FLOW_COLUMN);
    tab5_ui_obj_set_style_bg(card_conn, pal_surface, 255);
    tab5_ui_obj_set_style_border(card_conn, pal_border, 1);
    tab5_ui_obj_set_style_radius(card_conn, 12);
    tab5_ui_obj_set_pad(card_conn, 16);
    tab5_ui_obj_set_gap(card_conn, 12);

    s_lbl_selected_ssid = tab5_ui_label_create(card_conn, "Rede: Nenhuma selecionada");
    tab5_ui_obj_set_style_text_color(s_lbl_selected_ssid, pal_text, 255);

    tab5_ui_obj_t row_pwd = tab5_ui_container_create(card_conn);
    tab5_ui_obj_set_size(row_pwd, TAB5_UI_PCT(100), TAB5_UI_SIZE_CONTENT);
    tab5_ui_obj_set_flex_flow(row_pwd, TAB5_UI_FLEX_FLOW_ROW);
    tab5_ui_obj_set_style_bg(row_pwd, 0, 0);
    tab5_ui_obj_set_style_border(row_pwd, 0, 0);
    tab5_ui_obj_set_gap(row_pwd, 8);

    s_ta_password = tab5_ui_get_main_textarea();
    if (s_ta_password != TAB5_UI_INVALID_OBJ) {
        tab5_ui_textarea_set_placeholder(s_ta_password, "Digite a senha do Wi-Fi");
        tab5_ui_textarea_set_password_mode(s_ta_password, true);
    }

    s_btn_toggle_eye = tab5_ui_btn_create(row_pwd, LV_SYMBOL_EYE_OPEN);
    tab5_ui_obj_set_style_bg(s_btn_toggle_eye, pal_surface_alt, 255);
    tab5_ui_obj_set_style_text_color(s_btn_toggle_eye, pal_text, 255);

    tab5_ui_obj_t row_act = tab5_ui_container_create(card_conn);
    tab5_ui_obj_set_size(row_act, TAB5_UI_PCT(100), TAB5_UI_SIZE_CONTENT);
    tab5_ui_obj_set_flex_flow(row_act, TAB5_UI_FLEX_FLOW_ROW);
    tab5_ui_obj_set_style_bg(row_act, 0, 0);
    tab5_ui_obj_set_style_border(row_act, 0, 0);
    tab5_ui_obj_set_gap(row_act, 10);

    s_btn_connect = tab5_ui_btn_create(row_act, LV_SYMBOL_OK " Conectar");
    tab5_ui_obj_set_style_bg(s_btn_connect, pal_accent, 255);
    tab5_ui_obj_set_style_text_color(s_btn_connect, 0xFFFFFF, 255);
    tab5_ui_obj_set_flex_grow(s_btn_connect, 2);

    s_btn_disconnect = tab5_ui_btn_create(row_act, LV_SYMBOL_CLOSE " Desconectar");
    tab5_ui_obj_set_style_bg(s_btn_disconnect, pal_surface_alt, 255);
    tab5_ui_obj_set_style_text_color(s_btn_disconnect, pal_text, 255);
    tab5_ui_obj_set_flex_grow(s_btn_disconnect, 1);

    s_btn_forget = tab5_ui_btn_create(row_act, LV_SYMBOL_TRASH " Esquecer");
    tab5_ui_obj_set_style_bg(s_btn_forget, pal_surface_alt, 255);
    tab5_ui_obj_set_style_text_color(s_btn_forget, pal_text, 255);
    tab5_ui_obj_set_flex_grow(s_btn_forget, 1);

    // 3. Card Lista de Redes
    tab5_ui_obj_t card_list = tab5_ui_container_create(main_cont);
    tab5_ui_obj_set_size(card_list, TAB5_UI_PCT(100), TAB5_UI_SIZE_CONTENT);
    tab5_ui_obj_set_flex_flow(card_list, TAB5_UI_FLEX_FLOW_COLUMN);
    tab5_ui_obj_set_style_bg(card_list, pal_surface, 255);
    tab5_ui_obj_set_style_border(card_list, pal_border, 1);
    tab5_ui_obj_set_style_radius(card_list, 12);
    tab5_ui_obj_set_pad(card_list, 16);
    tab5_ui_obj_set_gap(card_list, 10);

    tab5_ui_obj_t lbl_list_t = tab5_ui_label_create(card_list, LV_SYMBOL_SETTINGS "  REDES DISPONIVEIS");
    tab5_ui_obj_set_style_text_color(lbl_list_t, pal_accent, 255);

    s_list_networks = tab5_ui_list_create(card_list);
    tab5_ui_obj_set_size(s_list_networks, TAB5_UI_PCT(100), 220);

    scan_wifi_networks();
    update_wifi_status_view();
}

static void app_init(void)
{
    tab5_system_log(2, "tab5_wifi", "Aplicativo Wi-Fi iniciado");
    tab5_ui_app_bar_set_title("Gerenciador Wi-Fi");
    build_wifi_ui();
}

static void app_resume(void)
{
    tab5_system_log(2, "tab5_wifi", "Wi-Fi retomado");
    update_wifi_status_view();
}

static void app_pause(void)
{
    tab5_system_log(2, "tab5_wifi", "Wi-Fi pausado");
}

static void app_destroy(void)
{
    tab5_system_log(2, "tab5_wifi", "Wi-Fi finalizado");
}

TAB5_APP_EXPORT void tab5_app_on_theme_changed(bool dark)
{
    (void)dark;
    tab5_ui_clear_content();
    build_wifi_ui();
}

TAB5_APP_EXPORT void tab5_app_on_ui_event(tab5_ui_obj_t obj, uint32_t event_type, int32_t event_val)
{
    if (event_type == TAB5_UI_EVENT_VALUE_CHANGED && obj == s_sw_wifi) {
        bool en = tab5_ui_switch_get_state(s_sw_wifi);
        tab5_wifi_set_enabled(en);
        tab5_sound_play_beep(en ? 1200 : 600, 30);
        tab5_ui_show_toast(en ? "Wi-Fi Ativado" : "Wi-Fi Desativado", 1000);
        update_wifi_status_view();
        return;
    }

    if (event_type != TAB5_UI_EVENT_CLICKED) {
        return;
    }

    if (obj == s_btn_scan) {
        scan_wifi_networks();
        return;
    } else if (obj == s_btn_toggle_eye) {
        on_toggle_eye_clicked();
        return;
    } else if (obj == s_btn_connect) {
        on_connect_clicked();
        return;
    } else if (obj == s_btn_disconnect) {
        on_disconnect_clicked();
        return;
    } else if (obj == s_btn_forget) {
        on_forget_clicked();
        return;
    }

    for (uint32_t i = 0; i < s_ap_count; i++) {
        if (obj == s_ap_btn_handles[i]) {
            on_select_ap(i);
            return;
        }
    }
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
