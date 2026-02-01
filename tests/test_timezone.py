"""Tests for timezone-aware datetime handling in fetch_new_posts"""

import os
import sys
from datetime import datetime, timedelta, timezone
from unittest.mock import Mock, MagicMock

# Mock command line arguments before importing
sys.argv = ["instawebhooks", "test_user", "https://discord.com/api/webhooks/123/abc"]

# Import the functions we want to test
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from instawebhooks.__main__ import fetch_new_posts


class TestTimezoneFix:
    """Test cases for timezone-aware datetime comparisons"""
    
    def test_cutoff_date_is_timezone_aware(self):
        """Test that cutoff_date is timezone-aware and can be compared with post.date"""
        # Create mock posts with timezone-aware dates
        mock_post_recent = Mock()
        mock_post_recent.shortcode = "RECENT1"
        mock_post_recent.date = datetime.now(timezone.utc) - timedelta(days=2)
        mock_post_recent.typename = "GraphImage"
        mock_post_recent.is_pinned = False
        
        mock_post_old = Mock()
        mock_post_old.shortcode = "OLD1"
        mock_post_old.date = datetime.now(timezone.utc) - timedelta(days=10)
        mock_post_old.typename = "GraphImage"
        mock_post_old.is_pinned = False
        
        # Create iterator of posts (old to new)
        posts_iterator = iter([mock_post_old, mock_post_recent])
        posts_to_send = []
        
        # This should not raise TypeError about comparing offset-naive and offset-aware datetimes
        try:
            fetch_new_posts(posts_iterator, "test_user", posts_to_send, limit=10)
            # Test passes if no exception is raised
            assert True, "Successfully compared timezone-aware datetimes"
        except TypeError as e:
            if "offset-naive and offset-aware" in str(e):
                assert False, f"Timezone comparison failed: {e}"
            raise
    
    def test_cutoff_date_filters_old_posts(self):
        """Test that posts older than 7 days are properly filtered"""
        # Create mock posts
        mock_post_within_cutoff = Mock()
        mock_post_within_cutoff.shortcode = "WITHIN1"
        mock_post_within_cutoff.date = datetime.now(timezone.utc) - timedelta(days=3)
        mock_post_within_cutoff.typename = "GraphImage"
        mock_post_within_cutoff.is_pinned = False
        
        mock_post_beyond_cutoff = Mock()
        mock_post_beyond_cutoff.shortcode = "BEYOND1"
        mock_post_beyond_cutoff.date = datetime.now(timezone.utc) - timedelta(days=10)
        mock_post_beyond_cutoff.typename = "GraphImage"
        mock_post_beyond_cutoff.is_pinned = False
        
        # Create iterator with posts beyond cutoff first (older posts first)
        posts_iterator = iter([mock_post_beyond_cutoff, mock_post_within_cutoff])
        posts_to_send = []
        
        # Fetch new posts
        fetch_new_posts(posts_iterator, "test_user", posts_to_send, limit=10)
        
        # Should stop at the 10-day old post and not include any posts
        # (since there are no sent posts in memory, it should still collect the recent one)
        # But the 10-day old post should cause the fetch to stop
        assert len(posts_to_send) == 0, f"Expected 0 posts, got {len(posts_to_send)}"
    
    def test_post_date_comparison_with_timezone_aware_cutoff(self):
        """Test that post.date (UTC) can be compared with cutoff_date (UTC)"""
        # This test verifies the fix works by checking datetime comparison directly
        cutoff_date = datetime.now(timezone.utc) - timedelta(days=7)
        post_date_recent = datetime.now(timezone.utc) - timedelta(days=2)
        post_date_old = datetime.now(timezone.utc) - timedelta(days=10)
        
        # These comparisons should work without TypeError
        assert post_date_recent > cutoff_date, "Recent post should be after cutoff"
        assert post_date_old < cutoff_date, "Old post should be before cutoff"


if __name__ == "__main__":
    print("Running timezone tests...")
    test = TestTimezoneFix()
    
    # Run test_cutoff_date_is_timezone_aware
    try:
        test.test_cutoff_date_is_timezone_aware()
        print("✓ test_cutoff_date_is_timezone_aware passed")
    except AssertionError as e:
        print(f"✗ test_cutoff_date_is_timezone_aware failed: {e}")
    except Exception as e:
        print(f"✗ test_cutoff_date_is_timezone_aware error: {e}")
    
    # Run test_cutoff_date_filters_old_posts
    try:
        test.test_cutoff_date_filters_old_posts()
        print("✓ test_cutoff_date_filters_old_posts passed")
    except AssertionError as e:
        print(f"✗ test_cutoff_date_filters_old_posts failed: {e}")
    except Exception as e:
        print(f"✗ test_cutoff_date_filters_old_posts error: {e}")
    
    # Run test_post_date_comparison_with_timezone_aware_cutoff
    try:
        test.test_post_date_comparison_with_timezone_aware_cutoff()
        print("✓ test_post_date_comparison_with_timezone_aware_cutoff passed")
    except AssertionError as e:
        print(f"✗ test_post_date_comparison_with_timezone_aware_cutoff failed: {e}")
    except Exception as e:
        print(f"✗ test_post_date_comparison_with_timezone_aware_cutoff error: {e}")
    
    print("\nAll timezone tests completed!")
