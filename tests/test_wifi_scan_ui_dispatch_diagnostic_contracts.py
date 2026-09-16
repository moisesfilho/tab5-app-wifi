"""Contratos adicionais do fluxo de scan Wi-Fi (review: needs_more_tests).

Contexto aprovado (plano do reviewer): no dispositivo fisico o app abre com
"Falha ao buscar redes Wi-Fi" e tocar em "Escanear Redes Proximas" mantem a
mensagem. A hipotese UI (clean sincrono durante callback) foi enderecada por
`test_wifi_scan_clean_deferred_contract.py` (12 testes, verdes apos a troca
clean -> clean_deferred em `scan_wifi_networks`). Falta separar essa hipotese
de uma falha fisica/backend do proprio `tab5_wifi_scan` — e garantir que o
tooling de diagnostico consiga ler as respostas do dispositivo para fazer essa
separacao.

Estes contratos adicionais cobrem tres lacunas reais, todos deterministas e
somente host/estaticos (nenhum abre serial, simulador ou hardware):

  (a) O evento do botao "Escanear Redes Proximas" despacha para
      `scan_wifi_networks`: dentro de `tab5_app_on_ui_event`, apenas o CLICKED
      em `s_btn_scan` chama `scan_wifi_networks()`. Esperado: VERDE hoje —
      pina o lado UI do fluxo de disparo.

  (b) Resultado OK com count>0 preserva a adicao dos SSIDs e NAO renderiza
      mensagem de falha: o if `err == TAB5_OK && s_ap_count > 0` adiciona os
      botoes com `s_aps[i].ssid` em loop limitado por `s_ap_count`; as
      mensagens de falha vivem somente no else e "Falha ao buscar redes
      Wi-Fi" so e alcancavel quando `err != TAB5_OK`. Esperado: VERDE hoje —
      prova estaticamente que, se a tela persistir mostrando a falha no
      dispositivo, o erro vem do backend (err != TAB5_OK), nao do render.

  (c) O diagnostico do device (tools/tab5_cli.py, automacao Serial Bridge)
      deve aceitar frames NDJSON validos mesmo com linhas de log intercaladas
      e com o frame fragmentado entre leituras (o console USB-Serial-JTAG
      compartilha o USB com ESP_LOG; um frame grande como a resposta de
      `wifi.scan` pode chegar em pedacos). Hoje `Tab5Session.exchange` descarta
      qualquer linha que nao parseie JSON, perdendo o frame parcial.
      Esperado: VERMELHO hoje — revela a falha real do tooling de diagnostico;
      a futura implementacao deve remontar linhas parciais ate o '\n'.

Contratos pre-existentes nao sao enfraquecidos: este arquivo apenas adiciona
cenarios. Self-checks dos parseadores permanecem verdes (independem da
implementacao).
"""

import json
import re
import sys
import unittest
from pathlib import Path

APP_SRC = Path(__file__).resolve().parents[1] / "src" / "main.c"
WORKSPACE = Path(__file__).resolve().parents[2]
OS_ROOT = WORKSPACE / "tab5-os"
CLI_PATH = OS_ROOT / "tools" / "tab5_cli.py"

HAS_CLI = CLI_PATH.is_file()
if HAS_CLI:
    sys.path.insert(0, str(OS_ROOT / "tools"))
    import tab5_cli

SCAN_SIG = "static void scan_wifi_networks(void)"
EVENT_SIG = ("TAB5_APP_EXPORT void tab5_app_on_ui_event(tab5_ui_obj_t obj, "
             "uint32_t event_type, int32_t event_val)")

SUCCESS_COND_RE = re.compile(r"\bif\s*\(\s*err\s*==\s*TAB5_OK\s*&&\s*s_ap_count\s*>\s*0")
LOOP_BOUND_RE = re.compile(r"\bi\s*<\s*s_ap_count")
SCAN_INVOKE_RE = re.compile(r"\btab5_wifi_scan\s*\(\s*s_aps\s*,\s*MAX_APS\s*,\s*&s_ap_count\s*\)")

FAILURE_MSGS = (
    "Falha ao buscar redes Wi-Fi",
    "Nenhuma rede encontrada no alcance",
    "Wi-Fi desabilitado",
    "Tempo esgotado ao buscar redes Wi-Fi",
)

MISSING_CLI_REASON = (
    "tools/tab5_cli.py ausente: sem o tooling de diagnostico nao ha contrato "
    "de leitura NDJSON a validar no host."
)


def _read(p: Path) -> str:
    return p.read_text(encoding="utf-8")


def _signature_pattern(signature: str) -> re.Pattern:
    """Converte assinatura C/C++ (possivelmente multilinha) em pattern
    tolerante a espacos em branco (espacos/comentarios/newlines entre tokens)."""
    norm = re.sub(r"\s+", " ", signature).strip()
    return re.compile(re.escape(norm).replace(r"\ ", r"\s+"))


def _function_body(source: str, signature: str) -> str:
    """Corpo da funcao C/C++, respeitando chaves aninhadas."""
    m = _signature_pattern(signature).search(source)
    if m is None:
        raise AssertionError(f"function definition not found: {signature!r}")
    opening = source.index("{", m.start())
    depth = 0
    for pos in range(opening, len(source)):
        if source[pos] == "{":
            depth += 1
        elif source[pos] == "}":
            depth -= 1
            if depth == 0:
                return source[opening + 1 : pos]
    raise AssertionError(f"unclosed function body: {signature!r}")


def _if_else_branches(body: str, cond_re: re.Pattern):
    """Extrai (if_body, else_body) do if/else cuja condicao casa cond_re.

    Usa casamento balanceado de parenteses/chaves (mesma tecnica de
    `_function_body`), tolerante a condicoes multilinha. Devolve None quando a
    estrutura if/else esperada nao existe (ex.: sem else braced, condicao
    ausente) — o contrato falha de forma explicita nesses casos.
    """
    m = cond_re.search(body)
    if m is None:
        return None
    cond_open = body.find("(", m.start())
    if cond_open < 0:
        return None
    depth = 0
    cond_close = -1
    for pos in range(cond_open, len(body)):
        if body[pos] == "(":
            depth += 1
        elif body[pos] == ")":
            depth -= 1
            if depth == 0:
                cond_close = pos
                break
    if cond_close < 0:
        return None
    if_open = body.find("{", cond_close)
    if if_open < 0:
        return None
    depth = 0
    if_close = -1
    for pos in range(if_open, len(body)):
        if body[pos] == "{":
            depth += 1
        elif body[pos] == "}":
            depth -= 1
            if depth == 0:
                if_close = pos
                break
    if if_close < 0:
        return None
    rest = body[if_close + 1:].lstrip()
    m_else = re.match(r"else\s*\{", rest)
    if m_else is None:
        return None
    else_open = m_else.end() - 1  # posicao da chave '{' dentro de rest
    depth = 0
    else_close = -1
    for pos in range(else_open, len(rest)):
        if rest[pos] == "{":
            depth += 1
        elif rest[pos] == "}":
            depth -= 1
            if depth == 0:
                else_close = pos
                break
    if else_close < 0:
        return None
    return body[if_open + 1: if_close], rest[else_open + 1: else_close]


class FragmentedFakeTransport:
    """Simula o console USB-Serial-JTAG com frames NDJSON fragmentados.

    Cada item da lista e devolvido por uma leitura; itens NAO terminam
    necessariamente em '\n' — um frame JSON valido pode chegar dividido em
    varias leituras (pacing USB/serial), com linhas de log intercaladas.
    """

    def __init__(self, responses):
        self._responses = [
            r.encode() if isinstance(r, str) else bytes(r) for r in responses
        ]
        self.sent = []
        self.readline_count = 0

    def write(self, data):
        if isinstance(data, (bytes, bytearray)):
            self.sent.append(data)
        else:
            self.sent.append(data.encode())

    def readline(self):
        self.readline_count += 1
        if self._responses:
            return self._responses.pop(0)
        return b""


def _naive_line_parse(raws):
    """Semantica ATUAL do Tab5Session.exchange: cada leitura e parseada isolada.

    Linhas que nao parseiam JSON sao descartadas sem remontagem — um frame
    valid0 fragmentado em N leituras e perdido.
    """
    frames = []
    for raw in raws:
        try:
            frame = json.loads(raw.decode().strip())
        except (TypeError, ValueError, UnicodeDecodeError):
            continue
        if isinstance(frame, dict):
            frames.append(frame)
    return frames


def _reassembled_line_parse(raws):
    """Semantica desejada: acumula bytes ate '\n' antes de tentar parsear.

    Especifica o formato da correcao futura do tooling: remontar a linha
    parcial entre leituras (log/ANSI continuam ignorados), nunca descartar
    metade de um frame valido.
    """
    frames = []
    pending = b""
    for raw in raws:
        pending += raw
        if b"\n" not in pending:
            continue
        line, _, pending = pending.partition(b"\n")
        try:
            frame = json.loads(line.decode().strip())
        except (TypeError, ValueError, UnicodeDecodeError):
            continue
        if isinstance(frame, dict):
            frames.append(frame)
    return frames


class WifiScanButtonDispatchContract(unittest.TestCase):
    """REQ (a): CLICKED em s_btn_scan despacha para scan_wifi_networks."""

    @classmethod
    def setUpClass(cls):
        cls.src = _read(APP_SRC)
        cls.body = _function_body(cls.src, EVENT_SIG)

    def test_event_handler_exists(self):
        """Anchor: tab5_app_on_ui_event deve existir (guarda anti-vazia)."""
        self.assertIn(EVENT_SIG, self.src)

    def test_clicked_gate_precedes_scan_dispatch(self):
        """O despacho do scan deve estar dentro do gate CLICKED.

        VALUE_CHANGED (switch Wi-Fi) retorna cedo; o branch de s_btn_scan so
        pode ser alcancado depois do gate `event_type != TAB5_UI_EVENT_CLICKED`
        — um scan disparado por outro evento seria um novo bug de UI.
        """
        idx_value = self.body.find("TAB5_UI_EVENT_VALUE_CHANGED")
        idx_clicked = self.body.find("TAB5_UI_EVENT_CLICKED")
        idx_scan = self.body.find("obj == s_btn_scan")
        self.assertGreaterEqual(
            idx_value, 0,
            "o handler deve tratar TAB5_UI_EVENT_VALUE_CHANGED (switch Wi-Fi)",
        )
        self.assertGreaterEqual(
            idx_clicked, 0,
            "o handler deve gatear o despacho com TAB5_UI_EVENT_CLICKED",
        )
        self.assertGreaterEqual(
            idx_scan, 0,
            "o handler deve comparar obj com s_btn_scan",
        )
        self.assertLess(
            idx_value, idx_clicked,
            "VALUE_CHANGED deve retornar antes do gate CLICKED",
        )
        self.assertLess(
            idx_clicked, idx_scan,
            "o branch de s_btn_scan deve estar DENTRO do gate CLICKED "
            "(nenhum outro evento pode disparar o scan)",
        )

    def test_scan_click_dispatches_to_scan_wifi_networks(self):
        """O CLICKED em s_btn_scan deve chamar scan_wifi_networks() no branch."""
        idx_scan = self.body.find("obj == s_btn_scan")
        idx_call = self.body.find("scan_wifi_networks(", idx_scan)
        self.assertGreaterEqual(
            idx_scan, 0,
            "o handler deve comparar obj com s_btn_scan",
        )
        self.assertGreaterEqual(
            idx_call, 0,
            "o CLICKED em s_btn_scan deve despachar para scan_wifi_networks()",
        )
        self.assertLessEqual(
            idx_call - idx_scan, 300,
            "scan_wifi_networks() deve ser chamada dentro do branch do botao "
            "Escanear (proximo a comparacao obj == s_btn_scan)",
        )

    def test_scan_dispatch_exclusive_and_returns(self):
        """O despacho do scan e exclusivo e retorna (sem fallthrough).

        Nenhum outro evento UI deve disparar scan_wifi_networks, e o branch
        do botao Escanear deve retornar imediatamente — um fallthrough para o
        loop de s_ap_btn_handles seria um scan duplicado/indevido.
        """
        self.assertEqual(
            self.body.count("scan_wifi_networks("), 1,
            "tab5_app_on_ui_event deve conter exatamente UMA chamada a "
            "scan_wifi_networks() — somente o botao Escanear despacha o scan",
        )
        idx_scan = self.body.find("obj == s_btn_scan")
        idx_call = self.body.find("scan_wifi_networks(", idx_scan)
        idx_ret = self.body.find("return;", idx_call)
        self.assertGreaterEqual(
            idx_ret, 0,
            "o branch do botao Escanear deve retornar apos o despacho "
            "(sem fallthrough para o loop de selecao de AP)",
        )
        self.assertLessEqual(
            idx_ret - idx_call, 120,
            "o return deve vir imediatamente apos scan_wifi_networks()",
        )


class WifiScanSuccessPathContract(unittest.TestCase):
    """REQ (b): OK com count>0 adiciona SSIDs e NAO renderiza falha."""

    @classmethod
    def setUpClass(cls):
        cls.src = _read(APP_SRC)
        cls.body = _function_body(cls.src, SCAN_SIG)
        pair = _if_else_branches(cls.body, SUCCESS_COND_RE)
        cls.if_body, cls.else_body = pair if pair is not None else (None, None)

    def test_scan_invokes_backend_with_out_count(self):
        """O scan deve alimentar a lista a partir do backend tab5_wifi_scan."""
        self.assertIsNotNone(
            SCAN_INVOKE_RE.search(self.body),
            "scan_wifi_networks deve chamar tab5_wifi_scan(s_aps, MAX_APS, "
            "&s_ap_count) — o resultado real do backend alimenta a lista",
        )

    def test_success_condition_requires_ok_and_count(self):
        """A adicao so pode ocorrer com TAB5_OK e s_ap_count > 0."""
        self.assertIsNotNone(
            SUCCESS_COND_RE.search(self.body),
            "deve existir o if `err == TAB5_OK && s_ap_count > 0` separando "
            "sucesso com redes de vazio/erro",
        )

    def test_success_branch_adds_ssid_buttons(self):
        """O branch de sucesso precisa repopular a lista com os SSIDs."""
        self.assertIsNotNone(
            self.if_body,
            "if/else de sucesso nao encontrado no corpo de scan_wifi_networks",
        )
        self.assertIn(
            "tab5_ui_list_add_btn(",
            self.if_body,
            "o branch de sucesso deve adicionar botoes com tab5_ui_list_add_btn",
        )
        self.assertIn(
            "s_aps[i].ssid",
            self.if_body,
            "o rotulo de cada botao deve conter o SSID do AP (s_aps[i].ssid) "
            "— a lista exibe as redes reais encontradas",
        )

    def test_success_branch_loop_bounded_by_reported_count(self):
        """O loop de adicao deve ser limitado por s_ap_count (nunca cego)."""
        self.assertIsNotNone(
            self.if_body,
            "if/else de sucesso nao encontrado no corpo de scan_wifi_networks",
        )
        self.assertIsNotNone(
            LOOP_BOUND_RE.search(self.if_body),
            "o loop de repopulate deve iterar i < s_ap_count — adiciona "
            "exatamente as redes reportadas pelo backend, sem slots fantasmas",
        )

    def test_success_branch_renders_no_failure_message(self):
        """Sucesso com redes NAO pode renderizar nenhuma mensagem de falha."""
        self.assertIsNotNone(
            self.if_body,
            "if/else de sucesso nao encontrado no corpo de scan_wifi_networks",
        )
        for msg in FAILURE_MSGS:
            self.assertNotIn(
                msg, self.if_body,
                f"o branch de sucesso (err == TAB5_OK && count > 0) nao pode "
                f"renderizar a mensagem de falha: {msg!r}",
            )

    def test_failure_messages_live_only_in_else_branch(self):
        """Toda a taxonomia de falha deve estar no else (mutuamente exclusivo)."""
        self.assertIsNotNone(
            self.else_body,
            "o if de sucesso deve ter else com as mensagens de falha "
            "(ou o caminho de erro fica sem resposta visivel)",
        )
        for msg in FAILURE_MSGS:
            self.assertIn(
                msg, self.else_body,
                f"o else deve preservar a mensagem {msg!r} do caminho de erro",
            )

    def test_failure_message_only_reachable_when_err_not_ok(self):
        """"Falha ao buscar redes Wi-Fi" so pode aparecer com err != TAB5_OK.

        Ligacao com o device: se a tela persistir mostrando exatamente essa
        mensagem, o erro ja esta provado como backend (err != TAB5_OK), pois
        o branch de sucesso nao a renderiza e o else a condiciona ao erro.
        """
        self.assertIsNotNone(
            self.else_body,
            "if/else de sucesso nao encontrado no corpo de scan_wifi_networks",
        )
        idx_default = self.else_body.find("Nenhuma rede encontrada no alcance")
        idx_err = self.else_body.find("err != TAB5_OK")
        idx_msg = self.else_body.find("Falha ao buscar redes Wi-Fi")
        self.assertGreaterEqual(
            idx_default, 0,
            "o else deve comecar com a mensagem informativa de lista vazia "
            "(err == TAB5_OK sem redes)",
        )
        self.assertGreaterEqual(
            idx_err, 0,
            "a mensagem de falha deve ser condicionada a err != TAB5_OK",
        )
        self.assertGreaterEqual(
            idx_msg, 0,
            "a mensagem 'Falha ao buscar redes Wi-Fi' deve existir no else",
        )
        self.assertLess(
            idx_default, idx_err,
            "a mensagem padrao (lista vazia) deve preceder o teste de erro",
        )
        self.assertLess(
            idx_err, idx_msg,
            "'Falha ao buscar redes Wi-Fi' deve ser atribuida somente no "
            "branch err != TAB5_OK — nunca para scan OK",
        )


class WifiScanDispatchSelfCheck(unittest.TestCase):
    """Pureza dos checkers estaticos (verdes, independentes da implementacao)."""

    def test_success_condition_regex_tolerant_to_multiline(self):
        self.assertIsNotNone(
            SUCCESS_COND_RE.search(
                "    if (err == TAB5_OK &&\n"
                "        s_ap_count > 0) {\n"
            )
        )

    def test_loop_bound_regex_matches_for_loop(self):
        self.assertIsNotNone(
            LOOP_BOUND_RE.search("for (uint32_t i = 0; i < s_ap_count; i++) {")
        )

    def test_scan_invoke_regex_tolerant_to_whitespace(self):
        self.assertIsNotNone(
            SCAN_INVOKE_RE.search("tab5_wifi_scan(s_aps, MAX_APS, &s_ap_count);")
        )
        self.assertIsNone(
            SCAN_INVOKE_RE.search("tab5_wifi_scan(s_aps, MAX_APS, &other);")
        )

    def test_if_else_branches_extraction_nested_braces(self):
        src = (
            "if (err == TAB5_OK && s_ap_count > 0) {\n"
            "    for (uint32_t i = 0; i < s_ap_count; i++) {\n"
            "        if (btn != TAB5_UI_INVALID_OBJ) {\n"
            "            s_ap_btn_handles[i] = btn;\n"
            "        }\n"
            "    }\n"
            "} else {\n"
            "    message = \"Falha ao buscar redes Wi-Fi\";\n"
            "}\n"
        )
        pair = _if_else_branches(src, SUCCESS_COND_RE)
        self.assertIsNotNone(pair)
        if_body, else_body = pair
        self.assertIn("s_ap_btn_handles[i] = btn;", if_body)
        self.assertIn("Falha ao buscar redes Wi-Fi", else_body)
        self.assertNotIn("Falha ao buscar redes Wi-Fi", if_body)

    def test_if_else_branches_requires_braced_else(self):
        src = "if (err == TAB5_OK && s_ap_count > 0) { ok(); } else fail();\n"
        self.assertIsNone(
            _if_else_branches(src, SUCCESS_COND_RE),
            "if sem else braced nao satisfaz a extracao (o contrato exige o "
            "else com { } para os dois caminhos ficarem estaticamente claros)",
        )
        self.assertIsNone(
            _if_else_branches("if (x) { }", SUCCESS_COND_RE),
            "condicao de sucesso ausente deve devolver None",
        )

    def test_function_body_extraction_with_nested_braces(self):
        src = (
            "static void scan_wifi_networks(void)\n"
            "{\n"
            "    if (s_list_networks == TAB5_UI_INVALID_OBJ) {\n"
            "        return;\n"
            "    }\n"
            "    tab5_ui_obj_clean_deferred(s_list_networks);\n"
            "}\n"
        )
        body = _function_body(src, SCAN_SIG)
        self.assertIn("tab5_ui_obj_clean_deferred(", body)
        self.assertIn("return;", body)


@unittest.skipUnless(HAS_CLI, MISSING_CLI_REASON)
class WifiScanDiagnosticNdjsonContract(unittest.TestCase):
    """REQ (c): diagnostico NDJSON aceita frames validos com logs/fragmentacao.

    Usa apenas o seam de transporte duck-typed do tools/tab5_cli.py — nenhum
    hardware, serial ou simulador e aberto. Esperado VERMELHO hoje: a leitura
    atual descarta linhas que nao parseiem JSON isoladamente, perdendo frames
    fragmentados (ex.: resposta grande de wifi.scan no console USB-Serial-JTAG
    compartilhado com ESP_LOG).
    """

    def test_sys_info_fragmented_with_log_lines_is_recovered(self):
        """Frame sys.info valido dividido em 2 leituras + logs nao pode se perder."""
        transport = FragmentedFakeTransport([
            "ESP-ROM:esp32p4\n",
            b'{"status":"ok"',
            ', "data": {"heap_free_internal": 350210, "battery_pct": 92, '
            '"wifi_connected": true}}\n',
        ])
        session = tab5_cli.open_session(transport)
        try:
            frames = session.exchange('{"cmd":"sys.info"}')
        except RuntimeError as exc:
            self.fail(f"frame NDJSON valido fragmentado foi descartado: {exc}")
        self.assertEqual(len(frames), 1,
                         "o frame sys.info fragmentado deve ser remontado")
        self.assertEqual(frames[0]["status"], "ok")
        self.assertEqual(frames[0]["data"]["battery_pct"], 92)

    def test_wifi_scan_response_fragmented_inside_aps_is_recovered(self):
        """Resposta de wifi.scan (grande, com aps[]) fragmentada no meio da lista.

        E exatamente a resposta que a investigacao device precisa ler para
        separar erro do scan de erro de renderizacao: se o frame e perdido, a
        investigacao nao consegue nem saber o que o bridge devolveu.
        """
        transport = FragmentedFakeTransport([
            "I (102) wifi_mgr: scan ok\n",
            '{"status":"ok","action":"wifi.scan","data":{"count":1,"aps":[{"ssid":"Tab5-LAB-2G",',
            '"rssi":-45,"authmode":3}]}}\n',
        ])
        session = tab5_cli.open_session(transport)
        try:
            frames = session.exchange('{"cmd":"wifi.scan","timeout_ms":15000}')
        except RuntimeError as exc:
            self.fail(f"frame NDJSON valido de wifi.scan fragmentado foi perdido: {exc}")
        self.assertEqual(len(frames), 1,
                         "o frame wifi.scan fragmentado deve ser remontado")
        self.assertEqual(frames[0]["action"], "wifi.scan")
        self.assertEqual(frames[0]["data"]["count"], 1)
        self.assertEqual(frames[0]["data"]["aps"][0]["ssid"], "Tab5-LAB-2G")

    def test_frame_fragmented_in_three_reads_with_crlf_is_recovered(self):
        """Fragmentacao em 3 leituras + CRLF final nao pode perder o frame."""
        transport = FragmentedFakeTransport([
            "\x1b[0;32mI (30) boot: ESP-IDF v5.5.5\x1b[0m\n",
            '{"status":"ok","action":"app.list","data":{"apps":[{"id":"com.tab5.wifi"',
            ',"name":"Wi-Fi"}]}',
            "}\r\n",
        ])
        session = tab5_cli.open_session(transport)
        try:
            frames = session.exchange('{"cmd":"app.list"}')
        except RuntimeError as exc:
            self.fail(f"frame app.list fragmentado foi descartado: {exc}")
        self.assertEqual(len(frames), 1)
        self.assertEqual(frames[0]["action"], "app.list")
        self.assertEqual(frames[0]["data"]["apps"][0]["id"], "com.tab5.wifi")

    def test_garbage_without_valid_frame_still_raises_no_response(self):
        """Solo de lixo/fragmentos que nunca fecham um frame continua erro.

        A correcao da remontagem nao pode mascarar um dispositivo que nunca
        responde: console que so emite logs/fragmentos termina em excecao
        explicita (mesmo contrato de CliConsoleLogToleranceContract).
        """
        transport = FragmentedFakeTransport([
            b'{"sta',
            b'tus": "o',
            "ESP-ROM:esp32p4\n",
        ])
        session = tab5_cli.open_session(transport)
        with self.assertRaises(RuntimeError) as ctx:
            session.exchange('{"cmd":"sys.info"}')
        self.assertIn("nenhuma resposta", str(ctx.exception))


@unittest.skipUnless(HAS_CLI, MISSING_CLI_REASON)
class WifiScanDiagnosticSelfCheck(unittest.TestCase):
    """Pureza do transporte falso e discriminancia do contrato (c)."""

    def test_fragmented_transport_delivers_exact_pieces(self):
        transport = FragmentedFakeTransport([
            b'{"status":"ok"',
            ', "data": {"battery_pct": 92}}\n',
        ])
        self.assertEqual(transport.readline(), b'{"status":"ok"')
        self.assertEqual(transport.readline(), b', "data": {"battery_pct": 92}}\n')
        self.assertEqual(transport.readline(), b"")

    def test_naive_line_parse_loses_fragmented_frame(self):
        """Semantica ATUAL do exchange perde o frame fragmentado (discriminante).

        Prova que o contrato nao e vacuo: a resposta wifi.scan dividida em 2
        leituras nao gera NENHUM frame com a leitura linha-a-linha atual.
        """
        raws = [
            b'{"status":"ok","action":"wifi.scan","data":{"count":1,"aps":[{"ssid":"Tab5-LAB-2G",',
            b'"rssi":-45,"authmode":3}]}}\n',
        ]
        self.assertEqual(_naive_line_parse(raws), [],
                         "a leitura isolada por linha (estado atual) descarta o frame")

    def test_reassembly_recovers_fragmented_frame(self):
        """Semantica desejada: acumular ate '\n' recupera o frame (spec do fix)."""
        raws = [
            b'{"status":"ok","action":"wifi.scan","data":{"count":1,"aps":[{"ssid":"Tab5-LAB-2G",',
            b'"rssi":-45,"authmode":3}]}}\n',
        ]
        frames = _reassembled_line_parse(raws)
        self.assertEqual(len(frames), 1)
        self.assertEqual(frames[0]["data"]["count"], 1)
        self.assertEqual(frames[0]["data"]["aps"][0]["ssid"], "Tab5-LAB-2G")

    def test_reassembly_still_ignores_log_lines(self):
        raw = (
            b"ESP-ROM:esp32p4\n",
            b'{"status":"ok","action":"app.active","data":{"active":true}}\n',
        )
        frames = _reassembled_line_parse(raw)
        self.assertEqual(len(frames), 1)
        self.assertEqual(frames[0]["action"], "app.active")


if __name__ == "__main__":
    unittest.main(verbosity=2)