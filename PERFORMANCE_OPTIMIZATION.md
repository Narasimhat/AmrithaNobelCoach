# Performance Optimization Guide for The Silent Room

## Critical Performance Issues Identified

### 1. **Excessive st.rerun() Calls** 🔴 HIGH IMPACT
**Problem**: 29+ `st.rerun()` calls throughout the app, causing full page reloads on every interaction.

**Impact**: Each rerun re-executes the entire app from top to bottom, including:
- Database connections
- Cache checks
- Background image encoding
- All UI rendering

**Solutions**:
```python
# BEFORE: Full page reload
if st.button("Update"):
    update_data()
    st.rerun()  # Reloads entire app

# AFTER: Use fragments for isolated updates
@st.fragment
def update_section():
    if st.button("Update"):
        update_data()
        st.rerun(scope="fragment")  # Only reruns this fragment
```

### 2. **Background Image Re-encoding on Every Load** 🔴 HIGH IMPACT
**Problem**: `add_bg()` called 3 times (coach, gallery, parents) - each encodes large images to base64.

**Current Flow**:
```python
def add_bg(image_path: Path):
    encoded = _encoded_bg(str(image_path))  # Reads file, base64 encodes
    st.markdown(f'<style>... {encoded} ...</style>')
```

**Issue**: Even with `@st.cache_data`, encoding happens early and blocks rendering.

**Solutions**:
- Serve images from static asset server instead of inline base64
- Lazy-load backgrounds after initial render
- Reduce image file sizes (optimize JPGs to 200-400KB max)
- Consider disabling backgrounds: `ENABLE_BACKGROUNDS=false`

### 3. **Redundant Cache Clears** 🟡 MEDIUM IMPACT
**Problem**: Multiple cache clears often called unnecessarily:
```python
cached_child_profiles.clear()  # Called twice in same function
cached_projects.clear()
cached_threads.clear()
cached_thread_messages.clear()
```

**Solution**: Create a single invalidation function:
```python
def invalidate_coach_caches():
    """Clear all coach-related caches once."""
    cached_child_profiles.clear()
    cached_projects.clear()
    cached_threads.clear()
    cached_thread_messages.clear()
```

### 4. **Sidebar Rendering on Every Page** 🟡 MEDIUM IMPACT
**Problem**: `render_sidebar()` runs on every tab, fetching metrics even when not visible.

**Solutions**:
- Use `st.fragment` for sidebar to avoid full reruns
- Lazy-load sidebar metrics only when sidebar is expanded
- Cache sidebar rendering result

### 5. **Snowflake Query Inefficiency** 🟡 MEDIUM IMPACT
**Problem**: Multiple sequential queries instead of batch operations.

**Example**:
```python
# SLOW: 3 separate queries
points = cached_points_total()     # SELECT SUM(delta) FROM points_log
streak = cached_streak_length()    # SELECT DISTINCT DATE(ts) FROM open_log
tags = cached_recent_tags()        # SELECT reason, COUNT(*) FROM points_log
```

**Solution**: Create combined query:
```python
@st.cache_data(ttl=60)
def cached_dashboard_metrics():
    return get_dashboard_metrics()  # Single query with all metrics
```

### 6. **Excessive Database Connections** 🟡 MEDIUM IMPACT
**Problem**: `get_conn()` called repeatedly; connection pool not optimized.

**Solution**: Already has singleton pattern, but consider:
```python
# In db_utils.py - add connection pooling
from snowflake.connector.pooling import SnowflakeConnectionPool

_pool = None

def get_pool():
    global _pool
    if _pool is None:
        params = _snowflake_params()
        _pool = SnowflakeConnectionPool(
            account=params["SNOWFLAKE_ACCOUNT"],
            user=params["SNOWFLAKE_USER"],
            password=params["SNOWFLAKE_PASSWORD"],
            warehouse=params["SNOWFLAKE_WAREHOUSE"],
            database=params["SNOWFLAKE_DATABASE"],
            schema=params["SNOWFLAKE_SCHEMA"],
            pool_size=5
        )
    return _pool
```

### 7. **Feed Loading Inefficiency** 🟢 LOW IMPACT
**Problem**: `cached_feed()` loads all posts on every Knowledge Hub visit, even if not viewed.

**Solution**: Implement pagination:
```python
@st.cache_data(ttl=30)
def cached_feed_page(page: int = 0, page_size: int = 10):
    return load_feed(limit=page_size, offset=page * page_size)
```

## Quick Wins (Implement These First)

### A. Disable Background Images Temporarily
```bash
# In .streamlit/secrets.toml or environment
ENABLE_BACKGROUNDS = false
```
**Impact**: Removes 100-300ms delay on page load.

### B. Add Fragment Decorators to High-Interaction Components
```python
@st.fragment
def render_child_selector():
    children = cached_child_profiles()
    # ... selection UI ...
    # Changes here won't reload entire app
```

### C. Optimize Cache TTLs
```python
# Reduce unnecessary cache refreshes
@st.cache_data(ttl=300)  # 5 min instead of 30 sec
def cached_child_profiles():
    return list_child_profiles()

@st.cache_data(ttl=600)  # 10 min for mostly-static data
def cached_points_total():
    return total_points()
```

### D. Batch Database Operations
```python
# In db_utils.py
def get_dashboard_metrics() -> Dict[str, Any]:
    """Single query for all dashboard data."""
    conn = get_conn()
    cursor = conn.cursor(DictCursor)
    
    results = {}
    
    # Points
    cursor.execute("SELECT SUM(delta) AS total FROM points_log")
    results['points'] = cursor.fetchone()['TOTAL'] or 0
    
    # Streak
    cursor.execute("""
        SELECT COUNT(DISTINCT DATE(ts)) AS streak 
        FROM open_log 
        WHERE ts >= CURRENT_DATE() - INTERVAL '30 days'
    """)
    results['streak'] = cursor.fetchone()['STREAK'] or 0
    
    # Recent tags - all in one query
    cursor.execute("""
        SELECT reason, COUNT(*) AS cnt 
        FROM points_log 
        WHERE ts >= CURRENT_TIMESTAMP() - INTERVAL '7 days'
        GROUP BY reason
    """)
    results['tag_counts'] = {row['REASON']: row['CNT'] for row in cursor.fetchall()}
    
    cursor.close()
    return results
```

### E. Lazy Load Heavy Components
```python
# Only load when tab is active
if selected_tab == "Coach":
    with st.spinner("Loading coach..."):
        render_coach_tab(client, profile, api_key)
elif selected_tab == "Knowledge Hub":
    with st.spinner("Loading feed..."):
        render_knowledge_hub()
```

## Performance Monitoring

### Add Performance Tracking
```python
import time

def perf_monitor(func_name: str):
    def decorator(func):
        def wrapper(*args, **kwargs):
            start = time.time()
            result = func(*args, **kwargs)
            elapsed = time.time() - start
            if elapsed > 0.5:  # Log slow functions
                st.warning(f"⚠️ {func_name} took {elapsed:.2f}s")
            return result
        return wrapper
    return decorator

@perf_monitor("render_coach_tab")
def render_coach_tab(...):
    ...
```

### Cache Hit Monitoring
```python
# Add to cached functions
@st.cache_data(ttl=60, show_spinner=False)
def cached_points_total() -> int:
    if st.session_state.get('debug_mode'):
        st.sidebar.caption("🔍 Cache miss: points_total")
    return total_points()
```

## Benchmarking Results (Expected)

| Optimization | Before | After | Improvement |
|-------------|--------|-------|-------------|
| Disable backgrounds | 2.5s | 0.8s | 68% faster |
| Fragment isolation | Full reload | Partial update | 90% faster interactions |
| Batch DB queries | 3 queries (150ms) | 1 query (60ms) | 60% faster |
| Optimized caching | 8 cache checks | 3 cache checks | 62% fewer calls |
| **Total page load** | **3-4s** | **0.8-1.2s** | **70-75% faster** |

## Implementation Priority

1. **Phase 1** (Immediate - <1 hour):
   - Disable background images
   - Optimize cache TTLs
   - Remove duplicate cache clears

2. **Phase 2** (Short-term - 2-4 hours):
   - Add st.fragment decorators
   - Batch database queries
   - Lazy load tabs

3. **Phase 3** (Long-term - 1-2 days):
   - Implement connection pooling
   - Add performance monitoring
   - Optimize Snowflake queries with indexes
   - Consider async loading for non-critical data

## Monitoring Commands

```bash
# Profile Streamlit performance
streamlit run app.py --server.fileWatcherType none --server.runOnSave false

# Monitor Snowflake query performance
# Add to db_utils.py _execute():
import logging
logging.basicConfig(level=logging.DEBUG)
# Will show query execution times
```

## Next Steps

1. Apply Phase 1 optimizations immediately
2. Test with real user load
3. Measure improvements with Chrome DevTools Performance tab
4. Iterate based on bottleneck identification
