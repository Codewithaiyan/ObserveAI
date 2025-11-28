"""
Alert Manager for incident notifications
"""
from typing import List, Optional, Dict
import httpx
import asyncio
from datetime import datetime
from config.settings import settings
from utils.logger import logger
from models.incident import Incident


class AlertManager:
    """Manages alert notifications for incidents"""
    
    def __init__(self):
        self.alert_history = []
        self.total_alerts_sent = 0
        self.failed_alerts = 0
        
        # Alert configuration
        self.slack_webhook_url = settings.slack_webhook_url
        self.generic_webhook_url = settings.generic_webhook_url
        self.alert_on_severities = settings.alert_on_severities or ["high", "critical"]
        
        logger.info(
            "Alert Manager initialized",
            slack_enabled=bool(self.slack_webhook_url),
            webhook_enabled=bool(self.generic_webhook_url),
            alert_severities=self.alert_on_severities
        )
    
    async def send_incident_alert(self, incident: Incident) -> bool:
        """
        Send alerts for an incident based on severity
        
        Args:
            incident: The incident to alert on
            
        Returns:
            bool: True if at least one alert was sent successfully
        """
        # Check if we should alert on this severity
        if incident.severity not in self.alert_on_severities:
            logger.debug(
                "Skipping alert - severity not in alert list",
                incident_id=incident.id,
                severity=incident.severity
            )
            return False
        
        logger.info(
            "Sending incident alerts",
            incident_id=incident.id,
            severity=incident.severity
        )
        
        alerts_sent = []
        
        # Send to Slack
        if self.slack_webhook_url:
            slack_result = await self._send_slack_alert(incident)
            alerts_sent.append(slack_result)
        
        # Send to generic webhook
        if self.generic_webhook_url:
            webhook_result = await self._send_webhook_alert(incident)
            alerts_sent.append(webhook_result)
        
        # Update statistics
        if any(alerts_sent):
            self.total_alerts_sent += 1
            self._record_alert(incident, success=True)
            return True
        else:
            self.failed_alerts += 1
            self._record_alert(incident, success=False)
            return False
    
    async def _send_slack_alert(self, incident: Incident) -> bool:
        """Send formatted alert to Slack"""
        try:
            message = self._format_slack_message(incident)
            
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(
                    self.slack_webhook_url,
                    json=message
                )
                
                if response.status_code == 200:
                    logger.info(
                        "Slack alert sent successfully",
                        incident_id=incident.id
                    )
                    return True
                else:
                    logger.error(
                        "Slack alert failed",
                        incident_id=incident.id,
                        status_code=response.status_code
                    )
                    return False
                    
        except Exception as e:
            logger.error(
                "Slack alert exception",
                incident_id=incident.id,
                error=str(e)
            )
            return False
    
    async def _send_webhook_alert(self, incident: Incident) -> bool:
        """Send JSON payload to generic webhook"""
        try:
            payload = self._format_webhook_payload(incident)
            
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(
                    self.generic_webhook_url,
                    json=payload
                )
                
                if response.status_code in [200, 201, 202]:
                    logger.info(
                        "Webhook alert sent successfully",
                        incident_id=incident.id
                    )
                    return True
                else:
                    logger.error(
                        "Webhook alert failed",
                        incident_id=incident.id,
                        status_code=response.status_code
                    )
                    return False
                    
        except Exception as e:
            logger.error(
                "Webhook alert exception",
                incident_id=incident.id,
                error=str(e)
            )
            return False
    
    def _format_slack_message(self, incident: Incident) -> Dict:
        """Format incident as Slack message with blocks"""
        
        # Severity emoji
        severity_emoji = {
            "critical": "🚨",
            "high": "⚠️",
            "medium": "⚡",
            "low": "ℹ️"
        }
        emoji = severity_emoji.get(incident.severity, "📊")
        
        # Color coding
        color_map = {
            "critical": "#FF0000",
            "high": "#FFA500",
            "medium": "#FFFF00",
            "low": "#00FF00"
        }
        color = color_map.get(incident.severity, "#808080")
        
        # Build message blocks
        blocks = [
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": f"{emoji} {incident.title}",
                    "emoji": True
                }
            },
            {
                "type": "section",
                "fields": [
                    {
                        "type": "mrkdwn",
                        "text": f"*Incident ID:*\n{incident.id}"
                    },
                    {
                        "type": "mrkdwn",
                        "text": f"*Severity:*\n{incident.severity.upper()}"
                    },
                    {
                        "type": "mrkdwn",
                        "text": f"*Error Rate:*\n{incident.error_count}/{incident.log_count} logs"
                    },
                    {
                        "type": "mrkdwn",
                        "text": f"*Services:*\n{', '.join(incident.affected_services)}"
                    }
                ]
            }
        ]
        
        # Add RCA summary if available
        if incident.rca_analysis:
            rca_text = incident.rca_analysis.root_cause[:200]
            blocks.append({
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*🤖 AI Root Cause:*\n{rca_text}..."
                }
            })
            
            if incident.rca_analysis.immediate_actions:
                actions_text = "\n".join([
                    f"{i}. {action[:80]}"
                    for i, action in enumerate(incident.rca_analysis.immediate_actions[:3], 1)
                ])
                blocks.append({
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f"*⚡ Immediate Actions:*\n{actions_text}"
                    }
                })
        
        # Add timestamp
        blocks.append({
            "type": "context",
            "elements": [
                {
                    "type": "mrkdwn",
                    "text": f"Detected at {incident.started_at.strftime('%Y-%m-%d %H:%M:%S UTC')}"
                }
            ]
        })
        
        return {
            "text": f"{emoji} Incident: {incident.title}",
            "blocks": blocks,
            "attachments": [{
                "color": color,
                "fallback": f"Incident {incident.id}: {incident.title}"
            }]
        }
    
    def _format_webhook_payload(self, incident: Incident) -> Dict:
        """Format incident as generic JSON payload"""
        
        payload = {
            "incident_id": incident.id,
            "title": incident.title,
            "description": incident.description,
            "severity": incident.severity,
            "started_at": incident.started_at.isoformat(),
            "error_count": incident.error_count,
            "log_count": incident.log_count,
            "error_rate": incident.error_count / incident.log_count if incident.log_count > 0 else 0,
            "affected_services": incident.affected_services,
            "anomalies": [
                {
                    "type": a.anomaly_type,
                    "severity": a.severity,
                    "score": a.score,
                    "description": a.description
                }
                for a in incident.anomalies
            ]
        }
        
        # Add RCA if available
        if incident.rca_analysis:
            payload["rca"] = {
                "root_cause": incident.rca_analysis.root_cause,
                "impact": incident.rca_analysis.impact,
                "immediate_actions": incident.rca_analysis.immediate_actions,
                "confidence": incident.rca_analysis.confidence
            }
        
        return payload
    
    def _record_alert(self, incident: Incident, success: bool):
        """Record alert in history"""
        self.alert_history.append({
            "incident_id": incident.id,
            "severity": incident.severity,
            "timestamp": datetime.utcnow(),
            "success": success
        })
        
        # Keep only last 50 alerts
        if len(self.alert_history) > 50:
            self.alert_history = self.alert_history[-50:]
    
    def get_statistics(self) -> Dict:
        """Get alert statistics"""
        return {
            "total_alerts_sent": self.total_alerts_sent,
            "failed_alerts": self.failed_alerts,
            "success_rate": (
                self.total_alerts_sent / (self.total_alerts_sent + self.failed_alerts)
                if (self.total_alerts_sent + self.failed_alerts) > 0
                else 0
            ),
            "recent_alerts": len(self.alert_history),
            "slack_enabled": bool(self.slack_webhook_url),
            "webhook_enabled": bool(self.generic_webhook_url)
        }
    
    def get_recent_alerts(self, limit: int = 10) -> List[Dict]:
        """Get recent alert history"""
        return self.alert_history[-limit:]


# Global alert manager instance
alert_manager = AlertManager()
