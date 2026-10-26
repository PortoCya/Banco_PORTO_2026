"""
Dashboard NPS KeyCore (Streamlit + Plotly) - responsivo, tema claro e escuro

Instalar:  pip install -r requirements-dashboard.txt
Rodar:     streamlit run dashboard/nps_dashboard.py   (a partir da raiz do projeto,
           para pegar o tema de .streamlit/config.toml)
"""
from html import escape

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots

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


SENT_COLOR = {"Positivo": GREEN, "Neutro": MUTED, "Negativo": RED}
FAIXA_COLOR = {"Promotor": GREEN, "Neutro": MUTED, "Detrator": RED}

# Comentários de exemplo por faixa ("" = respondeu só a nota)
_COMENTARIOS = {
    "Promotor": [
        "Atendimento excelente, resolveram meu problema no mesmo dia.",
        "A plataforma é muito fácil de usar, recomendo para todo mundo.",
        "Entrega antes do prazo e produto de ótima qualidade.",
        "Suporte rápido e atencioso, superou minhas expectativas.",
        "Melhor custo-benefício que já encontrei no mercado.",
        "",
    ],
    "Neutro": [
        "Bom produto, mas o preço poderia ser menor.",
        "Funciona bem, porém a interface é um pouco confusa.",
        "O prazo de entrega atrasou alguns dias.",
        "Atende ao básico, sem grandes diferenciais.",
        "",
    ],
    "Detrator": [
        "Demoraram uma semana para responder meu chamado.",
        "O sistema caiu várias vezes durante o mês.",
        "Cobrança indevida e ninguém resolve.",
        "Produto chegou com defeito e a troca foi um sofrimento.",
        "Muito caro para o que entrega.",
        "",
    ],
}


def faixa_nps(nota: int) -> str:
    return "Promotor" if nota >= 9 else "Neutro" if nota >= 7 else "Detrator"


@st.cache_data
def load_respostas(seed: int = 11, n: int = 120) -> pd.DataFrame:
    """
    Dados mock das respostas. Troque por consulta ao banco/API.

    As colunas *_ia ficam vazias até a camada de IA existir. Ela vai preencher
    a análise sugerida (sentimento, tema, confiança, justificativa) sem nunca
    alterar a nota nem o NPS.
    """
    rng = np.random.default_rng(seed)
    hoje = pd.Timestamp.today().normalize()
    notas = rng.choice(11, size=n, p=[.03, .02, .03, .03, .04, .05, .07, .10, .13, .20, .30])
    rows = []
    for i, nota in enumerate(notas):
        faixa = faixa_nps(int(nota))
        rows.append({
            "id": f"R{i + 1:04d}",
            "data": hoje - pd.Timedelta(days=int(rng.integers(0, 90))),
            "nota": int(nota),
            "faixa": faixa,
            "comentario": str(rng.choice(_COMENTARIOS[faixa])),
            "segmento": str(rng.choice(["Empresarial", "PME", "Gratuito"])),
            "empresa": str(rng.choice(["Empresa A", "Empresa B"])),
            "sentimento_ia": None,
            "tema_ia": None,
            "confianca_ia": None,
            "justificativa_ia": None,
        })
    return pd.DataFrame(rows)


def aplicar_filtros(df: pd.DataFrame, seg: str, emp: str, per: str) -> pd.DataFrame:
    dias = {"Últimos 7 dias": 7, "Últimos 30 dias": 30, "Últimos 90 dias": 90}[per]
    df = df[df["data"] >= pd.Timestamp.today().normalize() - pd.Timedelta(days=dias)]
    if not seg.startswith("Todos"):
        df = df[df["segmento"] == seg]
    if not emp.startswith("Todas"):
        df = df[df["empresa"] == emp]
    return df


def ranquear(df: pd.DataFrame, melhores: bool, n: int = 5) -> pd.DataFrame:
    """
    Melhores/piores respostas com comentário.

    Hoje ordena pela nota e, no empate, pela mais recente. Quando a IA existir,
    o desempate pode usar o sentimento sugerido (só com confiança >= 0,6),
    sem nunca mudar a nota.
    """
    com_texto = df[df["comentario"].str.strip() != ""]
    return com_texto.sort_values(
        ["nota", "data"], ascending=[not melhores, False]
    ).head(n)


def render_filters(key: str) -> tuple[str, str, str]:
    """Filtros de segmento, empresa e período (3 colunas; empilham no mobile)."""
    f1, f2, f3 = st.columns(3)
    seg = f1.selectbox("Segmento", ["Todos os segmentos", "Empresarial", "PME", "Gratuito"],
                       key=f"{key}_seg")
    emp = f2.selectbox("Empresa", ["Todas as empresas", "Empresa A", "Empresa B"],
                       key=f"{key}_emp")
    per = f3.selectbox("Período", ["Últimos 7 dias", "Últimos 30 dias", "Últimos 90 dias"],
                       key=f"{key}_per")
    return seg, emp, per


def kpi_grid(itens: list[tuple[str, str]]) -> None:
    """Cards de indicador sem variação (título, valor)."""
    cards = "".join(
        f'<div class="kpi"><div class="t">{t}</div>'
        f'<div class="row"><span class="v">{v}</span></div></div>'
        for t, v in itens
    )
    st.markdown(f'<div class="kpi-grid">{cards}</div>', unsafe_allow_html=True)


def card_resposta(r) -> str:
    """Card de uma resposta. Comentário vem do cliente: sempre escapado."""
    cor = FAIXA_COLOR[r.faixa]
    ia = (
        f"{escape(r.sentimento_ia)} · {escape(r.tema_ia)}"
        if r.sentimento_ia else "pendente"
    )
    return (
        '<div class="resp-card">'
        f'<div class="resp-top"><span class="nota" style="background:{cor}">{r.nota}</span>'
        f'<span class="resp-meta">{r.faixa} · {r.data:%d/%m/%Y} · {escape(r.empresa)}</span></div>'
        f'<div class="resp-txt">“{escape(r.comentario)}”</div>'
        f'<div class="resp-ia">🤖 Análise sugerida: {ia}</div>'
        "</div>"
    )


# ---------------------------------------------------------------- cabeçalho
col_title, col_btn = st.columns([5, 1], vertical_alignment="center")
col_title.title("NPS")
col_btn.button("Editar NPS", type="primary", width="stretch")

tab_overview, tab_responses, tab_tags = st.tabs(["Visão geral", "Respostas", "Tags"])

with tab_overview:
    render_filters("ov")

    # ------------------------------------------------------------ KPIs
    kpis = [
        ("👁 Total exibido", "2.000", 3),
        ("💬 Total de respostas", "1.200", 30),
        ("📈 Taxa de resposta", "3,5%", 2),
        ("⊗ Dispensadas", "800", 4),
        ("✅ Respostas qualitativas", "400", -4),
    ]
    cards = ""
    for title, value, delta in kpis:
        color = UP if delta >= 0 else DOWN
        arrow = "↑" if delta >= 0 else "↓"
        cards += (
            f'<div class="kpi"><div class="t">{title}</div>'
            f'<div class="row"><span class="v">{value}</span>'
            f'<span class="d" style="color:{color}">{arrow} {abs(delta)}%</span>'
            f"</div></div>"
        )
    st.markdown(f'<div class="kpi-grid">{cards}</div>', unsafe_allow_html=True)

    # ------------------------------------------------------------ Pontuação + Respostas
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
            ("😐", "Neutros", passives, MUTED),
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
        # barras empilhadas (% de respostas) -> eixo secundário
        fig.add_bar(x=df["period"], y=pct("detractors"), name="Detratores",
                    marker_color=RED, secondary_y=True)
        fig.add_bar(x=df["period"], y=pct("passives"), name="Neutros",
                    marker_color=GRAY, secondary_y=True)
        fig.add_bar(x=df["period"], y=pct("promoters"), name="Promotores",
                    marker_color=GREEN, secondary_y=True)

        # linha de pontuação: sólida até o penúltimo ponto, tracejada no último
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
    resp = aplicar_filtros(load_respostas(), *render_filters("rs"))

    if resp.empty:
        st.info("Nenhuma resposta para os filtros escolhidos.")
    else:
        # -------------------------------------------------------- Resumo
        cont = resp["faixa"].value_counts()
        com_texto = (resp["comentario"].str.strip() != "").mean()
        nps = calc_nps(cont.get("Promotor", 0), cont.get("Neutro", 0), cont.get("Detrator", 0))
        kpi_grid([
            ("📊 NPS do período", f"{nps:.1f}".replace(".", ",")),
            ("💬 Respostas", f"{len(resp)}"),
            ("⭐ Nota média", f"{resp['nota'].mean():.1f}".replace(".", ",")),
            ("✍️ Com comentário", f"{com_texto:.0%}"),
            ("🤖 Analisadas pela IA", f"{resp['sentimento_ia'].notna().sum()}"),
        ])

        # -------------------------------------------------------- Distribuição
        with st.container(border=True):
            st.subheader("Distribuição das notas")
            dist = resp["nota"].value_counts().reindex(range(11), fill_value=0)
            barras = go.Figure(go.Bar(
                x=list(dist.index), y=list(dist.values),
                marker_color=[FAIXA_COLOR[faixa_nps(n)] for n in dist.index],
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
            # executar fórmula (=, +, -, @ no início viram texto)
            exp = tabela[["data", "nota", "faixa", "comentario", "empresa", "segmento"]].copy()
            exp["comentario"] = exp["comentario"].where(
                ~exp["comentario"].str.match(r"^[=+\-@]"), "'" + exp["comentario"]
            )
            t3.download_button(
                "⬇ Exportar",
                exp.to_csv(index=False, sep=";", date_format="%d/%m/%Y").encode("utf-8-sig"),
                "respostas_nps.csv", "text/csv", width="stretch",
            )

            st.dataframe(
                tabela,
                hide_index=True,
                width="stretch",
                column_order=["data", "nota", "faixa", "comentario", "empresa",
                              "sentimento_ia", "tema_ia", "confianca_ia"],
                column_config={
                    "data": st.column_config.DateColumn("Data", format="DD/MM/YYYY"),
                    "nota": st.column_config.NumberColumn("Nota", format="%d"),
                    "faixa": "Faixa",
                    "comentario": st.column_config.TextColumn("Comentário", width="large"),
                    "empresa": "Empresa",
                    "sentimento_ia": "Sentimento (sugerido)",
                    "tema_ia": "Tema (sugerido)",
                    "confianca_ia": st.column_config.ProgressColumn(
                        "Confiança", min_value=0, max_value=1, format="percent"),
                },
            )
            st.caption(
                "🤖 As colunas *sugerido* e *Confiança* serão preenchidas pela análise de IA. "
                "A IA só sugere: nunca altera a nota nem o NPS."
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

        # ";" como separador: o Excel em português abre direto em colunas
        csv = tags[["nome", "respostas", "score", "sentimento"]].rename(
            columns={"nome": "Nome", "respostas": "Respostas",
                     "score": "Pontuação", "sentimento": "Sentimento"}
        ).to_csv(index=False, sep=";").encode("utf-8-sig")
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
