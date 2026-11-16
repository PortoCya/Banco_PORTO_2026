"""
Dashboard NPS KeyCore (Streamlit + Plotly) - responsivo, tema claro e escuro

Lê tudo da API (nada de banco ou IA direto daqui): entre com um usuário
ANALYST ou ADMIN. O NPS vem do backend; a análise sugerida (sentimento e
tema) é feita pelo worker de IA e só aparece aqui como sugestão.

Instalar:  pip install -r requirements-dashboard.txt
Rodar:     NPS_API_URL=http://localhost:8000 streamlit run dashboard/nps_dashboard.py
           (a partir da raiz do projeto, para pegar o tema de .streamlit/config.toml)
"""
from datetime import date, timedelta
from html import escape

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots

from api_cliente import API_URL, ClienteApi, ErroApi, nps_inteiro

st.set_page_config(page_title="NPS", layout="wide")

# Cores que funcionam nos dois temas (claro/escuro em .streamlit/config.toml).
# Não dependem do tema ativo: o Streamlit não reexecuta o script ao trocar de
# tema, então qualquer cor escolhida em Python ficaria presa no tema antigo.
# Fundos, textos e eixos ficam por conta do Streamlit/Plotly (theme="streamlit");
# no CSS, texto herda a cor do tema e fundos/bordas são cinzas translúcidos.
GREEN, RED, BLUE = "#00C060", "#F25555", "#4F7FBF"
GRAY = "rgba(128, 128, 128, 0.35)"   # translúcido: cinza neutro no claro e no escuro
LINE = "#8B7CF6"                     # linha da pontuação e links, legível nos dois fundos
MUTED = "#8A8A93"
UP, DOWN = "#16A34A", "#EF4444"      # variação dos KPIs

st.markdown(
    f"""
    <style>
    .block-container {{ padding: 1.5rem 2rem 3rem; max-width: 1400px; }}

    /* KPIs: grid que quebra sozinho conforme a largura */
    .kpi-grid {{ display:grid; gap:16px; margin:8px 0 16px;
                grid-template-columns:repeat(auto-fit, minmax(170px, 1fr)); }}
    .kpi {{ background:rgba(128,128,128,.06); border:1px solid rgba(128,128,128,.2);
           border-radius:8px; padding:16px 18px; }}
    .kpi .t {{ color:{MUTED}; font-size:.9rem; }}
    .kpi .row {{ display:flex; justify-content:space-between;
                align-items:baseline; margin-top:8px; }}
    .kpi .v {{ font-size:1.6rem; font-weight:600; }}
    .kpi .d {{ font-size:.8rem; font-weight:600; }}

    /* legenda do donut */
    .legend-item {{ margin:14px 0; font-size:1.05rem; }}

    /* mobile */
    @media (max-width: 640px) {{
        .block-container {{ padding: 1rem .75rem 2rem; }}
        .kpi-grid {{ grid-template-columns: repeat(2, 1fr); gap:10px; }}
        .kpi {{ padding:12px; }}
        .kpi .v {{ font-size:1.3rem; }}
        h1 {{ font-size:1.6rem !important; }}
    }}

    /* ---------- cards de resposta (melhores/piores) ---------- */
    .resp-card {{ border:1px solid rgba(128,128,128,.2); border-radius:8px;
                  padding:12px 14px; margin-bottom:10px; }}
    .resp-top {{ display:flex; align-items:center; gap:10px; }}
    .resp-top .nota {{ color:#fff; font-weight:700; border-radius:6px;
                       min-width:30px; text-align:center; padding:2px 6px; }}
    .resp-meta {{ color:{MUTED}; font-size:.8rem; }}
    .resp-txt {{ margin:8px 0 6px; line-height:1.4; }}
    .resp-ia {{ color:{MUTED}; font-size:.8rem; }}

    /* ---------- tabela de tags ---------- */
    .tags-table {{ width:100%; margin-top:8px; }}
    .tags-head, .tags-row {{
        display:grid; align-items:center; column-gap:16px;
        grid-template-columns: 2.2fr 1fr 1fr 3fr 1.3fr 32px;
        padding: 0 20px;
    }}
    .tags-head {{ background:rgba(128,128,128,.12); height:56px; font-weight:600;
                  border-radius:6px; }}
    .tags-row {{ min-height:84px; border-bottom:1px solid rgba(128,128,128,.2); }}
    .tags-row:hover {{ background:rgba(128,128,128,.06); }}
    .tags-row a {{ color:{LINE}; text-decoration:underline; font-weight:500; }}
    .tags-row .menu {{ text-align:center; font-size:1.4rem; }}
    .bar {{ display:flex; height:7px; border-radius:4px; overflow:hidden;
            background:rgba(128,128,128,.15); }}
    .bar span {{ display:block; height:100%; }}
    .dot {{ display:inline-block; width:8px; height:8px; border-radius:50%; margin-right:6px; }}
    .lbl {{ display:none; }}

    @media (max-width: 760px) {{
        .tags-head {{ display:none; }}
        .tags-row {{
            grid-template-columns: 1fr 1fr 1fr; row-gap:8px; padding:14px 12px;
            grid-template-areas: "name name menu" "resp score sent" "bar bar bar";
        }}
        .tags-row .c-name  {{ grid-area:name; font-weight:600; }}
        .tags-row .c-resp  {{ grid-area:resp; }}
        .tags-row .c-score {{ grid-area:score; }}
        .tags-row .c-sent  {{ grid-area:sent; }}
        .tags-row .c-bar   {{ grid-area:bar; }}
        .tags-row .menu    {{ grid-area:menu; text-align:right; }}
        .lbl {{ display:block; font-size:.7rem; color:{MUTED}; text-transform:uppercase; }}
    }}
    </style>
    """,
    unsafe_allow_html=True,
)

# Fundo transparente: o gráfico fica com o fundo do card/tema; vírgula decimal
PLOT_LAYOUT = dict(
    paper_bgcolor="rgba(0,0,0,0)",
    plot_bgcolor="rgba(0,0,0,0)",
    separators=",.",
    autosize=True,
)
PLOT_CFG = {"displayModeBar": False, "responsive": True}


# ---------------------------------------------------------------- rótulos
SENT_COLOR = {"Positivo": GREEN, "Neutro": MUTED, "Negativo": RED}
FAIXA_COLOR = {"Promotor": GREEN, "Neutro": MUTED, "Detrator": RED}
FAIXA_LABEL = {"PROMOTOR": "Promotor", "NEUTRO": "Neutro", "DETRATOR": "Detrator"}
SENTIMENTO_LABEL = {"POSITIVO": "Positivo", "NEUTRO": "Neutro", "NEGATIVO": "Negativo"}
TEMA_LABEL = {"atendimento": "Atendimento", "preco": "Preço", "produto": "Produto",
              "prazo": "Prazo", "usabilidade": "Usabilidade", "outro": "Outro"}
STATUS_IA_LABEL = {"CONCLUIDA": "Concluída", "BAIXA_CONFIANCA": "Baixa confiança",
                   "FALHA_SCHEMA": "Falha de formato", "PENDENTE": "Pendente",
                   "DESCARTADA_MANUAL": "Descartada"}
DIAS_PERIODO = {"Últimos 7 dias": 7, "Últimos 30 dias": 30, "Últimos 90 dias": 90}
COLUNAS = ["id", "data", "nota", "faixa", "comentario", "sentimento_ia", "tema_ia",
           "confianca_ia", "justificativa_ia", "status_ia"]


# ---------------------------------------------------------------- login
def tela_login() -> None:
    st.title("NPS")
    with st.form("login"):
        st.caption(f"Entre com seu usuário ANALYST ou ADMIN · API: `{API_URL}`")
        email = st.text_input("E-mail", max_chars=255)
        senha = st.text_input("Senha", type="password", max_chars=128)
        if st.form_submit_button("Entrar", type="primary"):
            try:
                api = ClienteApi()
                usuario = api.login(email, senha)
            except ErroApi as e:
                st.error(str(e))
                return
            # só o token fica na sessão; a senha não é guardada
            st.session_state["token"] = api.token
            st.session_state["usuario"] = usuario
            st.rerun()


def sair() -> None:
    for chave in ("token", "usuario"):
        st.session_state.pop(chave, None)
    st.cache_data.clear()


def chamar(funcao, *args):
    """Chama a API; 401 (token vencido ou usuário desativado) volta ao login."""
    try:
        return funcao(*args)
    except ErroApi as e:
        if e.status == 401:
            sair()
            st.warning("Sua sessão expirou. Entre de novo.")
            st.rerun()
        st.error(str(e))
        st.stop()


# ---------------------------------------------------------------- dados (API)
# Cache curto por token: cada usuário vê só o que a API deixa ele ver.
@st.cache_data(ttl=60, show_spinner=False)
def carregar_pesquisas(token: str) -> list[dict]:
    return ClienteApi(token=token).pesquisas()


@st.cache_data(ttl=60, show_spinner="Carregando respostas...")
def carregar_respostas(token: str, id_pesquisa: str, inicio: date, fim: date) -> pd.DataFrame:
    itens = ClienteApi(token=token).respostas(id_pesquisa, inicio, fim)
    if not itens:
        return pd.DataFrame(columns=COLUNAS)
    df = pd.DataFrame(itens)
    return pd.DataFrame({
        "id": df["id"],
        # datas da API vêm em UTC; o painel mostra no fuso de São Paulo
        "data": pd.to_datetime(df["criada_em"], utc=True)
                  .dt.tz_convert("America/Sao_Paulo").dt.tz_localize(None),
        "nota": df["nota_nps"].astype(int),
        "faixa": df["faixa_nps"].map(FAIXA_LABEL),
        "comentario": df["texto_comentario"].fillna(""),
        "sentimento_ia": df["sentimento"].map(SENTIMENTO_LABEL),
        "tema_ia": df["tema"].map(TEMA_LABEL),
        "confianca_ia": df["confianca"],
        "justificativa_ia": df["justificativa"],
        "status_ia": df["status_analise"].map(STATUS_IA_LABEL),
    })


@st.cache_data(ttl=60, show_spinner=False)
def carregar_nps(token: str, id_pesquisa: str, inicio: date, fim: date) -> dict:
    return ClienteApi(token=token).nps(id_pesquisa, inicio, fim)


def janela(dias: int, anterior: bool = False) -> tuple[date, date]:
    """Período escolhido (ou o imediatamente anterior), em dias corridos até hoje."""
    fim = date.today() - timedelta(days=dias if anterior else 0)
    return fim - timedelta(days=dias - 1), fim


def no_periodo(df: pd.DataFrame, inicio: date, fim: date) -> pd.DataFrame:
    dia = df["data"].dt.date
    return df[(dia >= inicio) & (dia <= fim)]


# ---------------------------------------------------------------- cálculos de exibição
def contagem_faixas(df: pd.DataFrame) -> tuple[int, int, int]:
    cont = df["faixa"].value_counts()
    return tuple(int(cont.get(f, 0)) for f in ("Promotor", "Neutro", "Detrator"))


def historico(df: pd.DataFrame, dias: int) -> pd.DataFrame:
    """NPS e faixas por dia (7 dias) ou por semana (30/90 dias)."""
    freq = "D" if dias <= 7 else "W"
    g = (df.assign(periodo=df["data"].dt.to_period(freq).dt.start_time)
         .groupby("periodo")["faixa"].value_counts().unstack(fill_value=0)
         .reindex(columns=["Promotor", "Neutro", "Detrator"], fill_value=0))
    g["total"] = g.sum(axis=1)
    g["score"] = [nps_inteiro(p, n, d) for p, n, d in zip(g["Promotor"], g["Neutro"], g["Detrator"])]
    g = g.reset_index()
    g["period"] = g["periodo"].dt.strftime("%d/%m")
    return g


def resumo_tags(df: pd.DataFrame, coluna: str, nomes: list[str]) -> pd.DataFrame:
    """Uma linha por tag fixa (mesmo sem respostas), a partir da análise sugerida."""
    linhas = []
    for nome in nomes:
        g = df[df[coluna] == nome]
        n = len(g)
        p, ne, d = contagem_faixas(g)
        linhas.append({
            "nome": nome,
            "respostas": n,
            "pro": p / n * 100 if n else 0, "pas": ne / n * 100 if n else 0,
            "det": d / n * 100 if n else 0,
            "score": nps_inteiro(p, ne, d),
            "sentimento": g["sentimento_ia"].mode().iloc[0] if n else "—",
        })
    return pd.DataFrame(linhas).sort_values("respostas", ascending=False)


def ranquear(df: pd.DataFrame, melhores: bool, n: int = 5) -> pd.DataFrame:
    """
    Melhores/piores respostas com comentário.

    Ordena pela nota. No empate, usa o sentimento sugerido pela IA ponderado
    pela confiança (só análises concluídas) e, por fim, a resposta mais
    recente. A IA só desempata: nunca muda a nota.
    """
    com_texto = df[df["comentario"].str.strip() != ""].copy()
    sinal = com_texto["sentimento_ia"].map({"Positivo": 1, "Neutro": 0, "Negativo": -1})
    valido = com_texto["status_ia"] == "Concluída"
    com_texto["_ia"] = (sinal * com_texto["confianca_ia"]).where(valido, 0).fillna(0)
    return com_texto.sort_values(
        ["nota", "_ia", "data"], ascending=[not melhores, not melhores, False]
    ).head(n)


def fmt_int(n: int) -> str:
    return f"{n:,}".replace(",", ".")


def fmt_nps(v) -> str:
    return "—" if v is None or pd.isna(v) else f"{int(v)}"


def variacao_pct(atual, anterior) -> float | None:
    if atual is None or anterior in (None, 0):
        return None
    return (atual - anterior) / abs(anterior) * 100


# ---------------------------------------------------------------- componentes
def kpi_grid(itens: list[tuple[str, str]]) -> None:
    """Cards de indicador sem variação (título, valor)."""
    cards = "".join(
        f'<div class="kpi"><div class="t">{t}</div>'
        f'<div class="row"><span class="v">{v}</span></div></div>'
        for t, v in itens
    )
    st.markdown(f'<div class="kpi-grid">{cards}</div>', unsafe_allow_html=True)


def kpi_grid_delta(itens: list[tuple[str, str, float | None, bool]]) -> None:
    """
    Cards com variação contra o período anterior: (título, valor, variação %, inverso).
    Variação None = sem base para comparar. inverso=True quando subir é ruim.
    """
    cards = ""
    for titulo, valor, delta, inverso in itens:
        if delta is None:
            d = f'<span class="d" style="color:{MUTED}">—</span>'
        else:
            bom = (delta >= 0) != inverso
            seta = "↑" if delta >= 0 else "↓"
            d = f'<span class="d" style="color:{UP if bom else DOWN}">{seta} {abs(delta):.0f}%</span>'
        cards += (f'<div class="kpi"><div class="t">{titulo}</div>'
                  f'<div class="row"><span class="v">{valor}</span>{d}</div></div>')
    st.markdown(f'<div class="kpi-grid">{cards}</div>', unsafe_allow_html=True)


def card_resposta(r) -> str:
    """Card de uma resposta. Comentário vem do cliente: sempre escapado."""
    cor = FAIXA_COLOR[r.faixa]
    if r.status_ia in ("Concluída", "Baixa confiança") and pd.notna(r.sentimento_ia):
        ia = f"{escape(r.sentimento_ia)} · {escape(r.tema_ia)} · {r.confianca_ia:.0%} de confiança"
        if r.status_ia == "Baixa confiança":
            ia += " (baixa, fora das contagens)"
        if isinstance(r.justificativa_ia, str) and r.justificativa_ia:
            ia += f'<br><i>{escape(r.justificativa_ia)}</i>'
    else:
        ia = escape(str(r.status_ia if pd.notna(r.status_ia) else "aguardando o worker de IA")).lower()
    return (
        '<div class="resp-card">'
        f'<div class="resp-top"><span class="nota" style="background:{cor}">{r.nota}</span>'
        f'<span class="resp-meta">{r.faixa} · {r.data:%d/%m/%Y}</span></div>'
        f'<div class="resp-txt">“{escape(r.comentario)}”</div>'
        f'<div class="resp-ia">🤖 Análise sugerida: {ia}</div>'
        "</div>"
    )


AVISO_IA = (
    "🤖 *Sugerido* = análise sugerida pela IA, feita automaticamente pelo worker depois de "
    "cada resposta (dados pessoais mascarados antes do envio). Confiança abaixo de 60% fica "
    "como baixa confiança e fora das contagens. A IA nunca altera a nota nem o NPS."
)


# ================================================================= página
if "token" not in st.session_state:
    tela_login()
    st.stop()

usuario = st.session_state["usuario"]
pesquisas = chamar(carregar_pesquisas, st.session_state["token"])

col_title, col_user = st.columns([5, 1], vertical_alignment="center")
col_title.title("NPS")
with col_user:
    st.caption(f"{escape(usuario['nome'])} · {usuario['papel']}")
    if st.button("Sair", width="stretch"):
        sair()
        st.rerun()

if not pesquisas:
    st.info("Nenhuma pesquisa cadastrada ainda. Um ADMIN cria e publica pesquisas no painel web.")
    st.stop()

# Filtros (valem para as três abas)
f1, f2 = st.columns([3, 1])
rotulos = {p["id"]: f'{p["titulo"]} · v{p["numero_versao"]} · {p["status"].lower()}' for p in pesquisas}
id_pesquisa = f1.selectbox("Pesquisa", list(rotulos), format_func=rotulos.get, key="pesquisa")
periodo = f2.selectbox("Período", list(DIAS_PERIODO), index=1, key="periodo")
dias = DIAS_PERIODO[periodo]
ini_at, fim_at = janela(dias)
ini_ant, fim_ant = janela(dias, anterior=True)

token = st.session_state["token"]
base = chamar(carregar_respostas, token, id_pesquisa, ini_ant, fim_at)
atual = no_periodo(base, ini_at, fim_at)
anterior = no_periodo(base, ini_ant, fim_ant)
nps_at = chamar(carregar_nps, token, id_pesquisa, ini_at, fim_at)
nps_ant = chamar(carregar_nps, token, id_pesquisa, ini_ant, fim_ant)

tab_overview, tab_responses, tab_tags = st.tabs(["Visão geral", "Respostas", "Tags"])

with tab_overview:
    qualitativas = lambda df: int((df["comentario"].str.strip() != "").sum())
    analisadas = lambda df: int((df["status_ia"] == "Concluída").sum())
    kpi_grid_delta([
        ("📊 NPS", fmt_nps(nps_at["valor_nps"]),
         variacao_pct(nps_at["valor_nps"], nps_ant["valor_nps"]), False),
        ("💬 Total de respostas", fmt_int(nps_at["total_respostas"]),
         variacao_pct(nps_at["total_respostas"], nps_ant["total_respostas"]), False),
        ("✅ Respostas qualitativas", fmt_int(qualitativas(atual)),
         variacao_pct(qualitativas(atual), qualitativas(anterior)), False),
        ("🤖 Analisadas pela IA", fmt_int(analisadas(atual)),
         variacao_pct(analisadas(atual), analisadas(anterior)), False),
    ])
    st.caption(f"Variação comparada aos {dias} dias anteriores. NPS calculado pela API.")

    if nps_at["status"] == "sem_dados_suficientes":
        st.info("Ainda não há respostas neste período: o NPS não existe (não é zero).")
    else:
        promoters, passives, detractors = (nps_at["qtd_promotores"], nps_at["qtd_neutros"],
                                           nps_at["qtd_detratores"])
        total = nps_at["total_respostas"]

        c1, c2 = st.columns(2)

        with c1, st.container(border=True):
            st.subheader("Pontuação")
            gauge = go.Figure(
                go.Indicator(
                    mode="gauge+number",
                    value=nps_at["valor_nps"],
                    number={"font": {"color": BLUE, "size": 44}},
                    gauge={
                        "axis": {"range": [-100, 100], "tickvals": [-100, 0, 100]},
                        "bar": {"color": BLUE, "thickness": 0.35},
                        "bgcolor": GRAY,
                        "borderwidth": 0,
                    },
                )
            )
            gauge.update_layout(**PLOT_LAYOUT, height=280, margin=dict(t=30, b=10, l=30, r=30))
            st.plotly_chart(gauge, width="stretch", config=PLOT_CFG)

        with c2, st.container(border=True):
            st.subheader("Respostas")
            d1, d2 = st.columns(2, vertical_alignment="center")
            donut = go.Figure(
                go.Pie(
                    values=[promoters, passives, detractors],
                    labels=["Promotores", "Neutros", "Detratores"],
                    hole=0.78,
                    marker_colors=[GREEN, GRAY, RED],
                    textinfo="none",
                    sort=False,
                )
            )
            donut.update_layout(
                **PLOT_LAYOUT, height=260, showlegend=False,
                margin=dict(t=10, b=10, l=10, r=10),
            )
            d1.plotly_chart(donut, width="stretch", config=PLOT_CFG)

            legend = ""
            for icon, label, val, color in [
                ("😊", "Promotores", promoters, GREEN),
                ("😐", "Neutros", passives, MUTED),
                ("☹️", "Detratores", detractors, RED),
            ]:
                legend += (
                    f'<div class="legend-item"><span style="color:{color}">{icon}</span> '
                    f"{label}<br><b>{val} ({val / total:.0%})</b></div>"
                )
            d2.markdown(legend, unsafe_allow_html=True)

        # -------------------------------------------------------- Histórico
        with st.container(border=True):
            st.subheader("Histórico do NPS")
            st.caption("Por dia" if dias <= 7 else "Por semana")
            df = historico(atual, dias)
            pct = lambda col: df[col] / df["total"] * 100

            fig = make_subplots(specs=[[{"secondary_y": True}]])
            fig.add_bar(x=df["period"], y=pct("Detrator"), name="Detratores",
                        marker_color=RED, secondary_y=True)
            fig.add_bar(x=df["period"], y=pct("Neutro"), name="Neutros",
                        marker_color=GRAY, secondary_y=True)
            fig.add_bar(x=df["period"], y=pct("Promotor"), name="Promotores",
                        marker_color=GREEN, secondary_y=True)

            # linha de pontuação: sólida até o penúltimo ponto, tracejada no último
            # (o período mais recente ainda está em andamento)
            fig.add_scatter(x=df["period"][:-1], y=df["score"][:-1], name="Pontuação",
                            mode="lines+markers", line=dict(color=LINE, shape="spline"),
                            secondary_y=False)
            fig.add_scatter(x=df["period"][-2:], y=df["score"][-2:], showlegend=False,
                            mode="lines+markers", line=dict(color=LINE, dash="dash"),
                            secondary_y=False)

            fig.update_layout(
                **PLOT_LAYOUT, barmode="stack", height=400, bargap=0.5,
                legend=dict(orientation="h", y=1.15, x=0),
                margin=dict(t=40, b=20, l=10, r=10),
            )
            fig.update_yaxes(title_text="Pontuação", range=[-100, 100], secondary_y=False)
            fig.update_yaxes(title_text="Respostas", range=[0, 100], ticksuffix="%",
                             showgrid=False, secondary_y=True)
            st.plotly_chart(fig, width="stretch", config=PLOT_CFG)

with tab_responses:
    resp = atual

    if resp.empty:
        st.info("Nenhuma resposta neste período.")
    else:
        # -------------------------------------------------------- Resumo
        com_texto = (resp["comentario"].str.strip() != "").mean()
        kpi_grid([
            ("📊 NPS do período", fmt_nps(nps_at["valor_nps"])),
            ("💬 Respostas", fmt_int(len(resp))),
            ("⭐ Nota média", f"{resp['nota'].mean():.1f}".replace(".", ",")),
            ("✍️ Com comentário", f"{com_texto:.0%}"),
            # baixa confiança fica fora das contagens
            ("🤖 Analisadas pela IA", fmt_int(int((resp["status_ia"] == "Concluída").sum()))),
        ])

        # -------------------------------------------------------- Distribuição
        with st.container(border=True):
            st.subheader("Distribuição das notas")
            dist = resp["nota"].value_counts().reindex(range(11), fill_value=0)
            barras = go.Figure(go.Bar(
                x=list(dist.index), y=list(dist.values),
                marker_color=[GREEN if n >= 9 else MUTED if n >= 7 else RED for n in dist.index],
                hovertemplate="Nota %{x}: %{y} respostas<extra></extra>",
            ))
            barras.update_layout(**PLOT_LAYOUT, height=280, bargap=0.25,
                                 margin=dict(t=10, b=10, l=10, r=10))
            barras.update_xaxes(title_text="Nota", tickmode="linear", dtick=1)
            barras.update_yaxes(title_text="Respostas")
            st.plotly_chart(barras, width="stretch", config=PLOT_CFG)

        # -------------------------------------------------------- Melhores x piores
        m1, m2 = st.columns(2)
        with m1, st.container(border=True):
            st.subheader("😊 Melhores respostas")
            st.markdown("".join(card_resposta(r) for r in ranquear(resp, True).itertuples()),
                        unsafe_allow_html=True)
        with m2, st.container(border=True):
            st.subheader("☹️ Piores respostas")
            st.markdown("".join(card_resposta(r) for r in ranquear(resp, False).itertuples()),
                        unsafe_allow_html=True)

        # -------------------------------------------------------- Reclamações por tema
        with st.container(border=True):
            st.subheader("🚨 Reclamações por tema (análise sugerida)")
            st.caption("Detratores e neutros com análise concluída, agrupados pelo tema sugerido.")
            reclamacoes = resp[(resp["status_ia"] == "Concluída") & (resp["faixa"] != "Promotor")
                               & resp["tema_ia"].notna()]
            if reclamacoes.empty:
                st.info("Ainda não há reclamações analisadas pelo worker de IA neste período.")
            else:
                resumo = (
                    reclamacoes.groupby("tema_ia")
                    .agg(reclamacoes=("id", "size"),
                         detratores=("faixa", lambda f: (f == "Detrator").sum()),
                         nota_media=("nota", "mean"))
                    .reindex(list(TEMA_LABEL.values()), fill_value=0)
                    .reset_index(names="tema")
                )
                resumo["nota_media"] = resumo["nota_media"].where(resumo["reclamacoes"] > 0)
                resumo["pct"] = resumo["reclamacoes"] / resumo["reclamacoes"].sum()
                resumo = resumo.sort_values("reclamacoes", ascending=False)

                st.dataframe(
                    resumo, hide_index=True, width="stretch",
                    column_config={
                        "tema": "Tema",
                        "reclamacoes": st.column_config.NumberColumn("Reclamações", format="%d"),
                        "detratores": st.column_config.NumberColumn("Detratores", format="%d"),
                        "nota_media": st.column_config.NumberColumn("Nota média", format="%.1f"),
                        "pct": st.column_config.ProgressColumn(
                            "% das reclamações", min_value=0, max_value=1, format="percent"),
                    },
                )
                for tema in resumo.loc[resumo["reclamacoes"] > 0, "tema"]:
                    grupo = reclamacoes[reclamacoes["tema_ia"] == tema].sort_values(
                        ["nota", "data"], ascending=[True, False])
                    with st.expander(f"{tema} · {len(grupo)} resposta(s)"):
                        st.dataframe(
                            grupo, hide_index=True, width="stretch",
                            column_order=["data", "nota", "faixa", "comentario",
                                          "justificativa_ia", "confianca_ia"],
                            column_config={
                                "data": st.column_config.DateColumn("Data", format="DD/MM/YYYY"),
                                "nota": st.column_config.NumberColumn("Nota", format="%d"),
                                "faixa": "Faixa",
                                "comentario": st.column_config.TextColumn("Comentário", width="large"),
                                "justificativa_ia": st.column_config.TextColumn(
                                    "Justificativa (sugerida)", width="large"),
                                "confianca_ia": st.column_config.ProgressColumn(
                                    "Confiança", min_value=0, max_value=1, format="percent"),
                            },
                        )

        # -------------------------------------------------------- Todas as respostas
        with st.container(border=True):
            t1, t2, t3 = st.columns([2, 3, 1], vertical_alignment="center")
            t1.subheader("Todas as respostas")
            faixa_sel = t2.segmented_control(
                "Faixa", ["Todas", "Promotor", "Neutro", "Detrator"],
                default="Todas", key="rs_faixa", label_visibility="collapsed",
            )
            tabela = resp if faixa_sel in (None, "Todas") else resp[resp["faixa"] == faixa_sel]
            tabela = tabela.sort_values("data", ascending=False)

            # Comentários vêm do cliente: o CSV aberto no Excel não pode
            # executar fórmula (=, +, -, @ no início viram texto). Os
            # comentários já chegam anonimizados da API.
            exp = tabela[["data", "nota", "faixa", "comentario", "sentimento_ia", "tema_ia"]].copy()
            exp["comentario"] = exp["comentario"].where(
                ~exp["comentario"].str.match(r"^[=+\-@]"), "'" + exp["comentario"]
            )
            t3.download_button(
                "⬇ Exportar",
                exp.to_csv(index=False, sep=";", date_format="%d/%m/%Y").encode("utf-8-sig"),
                "respostas_nps.csv", "text/csv", width="stretch",
            )

            st.dataframe(
                tabela, hide_index=True, width="stretch",
                column_order=["data", "nota", "faixa", "comentario", "sentimento_ia", "tema_ia",
                              "confianca_ia", "status_ia", "justificativa_ia"],
                column_config={
                    "data": st.column_config.DateColumn("Data", format="DD/MM/YYYY"),
                    "nota": st.column_config.NumberColumn("Nota", format="%d"),
                    "faixa": "Faixa",
                    "comentario": st.column_config.TextColumn("Comentário", width="large"),
                    "sentimento_ia": "Sentimento (sugerido)",
                    "tema_ia": "Tema (sugerido)",
                    "confianca_ia": st.column_config.ProgressColumn(
                        "Confiança", min_value=0, max_value=1, format="percent"),
                    "status_ia": "Status da análise",
                    "justificativa_ia": st.column_config.TextColumn("Justificativa (sugerida)",
                                                                    width="large"),
                },
            )
            st.caption(AVISO_IA)

with tab_tags:
    dados = atual

    with st.container(border=True):
        h1, h3, h4 = st.columns([1, 4, 1], vertical_alignment="center")
        h1.subheader("Tags")
        busca = h3.text_input("Buscar tags", placeholder="🔍 Buscar tags...",
                              label_visibility="collapsed")

        # tags fixas: a lista fechada de temas da IA. Ela só sugere a qual tag
        # cada comentário pertence; baixa confiança fica fora das contagens
        analisadas_tg = dados[dados["status_ia"] == "Concluída"]
        tags = resumo_tags(analisadas_tg, "tema_ia", list(TEMA_LABEL.values()))
        if busca:
            tags = tags[tags["nome"].str.contains(busca, case=False, regex=False)]

        # ";" como separador: o Excel em português abre direto em colunas
        csv = tags[["nome", "respostas", "score", "sentimento"]].rename(
            columns={"nome": "Nome", "respostas": "Respostas",
                     "score": "Pontuação", "sentimento": "Sentimento"}
        ).to_csv(index=False, sep=";", decimal=",").encode("utf-8-sig")
        h4.download_button("⬇ Exportar", csv, "tags_nps.csv", "text/csv", width="stretch")

        n_texto = int((dados["comentario"].str.strip() != "").sum())
        st.caption(
            f"🤖 Tags pela análise sugerida: {len(analisadas_tg)} de {n_texto} comentários do "
            "período classificados pelo worker de IA. A pontuação por tag segue a mesma regra "
            "do NPS da API, aplicada só às respostas daquele tema."
        )

        if tags.empty:
            st.info("Nenhuma tag encontrada.")
        else:
            rows = ""
            for t in tags.itertuples():
                cor = SENT_COLOR.get(t.sentimento, MUTED)
                rows += (
                    '<div class="tags-row">'
                    f'<div class="c-name">{escape(t.nome)}</div>'
                    f'<div class="c-resp"><span class="lbl">Respostas</span>{t.respostas}</div>'
                    f'<div class="c-score"><span class="lbl">Pontuação</span>{fmt_nps(t.score)}</div>'
                    '<div class="c-bar"><div class="bar">'
                    f'<span style="width:{t.pro:.1f}%;background:{GREEN}"></span>'
                    f'<span style="width:{t.pas:.1f}%;background:{GRAY}"></span>'
                    f'<span style="width:{t.det:.1f}%;background:{RED}"></span>'
                    "</div></div>"
                    f'<div class="c-sent"><span class="lbl">Sentimento</span>'
                    f'<span class="dot" style="background:{cor}"></span>{escape(t.sentimento)}</div>'
                    '<div class="menu">⋮</div>'
                    "</div>"
                )
            st.markdown(
                '<div class="tags-table"><div class="tags-head">'
                "<div>Nome</div><div>Respostas</div><div>Pontuação</div>"
                "<div></div><div>Sentimento</div><div></div></div>"
                f"{rows}</div>",
                unsafe_allow_html=True,
            )
