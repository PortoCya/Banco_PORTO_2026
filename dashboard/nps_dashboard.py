"""
Dashboard NPS KeyCore (Streamlit + Plotly) - responsivo, tema claro

Instalar:  pip install streamlit plotly pandas numpy
Rodar:     streamlit run dashboard/nps_dashboard.py
(o tema claro vem de dashboard/.streamlit/config.toml; rode a partir da
pasta dashboard/ ou copie a pasta .streamlit para a raiz do projeto)
"""
from html import escape

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots

from gemini_service import GeminiIndisponivel, classificar_respostas, gerar_insights

st.set_page_config(page_title="NPS", layout="wide")

GREEN, GRAY, RED, BLUE, INK = "#00C060", "#D4D4D8", "#F25555", "#3F6FA0", "#1F2937"

st.markdown(
    """
    <style>
    :root { color-scheme: light; }
    .stApp { background:#F4F4F5; color:#1F2937; }
    .block-container { padding: 1.5rem 2rem 3rem; max-width: 1400px; }

    /* cards (st.container(border=True)) */
    [data-testid="stVerticalBlockBorderWrapper"] {
        background:#fff; border:none; border-radius:8px;
        box-shadow:0 1px 3px rgba(0,0,0,.08);
    }

    /* KPIs: grid que quebra sozinho conforme a largura */
    .kpi-grid { display:grid; gap:16px; margin:8px 0 16px;
                grid-template-columns:repeat(auto-fit, minmax(170px, 1fr)); }
    .kpi { background:#fff; border-radius:8px; padding:16px 18px;
           box-shadow:0 1px 3px rgba(0,0,0,.08); }
    .kpi .t { color:#444; font-size:.9rem; }
    .kpi .row { display:flex; justify-content:space-between;
                align-items:baseline; margin-top:8px; }
    .kpi .v { font-size:1.6rem; font-weight:600; }
    .kpi .d { font-size:.8rem; font-weight:600; }

    /* legenda do donut */
    .legend-item { margin:14px 0; font-size:1.05rem; }

    /* mobile */
    @media (max-width: 640px) {
        .block-container { padding: 1rem .75rem 2rem; }
        .kpi-grid { grid-template-columns: repeat(2, 1fr); gap:10px; }
        .kpi { padding:12px; }
        .kpi .v { font-size:1.3rem; }
        h1 { font-size:1.6rem !important; }
    }

    /* ---------- tabela de tags ---------- */
    .tags-table { width:100%; margin-top:8px; }
    .tags-head, .tags-row {
        display:grid; align-items:center; column-gap:16px;
        grid-template-columns: 2.2fr 1fr 1fr 3fr 1.3fr 32px;
        padding: 0 20px;
    }
    .tags-head { background:#EDEDF0; height:56px; font-weight:600; color:#333; }
    .tags-row { min-height:84px; border-bottom:1px solid #ECECEF; color:#222; }
    .tags-row:hover { background:#FAFAFB; }
    .tags-row a { color:#4F46E5; text-decoration:underline; font-weight:500; }
    .tags-row .menu { text-align:center; font-size:1.4rem; color:#333; }
    .bar { display:flex; height:7px; border-radius:4px; overflow:hidden; background:#eee; }
    .bar span { display:block; height:100%; }
    .dot { display:inline-block; width:8px; height:8px; border-radius:50%; margin-right:6px; }
    .lbl { display:none; }

    @media (max-width: 760px) {
        .tags-head { display:none; }
        .tags-row {
            grid-template-columns: 1fr 1fr 1fr; row-gap:8px; padding:14px 12px;
            grid-template-areas: "name name menu" "resp score sent" "bar bar bar";
        }
        .tags-row .c-name  { grid-area:name; font-weight:600; }
        .tags-row .c-resp  { grid-area:resp; }
        .tags-row .c-score { grid-area:score; }
        .tags-row .c-sent  { grid-area:sent; }
        .tags-row .c-bar   { grid-area:bar; }
        .tags-row .menu    { grid-area:menu; text-align:right; }
        .lbl { display:block; font-size:.7rem; color:#777; text-transform:uppercase; }
    }
    </style>
    """,
    unsafe_allow_html=True,
)

PLOT_LAYOUT = dict(
    template="plotly_white",
    paper_bgcolor="rgba(0,0,0,0)",
    plot_bgcolor="rgba(0,0,0,0)",
    font=dict(color=INK),
    autosize=True,
)
PLOT_CFG = {"displayModeBar": False, "responsive": True}


# ---------------------------------------------------------------- dados
def calc_nps(promoters: int, passives: int, detractors: int) -> float:
    total = promoters + passives + detractors
    return round((promoters - detractors) / total * 100, 1) if total else 0.0


@st.cache_data
def load_history(seed: int = 7) -> pd.DataFrame:
    """Dados mock do histórico. Troque por consulta ao banco/API."""
    rng = np.random.default_rng(seed)
    periods = pd.date_range(end=pd.Timestamp.today().normalize(), periods=7, freq="W")
    rows = []
    for p in periods:
        total = int(rng.integers(150, 400))
        pro = rng.uniform(0.30, 0.75)
        det = rng.uniform(0.05, 0.30)
        rows.append(
            {
                "period": p.strftime("%d/%m"),
                "promoters": int(total * pro),
                "detractors": int(total * det),
                "passives": total - int(total * pro) - int(total * det),
            }
        )
    df = pd.DataFrame(rows)
    df["total"] = df[["promoters", "passives", "detractors"]].sum(axis=1)
    df["score"] = df.apply(
        lambda r: calc_nps(r.promoters, r.passives, r.detractors), axis=1
    )
    return df


def render_filters(key: str) -> None:
    """Filtros de segmento, empresa e período (3 colunas; empilham no mobile)."""
    f1, f2, f3 = st.columns(3)
    f1.selectbox("Segmento", ["Todos os segmentos", "Empresarial", "PME", "Gratuito"],
                 key=f"{key}_seg")
    f2.selectbox("Empresa", ["Todas as empresas", "Empresa A", "Empresa B"],
                 key=f"{key}_emp")
    f3.selectbox("Período", ["Últimos 7 dias", "Últimos 30 dias", "Últimos 90 dias"],
                 key=f"{key}_per")


@st.cache_data
def load_tags() -> pd.DataFrame:
    """Dados mock das tags. Troque por consulta ao banco/API."""
    rows = [  # nome, respostas, % promotores, % neutros, % detratores
        ("Bugs", 100, 15, 29, 56),
        ("Melhorias de UX", 50, 20, 45, 35),
        ("Responsividade", 100, 15, 29, 56),
        ("Solicitação de nova funcionalidade", 100, 60, 10, 30),
        ("Solicitação de funcionalidade experimental", 100, 0, 0, 100),
        ("Desempenho", 80, 25, 20, 55),
        ("Atendimento", 120, 70, 20, 10),
    ]
    df = pd.DataFrame(rows, columns=["nome", "respostas", "pro", "pas", "det"])
    df["score"] = df["pro"] - df["det"]
    df["sentimento"] = df["score"].apply(
        lambda v: "Positivo" if v > 20 else "Negativo" if v < -20 else "Neutro"
    )
    return df


COMENTARIOS_EXEMPLO = [
    "O app trava toda vez que tento exportar o relatório.",
    "Adorei a nova interface, ficou muito mais fácil de usar!",
    "O suporte demorou três dias para responder.",
    "Funciona bem, mas faltam mais filtros no dashboard.",
    "Está lento no celular, as páginas demoram a carregar.",
]


SENT_COLOR = {"Positivo": GREEN, "Neutro": "#9CA3AF", "Negativo": RED}


# ---------------------------------------------------------------- cabeçalho
col_title, col_btn = st.columns([5, 1], vertical_alignment="center")
col_title.title("NPS")
col_btn.button("Editar NPS", type="primary", width="stretch")

tab_overview, tab_responses, tab_tags = st.tabs(["Visão geral", "Respostas", "Tags"])

with tab_overview:
    # Filtros: 3 colunas no desktop, empilham sozinhas no mobile
    render_filters("ov")

    # ------------------------------------------------------------ KPIs
    kpis = [
        ("👁 Total exibido", "2.000", 3),
        ("💬 Total de respostas", "1.200", 30),
        ("📈 Taxa de resposta", "3.5", 2),
        ("⊗ Dispensadas", "800", 4),
        ("✅ Respostas qualitativas", "400", -4),
    ]
    cards = ""
    for title, value, delta in kpis:
        color = "#15803d" if delta >= 0 else "#dc2626"
        arrow = "↑" if delta >= 0 else "↓"
        cards += (
            f'<div class="kpi"><div class="t">{title}</div>'
            f'<div class="row"><span class="v">{value}</span>'
            f'<span class="d" style="color:{color}">{arrow} {abs(delta)}%</span>'
            f"</div></div>"
        )
    st.markdown(f'<div class="kpi-grid">{cards}</div>', unsafe_allow_html=True)

    # ------------------------------------------------------------ Score + Responses
    promoters, passives, detractors = 612, 101, 101
    score = calc_nps(promoters, passives, detractors)
    total = promoters + passives + detractors

    c1, c2 = st.columns(2)

    with c1, st.container(border=True):
        st.subheader("Pontuação")
        gauge = go.Figure(
            go.Indicator(
                mode="gauge+number",
                value=score,
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
            ("😐", "Neutros", passives, "#999"),
            ("☹️", "Detratores", detractors, RED),
        ]:
            legend += (
                f'<div class="legend-item"><span style="color:{color}">{icon}</span> '
                f"{label}<br><b>{val} ({val / total:.0%})</b></div>"
            )
        d2.markdown(legend, unsafe_allow_html=True)

    # ------------------------------------------------------------ Histórico
    with st.container(border=True):
        st.subheader("Histórico do NPS")
        df = load_history()
        pct = lambda col: df[col] / df["total"] * 100

        fig = make_subplots(specs=[[{"secondary_y": True}]])
        fig.add_bar(x=df["period"], y=pct("detractors"), name="Detratores",
                    marker_color=RED, secondary_y=True)
        fig.add_bar(x=df["period"], y=pct("passives"), name="Neutros",
                    marker_color=GRAY, secondary_y=True)
        fig.add_bar(x=df["period"], y=pct("promoters"), name="Promotores",
                    marker_color=GREEN, secondary_y=True)

        # linha de score: sólida até o penúltimo ponto, tracejada no último
        fig.add_scatter(x=df["period"][:-1], y=df["score"][:-1], name="Pontuação",
                        mode="lines+markers", line=dict(color=INK, shape="spline"),
                        secondary_y=False)
        fig.add_scatter(x=df["period"][-2:], y=df["score"][-2:], showlegend=False,
                        mode="lines+markers", line=dict(color=INK, dash="dash"),
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

    # ------------------------------------------------------------ Insights com IA
    with st.container(border=True):
        st.subheader("✨ Insights com IA")
        if st.button("Gerar insights", key="btn_ins_ov"):
            metricas = {
                "pontuacao_nps": score,
                "promotores": promoters,
                "neutros": passives,
                "detratores": detractors,
                "kpis": {t: f"{v} ({d:+d}%)" for t, v, d in kpis},
                "historico_semanal": df[
                    ["period", "promoters", "passives", "detractors", "score"]
                ].to_dict("records"),
            }
            with st.spinner("Analisando com o Gemini..."):
                try:
                    st.session_state["ins_ov"] = gerar_insights(
                        "Analise o desempenho do NPS no período e a tendência do histórico.",
                        metricas,
                    )
                except GeminiIndisponivel as e:
                    st.error(str(e))
        if "ins_ov" in st.session_state:
            st.markdown(st.session_state["ins_ov"])

with tab_responses:
    render_filters("rs")

    with st.container(border=True):
        st.subheader("Respostas qualitativas")
        texto = st.text_area(
            "Comentários (um por linha)",
            value="\n".join(COMENTARIOS_EXEMPLO),
            height=160,
        )
        comentarios = [c.strip() for c in texto.splitlines() if c.strip()][:50]
        st.caption(
            f"{len(comentarios)} comentário(s). Ao classificar, os textos são enviados "
            "à API do Gemini: evite dados pessoais (LGPD)."
        )

        if st.button("✨ Classificar com IA", key="btn_classif", disabled=not comentarios):
            with st.spinner("Classificando com o Gemini..."):
                try:
                    res = classificar_respostas(comentarios)
                    por_id = {r["id"]: r for r in res}
                    st.session_state["resp_ia"] = pd.DataFrame(
                        {
                            "Comentário": comentarios,
                            "Sentimento": [
                                por_id.get(i, {}).get("sentimento", "-")
                                for i in range(1, len(comentarios) + 1)
                            ],
                            "Tags": [
                                ", ".join(por_id.get(i, {}).get("tags", []))
                                for i in range(1, len(comentarios) + 1)
                            ],
                            "Resumo": [
                                por_id.get(i, {}).get("resumo", "")
                                for i in range(1, len(comentarios) + 1)
                            ],
                        }
                    )
                except GeminiIndisponivel as e:
                    st.error(str(e))

        if "resp_ia" in st.session_state:
            st.dataframe(
                st.session_state["resp_ia"],
                hide_index=True,
                width="stretch",
            )

with tab_tags:
    render_filters("tg")

    with st.container(border=True):
        h1, h2, h3 = st.columns([1, 3, 1], vertical_alignment="center")
        h1.subheader("Tags")
        busca = h2.text_input("Buscar tags", placeholder="🔍 Buscar tags...",
                              label_visibility="collapsed")

        tags = load_tags()
        if busca:
            tags = tags[tags["nome"].str.contains(busca, case=False, regex=False)]

        csv = tags[["nome", "respostas", "score", "sentimento"]].rename(
            columns={"nome": "Nome", "respostas": "Respostas",
                     "score": "Pontuação", "sentimento": "Sentimento"}
        ).to_csv(index=False).encode("utf-8-sig")
        h3.download_button("⬇ Exportar", csv, "tags_nps.csv", "text/csv",
                           width="stretch")

        if tags.empty:
            st.info("Nenhuma tag encontrada.")
        else:
            rows = ""
            for t in tags.itertuples():
                cor = SENT_COLOR[t.sentimento]
                rows += (
                    '<div class="tags-row">'
                    f'<div class="c-name">{escape(t.nome)}</div>'
                    f'<div class="c-resp"><span class="lbl">Respostas</span>'
                    f'<a href="#">{t.respostas}</a></div>'
                    f'<div class="c-score"><span class="lbl">Pontuação</span>{t.score}</div>'
                    '<div class="c-bar"><div class="bar">'
                    f'<span style="width:{t.pro}%;background:{GREEN}"></span>'
                    f'<span style="width:{t.pas}%;background:{GRAY}"></span>'
                    f'<span style="width:{t.det}%;background:{RED}"></span>'
                    "</div></div>"
                    f'<div class="c-sent"><span class="lbl">Sentimento</span>'
                    f'<span class="dot" style="background:{cor}"></span>{t.sentimento}</div>'
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

    with st.container(border=True):
        st.subheader("✨ Resumo das tags com IA")
        if st.button("Resumir tags", key="btn_ins_tags", disabled=tags.empty):
            dados = tags[["nome", "respostas", "score", "sentimento"]].to_dict("records")
            with st.spinner("Analisando com o Gemini..."):
                try:
                    st.session_state["ins_tags"] = gerar_insights(
                        "Resuma quais temas (tags) mais impactam o NPS e o que priorizar.",
                        {"tags": dados},
                    )
                except GeminiIndisponivel as e:
                    st.error(str(e))
        if "ins_tags" in st.session_state:
            st.markdown(st.session_state["ins_tags"])