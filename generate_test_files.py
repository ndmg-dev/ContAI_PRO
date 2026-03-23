import os
import pandas as pd
from fpdf import FPDF
from datetime import datetime, timedelta
import random

def create_pdf_extrato(filename):
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", "B", 16)
    pdf.cell(190, 10, "EXTRATO BANCARIO - CONTA CORRENTE", ln=True, align="C")
    pdf.set_font("Arial", "", 12)
    pdf.cell(190, 10, "Cliente: EMPRESA TESTE LTDA", ln=True)
    pdf.cell(190, 10, "Periodo: 01/11/2025 a 30/11/2025", ln=True)
    pdf.ln(10)
    
    # Headers
    pdf.set_font("Arial", "B", 10)
    pdf.cell(30, 8, "Data", border=1)
    pdf.cell(120, 8, "Historico", border=1)
    pdf.cell(40, 8, "Valor (R$)", border=1, ln=True)
    
    pdf.set_font("Arial", "", 10)
    data_base = datetime(2025, 11, 1)
    for i in range(15):
        dt = (data_base + timedelta(days=i*2)).strftime("%d/%m/%Y")
        hist = random.choice(["PAGAMENTO FORNECEDOR", "RECEBIMENTO CLIENTE", "TARIFA BANCARIA", "RESGATE INVESTIMENTO", "DOC/TED ENVIADO"])
        vlr = round(random.uniform(50, 2500), 2)
        if "RECEBIMENTO" in hist or "RESGATE" in hist:
            txt_vlr = f"+{vlr:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
        else:
            txt_vlr = f"-{vlr:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
            
        pdf.cell(30, 8, dt, border=1)
        pdf.cell(120, 8, hist, border=1)
        pdf.cell(40, 8, txt_vlr, border=1, ln=True)
        
    pdf.ln(10)
    pdf.cell(190, 10, "Saldo Final: R$ 12.450,32", align="R")
    pdf.output(filename)
    print(f"PDF {filename} gerado.")

def create_xlsx_movimentacao(filename):
    data = {
        'Data': [],
        'Historico': [],
        'Documento': [],
        'Valor': []
    }
    data_base = datetime(2025, 11, 1)
    for i in range(10):
        data['Data'].append((data_base + timedelta(days=i*3)).strftime("%d/%m/%Y"))
        data['Historico'].append(random.choice(["NOTA FISCAL 102", "RECIBO ALUGUEL", "DESPESA VIAGEM", "Venda de Servicos"]))
        data['Documento'].append(f"DOC-{1000+i}")
        # Valores positivos e negativos
        vlr = round(random.uniform(100, 3000), 2)
        if i % 3 == 0:
            data['Valor'].append(vlr)
        else:
            data['Valor'].append(-vlr)
            
    df = pd.DataFrame(data)
    df.to_excel(filename, index=False)
    print(f"XLSX {filename} gerado.")

def create_pdf_plano_contas(filename):
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Helvetica", "B", 14)
    pdf.cell(190, 10, "PLANO DE CONTAS - LAYOUT DOMINIO", ln=True, align="C")
    pdf.ln(5)
    
    pdf.set_font("Helvetica", "B", 10)
    pdf.cell(40, 8, "Classificacao", border=1)
    pdf.cell(100, 8, "Nome da Conta", border=1)
    pdf.cell(25, 8, "Tipo", border=1)
    pdf.cell(25, 8, "Natureza", border=1, ln=True)
    
    pdf.set_font("Helvetica", "", 9)
    contas = [
        ("1", "ATIVO", "SINTETICA", "ATIVO"),
        ("1.1", "CIRCULANTE", "SINTETICA", "ATIVO"),
        ("1.1.01", "DISPONIBILIDADES", "SINTETICA", "ATIVO"),
        ("1.1.01.001", "CAIXA GERAL", "ANALITICA", "ATIVO"),
        ("1.1.01.005", "BANCO ITAU S/A", "ANALITICA", "ATIVO"),
        ("1.1.03", "CLIENTES", "SINTETICA", "ATIVO"),
        ("1.1.03.001", "CLIENTES NACIONAIS", "ANALITICA", "ATIVO"),
        ("2", "PASSIVO", "SINTETICA", "PASSIVO"),
        ("2.1", "CIRCULANTE", "SINTETICA", "PASSIVO"),
        ("2.1.03", "FORNECEDORES", "SINTETICA", "PASSIVO"),
        ("2.1.03.001", "FORNECEDORES DIVERSOS", "ANALITICA", "PASSIVO"),
        ("3", "RECEITAS", "SINTETICA", "RECEITA"),
        ("3.1", "RECEITA BRUTA", "SINTETICA", "RECEITA"),
        ("3.1.01", "VENDAS DE MERCADORIAS", "ANALITICA", "RECEITA"),
        ("4", "DESPESAS", "SINTETICA", "DESPESA"),
        ("4.1", "DESPESAS ADMINISTRATIVAS", "SINTETICA", "DESPESA"),
        ("4.1.01", "ALUGUEIS E TAXAS", "ANALITICA", "DESPESA"),
    ]
    
    for cod, nome, tipo, nat in contas:
        # Note: IA do sistema busca "DEBITO"/"CREDITO" baseado na natureza se o PDF não tiver
        # Mas vamos seguir o layout que a IA espera
        # Analitica = Debito (se Ativo/Despesa) ou Credito (se Passivo/Receita)
        tipo_contabil = "DEBITO" if nat in ["ATIVO", "DESPESA"] else "CREDITO"
        
        pdf.cell(40, 8, cod, border=1)
        pdf.cell(100, 8, nome, border=1)
        pdf.cell(25, 8, tipo_contabil, border=1)
        pdf.cell(25, 8, nat, border=1, ln=True)
        
    pdf.output(filename)
    print(f"PDF {filename} gerado.")

if __name__ == "__main__":
    create_pdf_extrato("extrato_bancario_exemplo.pdf")
    create_xlsx_movimentacao("movimentacao_contabil_exemplo.xlsx")
    create_pdf_plano_contas("plano_contas_exemplo.pdf")
