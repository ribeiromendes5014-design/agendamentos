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

# --- Configurações ---
CALENDAR_ID = "ribeirodesenvolvedor@gmail.com"
TELEGRAM_TOKEN = st.secrets.get("TELEGRAM_TOKEN", "YOUR_TELEGRAM_TOKEN_HERE")
TELEGRAM_CHAT_ID = st.secrets.get("TELEGRAM_CHAT_ID", "YOUR_CHAT_ID_HERE")
TOPICO_ID = 64
ARQUIVO_CSV = "agendamentos.csv"
TIMEZONE = 'America/Sao_Paulo'


def get_google_calendar_service():
    """Autentica e retorna o serviço do Google Calendar."""
    try:
        service_account_info = st.secrets["google_service_account"]
        if isinstance(service_account_info, str):
            service_account_info = json.loads(service_account_info)
        creds = service_account.Credentials.from_service_account_info(
            service_account_info, scopes=SCOPES)
        return build('calendar', 'v3', credentials=creds)
    except Exception as e:
        st.error(f"Erro ao autenticar com a conta de serviço: {e}")
        return None


def criar_evento_google_calendar(service, info_evento):
    """Cria um evento no Google Calendar."""
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
        st.error(f"Erro na API do Google Calendar: {error}. Verifique se o CALENDAR_ID está correto e se a conta de serviço tem a permissão 'Fazer alterações nos eventos'.")
        return None


def enviar_mensagem_telegram_agendamento(cliente, data, hora, valor_total, valor_entrada, tipo_servico):
    """Envia uma mensagem de confirmação para o Telegram."""
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


def carregar_agendamentos_csv():
    """Carrega os agendamentos do arquivo CSV, garantindo a coluna 'Status'."""
    if os.path.exists(ARQUIVO_CSV):
        df = pd.read_csv(ARQUIVO_CSV)
        if 'Status' not in df.columns:
            df['Status'] = 'Pendente'
        return df
    return pd.DataFrame()


def parse_google_events(events):
    """Converte a lista de eventos do Google em um DataFrame do Pandas."""
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
            'ID Evento Google': event.get('id') # Adicionado para checagem
        })
    return pd.DataFrame(lista_eventos)


def puxar_eventos_google_calendar(service, periodo="futuro", dias=90):
    """Puxa eventos futuros ou passados do Google Calendar."""
    try:
        now = datetime.now(pytz.timezone(TIMEZONE))
        params = {'calendarId': CALENDAR_ID, 'maxResults': 2500, 'singleEvents': True, 'orderBy': 'startTime'}
        if periodo == "futuro":
            params['timeMin'] = now.isoformat()
        else:
            params['timeMax'] = now.isoformat()
            params['timeMin'] = (now - timedelta(days=dias)).isoformat()
        events_result = service.events().list(**params).execute()
        return parse_google_events(events_result.get('items', []))
    except HttpError as error:
        st.error(f"Erro ao buscar eventos do Google Calendar: {error}.")
        return pd.DataFrame()


def sincronizar_google_para_csv(service):
    """Busca eventos passados do Google e os adiciona ao CSV se não existirem."""
    with st.spinner("Buscando eventos passados do Google Calendar... Isso pode levar um momento."):
        df_google = puxar_eventos_google_calendar(service, periodo="passado", dias=365)
    
    if df_google.empty:
        st.warning("Nenhum evento passado encontrado no Google Calendar para sincronizar.")
        return

    df_csv_existente = carregar_agendamentos_csv()
    novas_linhas = []
    
    # Cria um conjunto de identificadores únicos para os eventos já existentes no CSV
    ids_existentes = set()
    if not df_csv_existente.empty and 'Data e Hora Início' in df_csv_existente.columns and 'Cliente' in df_csv_existente.columns:
        ids_existentes = set(pd.to_datetime(df_csv_existente['Data e Hora Início']).dt.strftime('%Y-%m-%d %H:%M') + df_csv_existente['Cliente'])

    for _, row in df_google.iterrows():
        # Cria um identificador para o evento do Google
        id_google = row['Data e Hora Início'].strftime('%Y-%m-%d %H:%M') + row['Cliente']
        
        # Se o evento não estiver no CSV, prepara para adicionar
        if id_google not in ids_existentes:
            linha = {
                "Data e Hora Início": row['Data e Hora Início'].strftime("%Y-%m-%d %H:%M"),
                "Data e Hora Fim": row['Data e Hora Fim'].strftime("%Y-%m-%d %H:%M"),
                "Cliente": row['Cliente'], "Serviço": row['Serviço'],
                "Duração (min)": (row['Data e Hora Fim'] - row['Data e Hora Início']).total_seconds() / 60,
                "Local": row.get('Local', 'N/A'), "Endereço": "", "Valor Total": 0.0,
                "Entrada": 0.0, "Forma de Pagamento": "N/A", "Link do Evento": "",
                "Status": "Concluído"
            }
            novas_linhas.append(linha)
    
    if not novas_linhas:
        st.success("Seu arquivo CSV já está sincronizado com o histórico do Google Calendar!")
        return

    df_novas_linhas = pd.DataFrame(novas_linhas)
    df_atualizado = pd.concat([df_csv_existente, df_novas_linhas], ignore_index=True)
    df_atualizado.to_csv(ARQUIVO_CSV, index=False)
    st.success(f"{len(novas_linhas)} agendamentos passados foram importados para o arquivo CSV!")
    st.rerun()


# --- App Streamlit ---
st.set_page_config(page_title="Sistema de Agendamentos", layout="centered")
st.title("📅 Sistema de Agendamento")

service = get_google_calendar_service()

if service:
    lembrete_opcoes = {"15 minutos antes": 15, "30 minutos antes": 30, "1 hora antes": 60, "2 horas antes": 120, "1 dia antes": 1440}
    tab1, tab2 = st.tabs(["➕ Novo Agendamento", "📋 Consultar Agendamentos"])

    with tab1:
        # ... (código para novo agendamento, sem alterações) ...
        st.subheader("Informações do Agendamento")
        cliente = st.text_input("👤 Nome do Cliente")
        tipo_servico = st.text_input("🛠 Tipo de Serviço (ex: Sessão de Fotos)")
        local = st.text_input("📍 Local")
        endereco = st.text_input("Endereço completo (opcional)")
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
        lembretes_selecionados = st.multiselect("🔔 Alertas:", list(lembrete_opcoes.keys()), default=["15 minutos antes"])
        valor_total = st.number_input("💰 Valor Total (R$)", min_value=0.0, value=100.0, step=10.0, format="%.2f")
        entrada = st.checkbox("✅ Houve entrada de dinheiro?")
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
                    st.success("✅ Agendamento criado com sucesso!")
                    st.markdown(f"[📅 Ver no Google Calendar]({link_evento})")
                    enviar_mensagem_telegram_agendamento(cliente, data_inicio, hora_inicio, valor_total, dados["valor_entrada"], tipo_servico)
                    linha = {"Data e Hora Início": data_hora_inicio.strftime("%Y-%m-%d %H:%M"), "Data e Hora Fim": data_hora_fim.strftime("%Y-%m-%d %H:%M"), "Cliente": cliente, "Serviço": tipo_servico, "Duração (min)": (data_hora_fim - data_hora_inicio).total_seconds()/60, "Local": local, "Endereço": endereco, "Valor Total": valor_total, "Entrada": dados["valor_entrada"], "Forma de Pagamento": dados["forma_pagamento"], "Link do Evento": link_evento, "Status": "Pendente"}
                    df_existente = carregar_agendamentos_csv()
                    df_novo = pd.concat([df_existente, pd.DataFrame([linha])], ignore_index=True)
                    df_novo.to_csv(ARQUIVO_CSV, index=False)
            else: st.error("Verifique se todos os campos estão preenchidos e se as datas/horas são válidas.")

    with tab2:
        st.header("🗓️ Seus Compromissos")
        with st.expander("Visualizar Agendamentos do Google Calendar", expanded=True):
            # ... (código de visualização do Google, sem alterações) ...
            df_futuros = puxar_eventos_google_calendar(service, periodo="futuro")
            if not df_futuros.empty:
                st.subheader("Próximo Agendamento")
                proximo = df_futuros.sort_values(by='Data e Hora Início').iloc[0]
                with st.container(border=True):
                    st.markdown(f"##### 👤 **Cliente:** {proximo['Cliente']}\n"
                                f"**🛠️ Serviço:** {proximo['Serviço']}\n"
                                f"**🗓️ Data:** {proximo['Data e Hora Início'].strftime('%d/%m/%Y às %H:%M')}\n"
                                f"**📍 Local:** {proximo['Local']}")
                st.subheader("Todos os Agendamentos Futuros")
                st.dataframe(df_futuros.assign(**{'Data e Hora Início': lambda df: df['Data e Hora Início'].dt.strftime('%d/%m/%Y %H:%M'), 'Data e Hora Fim': lambda df: df['Data e Hora Fim'].dt.strftime('%d/%m/%Y %H:%M')}), use_container_width=True, hide_index=True)
            else: st.info("Nenhum agendamento futuro encontrado no Google Calendar.")
        
        st.markdown("---")
        st.header("✔️ Gerenciar Tarefas (Backup Local)")
        
        # --- NOVO BOTÃO DE SINCRONIZAÇÃO ---
        if st.button("Sincronizar Histórico do Google Calendar para CSV"):
            sincronizar_google_para_csv(service)
        
        df_csv = carregar_agendamentos_csv()
        if not df_csv.empty:
            df_pendentes = df_csv[df_csv['Status'] == 'Pendente']
            df_concluidos = df_csv[df_csv['Status'] == 'Concluído']

            st.subheader("Tarefas Pendentes")
            if df_pendentes.empty:
                st.success("🎉 Nenhuma tarefa pendente!")
            else:
                # ... (código de gerenciamento de tarefas, sem alterações) ...
                for index, row in df_pendentes.iterrows():
                    with st.container(border=True):
                        col1, col2 = st.columns([3, 1])
                        cliente_info = row.get('Cliente', 'N/A')
                        servico_info = row.get('Serviço', 'N/A')
                        data_info = "Data não informada"
                        if 'Data e Hora Início' in row and pd.notna(row['Data e Hora Início']):
                            try:
                                data_info = pd.to_datetime(row['Data e Hora Início']).strftime('%d/%m/%Y às %H:%M')
                            except (ValueError, TypeError):
                                data_info = "Data em formato inválido"
                        
                        col1.markdown(f"**Cliente:** {cliente_info} | **Serviço:** {servico_info}\n\n"
                                      f"**Data:** {data_info}")
                        if col2.button("✅ Concluir", key=f"concluir_{index}", use_container_width=True):
                            df_csv.loc[index, 'Status'] = 'Concluído'
                            df_csv.to_csv(ARQUIVO_CSV, index=False)
                            st.toast(f"Tarefa de {cliente_info} concluída!")
                            st.rerun()

            with st.expander("Ver Histórico de Tarefas Concluídas"):
                if df_concluidos.empty:
                    st.info("Nenhuma tarefa foi concluída ainda.")
                else:
                    st.dataframe(df_concluidos.sort_values(by='Data e Hora Início', ascending=False), use_container_width=True, hide_index=True)
        else:
            st.info("Nenhum agendamento encontrado no arquivo de backup local.")
else:
    st.warning("Falha na autenticação com Google Calendar.")

