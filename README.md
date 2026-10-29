# Prévia de cotas por fatores

Prévia do retorno diário de fundos Long Only, Long Biased, Long Short, Macro e Hedge Alternative,
estimada em seis janelas (1m, 2m, 3m, 6m, 12m, 24m) e num modelo exponencial (EW), combinados pelo
erro fora da amostra, com intervalo de predição de 95% calibrado. Base de 36 meses de cotas da CVM.

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

Layout de estação de trabalho, em painéis uniformes:
- **Barra superior:** data, status dos preços (ao vivo ou último fechamento), base do dia, última cota CVM,
  modelo e número de fundos.
- **Hedge Alternative Investments:** prévia de hoje de Master, FICFI, W FIC e Prev FIC, com faixa de 95%,
  cota estimada, retorno realizado (último dia, mês e ano, pela CVM) e PL.
- **Rentabilidade acumulada (Hedge Alternative):** retorno pela cota oficial da CVM no dia, semana, mês,
  1M, 3M, 6M, ano e 12M; CDI do mesmo período; % do CDI no ano e em 12M; e mês, ano e 12M "com a prévia",
  que encadeiam o retorno estimado desde a última cota até agora.
- **Mercado:** cada fator com o último valor e a variação no dia, em 5 pregões, no mês e no ano.
- **Estratégias:** mediana, P10–P90 entre fundos e quantos sobem e caem.
- **Maiores altas, maiores quedas e atenção** (janelas divergindo, cota atrasada, R² baixo).
- Abas **Monitor de fundos** (tabela completa com busca, ordenação e exportação para Excel/CSV), **Fundo**
  (modelos, sensibilidades, gráfico de prévia × realizado) e **Qualidade do modelo**.

Logo abaixo do cabeçalho fica a **barra de controles**: estratégias, gestores, modelo de referência, R² e
PL mínimos, **Ajustes** (α, intervalo de atualização e movimento manual dos fatores), **Atualizar preços**
e **Atualizar base**. No monitor, as pílulas de estratégia filtram a tabela com um clique.

Botões de atualização:
- **Atualizar preços agora:** consulta o Yahoo na hora. Fora isso, os preços ficam em cache por 30 s.
- **Atualizar base e recalcular:** roda `pv.atualizar()` e `pv.estimar()` pelo próprio painel e recarrega os dados.
- **Movimento manual dos fatores:** a variação do dia digitada (% ou pp para `TX_`) substitui o Yahoo
  no fator preenchido. Os fatores marcados como manuais aparecem destacados nos cards.

Usa a paleta Hedge Investments (marinho #0A4263, azul #00A0D7, celeste #81C1D7) e a fonte Compass.
Se a fonte estiver instalada no computador, o painel a usa direto. Se não, coloque os arquivos em
`static/fonts/`. As cores do tema ficam em `.streamlit/config.toml`, e a paleta completa em `PALETA`,
no `painel.py`.

## Rentabilidade acumulada

`pv.retornos_acumulados(cot, cdi)` calcula, para cada fundo, o retorno da última cota da CVM contra a
cota da data-base de cada janela (`JANELAS_ACUM`): Dia, Semana (7 dias corridos), Mês (desde o fim do mês
anterior), 1M, 3M, 6M (meses corridos), Ano (desde 31/12), 12M, 24M e 36M. Também traz o CDI do mesmo período e o
% do CDI. Se o histórico do fundo começar até `TOLERANCIA_INICIO` (10) dias depois da data-base ideal,
usa a primeira cota disponível, e a data usada fica em `base_<janela>`. A atualização baixa 37 meses de
informes para que os 36M fiquem completos. O `pv.consolidado()` inclui essas colunas.

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

| Estratégia | Fatores principais (todos os modelos) | Adicionais (6m, 12m, 24m, EW) |
|---|---|---|
| Long Only, Long Biased | IBOV, SMAL11, S&P 500, dólar, XFIX11 | Nasdaq, Brent, ouro, EEM, S&P D-1, dólar D-1 |
| Long Short | IBOV, SMAL11, S&P 500, dólar, XFIX11 | Nasdaq, Brent, EEM, S&P D-1 |
| Macro | IBOV, S&P 500, dólar, IRFM11, IMAB11, XFIX11 | Treasury 10a, Brent, ouro, EEM, S&P D-1, dólar D-1 |
| Hedge Alternative | IBOV, SMAL11, S&P 500, dólar, IRFM11, IMAB11, XFIX11 | Treasury 10a, Brent, ouro, S&P D-1, dólar D-1 |

**Modelos:** janelas móveis de 1m, 2m, 3m, 6m, 12m e 24m (21 a 500 pregões) e **EW**, que usa todo o
histórico com peso exponencial (meia-vida de 63 pregões). A **combinada** pondera os sete pelo inverso do
erro recente de cada fundo.

**Fatores defasados (D-1):** S&P 500 e dólar do dia anterior, para fundos que marcam ativos no exterior
com preço de D-1 ou que têm fechamento assíncrono.

**Contra sobreajuste:** o ridge é adaptativo, `RIDGE × (1 + RIDGE_ESCALA × fatores / obs.)`, e os fatores
adicionais só entram nos modelos com pelo menos `OBS_MIN_ADICIONAIS` (120) observações. Para conferir
com os seus dados se vale incluí-los também nas janelas curtas, rode `pv.testar_fatores()`: ele compara,
fora da amostra, os extras em todos os modelos, só nos longos ou em nenhum.

`FUNDOS_INCLUIR` (topo do `previa.py`) força fundos no universo com estratégia própria, ignorando classe,
PL mínimo e exclusividade. Vem com os 4 fundos da Hedge Alternative Investments (Master, FICFI, W FIC e
Prev FIC), que têm uma aba própria no painel. Para acompanhar outro fundo, inclua o CNPJ e a estratégia
e, se for uma estratégia nova, os fatores dela em `FATORES_ESTRATEGIA`.

## Configuração (topo de `previa.py`)

- `JANELAS`, `MIN_OBS`, `JANELA_PRINCIPAL`
- `PL_MINIMO`, `FATORES`, `FATORES_ESTRATEGIA`, `RIDGE`, `IC_NIVEL`
- `DATAS_EXCLUIR`: dias fora da estimação. O circuit breaker de 26/10/2026 vem excluído.
- `dados/fatores_extra.csv`: séries próprias, como o DI futuro. Colunas com prefixo `TX_` são taxas.

## Limitações

- O Yahoo gratuito tem cerca de 15 min de atraso na B3.
- Os juros entram por ETFs (IRFM11/IMAB11), como proxy do DI futuro.
- Janelas curtas (1m, 2m) têm R² dentro da amostra alto, mas βs instáveis. Compare o erro de cada janela no backtest.
