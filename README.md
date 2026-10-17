# Worlds 2026 predictor

A learning project for building and evaluating machine-learning forecasts of professional League of Legends outcomes.

## Agreed scope

- Modular Python application operated from the terminal initially.
- Only regional and international professional tournament games from the 2026 competitive season, before the first Worlds game including Play-Ins.
- Elo baseline, followed by logistic regression, with chronological evaluation.
- Separate game prediction, series calculation/simulation, and tournament simulation.
- Game-win probabilities, series results, and tournament outcomes first; champion forecasting later.
- A hosted visualization will eventually read exported forecast results.

Read [the architecture](docs/architecture.md) for module responsibilities, assumptions, and implementation milestones.

## Current status

Architecture agreed and documented. No model, dataset, forecast, or deployed visualization exists yet. The exact UTC cutoff and data coverage must be verified before ingestion.

Changes should explain the machine-learning concept involved, alternatives considered, and relevant evaluation evidence.
