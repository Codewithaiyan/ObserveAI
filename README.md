# 🤖 ObserveAI

<div align="center">

![ObserveAI Banner](https://img.shields.io/badge/ObserveAI-DevOps_Observability-blue?style=for-the-badge&logo=kubernetes)

**AI-Powered DevOps Observability Platform with LLM-based Root Cause Analysis**

[![Kubernetes](https://img.shields.io/badge/kubernetes-%23326ce5.svg?style=for-the-badge&logo=kubernetes&logoColor=white)](https://kubernetes.io/)
[![Prometheus](https://img.shields.io/badge/Prometheus-E6522C?style=for-the-badge&logo=Prometheus&logoColor=white)](https://prometheus.io/)
[![Claude AI](https://img.shields.io/badge/Claude_AI-8B4513?style=for-the-badge&logo=anthropic&logoColor=white)](https://www.anthropic.com/)
[![Elasticsearch](https://img.shields.io/badge/Elasticsearch-005571?style=for-the-badge&logo=elasticsearch&logoColor=white)](https://www.elastic.co/)

[Features](#-features) • [Architecture](#-architecture) • [Quick Start](#-quick-start) • [Configuration](#%EF%B8%8F-configuration) • [Documentation](#-documentation)

</div>

---

## 🌟 Overview

ObserveAI is an intelligent DevOps observability platform that combines the power of traditional monitoring tools with advanced AI capabilities. Using Claude AI for root cause analysis, it automatically detects, analyzes, and helps resolve incidents in your Kubernetes infrastructure.

### Why ObserveAI?

- 🧠 **Intelligent Analysis**: Leverage Claude AI to automatically identify root causes of incidents
- 🚀 **Automated Response**: Reduce mean time to resolution (MTTR) with AI-driven insights
- 📊 **Unified Observability**: Single pane of glass for metrics, logs, and traces
- 🔄 **Real-time Monitoring**: Continuous monitoring with instant alerting
- 🎯 **Kubernetes Native**: Built specifically for cloud-native applications

---

## ✨ Features

### Core Capabilities

- **🤖 AI-Powered Root Cause Analysis**
  - Automatic incident detection and correlation
  - Natural language explanations of system issues
  - Intelligent anomaly detection with machine learning baselines

- **📈 Comprehensive Monitoring**
  - Prometheus metrics collection and alerting
  - Elasticsearch log aggregation and analysis
  - Real-time performance dashboards

- **🔔 Smart Alerting**
  - Context-aware alert generation
  - Alert correlation to reduce noise
  - Customizable notification channels

- **🔍 Deep Observability**
  - Container and pod-level visibility
  - Resource utilization tracking
  - Application performance monitoring

---

## 🏗️ Architecture

```
┌─────────────────────────────────────────────────────────┐
│                    Kubernetes Cluster                    │
│                                                           │
│  ┌─────────────┐    ┌──────────────┐   ┌─────────────┐ │
│  │ Prometheus  │───▶│  AI Agent    │◀──│Elasticsearch│ │
│  │  Metrics    │    │  (Claude AI) │   │    Logs     │ │
│  └─────────────┘    └──────────────┘   └─────────────┘ │
│         │                   │                   │        │
│         └───────────────────┼───────────────────┘        │
│                             │                            │
│                    ┌────────▼────────┐                   │
│                    │   Dashboard     │                   │
│                    │   & Alerts      │                   │
│                    └─────────────────┘                   │
└─────────────────────────────────────────────────────────┘
```

### Components

- **AI Agent**: Claude AI-powered analysis engine
- **Prometheus**: Time-series metrics database
- **Elasticsearch**: Log storage and search
- **Kubernetes**: Container orchestration platform

---

## 🚀 Quick Start

### Prerequisites

- Kubernetes cluster (v1.20+)
- kubectl configured
- Helm 3.x
- Claude AI API key ([Get one here](https://console.anthropic.com))

### Installation

1. **Clone the repository**
   ```bash
   git clone https://github.com/Codewithaiyan/ObserveAI.git
   cd ObserveAI
   ```

2. **Create namespace**
   ```bash
   kubectl create namespace observeai
   ```

3. **Configure API Key**
   ```bash
   kubectl create secret generic ai-agent-secrets \
     --from-literal=anthropic-api-key='your-api-key-here' \
     -n observeai
   ```

4. **Deploy ObserveAI**
   ```bash
   kubectl apply -f k8s/ -n observeai
   ```

5. **Verify deployment**
   ```bash
   kubectl get pods -n observeai
   ```

### Access the Dashboard

```bash
kubectl port-forward -n observeai svc/observeai-dashboard 3000:3000
```

Navigate to `http://localhost:3000`

---

## ⚙️ Configuration

### Environment Variables

Create a `.env` file with the following variables:

```env
ANTHROPIC_API_KEY=your_api_key_here
PROMETHEUS_URL=http://prometheus:9090
ELASTICSEARCH_URL=http://elasticsearch:9200
LOG_LEVEL=info
```

### Updating API Key

If you need to update your Claude AI API key:

```bash
kubectl create secret generic ai-agent-secrets \
  --from-literal=anthropic-api-key='your-new-key' \
  -n observeai \
  --dry-run=client -o yaml | kubectl apply -f -

# Restart the AI agent
kubectl rollout restart deployment/ai-agent -n observeai
```

### Machine Learning Baselines

ObserveAI learns normal behavior patterns and stores them in `baselines.json`. To reset or update:

```bash
kubectl exec -it deployment/ai-agent -n observeai -- rm /app/baselines.json
kubectl rollout restart deployment/ai-agent -n observeai
```

---

## 📖 Documentation

### Key Concepts

- **Incidents**: Detected anomalies or threshold breaches
- **Root Cause Analysis**: AI-generated explanations of incident causes
- **Baselines**: Learned normal behavior patterns
- **Alerts**: Notifications triggered by incidents

### API Reference

ObserveAI exposes a REST API for integration:

```bash
# Get system status
curl http://localhost:8080/api/v1/status

# Query incidents
curl http://localhost:8080/api/v1/incidents

# Trigger manual analysis
curl -X POST http://localhost:8080/api/v1/analyze \
  -H "Content-Type: application/json" \
  -d '{"target": "deployment/my-app"}'
```

---

## 🔒 Security Best Practices

⚠️ **Important**: Never commit sensitive files to version control!

Protected files:
- `secret.yaml` - Contains API keys
- `.env` - Local environment variables
- `*.db` - SQLite databases
- `baselines.json` - Learned ML baselines

Always use Kubernetes secrets for sensitive data in production.

---

## 🛠️ Development

### Local Development Setup

```bash
# Install dependencies
pip install -r requirements.txt

# Run tests
pytest tests/

# Run locally
python src/agent.py
```

### Building Docker Image

```bash
docker build -t observeai:latest .
docker push your-registry/observeai:latest
```

---

## 🤝 Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

1. Fork the repository
2. Create your feature branch (`git checkout -b feature/AmazingFeature`)
3. Commit your changes (`git commit -m 'Add some AmazingFeature'`)
4. Push to the branch (`git push origin feature/AmazingFeature`)
5. Open a Pull Request

---

## 🙏 Acknowledgments

- [Claude AI](https://www.anthropic.com/) for powering intelligent analysis
- [Prometheus](https://prometheus.io/) for metrics collection
- [Elasticsearch](https://www.elastic.co/) for log aggregation
- [Kubernetes](https://kubernetes.io/) for container orchestration

---

## 📧 Contact

**Author**: Codewithaiyan

**Project Link**: [https://github.com/Codewithaiyan/ObserveAI](https://github.com/Codewithaiyan/ObserveAI)

---

<div align="center">

**If you find this project helpful, please consider giving it a ⭐!**

Made with ❤️ by [Codewithaiyan](https://github.com/Codewithaiyan)

</div>
