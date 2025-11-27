"""
Claude API client for root cause analysis
"""
from typing import List, Dict, Optional
from config.settings import settings
from utils.logger import logger

try:
    import anthropic
    ANTHROPIC_AVAILABLE = True
except ImportError:
    ANTHROPIC_AVAILABLE = False
    logger.warning("Anthropic SDK not available")


class ClaudeClient:
    """Client for Claude API with RCA capabilities"""
    
    def __init__(self):
        """Initialize Claude client"""
        if not ANTHROPIC_AVAILABLE:
            logger.warning("Anthropic SDK not installed")
            self.client = None
            self.enabled = False
            return
        
        if not settings.anthropic_api_key or settings.anthropic_api_key == "placeholder":
            logger.warning("Claude API key not configured")
            self.client = None
            self.enabled = False
        else:
            try:
                self.client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
                self.enabled = True
                logger.info("Claude API client initialized successfully")
            except Exception as e:
                logger.error("Failed to initialize Claude", error=str(e))
                self.client = None
                self.enabled = False
    
    async def analyze_incident(
        self,
        incident_summary: str,
        error_logs: List[str],
        anomalies: List[Dict],
        metrics: Dict,
        context: Optional[Dict] = None
    ) -> Optional[Dict]:
        """Perform RCA using Claude"""
        if not self.enabled or not self.client:
            return None
        
        try:
            prompt = self._build_rca_prompt(
                incident_summary, error_logs, anomalies, metrics, context
            )
            
            logger.info("Sending to Claude for RCA")
            
            message = self.client.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=2000,
                temperature=0.3,
                messages=[{"role": "user", "content": prompt}]
            )
            
            response_text = message.content[0].text
            analysis = self._parse_rca_response(response_text)
            
            logger.info("Claude RCA completed")
            return analysis
            
        except Exception as e:
            logger.error("Claude API error", error=str(e))
            return None
    
    def _build_rca_prompt(self, incident_summary, error_logs, anomalies, metrics, context):
        prompt = f"""You are a DevOps expert. Analyze this incident:

# INCIDENT
{incident_summary}

# ERRORS
"""
        for i, log in enumerate(error_logs[:10], 1):
            prompt += f"{i}. {log[:100]}\n"
        
        prompt += "\n# ANOMALIES\n"
        for a in anomalies[:5]:
            prompt += f"- {a.get('type')}: {a.get('description')}\n"
        
        prompt += f"""
Provide:

## Root Cause
[Identify root cause]

## Immediate Actions
1. [Action 1]
2. [Action 2]
3. [Action 3]

## Confidence
[High/Medium/Low]
"""
        return prompt
    
    def _parse_rca_response(self, response_text):
        sections = {
            'root_cause': '',
            'impact': '',
            'technical_explanation': '',
            'immediate_actions': [],
            'prevention': [],
            'confidence': 'Medium',
            'full_analysis': response_text
        }
        
        lines = response_text.split('\n')
        current_section = None
        content = []
        
        for line in lines:
            lower = line.lower()
            if '## root' in lower:
                if current_section:
                    sections[current_section] = '\n'.join(content).strip()
                current_section = 'root_cause'
                content = []
            elif '## impact' in lower:
                if current_section:
                    sections[current_section] = '\n'.join(content).strip()
                current_section = 'impact'
                content = []
            elif '## immediate' in lower:
                if current_section:
                    sections[current_section] = '\n'.join(content).strip()
                current_section = 'immediate_actions'
                content = []
            elif '## confidence' in lower:
                if current_section == 'immediate_actions':
                    sections[current_section] = [c.strip() for c in content if c.strip()]
                elif current_section:
                    sections[current_section] = '\n'.join(content).strip()
                current_section = 'confidence'
                content = []
            elif current_section:
                if current_section == 'immediate_actions' and line.strip().startswith(('1.', '2.', '3.', '-')):
                    clean = line.strip().lstrip('123.-*').strip()
                    if clean:
                        content.append(clean)
                else:
                    content.append(line)
        
        if current_section:
            if current_section == 'immediate_actions':
                sections[current_section] = [c.strip() for c in content if c.strip()]
            else:
                sections[current_section] = '\n'.join(content).strip()
        
        if not sections['root_cause']:
            sections['root_cause'] = response_text[:200]
        if not sections['immediate_actions']:
            sections['immediate_actions'] = ['Check logs', 'Review changes', 'Monitor system']
        
        return sections


claude_client = ClaudeClient()
