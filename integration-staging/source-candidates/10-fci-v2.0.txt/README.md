# Fit Confidence Index (FCI) with Body Morphology & Skin Analysis

Production‑ready implementation of Cirvanna's hybrid probabilistic model for estimating fit success probability, extended with rich anthropometric and dermatological features from the Human Body Morphology & Calibration Master Atlas and the Global Skin Intelligence Master Atlas.

## Features

- **Structural layer**: Weighted sum of input signals (BMC, GSR, BFS, PHFA)
- **Bayesian layer**: Hierarchical Beta‑Binomial model with Redis storage
- **Neural residual**: Capped residual (±0.1) from any sklearn regressor, now using morphology and skin features
- **Calibration**: Isotonic regression + fast local‑variance confidence intervals
- **Friction policy**: Rule‑based or trainable contextual bandit (epsilon‑greedy)
- **Metrics**: Persistent storage in PostgreSQL or in‑memory, computes Brier, ECE, CI width, return rate, false confidence rate
- **Extended inputs**: Full body measurements (height, weight, circumferences, ratios, body shape) and skin analysis (Fitzpatrick type, undertone, melanin, texture, hydration, conditions)

## Installation
