# Fit Confidence Index (FCI)

Production‑ready implementation of Cirvanna's hybrid probabilistic model for estimating fit success probability.

## Components

- **Structural layer**: Weighted sum of input signals (BMC, GSR, BFS, PHFA)
- **Bayesian layer**: Hierarchical Beta‑Binomial model with Redis storage
- **Neural residual**: Capped residual (±0.1) from any sklearn regressor
- **Calibration**: Isotonic regression + fast local‑variance confidence intervals
- **Friction policy**: Rule‑based or trainable contextual bandit (epsilon‑greedy)
- **Metrics**: Persistent storage in PostgreSQL or in‑memory, computes Brier, ECE, CI width, return rate, false confidence rate

## Installation
