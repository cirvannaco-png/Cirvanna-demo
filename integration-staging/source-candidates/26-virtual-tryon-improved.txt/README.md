# Cirvanna Virtual Try-On Core Infrastructure

## 🚀 Overview
Production-ready virtual try-on system that generates 3D body meshes from images and provides fit confidence scores for garments.

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
