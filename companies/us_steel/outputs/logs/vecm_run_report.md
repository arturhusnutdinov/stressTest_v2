# VECM Run Report

Config: /home/companies/us_steel/configs/macro_ecm.yaml

- Cointegration testing with dummies: enabled
- Shock years: [2008, 2015, 2020, 2022, 2021]
- Max dummies: 5

- Cyclical factors detected: gdp_us, industrial_production_us, dxy, steel_price_hrc, iron_ore_price, cpi_us, ppi_us

- Univariate fallback order: auto_arima, ets, arima011, rw_drift

- Cyclical fallback order: seasonal_ets, stl_arima, auto_arima, ets, linear_reg, arima011, rw_drift

## Group Selection Summary
- us_economy: gdp_us, industrial_production_us, cpi_us, ppi_us (manual, score=None)
- metals_prices: steel_price_hrc, iron_ore_price (manual, score=None)
- fx_and_global: dxy, gdp_world (manual, score=None)
- auto_group_1: gdp_us, industrial_production_us, cpi_us (vecm, score=265.9608184837525)
- auto_group_2: gdp_us, dxy, cpi_us (vecm, score=253.15707598205506)

## Block: us_economy
- factors: gdp_us, industrial_production_us, cpi_us, ppi_us
- history_years: 15
- selected_lag_p: 2
- selected_rank: 1
- equations_exported: yes (1)
  - factor gdp_us: lb_pvalue=0.9419
  - factor industrial_production_us: lb_pvalue=0.9974
  - factor cpi_us: lb_pvalue=0.9253
  - factor ppi_us: lb_pvalue=0.5472

## Block: metals_prices
- factors: steel_price_hrc, iron_ore_price
- history_years: 15
- selected_lag_p: 2
- selected_rank: 2
- n_dummies: 3
- dummy_shock_years: [2021, 2015, 2020]
- equations_exported: yes (2)
  - factor steel_price_hrc: forecast unstable (extreme_yoy_change_5.9pct)
  - factor iron_ore_price: forecast unstable (too_large_initial_change_-5.6pct)
- decision: switching to univariate ECM (VECM forecast unstable)

## Block: fx_and_global
- factors: dxy, gdp_world
- history_years: 19
- selected_lag_p: 2
- selected_rank: 0
- decision: VAR fallback (rank=0, no cointegration)
- decision: univariate fallback (rank=0, VAR failed)

## Block: auto_group_1
- factors: gdp_us, industrial_production_us, cpi_us
- history_years: 15
- selected_lag_p: 2
- selected_rank: 1
- n_dummies: 3
- dummy_shock_years: [2021, 2022, 2020]
- equations_exported: yes (1)
  - factor gdp_us: lb_pvalue=0.3989
  - factor industrial_production_us: lb_pvalue=0.8306
  - factor cpi_us: lb_pvalue=0.0283

## Block: auto_group_2
- factors: gdp_us, dxy, cpi_us
- history_years: 15
- selected_lag_p: 2
- selected_rank: 1
- n_dummies: 2
- dummy_shock_years: [2022, 2015]
- equations_exported: yes (1)
  - factor gdp_us: lb_pvalue=0.5990
  - factor dxy: lb_pvalue=0.5544
  - factor cpi_us: lb_pvalue=0.4516
