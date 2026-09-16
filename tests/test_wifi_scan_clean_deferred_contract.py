"""Static contract REQ: scan_wifi_networks must clean the list deferred (red now).

Objetivo aprovado: corrigir o bug visual em tab5-app-wifi onde tocar
"Escanear Redes Proximas" deixa a lista em "Falha ao buscar redes Wi-Fi".

Hipótese aprovada: o fluxo de scan deve limpar/repopular a lista com
seguranca durante callback. O SDK documenta explicitamente (WASM_ABI.md,
secao "Limpeza durante callbacks"):

    Nao destrua sincronicamente o objeto que recebeu o clique enquanto o
    callback do evento ainda esta em execucao. Use
    `tab5_ui_obj_clean_deferred()` para ocultar e remover os filhos no
    proximo ciclo do LVGL, permitindo que o callback termine com o alvo
    valido.

O tab5_sdk.h define:
  - `tab5_ui_obj_clean(obj)` -- "Remove e desaloca todos os filhos de um
    objeto ou contêiner/lista" (SINCRONO);
  - `tab5_ui_obj_clean_deferred(obj)` -- "Limpa os filhos de um contêiner
    apos o callback de evento atual" (DEFERIDO, obrigatorio em callbacks).

Precedente interno: o app Files ja segue o contrato em
`render_content()` (tab5-app-files/src/main.c) usando
`tab5_ui_obj_clean_deferred(s_container)` ao reconstruir a lista.

Estado atual da implementacao (tab5-app-wifi/src/main.c, scan_wifi_networks):
usa `tab5_ui_obj_clean(s_list_networks)` SINCRONO. Por isso estes contratos
devem falhar (red) HOJE e ficar verdes depois que scan_wifi_networks trocar
a chamada por `tab5_ui_obj_clean_deferred(s_list_networks)`.

Contratos verificados (somente fonte estatica, sem device/simulador/hardware):

  1. `scan_wifi_networks` (funcao publica efetiva do fluxo de scan) deve
     existir e ter corpo extraivel (âncora nao-vazia).
  2. A limpeza da lista dentro de `scan_wifi_networks` deve usar
     `tab5_ui_obj_clean_deferred(...)` aplicada especificamente a
     `s_list_networks`.
  3. `scan_wifi_networks` NAO pode chamar `tab5_ui_obj_clean(...)`
     sincrono (nenhuma variante; a regex ignora `clean_deferred`).
  4. A limpeza deferida deve ocorrer ANTES do repopulate
     (`tab5_ui_list_add_btn`), encodando "limpar/repopular com seguranca
     durante callback" (nova populacao nunca apagada pelo clean).
  5. O repopulate (`tab5_ui_list_add_btn`) deve permanecer no fluxo
     (caminho positivo preservado, sem enfraquecimento).

Nota de contexto (registrada, NAO simulada aqui): a validacao device
anterior falhou ANTES do cenario porque `sys.info` retornou uma linha
JSON invalida; isso sera investigado separadamente e nao faz parte deste
contrato estatico.
"""

import re
import unittest
from pathlib import Path

APP_SRC = Path(__file__).resolve().parents[1] / "src" / "main.c"
SCAN_SIG = "static void scan_wifi_networks(void)"

# `\b` apos "clean" garante que "tab5_ui_obj_clean_deferred(" NAO case aqui:
# entre "n" e "_" nao ha word boundary (ambos sao word chars).
DEFERRED_RE = re.compile(r"\btab5_ui_obj_clean_deferred\s*\(")
DEFERRED_LIST_RE = re.compile(r"\btab5_ui_obj_clean_deferred\s*\(\s*s_list_networks\s*\)")
SYNC_CLEAN_RE = re.compile(r"\btab5_ui_obj_clean\s*\(")
REPOPULATE_RE = re.compile(r"\btab5_ui_list_add_btn\s*\(")


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


class WifiScanCleanDeferredContract(unittest.TestCase):
    """REQ: scan_wifi_networks deve limpar a lista com deferred (red hoje)."""

    @classmethod
    def setUpClass(cls):
        cls.src = _read(APP_SRC)
        cls.body = _function_body(cls.src, SCAN_SIG)

    def test_scan_wifi_networks_defined(self):
        """Anchor: scan_wifi_networks deve existir (guarda anti-vazia)."""
        self.assertIn(SCAN_SIG, self.src)

    def test_scan_list_clean_uses_deferred(self):
        """A limpeza da lista no scan DEVE usar tab5_ui_obj_clean_deferred.

        O SDK (WASM_ABI.md "Limpeza durante callbacks") proibe destruir
        sincronicamente o alvo enquanto o callback do evento ainda esta em
        execucao: a remocao dos filhos precisa ser deferida para o proximo
        ciclo do LVGL (mesma regra que o app Files ja segue em
        render_content com tab5_ui_obj_clean_deferred).
        """
        self.assertIsNotNone(
            DEFERRED_RE.search(self.body),
            "scan_wifi_networks deve limpar os filhos de s_list_networks com "
            "tab5_ui_obj_clean_deferred() (remocao deferida para o proximo "
            "ciclo do LVGL), conforme WASM_ABI.md 'Limpeza durante callbacks'",
        )
        self.assertIsNotNone(
            DEFERRED_LIST_RE.search(self.body),
            "o clean deferido de scan_wifi_networks deve ser aplicado "
            "especificamente a s_list_networks (a lista de redes do app)",
        )

    def test_scan_list_clean_is_not_synchronous(self):
        """scan_wifi_networks NAO pode chamar tab5_ui_obj_clean() sincrono.

        Clean sincrono remove/aloca os filhos durante o callback e deixa o
        alvo em estado invalido — a causa da lista 'Falha ao buscar redes'
        quando o scan e disparado pelo clique em 'Escanear Redes Proximas'.
        """
        self.assertIsNone(
            SYNC_CLEAN_RE.search(self.body),
            "scan_wifi_networks nao pode usar tab5_ui_obj_clean() sincrono; "
            "somente tab5_ui_obj_clean_deferred() e permitido no fluxo de "
            "scan (WASM_ABI.md: limpeza durante callbacks deve ser deferida)",
        )

    def test_scan_clean_precedes_repopulation(self):
        """A limpeza deferida deve ocorrer ANTES do repopulate da lista.

        Encoda 'limpar/repopular com seguranca durante callback': a nova
        populacao (tab5_ui_list_add_btn) nunca pode ser criada antes do
        clean, sob risco de ser apagada pela remocao postergada.
        """
        m_def = DEFERRED_RE.search(self.body)
        m_add = REPOPULATE_RE.search(self.body)
        self.assertIsNotNone(
            m_def,
            "a limpeza deferida deve existir para poder preceder o repopulate",
        )
        self.assertIsNotNone(
            m_add,
            "scan_wifi_networks deve repopular a lista (tab5_ui_list_add_btn) "
            "apos a limpeza — o fluxo continua exibindo redes",
        )
        self.assertLess(
            m_def.start(), m_add.start(),
            "scan_wifi_networks deve limpar (deferred) ANTES de repopular com "
            "tab5_ui_list_add_btn — populacao posterior nao pode ser apagada "
            "pelo clean deferido",
        )

    def test_scan_still_repopulates_list(self):
        """O repopulate deve permanecer no fluxo (caminho positivo preservado).

        Esta guarda impede que a correcao do clean remova acidentalmente o
        repopulate e deixe a lista vazia apos o scan.
        """
        self.assertIn(
            "tab5_ui_list_add_btn(",
            self.body,
            "scan_wifi_networks deve continuar adicionando redes a lista "
            "com tab5_ui_list_add_btn (resultados do scan exibidos)",
        )


class WifiScanCleanDeferredSelfCheck(unittest.TestCase):
    """Pureza dos checkers estaticos (verdes, independentes da implementacao)."""

    def test_deferred_regex_matches_deferred_call(self):
        self.assertIsNotNone(
            DEFERRED_RE.search("tab5_ui_obj_clean_deferred(s_list_networks);")
        )
        self.assertIsNotNone(
            DEFERRED_LIST_RE.search("tab5_ui_obj_clean_deferred(s_list_networks);")
        )

    def test_sync_regex_does_not_match_deferred_call(self):
        """'clean_deferred' NAO pode ser confundida com clean sincrono."""
        self.assertIsNone(
            SYNC_CLEAN_RE.search("tab5_ui_obj_clean_deferred(s_list_networks);"),
            "o checker de clean sincrono deve ignorar tab5_ui_obj_clean_deferred",
        )

    def test_sync_regex_matches_sync_call(self):
        self.assertIsNotNone(
            SYNC_CLEAN_RE.search("tab5_ui_obj_clean(s_list_networks);")
        )

    def test_sync_regex_is_whitespace_tolerant(self):
        self.assertIsNotNone(
            SYNC_CLEAN_RE.search("tab5_ui_obj_clean (\n    s_list_networks );")
        )

    def test_deferred_regex_ignores_other_apis(self):
        """APIs vizinhas (clear_content, clean de outros args) nao casam."""
        self.assertIsNone(DEFERRED_RE.search("tab5_ui_clear_content();"))
        self.assertIsNone(DEFERRED_RE.search("tab5_ui_obj_clean(s_other);"))

    def test_repopulate_regex_matches_add_btn(self):
        self.assertIsNotNone(
            REPOPULATE_RE.search(
                "tab5_ui_obj_t btn = tab5_ui_list_add_btn(s_list_networks, "
                "LV_SYMBOL_WIFI, label_buf);"
            )
        )

    def test_red_condition_is_discriminant(self):
        """Um corpo com clean sincrono NAO satisfaz o contrato (red real).

        Garante que o novo contrato discrimina o bug: se o corpo contem
        apenas tab5_ui_obj_clean (estado atual), a presenca do deferred
        falha e o sincrono e detectado — o teste nao e vacuo.
        """
        buggy_body = "    tab5_ui_obj_clean(s_list_networks);\n    s_ap_count = 0;\n"
        self.assertIsNone(
            DEFERRED_RE.search(buggy_body),
            "corpo com clean sincrono nao deve conter o clean deferido",
        )
        self.assertIsNotNone(
            SYNC_CLEAN_RE.search(buggy_body),
            "corpo com clean sincrono deve ser detectado pelo checker",
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)