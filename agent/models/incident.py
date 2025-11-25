"""
Incident data models
"""
from datetime import datetime
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field


class LogEntry(BaseModel):
    """Single log entry"""
    timestamp: str
    level: str
    message: str
    service: Optional[str] = None
    pod: Optional[str] = None
    namespace: Optional[str] = None


class Anomaly(BaseModel):
    """Detected anomaly"""
    anomaly_type: str  # "error_spike", "unusual_pattern", "service_degradation"
    severity: str  # "low", "medium", "high", "critical"
    score: float  # 0.0 to 1.0
    description: str
    detected_at: datetime = Field(default_factory=datetime.utcnow)
    metrics: Dict[str, Any] = {}


class Incident(BaseModel):
    """Incident record"""
    id: Optional[str] = None
    title: str
    description: str
    severity: str  # "low", "medium", "high", "critical"
    status: str = "open"  # "open", "investigating", "resolved"
    
    # Timing
    started_at: datetime
    detected_at: datetime = Field(default_factory=datetime.utcnow)
    resolved_at: Optional[datetime] = None
    
    # Analysis
    anomalies: List[Anomaly] = []
    affected_services: List[str] = []
    log_count: int = 0
    error_count: int = 0
    
    # Root cause analysis (to be filled by LLM)
    root_cause: Optional[str] = None
    recommendations: List[str] = []
    
    # Evidence
    sample_logs: List[LogEntry] = []
    metrics_snapshot: Dict[str, Any] = {}


class MonitoringState(BaseModel):
    """Current monitoring state"""
    last_check: datetime
    logs_processed: int = 0
    anomalies_detected: int = 0
    incidents_created: int = 0
    status: str = "healthy"  # "healthy", "degraded", "error"
