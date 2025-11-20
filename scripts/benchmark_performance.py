#!/usr/bin/env python3
"""
Performance testing utility for The Silent Room app.
Run this to benchmark key operations before/after optimizations.
"""

import time
import os
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

def time_operation(name: str, func, *args, **kwargs):
    """Time a function execution."""
    start = time.time()
    try:
        result = func(*args, **kwargs)
        elapsed = time.time() - start
        print(f"✓ {name}: {elapsed*1000:.1f}ms")
        return result, elapsed
    except Exception as e:
        elapsed = time.time() - start
        print(f"✗ {name}: {elapsed*1000:.1f}ms (ERROR: {e})")
        return None, elapsed

def test_database_operations():
    """Test Snowflake query performance."""
    print("\n=== Database Performance ===")
    
    try:
        from db_utils import (
            total_points,
            streak_days,
            recent_tag_counts,
            list_child_profiles,
        )
        
        time_operation("total_points()", total_points)
        time_operation("streak_days()", streak_days)
        time_operation("recent_tag_counts()", recent_tag_counts)
        time_operation("list_child_profiles()", list_child_profiles)
        
    except Exception as e:
        print(f"Database tests failed: {e}")

def test_cache_performance():
    """Test cache hit rates."""
    print("\n=== Cache Performance ===")
    
    try:
        # Import app to trigger cache setup
        import app
        
        # First call (cache miss)
        start = time.time()
        points1 = app.cached_points_total()
        miss_time = time.time() - start
        
        # Second call (cache hit)
        start = time.time()
        points2 = app.cached_points_total()
        hit_time = time.time() - start
        
        print(f"Cache MISS: {miss_time*1000:.1f}ms")
        print(f"Cache HIT:  {hit_time*1000:.1f}ms")
        print(f"Speedup: {miss_time/hit_time:.1f}x faster")
        
    except Exception as e:
        print(f"Cache tests failed: {e}")

def test_background_encoding():
    """Test background image encoding performance."""
    print("\n=== Background Image Performance ===")
    
    try:
        from app import _encoded_bg, ASSET_DIR
        import base64
        from pathlib import Path
        
        test_images = [
            ASSET_DIR / "lab.jpg",
            ASSET_DIR / "space.jpg",
            ASSET_DIR / "missions.jpg",
        ]
        
        total_time = 0
        for img_path in test_images:
            if img_path.exists():
                start = time.time()
                encoded = _encoded_bg(str(img_path))
                elapsed = time.time() - start
                size_kb = len(encoded) / 1024
                total_time += elapsed
                print(f"  {img_path.name}: {elapsed*1000:.1f}ms ({size_kb:.0f}KB base64)")
        
        print(f"Total encoding time: {total_time*1000:.1f}ms")
        
        if total_time > 0.3:
            print("⚠️  WARNING: Background encoding is slow. Consider:")
            print("   - Setting ENABLE_BACKGROUNDS=false")
            print("   - Optimizing image file sizes")
            print("   - Using a CDN instead of inline base64")
        
    except Exception as e:
        print(f"Background tests failed: {e}")

def test_full_page_load_simulation():
    """Simulate a full page load."""
    print("\n=== Full Page Load Simulation ===")
    
    total_start = time.time()
    
    operations = [
        ("Initialize DB", lambda: __import__('db_utils').init_db()),
        ("Load child profiles", lambda: __import__('app').cached_child_profiles()),
        ("Load points", lambda: __import__('app').cached_points_total()),
        ("Load streak", lambda: __import__('app').cached_streak_length()),
        ("Load recent tags", lambda: __import__('app').cached_recent_tags()),
    ]
    
    for name, func in operations:
        try:
            time_operation(f"  {name}", func)
        except Exception as e:
            print(f"  {name}: ERROR - {e}")
    
    total_elapsed = time.time() - total_start
    print(f"\nTotal simulated load time: {total_elapsed*1000:.1f}ms")
    
    if total_elapsed < 1.0:
        print("✓ GOOD: Page load under 1 second")
    elif total_elapsed < 2.0:
        print("⚠️  ACCEPTABLE: Page load 1-2 seconds")
    else:
        print("✗ SLOW: Page load over 2 seconds - needs optimization")

def main():
    """Run all performance tests."""
    print("=" * 60)
    print("The Silent Room - Performance Benchmark")
    print("=" * 60)
    
    # Check environment
    print("\n=== Environment Check ===")
    print(f"ENABLE_BACKGROUNDS: {os.getenv('ENABLE_BACKGROUNDS', '1')}")
    print(f"SNOWFLAKE configured: {'Yes' if os.getenv('SNOWFLAKE_ACCOUNT') else 'No'}")
    print(f"OpenAI configured: {'Yes' if os.getenv('OPENAI_API_KEY') else 'No'}")
    
    # Run tests
    test_database_operations()
    test_cache_performance()
    test_background_encoding()
    test_full_page_load_simulation()
    
    print("\n" + "=" * 60)
    print("Benchmark complete!")
    print("=" * 60)

if __name__ == "__main__":
    main()
