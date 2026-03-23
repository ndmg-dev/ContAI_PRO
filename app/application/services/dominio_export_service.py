import io
import csv
from datetime import datetime

class DominioExportService:
    """
    Gera arquivos no layout de importação do Domínio Sistemas (Separador).
    Campos padrão: Data;Conta Débito;Conta Crédito;Valor;Cód. Histórico;Complemento
    """
    
    @staticmethod
    def generate_txt(lancamentos_conciliados):
        """
        Recebe uma lista de objetos 'lancamento' e gera um buffer de texto.
        """
        output = io.StringIO()
        
        # O Domínio aceita diversos layouts, vamos usar um padrão de 6 colunas com ponto e vírgula
        # Layout: Data(10);Conta_Debito(10);Conta_Credito(10);Valor(15);Cod_Hist(5);Complemento(255)
        
        for lanc in lancamentos_conciliados:
            # Formata data: 2026-03-18 -> 18/03/2026
            dt = lanc.get('data_lancamento', '')
            if isinstance(dt, str) and '-' in dt:
                dt_obj = datetime.strptime(dt, '%Y-%m-%d')
                dt_str = dt_obj.strftime('%d/%m/%Y')
            else:
                dt_str = dt
            
            valor = f"{float(lanc.get('valor', 0)):.2f}".replace('.', ',')
            historico = lanc.get('historico', 'Lançamento via ContAI').upper()
            
            # Contas
            plano = lanc.get('plano_contas')
            conta_definida = plano.get('codigo') if (plano and isinstance(plano, dict)) else "999"

            if str(lanc.get('tipo_dc')).lower() == 'debito':
                conta_d = conta_definida 
                conta_c = "1.1.01.001" # Banco (Ativo)
            else:
                conta_d = "1.1.01.001" # Banco (Ativo)
                conta_c = conta_definida

            cod_hist = "800" # Código genérico de histórico
            
            linha = f"{dt_str};{conta_d};{conta_c};{valor};{cod_hist};{historico}\r\n"
            output.write(linha)
            
        return output.getvalue()
