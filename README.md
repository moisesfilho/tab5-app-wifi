# Tab5 Wi-Fi App (`tab5-app-wifi`)

Aplicativo isolado de gerenciamento e status de rede sem fio para o **Tab5 OS**.

## Compilação e Empacotamento

```bash
chmod +x tools/build.sh
./tools/build.sh
```

O pacote `.tab5pkg` será gerado em `dist/com.tab5.wifi.tab5pkg`.

## Testes

```bash
bash tests/run_all_tests.sh
```

O fluxo de escaneamento limpa a lista de forma adiada durante callbacks de
interface, preservando a repopulação dos resultados no ciclo seguinte do LVGL.
