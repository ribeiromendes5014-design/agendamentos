# -*- coding: utf-8 -*-
import streamlit as st
from datetime import datetime, timedelta
import pandas as pd
import os
import json
import pytz
import requests

# Google Calendar
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

# Escopo para acessar o Google Calendar
SCOPES = ['https://www.googleapis.com/auth/calendar']

# --- Configurações do Telegram ---
# Recomenda-se mover para o st.secrets
TELEGRAM_TOKEN = st.secrets.get("TELEGRAM_TOKEN", "YOUR_TELEGRAM_TOKEN_HERE")
TELEGRAM_CHAT_ID = st.secrets.get("TELEGRAM_CHAT_ID", "YOUR_CHAT_ID_HERE")
TOPICO_ID = 64  # ID do tópico (thread) no grupo Telegram


def get_google_calendar_service():
    """Autentica usando a conta de serviço do secrets e retorna o serviço do Google Calendar."""
    try:
        service_account_info = st.secrets["google_service_account"]
        if isinstance(service_account_info, str):
            service_account_info = json.loads(service_account_info)
        creds = service_account.Credentials.from_service_account_info(
            service_account_info, scopes=SCOPES)
        service = build('calendar', 'v3', credentials=creds)
        return service
    except Exception as e:
        st.error(f"Erro ao autenticar com a conta de serviço: {e}")
        return None


def criar_evento_google_calendar(service, info_evento):
    """Cria um evento no Google Calendar com as informações fornecidas."""
    tz = pytz.timezone('America/Sao_Paulo')
    data_hora_inicio_aware = tz.localize(info_evento['data_hora_inicio'])
    data_hora_fim_aware = tz.localize(info_evento['data_hora_fim'])

    reminders_list = [{'method': 'popup', 'minutes': m} for m in info_evento['lembretes_minutos']]
    reminders = {'useDefault': False, 'overrides': reminders_list}

    local = info_evento['local']
    if info_evento['endereco']:
        local = f"{info_evento['local']} ({info_evento['endereco']})"

    evento = {
        'summary': f"{info_evento['tipo_servico']} - {info_evento['cliente']}",
        'location': local,
        'description': (f"Valor total: R${info_evento['valor_total']:.2f}\n"
                        f"Entrada: R${info_evento['valor_entrada']:.2f}\n"
                        f"Forma de pagamento: {info_evento['forma_pagamento']}\n"),
        'start': {'dateTime': data_hora_inicio_aware.isoformat(), 'timeZone': 'America/Sao_Paulo'},
        'end': {'dateTime': data_hora_fim_aware.isoformat(), 'timeZone': 'America/Sao_Paulo'},
        'reminders': reminders,
    }

    try:
        calendar_id = 'ribeiromendes5016@gmail.com'
        evento_criado = service.events().insert(calendarId=calendar_id, body=evento).execute()
        return evento_criado.get('htmlLink')
    except HttpError as error:
        st.error(f"Erro na API do Google Calendar: {error}")
        return None
    except Exception as e:
        st.error(f"Ocorreu um erro: {e}")
        return None


def enviar_mensagem_telegram_agendamento(cliente, data, hora, valor_total, valor_entrada, tipo_servico):
    """Envia uma mensagem formatada para um grupo do Telegram."""
    mensagem = (
        f"📅 *Novo Agendamento Realizado!*\n\n"
        f"👤 *Cliente:* {cliente}\n"
        f"🛠 *Serviço:* {tipo_servico}\n"
        f"📆 *Data:* {data.strftime('%d/%m/%Y')}\n"
        f"⏰ *Horário:* {hora.strftime('%H:%M')}\n"
        f"💰 *Valor Total:* R$ {valor_total:,.2f}".replace(',', 'X').replace('.', ',').replace('X', '.') + "\n"
        f"💵 *Entrada:* R$ {valor_entrada:,.2f}".replace(',', 'X').replace('.', ',').replace('X', '.')
    )
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": mensagem, "parse_mode": "Markdown", "message_thread_id": TOPICO_ID}
    response = requests.post(url, data=payload)
    if response.status_code != 200:
        st.error(f"Erro ao enviar mensagem para o Telegram: {response.json()}")
    else:
        st.success("📨 Mensagem de confirmação enviada para o grupo do Telegram!")


# --- App Streamlit ---
st.set_page_config(page_title="Sistema de Agendamentos", layout="centered")
st.title("📅 Sistema de Agendamento com Google Calendar")

service = get_google_calendar_service()

if service:
    st.subheader("Informações do Agendamento")
    cliente = st.text_input("👤 Nome do Cliente")
    tipo_servico = st.text_input("🛠 Tipo de Serviço (ex: Sessão de Fotos, Consultoria)")
    local = st.text_input("📍 Local")
    endereco = st.text_input("Endereço completo (opcional)")
    st.markdown("---")

    metodo_termino = st.radio(
        "Como deseja definir o término do evento?",
        ('Definir Duração', 'Manualmente'),
        horizontal=True,
        index=0
    )
    
    col1, col2 = st.columns(2)
    with col1:
        data_inicio = st.date_input("📆 Data de Início")
        hora_inicio = st.time_input("⏰ Horário de Início")
    
    data_hora_fim = None  # Inicializa a variável

    if metodo_termino == 'Manualmente':
        with col2:
            data_fim_input = st.date_input("📆 Data de Fim")
            hora_fim_input = st.time_input("⏰ Horário de Fim")
            if data_fim_input and hora_fim_input:
                data_hora_fim = datetime.combine(data_fim_input, hora_fim_input)
    else:  # 'Definir Duração'
        with col2:
            # --- MUDANÇA: min_value alterado para 1 ---
            duracao_minutos = st.number_input("⏳ Duração (em minutos)", min_value=1, value=60, step=1)
            if data_inicio and hora_inicio:
                data_hora_inicio_preview = datetime.combine(data_inicio, hora_inicio)
                data_hora_fim_preview = data_hora_inicio_preview + timedelta(minutes=duracao_minutos)
                st.markdown(f"**Término calculado:** {data_hora_fim_preview.strftime('%d/%m/%Y às %H:%M')}")
                data_hora_fim = data_hora_fim_preview

    st.markdown("---")
    st.subheader("Lembretes")
    lembrete_opcoes = {
        "15 minutos antes": 15, "30 minutos antes": 30, "1 hora antes": 60,
        "2 horas antes": 120, "1 dia antes": 1440
    }
    lembretes_selecionados = st.multiselect("🔔 Quero ser alertado:", list(lembrete_opcoes.keys()), default=["15 minutos antes"])
    lembretes_minutos = [lembrete_opcoes[l] for l in lembretes_selecionados]
    
    st.markdown("---")
    st.subheader("Informações Financeiras")
    valor_total = st.number_input("💰 Valor Total (R$)", min_value=0.0, value=100.0, step=10.0, format="%.2f")
    
    entrada = st.checkbox("✅ Houve entrada de dinheiro?")
    valor_entrada_input = 0.0
    forma_pagamento_input = "Não houve entrada"
    if entrada:
        valor_entrada_input = st.number_input("💵 Valor da Entrada (R$)", min_value=0.0, max_value=valor_total, step=10.0, format="%.2f")
        forma_pagamento_input = st.selectbox("💳 Forma de Pagamento", ["Pix", "Dinheiro", "Cartão", "Transferência", "Outro"])

    st.markdown("---")
    submitted = st.button("Agendar Evento", type="primary")
    
    if submitted:
        data_hora_inicio = datetime.combine(data_inicio, hora_inicio)
        
        if data_hora_fim is None:
            st.error("Por favor, defina um horário de término válido.")
            st.stop()

        valor_entrada = valor_entrada_input if entrada else 0.0
        forma_pagamento = forma_pagamento_input if entrada else "Não houve entrada"
        
        if not all([cliente, tipo_servico, local]):
            st.error("Os campos 'Nome do Cliente', 'Tipo de Serviço' e 'Local' são obrigatórios.")
        elif data_hora_inicio >= data_hora_fim:
            st.error("A data/hora de início deve ser anterior à data/hora de fim.")
        else:
            duracao_total_minutos = (data_hora_fim - data_hora_inicio).total_seconds() / 60
            dados = {
                "cliente": cliente, "tipo_servico": tipo_servico, "local": local,
                "endereco": endereco, "data_hora_inicio": data_hora_inicio,
                "data_hora_fim": data_hora_fim, "valor_total": valor_total,
                "valor_entrada": valor_entrada, "forma_pagamento": forma_pagamento,
                "lembretes_minutos": lembretes_minutos
            }
            
            with st.spinner("Criando evento no Google Calendar..."):
                link_evento = criar_evento_google_calendar(service, dados)
            
            if link_evento:
                st.success("✅ Agendamento criado com sucesso no Google Calendar!")
                st.markdown(f"[📅 Ver no Google Calendar]({link_evento})")
                enviar_mensagem_telegram_agendamento(
                    cliente, data_inicio, hora_inicio, valor_total, valor_entrada, tipo_servico)
                
                linha = {
                    "Data e Hora Início": data_hora_inicio.strftime("%Y-%m-%d %H:%M"),
                    "Data e Hora Fim": data_hora_fim.strftime("%Y-%m-%d %H:%M"),
                    "Cliente": cliente, "Serviço": tipo_servico,
                    "Duração (min)": duracao_total_minutos, "Local": local, "Endereço": endereco,
                    "Valor Total": valor_total, "Entrada": valor_entrada,
                    "Forma de Pagamento": forma_pagamento, "Link do Evento": link_evento,
                }
                arquivo_csv = "agendamentos.csv"
                try:
                    df_existente = pd.read_csv(arquivo_csv) if os.path.exists(arquivo_csv) else pd.DataFrame()
                    df_novo = pd.concat([df_existente, pd.DataFrame([linha])], ignore_index=True)
                    df_novo.to_csv(arquivo_csv, index=False)
                    st.info(f"💾 Agendamento salvo em '{arquivo_csv}'.")
                except Exception as e:
                    st.error(f"Erro ao salvar o arquivo CSV: {e}")
else:
    st.warning("Falha na autenticação com Google Calendar. Verifique as credenciais no `secrets.toml` e as permissões do calendário.")

