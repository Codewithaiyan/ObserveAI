"""
Incident analyzer with Claude RCA
"""
from typing import List, Dict, Optional
from datetime import datetime
from models.incident import Incident
from ai_analysis.claude_client import claude_client
from utils.logger import logger


class IncidentAnalyzer:
    """Analyzes incidents using Claude"""
    
    def __init__(self):
        self.analysis_history = []
        self.total_analyses = 0
    
    async def analyze_incident(self, incident: Incident) -> Optional[Dict]:
        """Perform RCA on incident"""
        logger.info("Starting incident analysis", incident_id=incident.id)
        
        incident_summary = f"""Incident: {incident.title}
Severity: {incident.severity}
Errors: {incident.error_count}
Services: {', '.join(incident.affected_services)}"""
        
        error_logs = [log.message for log in incident.sample_logs]
        
        anomalies = [{
            'type': a.anomaly_type,
            'severity': a.severity,
            'description': a.description
        } for a in incident.anomalies]
        
        metrics = {
            'error_rate': incident.error_count / incident.log_count if incident.log_count > 0 else 0,
            'total_logs': incident.log_count,
            'error_count': incident.error_count
        }
        
        context = {
            'affected_services': incident.affected_services,
            'started_at': incident.started_at.isoformat()
        }
        
        analysis = await claude_client.analyze_incident(
            incident_summary, error_logs, anomalies, metrics, context
        )
        
        if analysis:
            analysis['analyzed_at'] = datetime.utcnow().isoformat()
            analysis['incident_id'] = incident.id
            
            self.analysis_history.append({
                'incident_id': incident.id,
                'timestamp': datetime.utcnow(),
                'root_cause': analysis.get('root_cause', '')[:100],
                'confidence': analysis.get('confidence', 'Unknown')
            })
            
            self.total_analyses += 1
            logger.info("RCA completed", incident_id=incident.id)
        
        return analysis
    
    async def quick_diagnose(self, error_message: str) -> Optional[str]:
        """Quick diagnosis"""
        return None  # Simplified for now
    
    def get_analysis_history(self, limit: int = 10) -> List[Dict]:
        """Get recent history"""
        return self.analysis_history[-limit:]
    
    def get_statistics(self) -> Dict:
        """Get stats"""
        return {
            'total_analyses': self.total_analyses,
            'history_size': len(self.analysis_history),
            'claude_enabled': claude_client.enabled
        }


incident_analyzer = IncidentAnalyzer()
