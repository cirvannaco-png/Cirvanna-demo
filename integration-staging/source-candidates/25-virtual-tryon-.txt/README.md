> **Status: unverified source candidate — not production-ready.** This directory preserves assembled source snippets whose completeness, dependencies, security, and runtime behavior have not been certified. A few truncated files were reconstructed minimally to restore syntax using sibling variants; this does not establish functional correctness. The original input remains preserved in `integration-staging/source-intake/original/cirvanna-source.txt`. See `docs/migration/source-candidate-syntax-repairs.md` for repair scope and limitations.

# Cirvanna Virtual Try-On Core Infrastructure

## Overview

The intended design describes virtual try-on, garment structure, deformation estimation, and fit-confidence concepts. Those goals are not proof that working implementations exist or have been validated.

## 🏗️ Architecture

- **AIS** - Anthropometric Intelligence Service (3D mesh generation)
- **GSIS** - Garment Structural Intelligence Service (garment database)
- **DTAE** - Deformation & Tension Approximation Engine
- **FCE** - Fit Confidence Engine (ML-based scoring)
- **Admin Dashboard** - Monitoring and management

## 📋 Prerequisites

- Docker & Docker Compose
- NVIDIA GPU + CUDA 11.7+ (optional, for GPU acceleration)
- AWS account (for S3 storage, optional)

## 🚀 Quick Start
