import os
import pandas as pd
from fpdf import FPDF
from datetime import datetime, timedelta
import random

# Definindo transacoes que serao identicas para garantir a conciliacao
TRANSACOES_PARA_CONCILIAR = [
    {"data": "05/11/2025", "hist": "PAGAMENTO FORNECEDOR ALFA", "valor": 1250.00, "tipo": "debito"},
    {"data": "10/11/2025", "hist": "RECEBIMENTO CLIENTE BETA", "valor": 3400.00, "tipo": "credito"},
    {"data": "15/11/2025", "hist": "TARIFA MENSAL CONTA", "valor": 45.90, "tipo": "debito"},
    {"data": "20/11/2025", "hist": "RESGATE APLICACAO", "valor": 5000.00, "tipo": "credito"},
    {"data": "25/11/2025", "hist": "PAGAMENTO ENERGIA ELETRICA", "valor": 890.30, "tipo": "debito"},
]

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
    
    # 1. Adiciona as transacoes de conciliacao
    for txn in TRANSACOES_PARA_CONCILIAR:
        txt_vlr = f"{'+' if txn['tipo'] == 'credito' else '-'}{txn['valor']:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
        pdf.cell(30, 8, txn['data'], border=1)
        pdf.cell(120, 8, txn['hist'], border=1)
        pdf.cell(40, 8, txt_vlr, border=1, ln=True)

    # 2. Adiciona algumas extras (excecoes)
    data_base = datetime(2025, 11, 2)
    for i in range(5):
        dt = (data_base + timedelta(days=i*4)).strftime("%d/%m/%Y")
        hist = f"OUTRA OPERACAO BANCARIA {i+1}"
        vlr = round(random.uniform(100, 500), 2)
        pdf.cell(30, 8, dt, border=1)
        pdf.cell(120, 8, hist, border=1)
        pdf.cell(40, 8, f"-{vlr:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."), border=1, ln=True)
        
    pdf.ln(10)
    pdf.cell(190, 10, "Saldo Final: R$ 12.450,32", align="R")
    pdf.output(filename)
    print(f"PDF {filename} gerado com transacoes para conciliar.")

def create_xlsx_movimentacao(filename):
    data = {
        'Data': [],
        'Historico': [],
        'Documento': [],
        'Valor': []
    }
    
    # 1. Adiciona as mesmas transacoes de conciliacao (com historico levemente diferente mas valor/data iguais)
    for txn in TRANSACOES_PARA_CONCILIAR:
        data['Data'].append(txn['data'])
        data['Historico'].append(txn['hist'] + " (REF NF-100)")
        data['Documento'].append(f"NF-{random.randint(1000,9999)}")
        # Inverte o sinal para o Excel pois as vezes o Excel contabilidade usa + p/ debito e - p/ credito? 
        # Nao, vamos manter igual ao banco para o parser encontrar
        vlr = txn['valor'] if txn['tipo'] == 'credito' else -txn['valor']
        data['Valor'].append(vlr)

    # 2. Adiciona algumas extras no Excel que nao estao no banco (excecoes do outro lado)
    data_base = datetime(2025, 11, 3)
    for i in range(5):
        data['Data'].append((data_base + timedelta(days=i*5)).strftime("%d/%m/%Y"))
        data['Historico'].append(f"LANCAMENTO APENAS CONTABIL {i+1}")
        data['Documento'].append(f"DOC-{2000+i}")
        data['Valor'].append(round(random.uniform(500, 1000), 2))
            
    df = pd.DataFrame(data)
    df.to_excel(filename, index=False)
    print(f"XLSX {filename} gerado com transacoes para conciliar.")

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
    # Contas especificas para os historicos que geramos acima
    contas = [
        ("1", "ATIVO", "SINTETICA", "ATIVO"),
        ("1.1.01.001", "CAIXA GERAL", "ANALITICA", "ATIVO"),
        ("1.1.01.005", "BANCO ITAU S/A", "ANALITICA", "ATIVO"),
        ("2", "PASSIVO", "SINTETICA", "PASSIVO"),
        ("2.1.03.001", "FORNECEDORES DIVERSOS", "ANALITICA", "PASSIVO"),
        ("3.1.01.001", "RECEITA DE VENDAS", "ANALITICA", "RECEITA"),
        ("4.1.01.001", "DESPESA COM ENERGIA", "ANALITICA", "DESPESA"),
        ("4.1.01.005", "TARIFAS BANCARIAS", "ANALITICA", "DESPESA"),
    ]
    
    for cod, nome, tipo, nat in contas:
        tipo_contabil = "DEBITO" if nat in ["ATIVO", "DESPESA"] else "CREDITO"
        pdf.cell(40, 8, cod, border=1)
        pdf.cell(100, 8, nome, border=1)
        pdf.cell(25, 8, tipo_contabil, border=1)
        pdf.cell(25, 8, nat, border=1, ln=True)
        
    pdf.output(filename)
    print(f"PDF {filename} gerado.")

if __name__ == "__main__":
    # Create files in the same directory as the script
    base_dir = os.path.dirname(__file__)
    create_pdf_extrato(os.path.join(base_dir, "extrato_bancario_exemplo.pdf"))
    create_xlsx_movimentacao(os.path.join(base_dir, "movimentacao_contabil_exemplo.xlsx"))
    create_pdf_plano_contas(os.path.join(base_dir, "plano_contas_exemplo.pdf"))
