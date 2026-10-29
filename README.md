# Prévia de cotas por fatores

Prévia do retorno diário de fundos Long Only, Long Biased, Long Short e Macro (PL ≥ R$ 100 mi),
estimada em quatro janelas (1m, 2m, 3m, 12m) com intervalo de predição de 95% bicaudal.

## Instalação

```
pip install -r requirements.txt
```

## Uso

Caderno: abra `Previa_de_Cotas.ipynb` e rode as células em ordem.

Console (Jupyter ou Spyder):

```python
import previa as pv
pv.atualizar()                                  # 1x por dia, depois das 8h
pv.estimar()
pv.backtest()
pv.previa(top=30)                               # filtros: estrategia, gestor, busca, so_confiaveis
pv.buscar("verde")
pv.detalhe("verde", janela="3m")
df = pv.consolidado(salvar="consolidado.xlsx")
```

Linha de comando: `python previa.py [atualizar|estimar|previa|backtest|consolidado]`.
Sem comando, roda tudo.

## Painel

```
streamlit run painel.py
```

O painel tem quatro abas:
- **Visão geral:** fatores do dia, prévia por estratégia, maiores altas e quedas, e alertas (janelas
  divergindo, ajuste fraco, cota CVM atrasada).
- **Fundos:** a tabela completa, com download em Excel ou CSV.
- **Fundo:** prévias e ICs por janela, pesos da combinada, βs, e o gráfico de real contra prévia com IC.
- **Qualidade do modelo:** erro e cobertura do IC (teórica e calibrada) por estratégia, e os fundos com maior erro.

Seção **Atualização** na barra lateral:
- **Atualizar preços agora:** consulta o Yahoo na hora. Fora isso, os preços ficam em cache por 30 s.
- **Atualizar base e recalcular:** roda `pv.atualizar()` e `pv.estimar()` pelo próprio painel e recarrega os dados.
- **Movimento manual dos fatores:** a variação do dia digitada (% ou pp para `TX_`) substitui o Yahoo
  no fator preenchido. Os fatores marcados como manuais aparecem destacados nos cards.

Usa a paleta Hedge Investments (marinho #0A4263, azul #00A0D7, celeste #81C1D7) e a fonte Compass.
Se a fonte estiver instalada no computador, o painel a usa direto. Se não, coloque os arquivos em
`static/fonts/`. As cores do tema ficam em `.streamlit/config.toml`, e a paleta completa em `PALETA`,
no `painel.py`.

## Modelo

Por fundo e janela, em log-retornos:

    r_fundo − r_CDI = α + Σ βk·xk + ε            (ridge com X padronizado)
    prévia do dia   = CDI(1 dia) + Σ βk·xk(hoje)
    IC              = prévia ± t(0,975; n−k−1)·σ·√(1 + 1/n + q'Vq),   q = x(hoje) − x̄

- A prévia é o retorno só de hoje, medido desde o fechamento anterior.
- A cota estimada encadeia os dias desde a última cota divulgada na CVM.
- A amplitude entre janelas é a maior prévia menos a menor. Quando ela é alta, o gestor mudou de posição recentemente.
- **Combinada** (janela principal padrão): é a média das janelas, ponderada pelo inverso do erro quadrático
  de cada uma fora da amostra nos últimos `CALIB_DIAS` (63) dias de cada fundo.
- **IC calibrado**: o intervalo teórico é multiplicado pelo fator que levaria a cobertura empírica
  recente do fundo a 95%. O fator é encolhido para 1 em amostras curtas e limitado entre 0,75 e 3.
  No backtest, a combinação e a calibração são rolantes, sem uso de dados futuros.

| Estratégia | Fatores |
|---|---|
| Long Only, Long Biased, Long Short | IBOV, SMAL11, S&P 500, dólar, XFIX11 |
| Macro | IBOV, S&P 500, dólar, IRFM11, IMAB11, XFIX11 |

## Configuração (topo de `previa.py`)

- `JANELAS`, `MIN_OBS`, `JANELA_PRINCIPAL`
- `PL_MINIMO`, `FATORES`, `FATORES_ESTRATEGIA`, `RIDGE`, `IC_NIVEL`
- `DATAS_EXCLUIR`: dias fora da estimação. O circuit breaker de 26/10/2026 vem excluído.
- `dados/fatores_extra.csv`: séries próprias, como o DI futuro. Colunas com prefixo `TX_` são taxas.

## Limitações

- O Yahoo gratuito tem cerca de 15 min de atraso na B3.
- Os juros entram por ETFs (IRFM11/IMAB11), como proxy do DI futuro.
- Janelas curtas (1m, 2m) têm R² dentro da amostra alto, mas βs instáveis. Compare o erro de cada janela no backtest.
