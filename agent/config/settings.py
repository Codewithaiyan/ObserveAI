"""
Configuration settings for AI Agent
"""
from pydantic_settings import BaseSettings
from typing import Optional


class Settings(BaseSettings):
    """Application settings"""
    
    # Application
    app_name: str = "ObserveAI Agent"
    app_version: str = "1.0.0"
    debug: bool = True
    
    # Elasticsearch
    elasticsearch_host: str = "elasticsearch.observeai.svc.cluster.local"
    elasticsearch_port: int = 9200
    elasticsearch_url: str = f"http://{elasticsearch_host}:{elasticsearch_port}"
    
    # Prometheus
    prometheus_host: str = "prometheus.observeai.svc.cluster.local"
    prometheus_port: int = 9090
    prometheus_url: str = f"http://{prometheus_host}:{prometheus_port}"
    
    # Monitoring
    log_check_interval: int = 30  # seconds
    anomaly_detection_enabled: bool = True
    error_rate_threshold: float = 0.5  # errors per second
    
    # Database
    database_path: str = "/data/incidents.db"
    
    # Claude API (will be set via environment variable)
    anthropic_api_key: Optional[str] = None
    
    # Alert thresholds
    high_error_threshold: int = 10  # errors in time window
    anomaly_score_threshold: float = 0.7
    
    class Config:
        env_file = ".env"
        case_sensitive = False


# Global settings instance
settings = Settings()
