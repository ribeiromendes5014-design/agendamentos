# -*- coding: utf-8 -*-
import streamlit as st
from datetime import datetime, timedelta
import pandas as pd
import os
import json
import pytz
import requests
import base64 

# Google Calendar
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

# Escopo para acessar o Google Calendar
SCOPES = ['https://www.googleapis.com/auth/calendar']

# --- Configurações ---
# ATENÇÃO: Verifique se este é o e-mail correto do seu calendário!
CALENDAR_ID = "ribeirodesenvolvedor@gmail.com" 
TELEGRAM_TOKEN = st.secrets.get("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = st.secrets.get("TELEGRAM_CHAT_ID")
TOPICO_ID = 64
ARQUIVO_CSV = "agendamentos.csv"
TIMEZONE = 'America/Sao_Paulo'

# --- Configuração do Fundo (Link direto da imagem) ---
BACKGROUND_IMAGE_URL = "https://imgur.com/a/hyZWUDF#7tefaKQ/minha-foto.jpg"

def set_background(image_url):
    st.markdown(
        f"""
        <style>
        .stApp::before {{
            content: "";
            position: fixed;
            left: 0; right: 0; top: 0; bottom: 0;
            z-index: 0; /* fundo visível */
            background-image: url("{image_url}");
            background-size: cover;
            background-position: center;
            filter: blur(8px);
            -webkit-filter: blur(8px);
        }}
        [data-testid="stAppViewContainer"] > .main .block-container {{
            position: relative;
            z-index: 1; /* fica por cima do fundo */
            background-color: rgba(255, 255, 255, 0.9); /* ajuste de opacidade */
            border-radius: 15px;
            padding: 2rem;
            box-shadow: 0 8px 32px 0 rgba(31, 38, 135, 0.37);
            border: 1px solid rgba(255, 255, 255, 0.18);
        }}
        [data-testid="stHeader"], [data-testid="stTabs"] {{
            background: transparent;
        }}
        [data-testid="stExpander"] {{
            background-color: rgba(240, 242, 246, 0.90);
            border-radius: 10px;
        }}
        </style>
        """,
        unsafe_allow_html=True
    )


def get_google_calendar_service():
    try:
        service_account_info = st.secrets["google_service_account"]
        if isinstance(service_account_info, str):
            service_account_info = json.loads(service_account_info)
        creds = service_account.Credentials.from_service_account_info(
            service_account_info, scopes=SCOPES)
        return build('calendar', 'v3', credentials=creds)
    except Exception as e:
        st.error(f"Erro ao autenticar: {e}")
        return None

def criar_evento_google_calendar(service, info_evento):
    tz = pytz.timezone(TIMEZONE)
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
        'start': {'dateTime': data_hora_inicio_aware.isoformat(), 'timeZone': TIMEZONE},
        'end': {'dateTime': data_hora_fim_aware.isoformat(), 'timeZone': TIMEZONE},
        'reminders': reminders,
    }
    try:
        evento_criado = service.events().insert(calendarId=CALENDAR_ID, body=evento).execute()
        return evento_criado.get('htmlLink')
    except HttpError as error:
        st.error(f"Erro na API do Google Calendar: {error}.")
        return None

def enviar_mensagem_telegram_agendamento(cliente, data, hora, valor_total, valor_entrada, tipo_servico):
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
    if TELEGRAM_TOKEN and TELEGRAM_CHAT_ID:
        try:
            response = requests.post(url, data=payload)
            if response.status_code != 200:
                st.error(f"Erro ao enviar mensagem para o Telegram: {response.json()}")
            else:
                st.success("📨 Mensagem enviada para o grupo do Telegram!")
        except Exception as e:
            st.error(f"Falha ao conectar com o Telegram: {e}")


def carregar_agendamentos_csv():
    if os.path.exists(ARQUIVO_CSV):
        df = pd.read_csv(ARQUIVO_CSV)
        if 'Status' not in df.columns:
            df['Status'] = 'Pendente'
        return df
    return pd.DataFrame()

def parse_google_events(events):
    lista_eventos = []
    for event in events:
        start = event['start'].get('dateTime', event['start'].get('date'))
        end = event['end'].get('dateTime', event['end'].get('date'))
        summary = event.get('summary', 'Sem Título')
        cliente, servico = (summary.split(' - ') + ['N/A'])[:2]
        lista_eventos.append({
            'Data e Hora Início': pd.to_datetime(start).tz_convert(TIMEZONE).tz_localize(None),
            'Data e Hora Fim': pd.to_datetime(end).tz_convert(TIMEZONE).tz_localize(None),
            'Cliente': cliente, 'Serviço': servico, 'Local': event.get('location', 'N/A'),
        })
    return pd.DataFrame(lista_eventos)

def puxar_eventos_google_calendar(service, periodo="futuro", dias=90):
    try:
        now = datetime.now(pytz.timezone(TIMEZONE))
        params = {'calendarId': CALENDAR_ID, 'maxResults': 250, 'singleEvents': True, 'orderBy': 'startTime'}
        if periodo == "futuro":
            params['timeMin'] = now.isoformat()
        else:
            params['timeMax'] = now.isoformat()
            params['timeMin'] = (now - timedelta(days=dias)).isoformat()
        events_result = service.events().list(**params).execute()
        return parse_google_events(events_result.get('items', []))
    except HttpError as error:
        st.error(f"Erro ao buscar eventos: {error}.")
        return pd.DataFrame()

# --- App Streamlit ---
st.set_page_config(page_title="Sistema de Agendamentos", layout="wide")

set_background(BACKGROUND_IMAGE_URL)

st.title("📅 Sistema de Agendamento")

if 'confirming' not in st.session_state:
    st.session_state.confirming = {}

service = get_google_calendar_service()

if service:
    lembrete_opcoes = {"15 min": 15, "30 min": 30, "1 hora": 60, "2 horas": 120, "1 dia": 1440}
    tab1, tab2 = st.tabs(["➕ Novo Agendamento", "📋 Consultar Agendamentos"])

    with tab1:
        st.subheader("Informações do Agendamento")
        cliente = st.text_input("👤 Nome do Cliente")
        tipo_servico = st.text_input("🛠 Tipo de Serviço")
        local = st.text_input("📍 Local")
        endereco = st.text_input("Endereço (opcional)")
        st.markdown("---")
        metodo_termino = st.radio("Como definir o término?", ('Definir Duração', 'Manualmente'), horizontal=True)
        col1, col2 = st.columns(2)
        data_inicio = col1.date_input("📆 Data de Início")
        hora_inicio = col1.time_input("⏰ Horário de Início")
        data_hora_fim = None
        if metodo_termino == 'Manualmente':
            data_fim_input = col2.date_input("📆 Data de Fim")
            hora_fim_input = col2.time_input("⏰ Horário de Fim")
            if data_fim_input and hora_fim_input:
                data_hora_fim = datetime.combine(data_fim_input, hora_fim_input)
        else:
            duracao_minutos = col2.number_input("⏳ Duração (min)", min_value=1, value=60, step=1)
            if data_inicio and hora_inicio:
                dt_inicio = datetime.combine(data_inicio, hora_inicio)
                dt_fim = dt_inicio + timedelta(minutes=duracao_minutos)
                col2.markdown(f"**Término:** {dt_fim.strftime('%d/%m/%Y às %H:%M')}")
                data_hora_fim = dt_fim
        st.markdown("---")
        st.subheader("Lembretes e Finanças")
        lembretes_selecionados = st.multiselect("🔔 Alertas:", list(lembrete_opcoes.keys()), default=["15 min"])
        valor_total = st.number_input("💰 Valor Total (R$)", min_value=0.0, value=100.0, step=10.0, format="%.2f")
        entrada = st.checkbox("✅ Houve entrada?")
        valor_entrada_input, forma_pagamento_input = 0.0, "Não houve entrada"
        if entrada:
            valor_entrada_input = st.number_input("💵 Valor da Entrada (R$)", min_value=0.0, max_value=valor_total, step=10.0, format="%.2f")
            forma_pagamento_input = st.selectbox("💳 Forma de Pagamento", ["Pix", "Dinheiro", "Cartão", "Transferência", "Outro"])
        st.markdown("---")
        if st.button("Agendar Evento", type="primary"):
            data_hora_inicio = datetime.combine(data_inicio, hora_inicio)
            if data_hora_fim and all([cliente, tipo_servico, local]) and data_hora_inicio < data_hora_fim:
                dados = {"cliente": cliente, "tipo_servico": tipo_servico, "local": local, "endereco": endereco, "data_hora_inicio": data_hora_inicio, "data_hora_fim": data_hora_fim, "valor_total": valor_total, "valor_entrada": valor_entrada_input if entrada else 0.0, "forma_pagamento": forma_pagamento_input if entrada else "Não houve entrada", "lembretes_minutos": [lembrete_opcoes[l] for l in lembretes_selecionados]}
                with st.spinner("Criando evento..."): link_evento = criar_evento_google_calendar(service, dados)
                if link_evento:
                    st.success("✅ Agendamento criado!")
                    st.markdown(f"[📅 Ver no Google Calendar]({link_evento})")
                    enviar_mensagem_telegram_agendamento(cliente, data_inicio, hora_inicio, valor_total, dados["valor_entrada"], tipo_servico)
                    linha = {"Data e Hora Início": data_hora_inicio.strftime("%Y-%m-%d %H:%M"), "Data e Hora Fim": data_hora_fim.strftime("%Y-%m-%d %H:%M"), "Cliente": cliente, "Serviço": tipo_servico, "Duração (min)": (data_hora_fim - data_hora_inicio).total_seconds()/60, "Local": local, "Endereço": endereco, "Valor Total": valor_total, "Entrada": dados["valor_entrada"], "Forma de Pagamento": dados["forma_pagamento"], "Link do Evento": link_evento, "Status": "Pendente"}
                    df_existente = carregar_agendamentos_csv()
                    df_novo = pd.concat([df_existente, pd.DataFrame([linha])], ignore_index=True)
                    df_novo.to_csv(ARQUIVO_CSV, index=False)
            else: st.error("Preencha todos os campos e verifique as datas.")

    with tab2:
        st.header("🗓️ Seus Compromissos")
        with st.expander("Agendamentos do Google Calendar", expanded=True):
            df_futuros = puxar_eventos_google_calendar(service, periodo="futuro")
            if not df_futuros.empty:
                st.subheader("Próximo Agendamento")
                proximo = df_futuros.sort_values(by='Data e Hora Início').iloc[0]
                with st.container(border=True):
                    st.markdown(f"##### 👤 **Cliente:** {proximo['Cliente']}\n"
                                f"**🛠️ Serviço:** {proximo['Serviço']}\n"
                                f"**🗓️ Data:** {proximo['Data e Hora Início'].strftime('%d/%m/%Y às %H:%M')}\n"
                                f"**📍 Local:** {proximo['Local']}")
                st.subheader("Agendamentos Futuros")
                st.dataframe(df_futuros.assign(**{'Data e Hora Início': lambda df: df['Data e Hora Início'].dt.strftime('%d/%m/%Y %H:%M'), 'Data e Hora Fim': lambda df: df['Data e Hora Fim'].dt.strftime('%d/%m/%Y %H:%M')}), use_container_width=True, hide_index=True)
            else: st.info("Nenhum agendamento futuro no Google Calendar.")
        
        st.markdown("---")
        st.header("✔️ Gerenciar Tarefas (Backup Local)")
        df_csv = carregar_agendamentos_csv()
        if not df_csv.empty:
            df_pendentes = df_csv[df_csv['Status'] == 'Pendente']
            df_concluidos = df_csv[df_csv['Status'] == 'Concluído']

            st.subheader("Tarefas Pendentes")
            if df_pendentes.empty:
                st.success("🎉 Nenhuma tarefa pendente!")
            else:
                for index, row in df_pendentes.iterrows():
                    with st.container(border=True):
                        col1, col2 = st.columns([3, 1.2])
                        col1.markdown(f"**Cliente:** {row.get('Cliente', 'N/A')} | **Serviço:** {row.get('Serviço', 'N/A')}\n\n"
                                      f"**Data:** {pd.to_datetime(row.get('Data e Hora Início')).strftime('%d/%m/%Y às %H:%M')}")
                        
                        if st.session_state.confirming.get(index):
                            col2.write("Confirmar?")
                            confirm_col, cancel_col = col2.columns(2)
                            if confirm_col.button("Sim", key=f"confirm_{index}", use_container_width=True):
                                df_csv.loc[index, 'Status'] = 'Concluído'
                                df_csv.to_csv(ARQUIVO_CSV, index=False)
                                st.toast(f"Tarefa de {row.get('Cliente')} concluída!")
                                st.session_state.confirming[index] = False
                                st.rerun()
                            if cancel_col.button("Não", key=f"cancel_{index}", use_container_width=True):
                                st.session_state.confirming[index] = False
                                st.rerun()
                        else:
                            if col2.button("✅ Concluir", key=f"concluir_{index}", use_container_width=True):
                                st.session_state.confirming[index] = True
                                st.rerun()

            with st.expander("Ver Histórico de Tarefas Concluídas"):
                if df_concluidos.empty:
                    st.info("Nenhuma tarefa foi concluída.")
                else:
                    st.dataframe(df_concluidos.sort_values(by='Data e Hora Início', ascending=False), use_container_width=True, hide_index=True)
        else:
            st.info("Nenhum agendamento no arquivo de backup.")
else:
    st.warning("Falha na autenticação com Google Calendar.")





