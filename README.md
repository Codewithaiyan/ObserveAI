
## 🔐 Security Configuration

### Claude API Key Setup

1. Get API key from https://console.anthropic.com
2. Update Kubernetes secret:
```bash
kubectl create secret generic ai-agent-secrets \
  --from-literal=anthropic-api-key='your-key-here' \
  -n observeai \
  --dry-run=client -o yaml | kubectl apply -f -
```

3. Restart agent:
```bash
kubectl rollout restart deployment/ai-agent -n observeai
```

### Files Excluded from Git

- `secret.yaml` - Contains API keys
- `.env` - Local environment variables
- `*.db` - SQLite databases
- `baselines.json` - Learned ML baselines

**Never commit sensitive files to version control!**
