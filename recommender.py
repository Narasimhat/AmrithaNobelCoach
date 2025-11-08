
# Simple rule-based recommender for The Silent Room
from typing import List, Dict, Any

def recommend(profile: Dict[str, Any]) -> List[Dict[str, str]]:
    """Return a list of suggested next actions based on recent activity."""
    tags = profile.get('tags_counts', {})
    top = sorted(tags.items(), key=lambda x: x[1], reverse=True)
    top_tag = top[0][0] if top else 'Curiosity'
    suggestions = []

    if tags.get('Planet', 0) >= 3:
        suggestions.append({'type':'weekly_path','id':'climate_guardian_lvl1','reason':'High Planet interest'})
    if tags.get('Health', 0) >= 3:
        suggestions.append({'type':'weekly_path','id':'health_hero_lvl1','reason':'High Health interest'})
    if tags.get('Build', 0) >= 3:
        suggestions.append({'type':'daily_mission','id':'paper-bridge','reason':'Build tag & 2-min slot'})

    if profile.get('recent_idle_days', 0) >= 3:
        suggestions.append({'type':'micro_mission','id':'thirty_second_brain_spark','reason':'Re-engage after a few idle days'})

    if tags.get('Think', 0) >= 3:
        suggestions.append({'type':'coach_prompt','id':'think_checklist','reason':'Promote verification skills'})

    suggestions.append({'type':'daily_mission','id':f"{'{}'}-quick-mission".format(top_tag.lower()),'reason':f"Keep momentum in {top_tag}"})
    return suggestions
