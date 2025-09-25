# -*- coding: utf-8 -*-
import streamlit as st
from datetime import datetime, timedelta
import pandas as pd
import os
import pickle

# Google Calendar
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

# Se alterar esses SCOPES, apague o arquivo token.pickle.
SCOPES = ['https://www.googleapis.com/auth/calendar'] 
CREDENTIALS_FILE = 'credentials.json'
TOKEN_FILE = 'token.pickle'
API_SERVICE_NAME = 'calendar'
API_VERSION = 'v3'

# ========== Função para obter o serviço da API do Google Calendar ==========
def get_google_calendar_service():
    """Realiza a autenticação e retorna o objeto de serviço da API do Google Calendar."""
    creds = None
    
    # O arquivo token.pickle armazena os tokens do usuário e é criado automaticamente.
    if os.path.exists(TOKEN_FILE):
        with open(TOKEN_FILE, 'rb') as token:
            creds = pickle.load(token)

    # Se não houver credenciais válidas, permite que o usuário faça login.
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not os.path.exists(CREDENTIALS_FILE):
                st.error("❌ Arquivo 'credentials.json' não encontrado. Por favor, coloque-o na mesma pasta do script.")
                return None
                
            flow = InstalledAppFlow.from_client_secrets_file(CREDENTIALS_FILE, SCOPES)
            creds = flow.run_local_server(port=0) 

        # Salva as credenciais para a próxima execução
        with open(TOKEN_FILE, 'wb') as token:
            pickle.dump(creds, token)
            
    if creds:
        try:
            service = build(API_SERVICE_NAME, API_VERSION, credentials=creds)
            return service
        except Exception as e:
            st.error(f"Erro ao construir o serviço da API: {e}")
            return None
    return None

# ========== Função para criar evento no Google Calendar ==========
def criar_evento_google_calendar(service, info_evento):
    """Cria um evento no Google Calendar usando o serviço autenticado."""
    evento = {
        'summary': f"{info_evento['tipo_servico']} - {info_evento['cliente']}",
        'location': info_evento['local'],
        'description': f"Valor total: R${info_evento['valor_total']:.2f}\n"
                       f"Entrada: R${info_evento['valor_entrada']:.2f}\n"
                       f"Forma de pagamento: {info_evento['forma_pagamento']}\n",
        'start': {
            'dateTime': info_evento['data_hora'].isoformat(),
            'timeZone': 'America/Sao_Paulo',
        },
        'end': {
            'dateTime': (info_evento['data_hora'] + timedelta(minutes=info_evento['duracao'])).isoformat(),
            'timeZone': 'America/Sao_Paulo',
        },
    }

    try:
        calendar_id = 'primary'
        evento_criado = service.events().insert(calendarId=calendar_id, body=evento).execute()
        return evento_criado.get('htmlLink')
    except HttpError as error:
        st.error(f"Erro na API do Google Calendar: {error}")
        return None
    except Exception as e:
        st.error(f"Ocorreu um erro: {e}")
        return None

# ========== App Streamlit ==========
st.set_page_config(page_title="Sistema de Agendamentos", layout="centered")
st.title("📅 Sistema de Agendamento com Google Calendar")

# Tenta obter o serviço autenticado
service = get_google_calendar_service()

if service:
    with st.form("form_agendamento"):
        st.subheader("Informações do Agendamento")
        cliente = st.text_input("👤 Nome do Cliente")
        tipo_servico = st.selectbox("🛠 Tipo de Serviço", ["Fotos", "Consultoria", "Outro"])
        
        duracao = 0
        if tipo_servico == "Fotos":
            quantidade_fotos = st.number_input("📷 Quantidade de Fotos", min_value=1, step=1, key="fotos_input")
            duracao = quantidade_fotos * 5
        else:
            duracao = st.number_input("⏱ Duração do Serviço (minutos)", min_value=15, step=15, key="duracao_input")
        
        local = st.text_input("📍 Local")
        data = st.date_input("📆 Data")
        hora = st.time_input("⏰ Horário")
    
        st.subheader("Informações Financeiras")
        valor_total = st.number_input("💰 Valor Total (R$)", min_value=0.0, step=10.0)
        
        entrada = st.checkbox("✅ Houve entrada de dinheiro?")
        valor_entrada = 0.0
        forma_pagamento = ""
        if entrada:
            valor_entrada = st.number_input("💵 Valor da Entrada (R$)", min_value=0.0, max_value=valor_total, step=10.0, key="entrada_input")
            forma_pagamento = st.selectbox("💳 Forma de Pagamento", ["Pix", "Dinheiro", "Cartão", "Transferência", "Outro"], key="pagamento_input")
    
        submitted = st.form_submit_button("Agendar")
    
    # ========== Processamento ==========
    if submitted:
        if not cliente:
            st.error("O campo 'Nome do Cliente' é obrigatório.")
        elif not local:
            st.error("O campo 'Local' é obrigatório.")
        else:
            data_hora = datetime.combine(data, hora)
    
            dados = {
                "cliente": cliente,
                "tipo_servico": tipo_servico,
                "duracao": duracao,
                "local": local,
                "data_hora": data_hora,
                "valor_total": valor_total,
                "valor_entrada": valor_entrada,
                "forma_pagamento": forma_pagamento
            }
    
            link_evento = criar_evento_google_calendar(service, dados)
            if link_evento:
                st.success("✅ Agendamento criado com sucesso no Google Calendar!")
                st.markdown(f"[📅 Ver no Google Calendar]({link_evento})")
    
                # Salvar em CSV
                linha = {
                    "Data e Hora": data_hora.strftime("%Y-%m-%d %H:%M"),
                    "Cliente": cliente,
                    "Serviço": tipo_servico,
                    "Duração (min)": duracao,
                    "Local": local,
                    "Valor Total": valor_total,
                    "Entrada": valor_entrada,
                    "Forma de Pagamento": forma_pagamento,
                    "Link do Evento": link_evento
                }
    
                arquivo_csv = "agendamentos.csv"
                if os.path.exists(arquivo_csv):
                    df_existente = pd.read_csv(arquivo_csv)
                    df_novo = pd.concat([df_existente, pd.DataFrame([linha])], ignore_index=True)
                else:
                    df_novo = pd.DataFrame([linha])
    
                df_novo.to_csv(arquivo_csv, index=False)
else:
    st.warning("Autenticação com o Google Calendar pendente. Por favor, siga as instruções para autorizar o acesso.")
