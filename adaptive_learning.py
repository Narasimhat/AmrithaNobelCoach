"""
Adaptive Learning Engine for The Silent Room
Tracks comprehension, adjusts difficulty, and creates personalized learning pathways.
"""

from typing import Dict, List, Optional, Tuple, Any, Union
from datetime import datetime, timedelta
import json
import math


class AdaptiveLearningEngine:
    """
    Manages personalized learning pathways based on child's performance and comprehension.
    Uses Zone of Proximal Development (ZPD) theory to optimize learning.
    """
    
    # Difficulty levels
    BEGINNER = 1
    ELEMENTARY = 2
    INTERMEDIATE = 3
    ADVANCED = 4
    EXPERT = 5
    
    # Comprehension indicators
    COMPREHENSION_KEYWORDS = {
        'high': ['understand', 'makes sense', 'i see', 'got it', 'clear', 'know', 'learned'],
        'medium': ['think', 'maybe', 'probably', 'seems', 'guess'],
        'low': ['confused', 'don\'t understand', 'what', 'why', 'help', 'hard', 'difficult'],
        'curiosity': ['how', 'why', 'what if', 'can we', 'tell me more', 'interesting', 'cool']
    }
    
    # Topic categories from your app
    TOPICS = [
        'Space', 'Oceans', 'Robots', 'Climate', 'Nature', 'Energy', 'Math',
        'Physics', 'Chemistry', 'Biology', 'Engineering', 'Art', 'Music',
        'Coding', 'History', 'Philosophy', 'Ethics'
    ]
    
    def __init__(self, saved_state: Optional[Union[str, Dict[str, Any]]] = None):
        """Initialize the adaptive learning engine with optional saved state."""
        self.skill_matrix: Dict[str, Dict[int, float]] = {}  # {topic: {difficulty: performance_score}}
        self.comprehension_history: List[Dict[str, Any]] = []  # Track recent comprehension
        self.question_history: List[Dict[str, Any]] = []  # Track questions asked
        if saved_state:
            self.load_state(saved_state)
    
    def load_state(self, state: Union[str, Dict[str, Any]]) -> None:
        """Load persisted state from JSON string or dict."""
        try:
            data = json.loads(state) if isinstance(state, str) else state
        except Exception:
            return
        self.skill_matrix = data.get('skill_matrix', {}) or {}
        self.comprehension_history = data.get('comprehension_history', []) or []
        self.question_history = data.get('question_history', []) or []
        
    def assess_comprehension(self, response_text: str, context: Dict[str, Any]) -> Dict[str, float]:
        """
        Analyze a child's response to assess comprehension level.
        
        Args:
            response_text: The child's response
            context: Additional context (time_taken, length, etc.)
            
        Returns:
            Dict with comprehension_score (0-1), curiosity_score (0-1), confidence_score (0-1)
        """
        response_lower = response_text.lower()
        word_count = len(response_text.split())
        
        # Calculate comprehension indicators
        high_indicators = sum(1 for word in self.COMPREHENSION_KEYWORDS['high'] if word in response_lower)
        medium_indicators = sum(1 for word in self.COMPREHENSION_KEYWORDS['medium'] if word in response_lower)
        low_indicators = sum(1 for word in self.COMPREHENSION_KEYWORDS['low'] if word in response_lower)
        curiosity_indicators = sum(1 for word in self.COMPREHENSION_KEYWORDS['curiosity'] if word in response_lower)
        
        # Comprehension score (0-1)
        comprehension_score = min(1.0, (high_indicators * 0.3 + 
                                       medium_indicators * 0.15 - 
                                       low_indicators * 0.2 + 
                                       0.5))  # Base score
        
        # Curiosity score (0-1) - high curiosity is positive
        curiosity_score = min(1.0, curiosity_indicators * 0.2 + 0.3)
        
        # Confidence score based on response length and clarity
        confidence_score = min(1.0, word_count / 50.0 + 0.3)  # Longer = more confident
        
        # Adjust based on question marks (questions indicate uncertainty or curiosity)
        question_count = response_text.count('?')
        if question_count > 2:
            confidence_score *= 0.8
            curiosity_score = min(1.0, curiosity_score + 0.2)
        
        return {
            'comprehension_score': max(0.0, min(1.0, comprehension_score)),
            'curiosity_score': max(0.0, min(1.0, curiosity_score)),
            'confidence_score': max(0.0, min(1.0, confidence_score)),
            'timestamp': datetime.now().isoformat()
        }
    
    def update_skill_level(self, topic: str, difficulty: int, performance_score: float):
        """
        Update skill level for a topic based on performance.
        
        Args:
            topic: The topic/subject area
            difficulty: Current difficulty level (1-5)
            performance_score: How well they did (0-1)
        """
        if topic not in self.skill_matrix:
            self.skill_matrix[topic] = {}
        
        # Exponential moving average for smooth transitions
        alpha = 0.3  # Learning rate
        if difficulty in self.skill_matrix[topic]:
            old_score = self.skill_matrix[topic][difficulty]
            new_score = alpha * performance_score + (1 - alpha) * old_score
        else:
            new_score = performance_score
        
        self.skill_matrix[topic][difficulty] = new_score
    
    def get_optimal_difficulty(self, topic: str, current_difficulty: int) -> int:
        """
        Calculate optimal difficulty level using Zone of Proximal Development.
        
        Args:
            topic: The topic being learned
            current_difficulty: Current difficulty level
            
        Returns:
            Recommended difficulty level (1-5)
        """
        if topic not in self.skill_matrix:
            return self.ELEMENTARY  # Start at elementary for new topics
        
        scores = self.skill_matrix[topic]
        
        # If mastery at current level (>0.8), increase difficulty
        if current_difficulty in scores and scores[current_difficulty] > 0.8:
            return min(self.EXPERT, current_difficulty + 1)
        
        # If struggling at current level (<0.4), decrease difficulty
        if current_difficulty in scores and scores[current_difficulty] < 0.4:
            return max(self.BEGINNER, current_difficulty - 1)
        
        # Otherwise, stay at current level
        return current_difficulty
    
    def suggest_next_topic(self, recent_topics: List[str], interests: List[str]) -> str:
        """
        Suggest the next topic based on performance and interests.
        
        Args:
            recent_topics: Topics covered recently
            interests: Child's stated interests
            
        Returns:
            Recommended next topic
        """
        # Prioritize interests
        interest_topics = [t for t in self.TOPICS if any(i.lower() in t.lower() for i in interests)]
        
        # Find topics with medium proficiency (ZPD sweet spot)
        zpd_topics = []
        for topic, scores in self.skill_matrix.items():
            avg_score = sum(scores.values()) / len(scores) if scores else 0.5
            if 0.4 <= avg_score <= 0.7:  # Not too easy, not too hard
                zpd_topics.append(topic)
        
        # Combine strategies
        candidates = list(set(interest_topics + zpd_topics))
        
        # Filter out recently covered topics
        candidates = [t for t in candidates if t not in recent_topics[-3:]]
        
        # Return best candidate or random interest
        if candidates:
            return candidates[0]
        elif interest_topics:
            return interest_topics[0]
        else:
            return self.TOPICS[0]
    
    def generate_adaptive_prompt(
        self, 
        topic: str, 
        difficulty: int, 
        child_name: str,
        recent_comprehension: List[Dict[str, float]]
    ) -> str:
        """
        Generate a prompt for SilenceGPT that adapts to the child's level.
        
        Args:
            topic: Current topic
            difficulty: Current difficulty level
            child_name: Child's name
            recent_comprehension: Recent comprehension scores
            
        Returns:
            Adaptive prompt for the AI
        """
        # Calculate average recent comprehension
        avg_comp = 0.7  # Default
        if recent_comprehension:
            scores = [c['comprehension_score'] for c in recent_comprehension[-5:]]
            avg_comp = sum(scores) / len(scores)
        
        # Adjust instructions based on comprehension
        if avg_comp < 0.5:
            guidance = """
            - Use VERY simple language and short sentences
            - Provide more examples and analogies
            - Break concepts into tiny steps
            - Check understanding after each point
            - Be extra encouraging and patient
            """
        elif avg_comp < 0.7:
            guidance = """
            - Use clear, age-appropriate language
            - Provide examples when needed
            - Build on what they already understand
            - Ask guiding questions
            - Encourage exploration
            """
        else:  # High comprehension
            guidance = """
            - Introduce more complex concepts
            - Challenge with "what if" scenarios
            - Encourage deeper analysis
            - Connect multiple concepts
            - Celebrate their advanced thinking
            """
        
        difficulty_map = {
            1: "foundational concepts using everyday examples",
            2: "elementary principles with hands-on connections",
            3: "intermediate ideas with real-world applications",
            4: "advanced concepts with critical thinking challenges",
            5: "expert-level exploration with creative problem-solving"
        }
        
        difficulty_desc = difficulty_map.get(difficulty, difficulty_map[2])
        
        return f"""
        Current Learning Context for {child_name}:
        - Topic: {topic}
        - Difficulty Level: {difficulty}/5 ({difficulty_desc})
        - Recent Comprehension: {avg_comp:.1%}
        
        Adaptive Teaching Guidance:
        {guidance}
        
        Remember: You're in their Zone of Proximal Development. Not too easy (boredom), 
        not too hard (frustration), but just right for optimal growth.
        """
    
    def get_learning_insights(self, child_name: str) -> Dict[str, Any]:
        """
        Generate insights about the child's learning journey.
        
        Returns:
            Dict with strengths, growth areas, recommendations
        """
        if not self.skill_matrix:
            return {
                'status': 'beginning_journey',
                'message': f'{child_name} is just starting their learning adventure!',
                'strengths': [],
                'growth_areas': [],
                'recommendations': ['Explore diverse topics to discover interests']
            }
        
        # Find strengths (topics with high scores)
        strengths = []
        growth_areas = []
        
        for topic, scores in self.skill_matrix.items():
            if not scores:
                continue
            avg_score = sum(scores.values()) / len(scores)
            max_difficulty = max(scores.keys())
            
            if avg_score > 0.7:
                strengths.append({
                    'topic': topic,
                    'level': max_difficulty,
                    'mastery': avg_score
                })
            elif avg_score < 0.5:
                growth_areas.append({
                    'topic': topic,
                    'level': max_difficulty,
                    'mastery': avg_score
                })
        
        # Generate recommendations
        recommendations = []
        if strengths:
            top_strength = max(strengths, key=lambda x: x['mastery'])
            recommendations.append(
                f"Keep exploring {top_strength['topic']} - you're becoming an expert!"
            )
        
        if growth_areas:
            focus_area = growth_areas[0]
            recommendations.append(
                f"Let's build confidence in {focus_area['topic']} with fun, hands-on activities"
            )
        
        if len(self.skill_matrix) < 5:
            recommendations.append(
                "Try exploring new topics to discover hidden talents"
            )
        
        return {
            'status': 'progressing',
            'strengths': strengths[:3],  # Top 3
            'growth_areas': growth_areas[:2],  # Top 2
            'recommendations': recommendations,
            'topics_explored': len(self.skill_matrix),
            'avg_mastery': sum(
                sum(scores.values()) / len(scores) 
                for scores in self.skill_matrix.values() if scores
            ) / len(self.skill_matrix) if self.skill_matrix else 0
        }
    
    def should_introduce_challenge(self, recent_responses: List[Dict[str, Any]]) -> bool:
        """
        Determine if it's time to introduce a challenge/stretch goal.
        
        Args:
            recent_responses: Recent interaction history
            
        Returns:
            True if child is ready for a challenge
        """
        if len(recent_responses) < 3:
            return False
        
        # Check if last 3 responses show high comprehension
        recent_comp = [r.get('comprehension_score', 0.5) for r in recent_responses[-3:]]
        avg_recent = sum(recent_comp) / len(recent_comp)
        
        # Check if curiosity is high
        recent_curiosity = [r.get('curiosity_score', 0.5) for r in recent_responses[-3:]]
        avg_curiosity = sum(recent_curiosity) / len(recent_curiosity)
        
        return avg_recent > 0.75 and avg_curiosity > 0.6
    
    def to_dict(self) -> Dict[str, Any]:
        """Export engine state for persistence."""
        return {
            'skill_matrix': self.skill_matrix,
            'comprehension_history': self.comprehension_history[-50:],  # Keep last 50
            'question_history': self.question_history[-50:],
            'last_updated': datetime.now().isoformat()
        }
    
    def get_state(self) -> str:
        """Return persisted state as JSON string."""
        try:
            return json.dumps(self.to_dict(), default=str)
        except Exception:
            return json.dumps({})
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'AdaptiveLearningEngine':
        """Load engine state from persisted data."""
        engine = cls()
        engine.skill_matrix = data.get('skill_matrix', {})
        engine.comprehension_history = data.get('comprehension_history', [])
        engine.question_history = data.get('question_history', [])
        return engine


def analyze_conversation_for_learning(
    messages: List[Dict[str, str]], 
    topic: str,
    engine: AdaptiveLearningEngine
) -> Dict[str, Any]:
    """
    Analyze a conversation thread to extract learning metrics.
    
    Args:
        messages: List of conversation messages
        topic: The topic being discussed
        engine: The adaptive learning engine
        
    Returns:
        Analysis with comprehension trends, engagement, and recommendations
    """
    user_messages = [m for m in messages if m['role'] == 'user']
    
    if not user_messages:
        return {'status': 'no_data'}
    
    # Analyze each user message
    comprehension_scores = []
    for msg in user_messages:
        assessment = engine.assess_comprehension(msg['content'], {})
        comprehension_scores.append(assessment)
    
    # Calculate trends
    if len(comprehension_scores) > 1:
        early_avg = sum(c['comprehension_score'] for c in comprehension_scores[:2]) / 2
        late_avg = sum(c['comprehension_score'] for c in comprehension_scores[-2:]) / 2
        growth = late_avg - early_avg
    else:
        growth = 0
    
    avg_comprehension = sum(c['comprehension_score'] for c in comprehension_scores) / len(comprehension_scores)
    avg_curiosity = sum(c['curiosity_score'] for c in comprehension_scores) / len(comprehension_scores)
    
    return {
        'status': 'analyzed',
        'message_count': len(user_messages),
        'avg_comprehension': avg_comprehension,
        'avg_curiosity': avg_curiosity,
        'growth_trend': growth,
        'engagement_level': 'high' if avg_curiosity > 0.6 else 'medium' if avg_curiosity > 0.4 else 'low',
        'comprehension_level': 'strong' if avg_comprehension > 0.7 else 'developing' if avg_comprehension > 0.5 else 'needs_support',
        'ready_for_next_level': avg_comprehension > 0.8 and growth >= 0,
        'needs_reinforcement': avg_comprehension < 0.5 or growth < -0.2,
        'topic': topic
    }
