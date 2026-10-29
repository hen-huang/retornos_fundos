"""Painel da prévia de cotas, identidade Hedge Investments. Uso: streamlit run painel.py"""
import html
import io
from pathlib import Path

import altair as alt
import numpy as np
import pandas as pd
import streamlit as st

import previa as pv

_PRECISA = ["ordenar_estrategias", "todas_janelas", "rot", "carregar_calibracao", "calibracao", "APELIDOS",
            "FUNDOS_INCLUIR", "ORDEM_ESTRATEGIAS", "hoje_br"]
_faltam = [n for n in _PRECISA if not hasattr(pv, n)]
if _faltam:
    import importlib
    pv = importlib.reload(pv)
    _faltam = [n for n in _PRECISA if not hasattr(pv, n)]
if _faltam:
    st.error("O previa.py em uso está desatualizado em relação ao painel.py. Confira se a versão nova está no "
             "GitHub (ela contém FUNDOS_INCLUIR). Se já estiver, reinicie o app em Manage app → Reboot app. "
             "Faltam: " + ", ".join(_faltam))
    st.stop()

COR = {
    "marinho": "#0A4263", "tinta": "#0B2C42", "azul": "#00A0D7", "celeste": "#81C1D7", "petroleo": "#145A75",
    "verde": "#3F7A1F", "vermelho": "#B83A00", "laranja": "#F98909", "cinza": "#5F6B75", "linha": "#D5E0E8",
    "fundo": "#EEF3F7", "zebra": "#F7FAFC",
}
JAN = list(getattr(pv, "MODELOS", pv.JANELAS))
TODAS = pv.todas_janelas()
COR_JANELA = {"1m": "#B9DCE8", "2m": COR["celeste"], "3m": COR["azul"], "6m": "#2BA9B4", "12m": COR["petroleo"],
              "24m": COR["marinho"], "ew": "#5F6B75", "EW": "#5F6B75",
              "comb": COR["laranja"], "combinada": COR["laranja"], "só CDI": "#B8C2CA"}
FONTE = "'Compass', 'Compass Sans', 'Compass Pro', 'Segoe UI', 'Helvetica Neue', Arial, sans-serif"
AMPLITUDE_MIN = 0.0025
NOMES_FATOR = {"IBOV": "Ibovespa", "SMLL": "Small caps", "USD": "Dólar", "SPX": "S&P 500", "IFIX": "IFIX",
               "NDX": "Nasdaq", "BRENT": "Petróleo Brent", "OURO": "Ouro", "EEM": "Emergentes (EEM)",
               "TX_UST10": "Treasury 10a", "SPX_L1": "S&P 500 (D-1)", "USD_L1": "Dólar (D-1)",
               "IRFM": "IRF-M", "IMAB": "IMA-B"}

st.set_page_config(page_title="Prévia de cotas · Hedge Investments", layout="wide",
                   initial_sidebar_state="collapsed")


# Formatação pt-BR
def pct(x, casas=2, sinal=True):
    if x is None or pd.isna(x):
        return "–"
    if abs(x) < 0.5 * 10 ** -(casas + 2):
        x = 0.0
    s = f"{x * 100:+.{casas}f}" if sinal else f"{x * 100:.{casas}f}"
    return s.replace(".", ",") + "%"


def num(x, casas=0):
    if x is None or pd.isna(x):
        return "–"
    if abs(x) < 0.5 * 10 ** -casas:
        x = 0.0
    return f"{x:,.{casas}f}".replace(",", "§").replace(".", ",").replace("§", ".")


def data_br(d):
    return f"{d:%d/%m}"


def cls(v):
    return "" if v is None or pd.isna(v) else ("pos" if v > 0 else ("neg" if v < 0 else ""))


def esc(t):
    return html.escape(str(t))


def rot(j):
    return {"comb": "Comb", "ew": "EW"}.get(j, j)


import re as _re

_ABREV = [
    (r"FUNDO DE INVESTIMENTO FINANCEIRO EM COTAS DE FUNDOS DE INVESTIMENTO", "FIC FIF"),
    (r"FUNDO DE INVESTIMENTO EM COTAS DE FUNDOS DE INVESTIMENTO", "FIC FI"),
    (r"FUNDO DE INVESTIMENTO EM QUOTAS DE FUNDOS DE INVESTIMENTO", "FIC FI"),
    (r"FUNDO DE INVESTIMENTO FINANCEIRO", "FIF"), (r"FUNDO DE INVESTIMENTO IMOBILI[ÁA]RIO", "FII"),
    (r"FUNDO DE INVESTIMENTO EM COTAS", "FIC"), (r"FUNDO DE INVESTIMENTO EM QUOTAS", "FIC"),
    (r"FUNDO DE INVESTIMENTO", "FI"), (r"CLASSE DE INVESTIMENTO EM COTAS", "CIC"),
    (r"CLASSE DE INVESTIMENTO FINANCEIRO", "CIF"), (r"CLASSE DE INVESTIMENTO", "CI"), (r"CLASSE [ÚU]NICA", "Classe Única"),
    (r"DE COTAS DE FUNDOS DE INVESTIMENTO", "FIC"), (r"EM COTAS DE FUNDOS DE INVESTIMENTO", "FIC"),
    (r"RESPONSABILIDADE LIMITADA", "RL"), (r"RESP\.? LIMITADA", "RL"), (r"RESP\.? LTDA", "RL"),
    (r"CR[ÉE]DITO PRIVADO", "CP"), (r"CR[ÉE]D\.? PRIV\.?", "CP"), (r"MULTIMERCADO", "Mult"), (r"\bMULTI\b", "Mult"),
    (r"PREVIDENCI[ÁA]RIO", "Prev"), (r"INVESTIMENTO NO EXTERIOR", "IE"), (r"\bEM A[ÇC][ÕO]ES\b", "Ações"),
    (r"\bDE A[ÇC][ÕO]ES\b", "Ações"), (r"LONGO PRAZO", "LP"),
]
_SIGLAS = {"FIF", "FIC", "FI", "FII", "FIM", "FIA", "CIC", "CIF", "CI", "RL", "CP", "LP", "IE", "BDR", "XP", "BB", "BTG",
           "SPX", "WHG", "EUA", "DI", "ESG", "ETF", "PIMCO", "JGP", "ARX", "AZ", "BNP", "UBS", "BV", "HSBC", "IMA",
           "IMA-B", "IRF-M", "CDI", "ADR", "S&P", "USD", "BRL", "DTVM", "S.A.", "SA", "RF", "MM", "PB", "AM",
           "II", "III", "IV", "VI", "VII", "VIII", "IX", "XI", "XII", "PGBL", "VGBL", "CIA", "MSCI", "NY", "US",
           "FICFI", "FIFE", "IBRX", "IBX", "IBOV", "SMLL", "IDIV", "MLP", "LB", "LS", "LO", "AI", "TOP", "FOF"}


def abreviar(nome):
    """Nome completo com abreviações de mercado (FIF, FIC, RL, CP…), sem cortar palavras que distinguem fundos."""
    s = " " + _re.sub(r"\s+", " ", str(nome).upper().strip()) + " "
    s = _re.sub(r"\bFI FINANCEIRO\b", "FIF", s)
    for padrao, sub in _ABREV:
        s = _re.sub(padrao, sub.upper(), s)
    s = _re.sub(r"\s*-\s*(RL|CP|CI|CIC|CIF|CIA|FIC|FIF|IE)\b", r" \1", s)
    s = _re.sub(r"\s+", " ", s).strip(" -")
    out = []
    for w in s.split(" "):
        base = w.strip(",.()")
        if base in _SIGLAS or base.upper() in {x.upper() for x in _SIGLAS} or _re.fullmatch(r"[IVX]+", base) \
                or _re.search(r"\d", base):
            out.append(w.upper())
        elif base in {"DE", "DA", "DO", "DOS", "DAS", "E", "EM"}:
            out.append(w.lower())
        else:
            sig = {x.upper() for x in _SIGLAS}
            out.append("-".join(x.upper() if x.strip(",.()") in sig or _re.search(r"\d", x) else x.capitalize()
                                for x in w.split("-")))
    r = " ".join(out)
    return r[:1].upper() + r[1:]


def curto(nome, n=60):
    s = abreviar(nome)
    return s if len(s) <= n else s[:n - 1].rstrip() + "…"


def nome_td(nome, n=46):
    """Célula de nome para os painéis: abreviado, com o nome completo ao passar o mouse."""
    return f'<span title="{esc(nome)}">{esc(curto(nome, n))}</span>'


def apelido(cnpj, nome):
    return pv.APELIDOS.get(cnpj, curto(nome, 32))


# Estilo
def _font_faces() -> str:
    pasta = Path(__file__).resolve().parent / "static" / "fonts"
    pesos = {"thin": 100, "extralight": 200, "light": 300, "regular": 400, "book": 400, "medium": 500,
             "semibold": 600, "bold": 700, "extrabold": 800, "black": 900, "heavy": 900}
    formatos = {".woff2": "woff2", ".woff": "woff", ".ttf": "truetype", ".otf": "opentype"}
    css = []
    for f in sorted(pasta.glob("*")) if pasta.exists() else []:
        if f.suffix.lower() in formatos:
            nome = f.stem.lower().replace("-", "").replace("_", "")
            peso = next((p for k, p in sorted(pesos.items(), key=lambda kv: -len(kv[0])) if k in nome), 400)
            css.append(f"@font-face{{font-family:'Compass';src:url('app/static/fonts/{f.name}') "
                       f"format('{formatos[f.suffix.lower()]}');font-weight:{peso};"
                       f"font-style:{'italic' if 'italic' in nome else 'normal'};font-display:swap;}}")
    return "\n".join(css)


st.markdown(f"""
<style>
{_font_faces()}
html, body, .stApp, .stMarkdown, .stDataFrame, button, input, textarea, select, [data-testid="stSidebar"] {{
  font-family: {FONTE} !important; }}
.stApp {{ background: {COR["fundo"]}; color: {COR["tinta"]}; }}
[data-testid="stHeader"] {{ background: transparent; height: 0; }}
.block-container {{ padding: .6rem 1.2rem 2rem; max-width: 1600px; }}
[data-testid="stSidebar"] {{ background: #FFFFFF; border-right: 1px solid {COR["linha"]}; }}
[data-testid="stSidebar"] h2 {{ color: {COR["marinho"]}; font-size: .78rem; font-weight: 700; letter-spacing: .08em;
  text-transform: uppercase; margin: .8rem 0 .2rem; }}
[data-testid="stVerticalBlock"] {{ gap: .55rem; }}
[data-testid="stHorizontalBlock"] {{ gap: .55rem; }}
.n {{ font-variant-numeric: tabular-nums; }}
.pos {{ color: {COR["verde"]}; }} .neg {{ color: {COR["vermelho"]}; }}

.topo {{ display:flex; align-items:stretch; justify-content:space-between; background:{COR["marinho"]}; color:#fff;
  border-radius:3px 3px 0 0; overflow:hidden; border-bottom:3px solid {COR["azul"]}; }}
.topo .marca {{ padding:10px 18px; font-weight:700; font-size:1rem; letter-spacing:.02em; display:flex; align-items:center;
  gap:12px; }}
.topo .marca span {{ font-weight:400; color:{COR["celeste"]}; font-size:.9rem; }}
.topo .chips {{ display:flex; flex-wrap:wrap; }}
.topo .chip {{ padding:8px 16px; border-left:1px solid #1D5B7E; font-size:.74rem; line-height:1.25; color:{COR["celeste"]}; }}
.topo .chip b {{ display:block; color:#fff; font-size:.88rem; font-weight:600; }}
.topo .chip .vivo {{ display:inline-block; width:7px; height:7px; border-radius:50%; background:#7FD06B; margin-right:6px; }}
.topo .chip .parado {{ display:inline-block; width:7px; height:7px; border-radius:50%; background:#9AB0BF; margin-right:6px; }}

[data-testid="stMarkdownContainer"]:has(.pn), [data-testid="stMarkdownContainer"]:has(.topo) {{
  margin-bottom:0 !important; }}
.pn {{ background:#FFFFFF; border:1px solid {COR["linha"]}; border-radius:3px; overflow:hidden; }}
.pn-h {{ display:flex; justify-content:space-between; align-items:center; background:{COR["marinho"]}; color:#fff;
  padding:6px 12px; font-size:.74rem; font-weight:700; letter-spacing:.07em; text-transform:uppercase; }}
.pn-h small {{ font-weight:400; letter-spacing:0; text-transform:none; color:{COR["celeste"]}; font-size:.74rem; }}
.pn-b {{ padding:0; }}
.pn-p {{ padding:8px 12px; font-size:.78rem; color:{COR["cinza"]}; border-top:1px solid {COR["linha"]}; }}
table.t {{ width:100%; border-collapse:collapse; font-size:.8rem; margin:0; border:0 !important; }}
table.t tr {{ background:transparent !important; border:0 !important; }}
table.t th {{ font-size:.68rem; font-weight:600; color:{COR["cinza"]}; text-transform:uppercase; letter-spacing:.04em;
  padding:5px 8px; text-align:right; border:0 !important; border-bottom:1px solid {COR["linha"]} !important;
  background:{COR["zebra"]} !important; white-space:nowrap; }}
table.t td {{ padding:4px 8px; text-align:right; border:0 !important; border-bottom:1px solid #EDF2F6 !important;
  white-space:nowrap; font-variant-numeric: tabular-nums; vertical-align:middle; height:26px; }}
table.t th.l, table.t td.l {{ text-align:left; }}
table.t td.l {{ color:{COR["tinta"]}; overflow:hidden; text-overflow:ellipsis; max-width:360px; }}
table.t td.l span[title] {{ cursor:help; }}
table.t td.l b {{ color:{COR["marinho"]}; }}
table.t td.s {{ color:{COR["cinza"]}; font-size:.74rem; }}
table.t tr:nth-child(even) td {{ background:{COR["zebra"]}; }}
table.t tr.casa td {{ background:#EAF6FB; }}
table.t tr.casa td:first-child {{ box-shadow: inset 3px 0 0 {COR["azul"]}; }}
table.t tr.grande td {{ height:34px; font-size:.9rem; }}
table.t td.v {{ font-weight:600; }}
.rolagem {{ overflow-x:auto; }}
.nota {{ font-size:.76rem; color:{COR["cinza"]}; line-height:1.45; margin:.2rem 0 0; }}

.stTabs [data-baseweb="tab-list"] {{ gap:0; background:#FFFFFF; border:1px solid {COR["linha"]}; border-radius:3px;
  padding:0; }}
.stTabs [data-baseweb="tab"] {{ color:{COR["cinza"]}; font-weight:700; font-size:.78rem; letter-spacing:.06em;
  text-transform:uppercase; padding:9px 18px; border-right:1px solid {COR["linha"]}; margin:0; }}
.stTabs [aria-selected="true"] {{ color:#FFFFFF !important; background:{COR["marinho"]}; }}
.stTabs [data-baseweb="tab-highlight"], .stTabs [data-baseweb="tab-border"] {{ display:none; }}
.stTabs [data-baseweb="tab-panel"] {{ padding-top:.55rem; }}
[data-testid="stVerticalBlockBorderWrapper"] {{ background:#FFFFFF; border-color:{COR["linha"]} !important;
  border-radius:3px !important; overflow:hidden; }}
[data-testid="stDataFrame"] {{ border:1px solid {COR["linha"]}; border-radius:3px; background:#fff; }}
div.stDownloadButton > button, div.stButton > button[kind="primary"] {{ background:{COR["marinho"]}; color:#fff;
  border:0; border-radius:3px; font-size:.8rem; }}
div.stDownloadButton > button:hover, div.stButton > button[kind="primary"]:hover {{ background:{COR["azul"]}; color:#fff; }}
.stSelectbox label, .stTextInput label {{ font-size:.74rem !important; color:{COR["cinza"]} !important; }}
[data-testid="stSidebar"], [data-testid="stSidebarCollapsedControl"], [data-testid="stExpandSidebarButton"] {{ display:none !important; }}
.st-key-barra {{ background:#FFFFFF; border:1px solid {COR["linha"]}; border-top:0; border-radius:0 0 3px 3px;
  padding:6px 12px 10px; margin-top:-.55rem; }}
.st-key-barra label p {{ font-size:.66rem !important; font-weight:700 !important; letter-spacing:.06em;
  text-transform:uppercase; color:{COR["cinza"]} !important; }}
.st-key-barra [data-baseweb="select"] > div, .st-key-barra button {{ min-height:34px; font-size:.82rem; }}
[data-baseweb="select"] > div, [data-baseweb="input"], [data-baseweb="base-input"] {{ border-color:{COR["linha"]} !important;
  border-radius:3px !important; background:#FFFFFF !important; }}
[data-baseweb="select"] > div:focus-within, [data-baseweb="input"]:focus-within, [data-baseweb="base-input"]:focus-within,
[data-testid="stTextInputRootElement"]:focus-within {{ border-color:{COR["azul"]} !important; box-shadow:0 0 0 1px {COR["azul"]} !important; }}
[data-baseweb="tag"] {{ background:#E6F3F9 !important; color:{COR["marinho"]} !important; border-radius:3px !important; }}
[data-baseweb="tag"] span {{ color:{COR["marinho"]} !important; }}
[data-testid="stBaseButton-primary"] {{ background:{COR["marinho"]} !important; border:1px solid {COR["marinho"]} !important;
  color:#fff !important; border-radius:3px !important; }}
[data-testid="stBaseButton-primary"]:hover {{ background:{COR["azul"]} !important; border-color:{COR["azul"]} !important; }}
[data-testid="stBaseButton-secondary"], [data-testid="stPopoverButton"], [data-testid="stBaseButton-secondaryFormSubmit"] {{
  border:1px solid {COR["linha"]} !important; color:{COR["marinho"]} !important; background:#fff !important;
  border-radius:3px !important; }}
[data-testid="stBaseButton-secondary"]:hover, [data-testid="stPopoverButton"]:hover {{ border-color:{COR["azul"]} !important;
  color:{COR["azul"]} !important; }}
[data-testid="stButtonGroup"] button[data-variant^="pills"], [data-testid="stBaseButton-pills"] {{ border:1px solid {COR["linha"]} !important; background:#fff !important;
  color:{COR["marinho"]} !important; border-radius:3px !important; font-size:.78rem !important; }}
[data-testid="stButtonGroup"] button[aria-pressed="true"], [data-testid="stButtonGroup"] button[aria-checked="true"],
[data-testid="stButtonGroup"] button[data-variant="pillsActive"], [data-testid="stBaseButton-pillsActive"] {{ background:{COR["marinho"]} !important; border:1px solid {COR["marinho"]} !important;
  color:#fff !important; border-radius:3px !important; font-size:.78rem !important; }}
[data-testid="stButtonGroup"] button p {{ font-size:.78rem !important; }}
[data-testid="stButtonGroup"] button[aria-pressed="true"] p {{ color:#fff !important; }}
label[data-baseweb="checkbox"] [role="checkbox"][aria-checked="true"], label[data-baseweb="checkbox"] input:checked + div {{
  background:{COR["azul"]} !important; }}
[data-testid="stPopoverBody"] {{ border:1px solid {COR["linha"]}; border-radius:3px; }}
@media (max-width: 900px) {{ .topo {{ flex-direction:column; }} .topo .chip {{ border-left:0; border-top:1px solid #1D5B7E; }} }}
</style>
""", unsafe_allow_html=True)


@alt.theme.register("hedge", enable=True)
def _tema():
    return alt.theme.ThemeConfig({"config": {
        "font": FONTE.replace("'", ""), "background": "#FFFFFF",
        "axis": {"labelColor": COR["cinza"], "titleColor": COR["cinza"], "gridColor": "#EDF2F6",
                 "domainColor": COR["linha"], "tickColor": COR["linha"], "labelFontSize": 10, "titleFontSize": 10},
        "legend": {"labelColor": COR["tinta"], "titleColor": COR["cinza"], "orient": "top", "labelFontSize": 11},
        "view": {"stroke": None},
    }})


# Componentes
def painel(titulo, corpo, direita="", rodape=""):
    return (f'<div class="pn"><div class="pn-h"><span>{esc(titulo)}</span><small>{direita}</small></div>'
            f'<div class="pn-b rolagem">{corpo}</div>' + (f'<div class="pn-p">{rodape}</div>' if rodape else "")
            + '</div>')


def tabela(cab, linhas, classes_linha=None):
    th = "".join(f'<th class="{"l" if a == "l" else ""}">{esc(c)}</th>' for c, a in cab)
    corpo = ""
    for i, ln in enumerate(linhas):
        c = classes_linha[i] if classes_linha and i < len(classes_linha) else ""
        corpo += f'<tr class="{c}">' + "".join(ln) + "</tr>"
    return f'<table class="t"><thead><tr>{th}</tr></thead><tbody>{corpo}</tbody></table>'


def td(v, kind="pct", casas=None, extra=""):
    if casas is None:
        casas = 0 if kind == "num" else 2
    if kind == "pct":
        return f'<td class="{cls(v)} {extra}">{pct(v, casas)}</td>'
    if kind == "pctu":
        return f'<td class="{extra}">{pct(v, casas, sinal=False)}</td>'
    if kind == "num":
        return f'<td class="{extra}">{num(v, casas)}</td>'
    if kind == "html":
        return f'<td class="{extra}">{v}</td>'
    return f'<td class="l {extra}">{v}</td>'


def faixa_svg(lo, mid, hi, escala, largura=120, altura=14):
    if any(pd.isna(v) for v in (lo, mid, hi)) or escala <= 0:
        return ""
    x = lambda v: 4 + (np.clip(v, -escala, escala) + escala) / (2 * escala) * (largura - 8)
    cor = COR["verde"] if mid > 0 else (COR["vermelho"] if mid < 0 else COR["marinho"])
    y = altura / 2
    return (f'<svg width="{largura}" height="{altura}" viewBox="0 0 {largura} {altura}" '
            f'style="max-width:100%;height:auto;display:block;margin-left:auto" role="img" '
            f'aria-label="{pct(mid)} entre {pct(lo)} e {pct(hi)}">'
            f'<line x1="4" y1="{y}" x2="{largura - 4}" y2="{y}" stroke="#E1E9EF" stroke-width="2"/>'
            f'<line x1="{x(0):.1f}" y1="1" x2="{x(0):.1f}" y2="{altura - 1}" stroke="#9FB3C2" stroke-width="1"/>'
            f'<rect x="{x(lo):.1f}" y="{y - 3}" width="{max(x(hi) - x(lo), 2):.1f}" height="6" rx="3" '
            f'fill="{COR["celeste"]}"/>'
            f'<circle cx="{x(mid):.1f}" cy="{y}" r="3.8" fill="{cor}" stroke="#fff" stroke-width="1"/></svg>')


def escala_de(*series, minimo=0.005):
    vals = np.concatenate([np.abs(np.asarray(s, dtype=float)).ravel() for s in series])
    vals = vals[np.isfinite(vals)]
    return max(np.quantile(vals, 0.98) * 1.1 if len(vals) else minimo, minimo)


def nota(txt, alvo=st):
    alvo.markdown(f'<p class="nota">{txt}</p>', unsafe_allow_html=True)


def html_bloco(txt, alvo=st):
    alvo.markdown(txt, unsafe_allow_html=True)


def cor_sinal(x):
    if isinstance(x, (float, np.floating)) and pd.notna(x) and abs(x) > 1e-12:
        return f"color:{COR['verde'] if x > 0 else COR['vermelho']}"
    return ""


def _mapa_marca():
    from matplotlib.colors import LinearSegmentedColormap
    return LinearSegmentedColormap.from_list("hedge", [COR["vermelho"], "#F7E3D6", "#FFFFFF", "#D3E8F1", COR["marinho"]])


def para_excel(df: pd.DataFrame) -> bytes:
    buf = io.BytesIO()
    pv._salvar_excel(df, buf)
    return buf.getvalue()


# Dados
def _mtime():
    return tuple((pv.DADOS / n).stat().st_mtime if (pv.DADOS / n).exists() else 0
                 for n in ["betas.parquet", "calibracao.parquet", "fatores.parquet", "cotas.parquet"])


@st.cache_data(show_spinner="Carregando base…")
def base(_m):
    univ, cot, bet = pv.carregar_base()
    px, cdi = pv.carregar_fatores()
    return univ, cot, bet, px, cdi, pv.carregar_calibracao()


@st.cache_data(show_spinner=False)
def acumulados(_m):
    _, cot, _, _, cdi, _ = base(_m)
    a = pv.retornos_acumulados(cot, cdi)
    a["r_dia"], a["r_mes"], a["r_ano"] = a["r_Dia"], a["r_Mês"], a["r_Ano"]
    return a


@st.cache_data(show_spinner=False)
def serie_cota(_m, chave, dias=400):
    _, cot, _, _, cdi, _ = base(_m)
    s = cot[cot["chave"] == chave].set_index("data")["cota"].sort_index()
    s = s[s.index >= s.index.max() - pd.Timedelta(days=dias)]
    c = np.log1p(cdi.dropna() / 100).cumsum()
    cdi_ac = np.exp(c.reindex(c.index.union(s.index)).ffill().reindex(s.index) - c.asof(s.index[0]))
    return pd.DataFrame({"Data": s.index, "Fundo": s.values / s.iloc[0] - 1, "CDI": cdi_ac.values - 1})


@st.cache_data(show_spinner="Calculando a qualidade do modelo…")
def qualidade(_m):
    univ, cot, _, px, cdi, _ = base(_m)
    bt = pv._backtest_fundos(univ, cot, px, cdi)
    ok = bt[bt["usada_estim"]]
    pf = (ok.assign(e=(np.expm1(ok["real"]) - np.expm1(ok["prev_comb"])).abs() * 1e4).groupby("chave")["e"].mean())
    return pv.resumir_backtest(ok), pf, (ok["data"].min(), ok["data"].max(), len(ok))


@st.cache_data(show_spinner=False)
def historico_fundo(_m, chave):
    univ, cot, _, px, cdi, _ = base(_m)
    return pv._backtest_fundos(univ[univ["chave"] == chave], cot, px, cdi).tail(63)


@st.cache_data(ttl=30, show_spinner=False)
def precos(colunas: tuple):
    try:
        agora, ts = pv.precos_ao_vivo(list(colunas))
        return agora, ts, None
    except Exception as e:
        return None, None, str(e)


def variacoes_fatores(px, agora, d_ant):
    """Último valor e variação no dia, em 5 pregões, no mês e no ano."""
    h = px.ffill().loc[:d_ant]
    hoje = pd.Timestamp(pv.hoje_br())
    base_mes = h[h.index < hoje.replace(day=1)]
    base_ano = h[h.index < hoje.replace(month=1, day=1)]
    ref = {"dia": h.iloc[-1], "5d": h.iloc[-5] if len(h) >= 5 else h.iloc[0],
           "mês": base_mes.iloc[-1] if len(base_mes) else h.iloc[0],
           "ano": base_ano.iloc[-1] if len(base_ano) else h.iloc[0]}
    out = {}
    for f in pv.fatores_visiveis(px.columns):
        tx = f.startswith("TX_")
        out[f] = {"último": agora[f], **{k: (agora[f] - b[f]) if tx else (agora[f] / b[f] - 1) for k, b in ref.items()}}
    return pd.DataFrame(out).T


# Atualização da base
TRAVA = pv.DADOS / ".atualizando"
FALHA = pv.DADOS / ".falha_atualizacao"
AUTO_ATUALIZAR = True


def _agora_br():
    return pd.Timestamp.now(tz="America/Sao_Paulo")


def _travado() -> bool:
    return TRAVA.exists() and (pd.Timestamp.now().timestamp() - TRAVA.stat().st_mtime) < 30 * 60


def atualizar_base(rotulo="Atualizando a base"):
    import contextlib
    import time
    if _travado():
        st.info("Outra sessão está atualizando a base. A página recarrega quando terminar.")
        time.sleep(20)
        st.rerun()
    pv.DADOS.mkdir(parents=True, exist_ok=True)
    TRAVA.write_text(str(_agora_br()))
    linhas = []

    class _Escreve(io.StringIO):
        def write(self, txt):
            if txt.strip():
                linhas.append(txt.strip())
                caixa.code("\n".join(linhas[-12:]), language=None)
            return len(txt)

    try:
        with st.status(rotulo, expanded=True) as status:
            caixa = st.empty()
            try:
                with contextlib.redirect_stdout(_Escreve()):
                    pv.atualizar()
                    pv.estimar()
            except Exception as e:
                msg = ("sem conexão com a CVM, o Yahoo ou o Banco Central" if "Connection" in type(e).__name__
                       or "Max retries" in str(e) else str(e)[:160])
                status.update(label=f"A atualização falhou: {msg}. A base anterior continua valendo.", state="error")
                FALHA.write_text(msg)
                return
            status.update(label="Base atualizada", state="complete")
            FALHA.unlink(missing_ok=True)
    finally:
        TRAVA.unlink(missing_ok=True)
    st.cache_data.clear()
    pv._CACHE.clear()
    st.rerun()


def _base_desatualizada() -> bool:
    p = pv.DADOS / "betas.parquet"
    if not p.exists():
        return True
    feita = pd.Timestamp(p.stat().st_mtime, unit="s", tz="UTC").tz_convert("America/Sao_Paulo")
    agora = _agora_br()
    return agora.weekday() < 5 and (agora.hour, agora.minute) >= (8, 30) and feita.date() < agora.date()


if not (pv.DADOS / "betas.parquet").exists():
    html_bloco('<div class="topo"><div class="marca">Hedge Investments<span>Prévia de cotas</span></div></div>')
    st.info("Primeira execução: montando a base com 36 meses de cotas da CVM (37 arquivos, cerca de 400 MB), "
            "cadastro, fatores e CDI. Leva de 5 a 10 minutos na primeira vez; depois, só os 2 últimos meses são baixados.")
    atualizar_base("Montando a base")
    st.stop()

falhou_recente = FALHA.exists() and (pd.Timestamp.now().timestamp() - FALHA.stat().st_mtime) < 60 * 60
if AUTO_ATUALIZAR and _base_desatualizada() and not _travado() and not falhou_recente:
    st.info("Atualizando com as cotas de hoje da CVM. Leva alguns minutos.")
    atualizar_base("Atualizando a base do dia")

M = _mtime()
univ, cot, bet, px, cdi, cal = base(M)
REAL = acumulados(M)
d_ref = cot["data"].max()
d_ant = pv.fechamento_anterior(px)


def limpar_manual():
    for fz in pv.fatores_visiveis(px.columns):
        st.session_state[f"man_{fz}"] = None


def aplicar_manual(agora: pd.Series, manual: dict) -> pd.Series:
    agora = agora.copy()
    ant = px.ffill().loc[:d_ant].iloc[-1]
    for fz, x in manual.items():
        agora[fz] = ant[fz] + x if fz.startswith("TX_") else ant[fz] * (1 + x / 100)
    return agora


ESTRATEGIAS = [e for e in pv.ordenar_estrategias(univ["Estrategia"].unique()) if e != "Todas"]
NOME_MODELO = {"comb": "Combinada", "ew": "EW (exponencial)", **{j: f"Janela {j}" for j in JAN if j != "ew"}}
estr, gest, jref, r2min, plmin, com_alfa, manual = [], [], "comb", 0.0, 0, False, {}
intervalo = st.session_state.get("intervalo", 60)


def controles():
    """Barra de controles horizontal (substitui a barra lateral)."""
    global estr, gest, jref, r2min, plmin, com_alfa, manual
    with st.container(key="barra"):
        c = st.columns([2.3, 2.1, 1.15, .85, .95, .8, 1.05, 1.2], vertical_alignment="bottom")
        estr = c[0].multiselect("Estratégias", ESTRATEGIAS, placeholder="Todas", key="f_estr")
        gest = c[1].multiselect("Gestores", sorted(univ["Gestor"].dropna().unique()), placeholder="Todos", key="f_gest")
        jref = c[2].selectbox("Modelo", TODAS, format_func=NOME_MODELO.get, key="f_modelo",
                              help="Combinada: média das janelas 1m, 2m, 3m e 12m ponderada pelo erro recente do fundo.")
        r2min = c[3].selectbox("R² mín.", [0.0, 0.3, 0.5, 0.7, 0.9], format_func=lambda x: "Todos" if x == 0 else num(x, 1),
                               key="f_r2")
        plmin = c[4].selectbox("PL mín.", [0, 50, 100, 250, 500, 1000],
                               format_func=lambda x: "Todos" if x == 0 else f"R$ {num(x)} mi", key="f_pl")
        with c[5].popover("Ajustes", width="stretch"):
            com_alfa = st.toggle("Somar α estimado", value=False, key="f_alfa")
            novo = st.selectbox("Atualizar a cada", [30, 60, 120, 300], index=[30, 60, 120, 300].index(intervalo),
                                format_func=lambda x: f"{x} segundos")
            if novo != intervalo:
                st.session_state["intervalo"] = novo
                st.rerun(scope="app")
            st.markdown("**Movimento manual dos fatores**")
            nota(f"Variação do dia desde o fechamento de {data_br(d_ant)}, em % (pp para taxas TX_). "
                 "Campos vazios seguem o Yahoo.")
            cc = st.columns(2)
            vals = {fz: cc[i % 2].number_input(NOMES_FATOR.get(fz, fz), value=None, step=0.1, format="%.2f",
                                               key=f"man_{fz}", placeholder="Yahoo")
                    for i, fz in enumerate(pv.fatores_visiveis(px.columns))}
            st.button("Limpar valores manuais", width="stretch", on_click=limpar_manual)
        manual = {k: x for k, x in vals.items() if x is not None}
        if c[6].button("Atualizar preços", width="stretch", help="Consulta o Yahoo agora."):
            precos.clear()
        if c[7].button("Atualizar base", width="stretch", type="primary",
                       help="Baixa CVM, cadastro, fatores e CDI e reestima os modelos. Leva alguns minutos."):
            atualizar_base()


def aplicar_filtros(df):
    m = (df[f"r2_{jref}"].fillna(0) >= r2min) & (df["pl"] >= plmin * 1e6)
    if estr:
        m &= df["Estrategia"].isin(estr)
    if gest:
        m &= df["Gestor"].isin(gest)
    return df[m]


# Painéis
def barra_topo(ts, vivo, n_fundos):
    agora = _agora_br()
    luz = "vivo" if vivo else "parado"
    status = f"Ao vivo {ts:%H:%M}" if vivo else "Último fechamento"
    feita = pd.Timestamp(M[0], unit="s", tz="UTC").tz_convert("America/Sao_Paulo")
    chips = [("Data", f"{agora:%d/%m/%Y}"), (f'<span class="{luz}"></span>Preços', status + (" + manual" if manual else "")),
             ("Base do dia", f"Fech. {data_br(d_ant)}"), ("Cotas CVM", f"até {data_br(d_ref)}"),
             ("Modelos", f"{feita:%d/%m %H:%M}"), ("Modelo", NOME_MODELO[jref]), ("Fundos", num(n_fundos))]
    return ('<div class="topo"><div class="marca">HEDGE INVESTMENTS<span>Prévia diária de cotas</span></div>'
               '<div class="chips">' + "".join(f'<div class="chip">{r}<b>{esc(v)}</b></div>' for r, v in chips)
               + "</div></div>")


def painel_hedge(df):
    h = df[df["CNPJ"].isin(pv.FUNDOS_INCLUIR)].copy()
    if h.empty:
        return painel("Hedge Alternative", '<p class="nota" style="padding:10px">Fundos não encontrados na base.</p>')
    h["o"] = (~h["Nome"].str.upper().str.contains("MASTER")).astype(int)
    h = h.sort_values(["o", "pl"], ascending=[True, False])
    j = jref
    escala = escala_de(h[f"previa_{j}_min"], h[f"previa_{j}_max"])
    linhas = []
    for _, r in h.iterrows():
        rr = REAL.loc[r["chave"]] if r["chave"] in REAL.index else pd.Series(dtype=float)
        linhas.append([
            td(f'<b>{esc(apelido(r["CNPJ"], r["Nome"]))}</b>', "l"),
            td(r[f"previa_{j}"], extra="v"),
            td(faixa_svg(r[f"previa_{j}_min"], r[f"previa_{j}"], r[f"previa_{j}_max"], escala), "html"),
            td(r[f"cota_est_{j}"], "num", 6),
            td(rr.get("r_dia"), extra="s"), td(rr.get("r_mes")), td(rr.get("r_ano")), td(rr.get("r_12M")),
            td(r["pl"] / 1e6, "num"),
        ])
    corpo = tabela([("Classe", "l"), ("Prévia", "r"), ("Faixa 95%", "r"), ("Cota est.", "r"),
                    (f"Real {data_br(d_ref)}", "r"), ("Mês", "r"), ("Ano", "r"), ("12M", "r"), ("PL mi", "r")],
                   linhas, ["casa grande"] + ["grande"] * (len(linhas) - 1))
    m = h.iloc[0]
    return painel("Hedge Alternative Investments", corpo, f"modelo {rot(j)}",
                  f"Master: prévia {pct(m[f'previa_{j}'])}, entre {pct(m[f'previa_{j}_min'])} e "
                  f"{pct(m[f'previa_{j}_max'])} (95%). Real, mês e ano pela cota CVM até {data_br(d_ref)}.")


def painel_rentabilidade(df):
    h = df[df["CNPJ"].isin(pv.FUNDOS_INCLUIR)].copy()
    if h.empty:
        return ""
    h["o"] = (~h["Nome"].str.upper().str.contains("MASTER")).astype(int)
    h = h.sort_values(["o", "pl"], ascending=[True, False])
    acp = pv.com_previa(REAL, df)
    jans = pv.JANELAS_ACUM
    linhas, classes = [], []
    for i, (_, r) in enumerate(h.iterrows()):
        a = REAL.loc[r["chave"]] if r["chave"] in REAL.index else pd.Series(dtype=float)
        p = acp.loc[r["chave"]] if r["chave"] in acp.index else pd.Series(dtype=float)
        linhas.append([td(f'<b>{esc(apelido(r["CNPJ"], r["Nome"]))}</b>', "l")]
                      + [td(a.get(f"r_{k}"), extra="v" if k in ("Ano", "12M") else "") for k in jans]
                      + [td(a.get("pcdi_Ano"), "pctu", 0), td(a.get("pcdi_12M"), "pctu", 0),
                         td(p.get("rp_Semana"), extra="s"), td(p.get("rp_Mês"), extra="s"), td(p.get("rp_Ano"), extra="s"),
                         td(p.get("rp_12M"), extra="s")])
        classes.append("casa" if i == 0 else "")
    a0 = REAL.loc[h.iloc[0]["chave"]]
    linhas.append([td("CDI", "l")] + [td(a0.get(f"cdi_{k}"), extra="s") for k in jans] + [td("", "html")] * 6)
    classes.append("")
    corpo = tabela([("Classe", "l")] + [(k, "r") for k in jans]
                   + [("% CDI ano", "r"), ("% CDI 12M", "r"), ("Semana c/ prévia", "r"), ("Mês c/ prévia", "r"),
                      ("Ano c/ prévia", "r"), ("12M c/ prévia", "r")], linhas, classes)
    ini12 = a0.get("base_12M")
    return painel("Rentabilidade acumulada · Hedge Alternative", corpo, f"cota CVM até {data_br(d_ref)}",
                  f"Retornos pela cota oficial da CVM, da última cota até a data-base de cada janela"
                  f"{'' if pd.isna(ini12) else f' (12M desde {ini12:%d/%m/%y})'}. CDI no mesmo período do Master. "
                  f"'c/ prévia' soma ao acumulado o retorno estimado desde a última cota até agora.")


def painel_mercado(px, agora):
    v = variacoes_fatores(px, agora, d_ant)
    linhas = []
    for f, r in v.iterrows():
        tx = f.startswith("TX_")
        nome = NOMES_FATOR.get(f, f) + (' <small style="color:#F98909">manual</small>' if f in manual else "")
        fmt = (lambda x: td(f'{num(x, 2)} pp', "html", extra=cls(x))) if tx else (lambda x: td(x))
        linhas.append([td(nome, "l"), td(r["último"], "num", 2), fmt(r["dia"]), fmt(r["5d"]), fmt(r["mês"]), fmt(r["ano"])])
    corpo = tabela([("Fator", "l"), ("Último", "r"), ("Dia", "r"), ("5 dias", "r"), ("Mês", "r"), ("Ano", "r")], linhas)
    return painel("Mercado", corpo, f"desde fech. {data_br(d_ant)}")


def painel_estrategias(v):
    j = jref
    g = v.groupby("Estrategia")
    ordem = [e for e in pv.ORDEM_ESTRATEGIAS if e in g.groups] + sorted(set(g.groups) - set(pv.ORDEM_ESTRATEGIAS))
    p10, p50, p90 = g[f"previa_{j}"].quantile(.1), g[f"previa_{j}"].median(), g[f"previa_{j}"].quantile(.9)
    escala = escala_de(p10, p90)
    casa = set(pv.FUNDOS_INCLUIR.values())
    linhas, classes = [], []
    for e in ordem:
        x = g.get_group(e)[f"previa_{j}"]
        linhas.append([td(f"<b>{esc(e)}</b>", "l"), td(len(x), "num"), td(p50[e], extra="v"),
                       td(faixa_svg(p10[e], p50[e], p90[e], escala), "html"), td(p10[e], extra="s"), td(p90[e], extra="s"),
                       td(f'<span class="pos">{int((x > 0).sum())}</span> / <span class="neg">{int((x < 0).sum())}</span>',
                          "html")])
        classes.append("casa" if e in casa else "")
    corpo = tabela([("Estratégia", "l"), ("N", "r"), ("Mediana", "r"), ("P10–P90", "r"), ("P10", "r"), ("P90", "r"),
                    ("Sobe/cai", "r")], linhas, classes)
    return painel("Estratégias", corpo, f"prévia do dia, {rot(j)}")


def painel_lista(v, maiores, n=10):
    j = jref
    t = v.nlargest(n, f"previa_{j}") if maiores else v.nsmallest(n, f"previa_{j}")
    escala = escala_de(t[f"previa_{j}_min"], t[f"previa_{j}_max"])
    linhas = [[td(nome_td(r["Nome"], 48), "l"), td(esc(r["Estrategia"][:11]), "html", extra="s"),
               td(r[f"previa_{j}"], extra="v"),
               td(faixa_svg(r[f"previa_{j}_min"], r[f"previa_{j}"], r[f"previa_{j}_max"], escala, 90), "html")]
              for _, r in t.iterrows()]
    corpo = tabela([("Fundo", "l"), ("Estr.", "r"), ("Prévia", "r"), ("Faixa", "r")], linhas,
                   ["casa" if c in pv.FUNDOS_INCLUIR else "" for c in t["CNPJ"]])
    return painel("Maiores altas" if maiores else "Maiores quedas", corpo, f"top {n}")


def painel_alertas(df, v, n=10):
    j = jref
    lim = max(df["amplitude_janelas"].quantile(0.9), AMPLITUDE_MIN)
    al = v[(v["amplitude_janelas"] >= lim) | (v[f"r2_{j}"] < 0.4) | (v["dias_desde_base"] > 2)].copy()
    al["motivo"] = np.select([al["amplitude_janelas"] >= lim, al["dias_desde_base"] > 2, al[f"r2_{j}"] < 0.4],
                             ["Janelas divergem", "Cota atrasada", "R² baixo"], "")
    al["ordem"] = al["motivo"].map({"Janelas divergem": 0, "Cota atrasada": 1, "R² baixo": 2})
    al = al.sort_values(["ordem", "amplitude_janelas"], ascending=[True, False]).head(n)
    linhas = [[td(nome_td(r["Nome"], 44), "l"), td(esc(r["motivo"]), "html", extra="s"),
               td(r["amplitude_janelas"], "pctu"), td(r[f"r2_{j}"], "num", 2)] for _, r in al.iterrows()]
    total = int(((v["amplitude_janelas"] >= lim) | (v[f"r2_{j}"] < 0.4) | (v["dias_desde_base"] > 2)).sum())
    corpo = tabela([("Fundo", "l"), ("Motivo", "r"), ("Diverg.", "r"), ("R²", "r")], linhas) if linhas else \
        '<p class="nota" style="padding:10px">Nenhum ponto de atenção.</p>'
    return painel("Atenção", corpo, f"{total} fundos",
                  f"Divergência = maior menos menor prévia entre janelas; alerta a partir de {pct(lim, sinal=False)}.")


def grafico_real_previa(chave, j, altura=230):
    bt = historico_fundo(M, chave)
    if bt.empty:
        return None, None
    gd = pd.DataFrame({"Data": bt["data"].values, "Real": np.expm1(bt["real"].values),
                       "Prévia": np.expm1(bt[f"prev_{j}"].values),
                       "Mín": np.expm1(bt[f"ic_{j}_min"].values), "Máx": np.expm1(bt[f"ic_{j}_max"].values)})
    x = alt.X("Data:T", title=None, axis=alt.Axis(format="%d/%m", grid=False))
    faixa = alt.Chart(gd).mark_area(color=COR["celeste"], opacity=.35).encode(
        x=x, y=alt.Y("Mín:Q", axis=alt.Axis(format="+.1%"), title=None), y2="Máx:Q")
    real = alt.Chart(gd).mark_bar(color=COR["marinho"], size=4).encode(
        x=x, y="Real:Q", tooltip=[alt.Tooltip("Data:T", format="%d/%m", title="Dia"),
                                  alt.Tooltip("Real:Q", format="+.2%"), alt.Tooltip("Prévia:Q", format="+.2%")])
    linha = alt.Chart(gd).mark_line(color=COR["laranja"] if j == "comb" else COR["azul"], strokeWidth=1.6).encode(
        x=x, y="Prévia:Q")
    res = {"erro": (gd["Real"] - gd["Prévia"]).abs().mean() * 1e4,
           "dentro": ((gd["Real"] >= gd["Mín"]) & (gd["Real"] <= gd["Máx"])).mean(), "dias": len(gd)}
    return (faixa + real + linha).properties(height=altura, padding={"left": 6, "right": 10, "top": 8, "bottom": 4}), res


# Abas
def aba_monitor(v):
    c1, c2, c3 = st.columns([2.1, 3.6, 1.1], vertical_alignment="center")
    busca = c1.text_input("Buscar fundo, gestor ou CNPJ", placeholder="Buscar fundo, gestor ou CNPJ",
                          label_visibility="collapsed")
    opcoes = [e for e in ESTRATEGIAS if e in set(v["Estrategia"])]
    sel = c2.pills("Estratégia", opcoes, selection_mode="multi", key="mon_estr", label_visibility="collapsed")
    ordem = c3.selectbox("Ordenar", ["Prévia (maior)", "Prévia (menor)", "Ano", "12M", "PL", "Divergência", "R²"],
                         label_visibility="collapsed")
    if sel:
        v = v[v["Estrategia"].isin(sel)]
    if busca:
        v = v[pv._contem(v["Nome"], busca) | pv._contem(v["Gestor"], busca) | v["CNPJ"].str.contains(busca, regex=False)]
    j = jref
    rr = REAL.reindex(v["chave"])
    t = pd.DataFrame({
        "Fundo": [abreviar(n) + (f" · {sb}" if sb else "") for n, sb in zip(v["Nome"], v["Subclasse"].fillna(""))],
        "Estratégia": v["Estrategia"].values, "Classe ANBIMA": v["Classe_ANBIMA"].values,
        "Gestor": v["Gestor"].astype(str).map(abreviar).values, "PL mi": (v["pl"] / 1e6).values,
        f"Prévia {rot(j)}": v[f"previa_{j}"].values, "Mín 95%": v[f"previa_{j}_min"].values,
        "Máx 95%": v[f"previa_{j}_max"].values,
        **{f"{rot(k)}": v[f"previa_{k}"].values for k in TODAS if k != j},
        "Diverg.": v["amplitude_janelas"].values, "R²": v[f"r2_{j}"].values,
        f"Real {data_br(d_ref)}": rr["r_dia"].values, "Mês": rr["r_mes"].values, "3M": rr["r_3M"].values,
        "6M": rr["r_6M"].values, "Ano": rr["r_Ano"].values, "12M ac.": rr["r_12M"].values,
        "% CDI 12M": rr["pcdi_12M"].values,
        "Cota est.": v[f"cota_est_{j}"].values, "Última": v["data_base"].dt.strftime("%d/%m").values,
        "CNPJ": v["CNPJ"].values, "Subclasse": v["Subclasse"].fillna("").values,
        "Administrador": v["Administrador"].astype(str).map(abreviar).values,
        "Denominação social": v["Nome"].values,
    })
    chave = {"Prévia (maior)": (f"Prévia {rot(j)}", False), "Prévia (menor)": (f"Prévia {rot(j)}", True),
             "PL": ("PL mi", False), "Divergência": ("Diverg.", False), "R²": ("R²", False),
             "Ano": ("Ano", False), "12M": ("12M ac.", False)}[ordem]
    t = t.sort_values(chave[0], ascending=chave[1])
    pcols = [c for c in t if c.startswith(("Prévia", "Mín", "Máx", "Real")) or c in TODAS
             or c in ("Comb", "Mês", "3M", "6M", "Ano", "12M ac.") or c in [rot(k) for k in TODAS]]
    sty = (t.style.format({**{c: (lambda x: pct(x)) for c in pcols}, "Diverg.": lambda x: pct(x, sinal=False),
                           "% CDI 12M": lambda x: pct(x, 0, False),
                           "PL mi": num, "Cota est.": lambda x: num(x, 6), "R²": lambda x: num(x, 2)}, na_rep="–")
           .map(cor_sinal, subset=pcols).bar(subset=["R²"], color="#CFE6F0", vmin=0, vmax=1))
    st.dataframe(sty, hide_index=True, width="stretch", height=560,
                 column_config={"Fundo": st.column_config.TextColumn(width=420, pinned=True),
                                "Gestor": st.column_config.TextColumn(width=300),
                                "Classe ANBIMA": st.column_config.TextColumn(width=170),
                                "Administrador": st.column_config.TextColumn(width=230),
                                "Denominação social": st.column_config.TextColumn(width=600)})
    agora_txt = _agora_br().strftime("%Y%m%d_%H%M")
    b1, b2, b3 = st.columns([1, 1, 6])
    b1.download_button("Excel", para_excel(t), f"previa_{agora_txt}.xlsx",
                       "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", width="stretch")
    b2.download_button("CSV", t.to_csv(sep=";", decimal=",", index=False).encode("utf-8-sig"),
                       f"previa_{agora_txt}.csv", "text/csv", width="stretch")
    nota(f"{len(t)} fundos. Prévia, mín e máx pelo modelo {rot(j)}; demais colunas de janela são a prévia de cada "
         f"modelo. Real, mês, 3M, 6M, ano e 12M acumulados pela cota da CVM até {data_br(d_ref)}.", b3)


def aba_fundo(v):
    casa = v["CNPJ"].isin(pv.FUNDOS_INCLUIR)
    op = v.assign(_c=(~casa).astype(int)).sort_values(["_c", "pl"], ascending=[True, False])
    rotulos = dict(zip(op["chave"], [abreviar(n) + (f" · {sb}" if sb else "") + f"  ·  {c}"
                                     for n, sb, c in zip(op["Nome"], op["Subclasse"].fillna(""), op["CNPJ"])]))
    sel = st.selectbox("Fundo", list(rotulos), format_func=rotulos.get, index=0 if len(rotulos) else None,
                       label_visibility="collapsed")
    if not sel:
        return
    f = op[op["chave"] == sel].iloc[0]
    rr = REAL.loc[f["chave"]] if f["chave"] in REAL.index else pd.Series(dtype=float)
    esc_f = escala_de([f[f"previa_{k}_min"] for k in TODAS], [f[f"previa_{k}_max"] for k in TODAS])
    linhas = [[td(f"<b>{'Combinada' if k == 'comb' else 'Janela ' + k}</b>", "l"), td(f[f"previa_{k}"], extra="v"),
               td(faixa_svg(f[f"previa_{k}_min"], f[f"previa_{k}"], f[f"previa_{k}_max"], esc_f, 150), "html"),
               td(f[f"previa_{k}_min"], extra="s"), td(f[f"previa_{k}_max"], extra="s"),
               td(f[f"cota_est_{k}"], "num", 6),
               td("" if k == "comb" else pct(f[f"peso_{k}"], 0, False), "html"), td(f[f"r2_{k}"], "num", 2)]
              for k in TODAS]
    c1, c2 = st.columns([1.35, 1])
    html_bloco(painel(abreviar(f["Nome"]) + (f" · {f['Subclasse']}" if f["Subclasse"] else ""), tabela(
        [("Modelo", "l"), ("Prévia", "r"), ("Faixa 95%", "r"), ("Mín", "r"), ("Máx", "r"), ("Cota est.", "r"),
         ("Peso", "r"), ("R²", "r")], linhas, ["casa grande"] + ["grande"] * (len(linhas) - 1)),
        f'{esc(f["Estrategia"])} · {esc(f["Classe_ANBIMA"])} · {esc(abreviar(str(f["Gestor"])))} · {esc(f["CNPJ"])}',
        f'Última cota {num(f["cota_base"], 6)} em {data_br(f["data_base"])}. Realizado: dia {pct(rr.get("r_dia"))}, '
        f'mês {pct(rr.get("r_mes"))}, ano {pct(rr.get("r_ano"))}. PL R$ {num(f["pl"] / 1e6)} mi.'), c1)
    b = bet[bet["chave"] == f["chave"]].set_index("janela").reindex(JAN)
    bcols = [c for c in b if c.startswith("b_") and b[c].notna().any()]
    lin_b = [[td(NOMES_FATOR.get(c[2:], c[2:]), "l")] + [td(b.loc[jn, c], "num", 2, extra=cls(b.loc[jn, c])) if pd.notna(b.loc[jn, c])
                                                        else td("·", "html", extra="s") for jn in JAN]
             for c in bcols]
    lin_b.append([td("<b>R²</b>", "l")] + [td(b.loc[jn, "r2"], "num", 2) for jn in JAN])
    lin_b.append([td("<b>Erro anual</b>", "l")] + [td(b.loc[jn, "te"], "pctu", 1) for jn in JAN])
    html_bloco(painel("Sensibilidades (β)", tabela([("Fator", "l")] + [(rot(jn), "r") for jn in JAN], lin_b),
                      "% do fundo por 1% do fator"), c2)
    jans = pv.JANELAS_ACUM
    acp = pv.com_previa(REAL, v).reindex([f["chave"]])
    lin = [[td("<b>Fundo</b>", "l")] + [td(rr.get(f"r_{k}"), extra="v") for k in jans],
           [td("CDI", "l")] + [td(rr.get(f"cdi_{k}"), extra="s") for k in jans],
           [td("% do CDI", "l")] + [td(rr.get(f"pcdi_{k}"), "pctu", 0) for k in jans],
           [td("Com a prévia de hoje", "l"), td("", "html")] + [td(acp.iloc[0].get(f"rp_{k}"), extra="s") for k in jans[1:]]]
    c1, c2 = st.columns([1.35, 1])
    html_bloco(painel("Rentabilidade acumulada", tabela([("", "l")] + [(k, "r") for k in jans], lin, ["casa"]),
                      f"cota CVM até {data_br(d_ref)}"), c1)
    sc = serie_cota(M, f["chave"])
    if len(sc) > 5:
        longo = sc.melt(id_vars="Data", var_name="Série", value_name="Acumulado")
        g = alt.Chart(longo).mark_line(strokeWidth=1.8).encode(
            x=alt.X("Data:T", title=None, axis=alt.Axis(format="%m/%y", grid=False)),
            y=alt.Y("Acumulado:Q", title=None, axis=alt.Axis(format="+.0%")),
            color=alt.Color("Série:N", title=None, scale=alt.Scale(domain=["Fundo", "CDI"],
                                                                  range=[COR["marinho"], COR["celeste"]])),
            tooltip=[alt.Tooltip("Data:T", format="%d/%m/%y"), "Série", alt.Tooltip("Acumulado:Q", format="+.2%")]
        ).properties(height=165, padding={"left": 6, "right": 10, "top": 4, "bottom": 2})
        with c2.container(border=True):
            html_bloco(f'<div class="pn-h" style="margin:-1rem -1rem .3rem;border-radius:3px 3px 0 0">'
                       f'<span>ACUMULADO × CDI</span><small>desde {sc["Data"].iloc[0]:%d/%m/%y}</small></div>')
            st.altair_chart(g, width="stretch")
    graf, res = grafico_real_previa(f["chave"], jref)
    if graf is not None:
        with st.container(border=True):
            html_bloco(f'<div class="pn-h" style="margin:-1rem -1rem .4rem;border-radius:3px 3px 0 0">'
                       f'<span>PRÉVIA × REALIZADO, FORA DA AMOSTRA</span>'
                       f'<small>últimos {res["dias"]} dias, {rot(jref)}</small></div>')
            st.altair_chart(graf, width="stretch")
            nota(f"Barras: realizado. Linha: prévia. Faixa: IC 95%. Erro médio {num(res['erro'])} bps/dia; "
                 f"realizado dentro da faixa em {pct(res['dentro'], 0, False)} dos dias.")


def aba_qualidade():
    r, pf, (ini, fim, nobs) = qualidade(M)
    ordem = pv.ordenar_estrategias(set(r["Estrategia"]))
    modelos = TODAS + ["só CDI"]
    erro = r.pivot(index="Estrategia", columns="Modelo", values="MAE_bps").reindex(ordem)[modelos]
    cob = r[r["Modelo"].isin(TODAS)].pivot(index="Estrategia", columns="Modelo", values="cobertura_IC").reindex(ordem)[TODAS]
    sinal = r[r["Modelo"].isin(TODAS)].pivot(index="Estrategia", columns="Modelo", values="acerto_sinal").reindex(ordem)[TODAS]
    c1, c2 = st.columns(2)
    lin = []
    for e in ordem:
        melhor = erro.loc[e, TODAS].idxmin()
        lin.append([td(f"<b>{esc(e)}</b>", "l")] + [
            td(f'<b>{num(erro.loc[e, m], 1)}</b>' if m == melhor else num(erro.loc[e, m], 1), "html") for m in modelos])
    html_bloco(painel("Erro médio diário (bps)", tabela([("Estratégia", "l")] + [(rot(m), "r") for m in modelos], lin),
                      f"{ini:%d/%m/%y} a {fim:%d/%m/%y}",
                      f"Fora da amostra, {num(nobs)} fundo-dias. Em negrito, o melhor modelo da estratégia. "
                      "Só CDI = referência ingênua."), c1)
    lin = []
    for e in ordem:
        lin.append([td(f"<b>{esc(e)}</b>", "l")] + [
            td(pct(cob.loc[e, m], 0, False), "html", extra="neg" if abs(cob.loc[e, m] - .95) > .03 else "") for m in TODAS]
            + [td(pct(sinal.loc[e, "comb"], 0, False), "html")])
    html_bloco(painel("Cobertura do IC 95% e acerto de sinal", tabela(
        [("Estratégia", "l")] + [(rot(m), "r") for m in TODAS] + [("Sinal comb", "r")], lin), "ideal ≈ 95%",
        "Cobertura: % dos dias em que o realizado caiu dentro da faixa calibrada; em vermelho, desvio acima de 3 pontos. "
        "Sinal: % dos dias em que a prévia acertou o lado do retorno contra o CDI."), c2)
    pior = (pf.rename("e").to_frame().join(univ.set_index("chave")[["Nome", "Estrategia", "Gestor"]]).nlargest(12, "e"))
    lin = [[td(nome_td(x["Nome"], 90), "l"), td(esc(x["Estrategia"]), "html", extra="s"),
            td(esc(abreviar(str(x["Gestor"]))), "html", extra="s"), td(x["e"], "num")] for _, x in pior.iterrows()]
    html_bloco(painel("Fundos que o modelo explica pior", tabela(
        [("Fundo", "l"), ("Estratégia", "r"), ("Gestor", "r"), ("Erro bps", "r")], lin), "modelo combinado"))


@st.fragment(run_every=intervalo)
def ao_vivo():
    topo = st.empty()
    controles()
    if cal is None:
        st.warning("Sem calibração dos modelos. Use Atualizar base.")
    agora, ts, erro = precos(tuple(px.columns))
    vivo = erro is None
    if not vivo:
        agora = px.ffill().iloc[-1]
    agora = agora.reindex(px.columns).fillna(px.ffill().iloc[-1])
    if manual:
        agora = aplicar_manual(agora, manual)
    df = pv.calcular_previa(univ, cot, bet, px, cdi, agora, com_alfa=com_alfa, cal=cal)
    v = aplicar_filtros(df)

    topo.markdown(barra_topo(ts, vivo, len(v)), unsafe_allow_html=True)
    c1, c2, c3 = st.columns([1.45, 1, 1.15])
    html_bloco(painel_hedge(df), c1)
    html_bloco(painel_mercado(px, agora), c2)
    if v.empty:
        c3.info("Nenhum fundo com os filtros atuais.")
        return
    html_bloco(painel_estrategias(v), c3)
    html_bloco(painel_rentabilidade(df))
    c1, c2, c3 = st.columns(3)
    html_bloco(painel_lista(v, True), c1)
    html_bloco(painel_lista(v, False), c2)
    html_bloco(painel_alertas(df, v), c3)

    t1, t2, t3 = st.tabs(["Monitor de fundos", "Fundo", "Qualidade do modelo"])
    with t1:
        aba_monitor(v)
    with t2:
        aba_fundo(v)
    with t3:
        aba_qualidade()


ao_vivo()
