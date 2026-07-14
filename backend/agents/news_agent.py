"""News Sentiment Agent - Analyze news and sentiment data"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Dict, Any, Optional, List

from .base_agent import BaseAgent, AgentVote, AgentStatus

log = logging.getLogger(__name__)


@dataclass
class NewsConfig:
    """News sentiment analysis configuration"""
    sentiment_threshold_positive: float = 0.6
    sentiment_threshold_negative: float = -0.6
    urgency_threshold: float = 0.7
    weight_recent_news: float = 0.8  # More recent = higher weight
    min_confidence: float = 0.5


class NewsSentiment:
    """News sentiment data"""
    headline: str
    source: str
    sentiment_score: float  # -1.0 to +1.0
    urgency: float  # 0.0 to 1.0 (impact importance)
    timestamp: float
    category: str  # "economic", "company", "geopolitical", etc.


class NewsAgent(BaseAgent):
    """
    Analyzes news and sentiment data.
    
    Processes:
    - Economic calendars
    - Company news
    - Market sentiment
    - Breaking news
    - Social media sentiment
    """
    
    def __init__(self, config: Optional[NewsConfig] = None):
        super().__init__(agent_id="news", agent_name="News Sentiment")
        self.config = config or NewsConfig()
        self.enabled = True
        self.recent_news: List[NewsSentiment] = []
    
    async def analyze(self, market_data: Dict[str, Any]) -> AgentVote:
        """
        Analyze news sentiment.
        
        Args:
            market_data: News and sentiment data
        
        Returns:
            AgentVote based on sentiment analysis
        """
        try:
            # Extract news data
            sentiment_score = market_data.get("sentiment_score", 0.0)
            urgency = market_data.get("news_urgency", 0.5)
            news_items = market_data.get("news_items", [])
            sentiment_trend = market_data.get("sentiment_trend", "NEUTRAL")
            
            # Calculate weighted sentiment
            weighted_sentiment = self._calculate_weighted_sentiment(news_items)
            
            # Adjust by urgency
            effective_sentiment = weighted_sentiment * (1.0 + urgency * 0.5)
            
            # Generate signal
            direction, confidence, reason = self._generate_signal(
                effective_sentiment, sentiment_trend, urgency, news_items
            )
            
            return AgentVote(
                agent_id=self.agent_id,
                direction=direction,
                confidence=confidence,
                weight=0.9 + (urgency * 0.2),  # Higher weight for urgent news
                reason=reason,
                status=AgentStatus.OK,
                metadata={
                    "sentiment_score": round(weighted_sentiment, 3),
                    "urgency": round(urgency, 3),
                    "sentiment_trend": sentiment_trend,
                    "news_count": len(news_items),
                    "effective_sentiment": round(effective_sentiment, 3)
                }
            )
        
        except Exception as e:
            log.error(f"News sentiment analysis error: {e}")
            return AgentVote(
                agent_id=self.agent_id,
                direction="HOLD",
                confidence=0.0,
                status=AgentStatus.ERROR,
                reason=f"Analysis error: {e}",
                metadata={"error": str(e)}
            )
    
    def _calculate_weighted_sentiment(self, news_items: List[Dict]) -> float:
        """Calculate weighted sentiment from news items"""
        if not news_items:
            return 0.0
        
        total_weight = 0.0
        weighted_sum = 0.0
        
        for news in news_items:
            sentiment = news.get("sentiment", 0.0)
            urgency = news.get("urgency", 0.5)
            recency = news.get("recency", 0.5)  # 0=old, 1=very recent
            
            # Weight = urgency * recency
            weight = urgency * self.config.weight_recent_news + recency * (1 - self.config.weight_recent_news)
            
            weighted_sum += sentiment * weight
            total_weight += weight
        
        if total_weight > 0:
            return weighted_sum / total_weight
        return 0.0
    
    def _generate_signal(
        self, sentiment: float, trend: str, urgency: float, news_items: List[Dict]
    ) -> tuple:
        """Generate trading signal from sentiment"""
        
        confidence = abs(sentiment)
        
        # Strong negative sentiment
        if sentiment < self.config.sentiment_threshold_negative:
            return "SELL", min(confidence, 0.85), f"Negative sentiment ({sentiment:.2f})"
        
        # Strong positive sentiment
        if sentiment > self.config.sentiment_threshold_positive:
            return "BUY", min(confidence, 0.85), f"Positive sentiment ({sentiment:.2f})"
        
        # Sentiment trend analysis
        if trend == "POSITIVE":
            return "BUY", 0.65, "Sentiment improving - bullish trend"
        elif trend == "NEGATIVE":
            return "SELL", 0.65, "Sentiment deteriorating - bearish trend"
        
        # Urgent negative news
        if urgency > self.config.urgency_threshold and sentiment < 0:
            return "SELL", 0.7, "Urgent negative news - selling pressure"
        
        # Urgent positive news
        if urgency > self.config.urgency_threshold and sentiment > 0:
            return "BUY", 0.7, "Urgent positive news - buying opportunity"
        
        # Neutral
        return "HOLD", 0.5, "Neutral sentiment"
    
    async def add_news(self, news: NewsSentiment) -> None:
        """Add news item to recent list"""
        self.recent_news.append(news)
        # Keep only last 100 news items
        if len(self.recent_news) > 100:
            self.recent_news = self.recent_news[-100:]
    
    def get_status(self) -> Dict[str, Any]:
        """Get agent status"""
        return {
            "agent": self.agent_name,
            "enabled": self.enabled,
            "recent_news_count": len(self.recent_news),
            "sentiment_thresholds": {
                "positive": self.config.sentiment_threshold_positive,
                "negative": self.config.sentiment_threshold_negative
            },
            "status": "operational"
        }
