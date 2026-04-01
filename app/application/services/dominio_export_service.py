"""
Domínio Export Service
======================
Gera arquivos no layout posicional de largura fixa do Domínio Sistemas,
compatível com o padrão de importação (arquivo referência: (521) Dominio.txt).

Estrutura dos Registros
-----------------------
Tipo 01 – Cabeçalho do arquivo (1 linha)
    Pos  1-2   : "01"
    Pos  3-7   : Código do banco (5 dígitos)
    Pos  8-21  : CNPJ da empresa (14 dígitos, sem formatação)
    Pos 22-29  : Data inicial do período (DDMMAAAA)
    Pos 30-37  : Data final do período   (DDMMAAAA)
    Pos 38     : "N"
    Pos 39-40  : Número sequencial do arquivo (2 dígitos)
    Pos 41-48  : Total de linhas do arquivo (8 dígitos)

Tipo 02 – Cabeçalho de lote (1 linha por grupo de data)
    Pos  1-2   : "02"
    Pos  3-8   : Sequência (6 dígitos, ímpar)
    Pos  9     : "X"
    Pos 10-17  : Data do lote (DDMMAAAA)
    Pos 18-97  : Nome do operador (80 chars, espaço à direita)

Tipo 03 – Transação
    Pos  1-2   : "03"
    Pos  3-8   : Sequência (6 dígitos, par)
    Pos  9-14  : Código da conta (6 dígitos)
    Pos 15-18  : Código do banco da conta (4 dígitos)
    Pos 19-22  : Indicador D/C (4 dígitos: 0008=débito, 5190=crédito)
    Pos 23-35  : Valor em centavos (13 dígitos, sem separador)
    Pos 36-42  : Espaços (7)
    Pos 43-45  : Código do histórico (3 dígitos)
    Pos 46     : Espaço
    Pos 47-...  : Descrição (complemento histórico, padded com espaços)
    Últimos 7  : "0000000"

Tipo 9 – Trailer
    Linha de 9s (100 chars)
"""
import io
import os
from datetime import datetime
from itertools import groupby


# ─── Constantes de layout ────────────────────────────────────────────────────

_BANK_COD        = "00052"          # Código do banco padrão (Santander = 00033, genérico = 00052)
_OPERATOR_NAME   = "CONTAI"         # Nome do operador/usuário exportador
_COD_HISTORICO   = "800"            # Código genérico de histórico no Domínio
_CONTA_BANCO     = "000008"         # Código da conta bancária no plano (ativo circulante)
_BANK_REF        = "0000"           # Código do banco de referência na linha 03
_DC_DEBITO       = "0008"           # Indicador de débito (saída)
_DC_CREDITO      = "5190"           # Indicador de crédito (entrada)
_DESC_TOTAL_LEN  = 512              # Tamanho do campo descrição + zeros finais
_ZEROS_TRAILER   = "0000000"        # Sufixo dos registros de transação
_TRAILER_LINE    = "9" * 100        # Linha de encerramento


# ─── Helpers ─────────────────────────────────────────────────────────────────

def _fmt_date_short(dt_str: str) -> str:
    """'2025-01-03' → '03/01/2025'"""
    if isinstance(dt_str, str) and "-" in dt_str:
        d = datetime.strptime(dt_str[:10], "%Y-%m-%d")
        return d.strftime("%d/%m/%Y")
    return dt_str or ""


def _fmt_date_compact(dt_str: str) -> str:
    """'2025-01-03' → '03012025'"""
    if isinstance(dt_str, str) and "-" in dt_str:
        d = datetime.strptime(dt_str[:10], "%Y-%m-%d")
        return d.strftime("%d%m%Y")
    return (dt_str or "").replace("/", "")


def _valor_centavos(valor) -> str:
    """Converte float para string de 13 dígitos em centavos sem separador."""
    try:
        cents = round(float(valor or 0) * 100)
    except (TypeError, ValueError):
        cents = 0
    return str(abs(cents)).zfill(13)


def _conta_codigo(lanc: dict) -> str:
    """Retorna o código da conta do plano de contas (6 dígitos)."""
    plano = lanc.get("plano_contas")
    if plano and isinstance(plano, dict):
        cod = str(plano.get("codigo", "999")).replace(".", "")
    else:
        cod = "999"
    # Remove pontos e garante 6 dígitos
    return cod.zfill(6)[:6]


def _sort_key(lanc: dict) -> str:
    return (lanc.get("data_lancamento") or "1900-01-01")[:10]


# ─── Gerador principal ────────────────────────────────────────────────────────

class DominioExportService:
    """
    Gera arquivos no layout posicional de largura fixa do Domínio Sistemas.
    Compatível com o padrão do arquivo (521) Dominio.txt.
    """

    @staticmethod
    def generate_txt(lancamentos_conciliados: list, empresa: dict = None) -> str:
        """
        Recebe uma lista de lançamentos conciliados e gera o texto do arquivo
        no layout posicional do Domínio.

        Args:
            lancamentos_conciliados: lista de dicts de lançamentos.
            empresa: dict opcional com 'cnpj' e 'nome' da empresa exportadora.

        Returns:
            str com o conteúdo do arquivo pronto para download.
        """
        if not lancamentos_conciliados:
            return ""

        empresa = empresa or {}
        cnpj_raw = re.sub(r"\D", "", empresa.get("cnpj", "00000000000000"))
        cnpj = cnpj_raw.zfill(14)[:14]

        # Ordena por data para agrupar corretamente
        sorted_lancs = sorted(lancamentos_conciliados, key=_sort_key)

        # Calcula datas início/fim para o cabeçalho
        datas = [_sort_key(l) for l in sorted_lancs if _sort_key(l) != "1900-01-01"]
        dt_ini = _fmt_date_compact(min(datas)) if datas else "01012000"
        dt_fim = _fmt_date_compact(max(datas)) if datas else "31122000"

        linhas_corpo = []  # Vai receber as linhas tipo 02 e 03 antes de contar
        seq = 1            # Contador de sequência global (sempre ímpar para 02, par para 03)

        # Agrupa por data
        for data_key, grupo in groupby(sorted_lancs, key=_sort_key):
            grupo_list = list(grupo)

            # ── Tipo 02: Cabeçalho de lote ──────────────────────────────────
            seq_02 = str(seq).zfill(6)
            data_compact = _fmt_date_compact(data_key)
            operator = _OPERATOR_NAME.ljust(80)[:80]
            linha_02 = f"02{seq_02}X{data_compact}{operator}"
            linhas_corpo.append(linha_02)
            seq += 1

            # ── Tipo 03: Transações ─────────────────────────────────────────
            for lanc in grupo_list:
                seq_03 = str(seq).zfill(6)
                conta_cod = _conta_codigo(lanc)
                valor_str = _valor_centavos(lanc.get("valor", 0))

                tipo_dc = str(lanc.get("tipo_dc", "debito")).lower()
                if tipo_dc == "debito":
                    dc_flag   = _DC_DEBITO
                    conta_d   = conta_cod
                    conta_c   = _CONTA_BANCO
                else:
                    dc_flag   = _DC_CREDITO
                    conta_d   = _CONTA_BANCO
                    conta_c   = conta_cod

                # Campo descrição: complemento do histórico (padded/truncated)
                historico = (lanc.get("historico") or "LANCAMENTO CONTAI").upper()
                # Calcula padding: o restante da linha após os campos fixos
                # Campos fixos até aqui: "03"(2) + seq(6) + conta(6) + bank(4) + dc(4) + valor(13) + spaces(7) + cod_hist(3) + space(1) = 46 chars
                # Descrição + "0000000" deve ter _DESC_TOTAL_LEN chars
                desc_max = _DESC_TOTAL_LEN - len(_ZEROS_TRAILER)
                desc_padded = historico[:desc_max].ljust(desc_max)

                linha_03 = (
                    f"03"
                    f"{seq_03}"
                    f"{conta_cod}"
                    f"{_BANK_REF}"
                    f"{dc_flag}"
                    f"{valor_str}"
                    f"       "           # 7 espaços
                    f"{_COD_HISTORICO}"
                    f" "
                    f"{desc_padded}"
                    f"{_ZEROS_TRAILER}"
                )
                linhas_corpo.append(linha_03)
                seq += 1

        # Total de linhas = 1 (header) + corpo + 1 (trailer)
        total_linhas = 1 + len(linhas_corpo) + 1

        # ── Tipo 01: Cabeçalho do arquivo ────────────────────────────────────
        seq_arquivo = "05"   # Número sequencial do arquivo (fixo/padrão)
        header = (
            f"01"
            f"{_BANK_COD}"
            f"{cnpj}"
            f"{dt_ini}"
            f"{dt_fim}"
            f"N"
            f"{seq_arquivo}"
            f"{str(total_linhas).zfill(8)}"
        )

        # ── Monta arquivo final ──────────────────────────────────────────────
        output = io.StringIO()
        output.write(header + "\r\n")
        for linha in linhas_corpo:
            output.write(linha + "\r\n")
        output.write(_TRAILER_LINE + "\r\n")

        return output.getvalue()


# Importação de re necessária para limpeza do CNPJ
import re
