# Alert Configuration Setup

## 1. Get Slack Webhook URL

### Create Slack Incoming Webhook:
1. Go to your Slack workspace
2. Navigate to: https://api.slack.com/apps
3. Click "Create New App" → "From scratch"
4. Name: "ObserveAI Alerts"
5. Select your workspace
6. Click "Incoming Webhooks" in sidebar
7. Toggle "Activate Incoming Webhooks" to ON
8. Click "Add New Webhook to Workspace"
9. Select channel (e.g., #alerts, #incidents)
10. Copy the webhook URL (starts with https://hooks.slack.com/services/...)

## 2. Create Kubernetes Secret
```bash
# Create secret with your actual webhook URL
kubectl create secret generic ai-agent-alerts \
  --from-literal=slack-webhook-url='https://hooks.slack.com/services/YOUR/WEBHOOK/URL' \
  --from-literal=generic-webhook-url='' \
  -n observeai
```

## 3. Update Deployment
```bash
# Apply the deployment patch
kubectl patch deployment ai-agent -n observeai --patch-file deployment-patch.yaml

# Restart to pick up new environment variables
kubectl rollout restart deployment/ai-agent -n observeai
kubectl rollout status deployment/ai-agent -n observeai
```

## 4. Test Alert System
```bash
# Test via API
kubectl exec -n observeai deployment/ai-agent -- curl -X POST http://localhost:8000/api/alerts/test

# Check alert status
kubectl exec -n observeai deployment/ai-agent -- curl http://localhost:8000/api/alerts/status
```

## Alternative: webhook.site for Testing

If you don't have Slack access:
1. Go to https://webhook.site
2. Copy your unique URL
3. Use it as generic-webhook-url to see webhook payloads
