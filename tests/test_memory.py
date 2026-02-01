"""Tests for memory system functions"""

import json
import os
import tempfile
import shutil
from datetime import datetime, timezone
from unittest.mock import Mock, patch
import sys

# Mock command line arguments before importing
sys.argv = ["instawebhooks", "test_user", "https://discord.com/api/webhooks/123/abc"]

# Import the functions we want to test
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from instawebhooks.__main__ import (
    load_memory,
    save_memory,
    add_sent_post,
    get_sent_shortcodes,
    get_post_type_display,
    get_memory_path,
)


class TestMemorySystem:
    """Test cases for the memory system"""
    
    def setup_method(self):
        """Set up test fixtures"""
        # Create a temporary directory for test memory files
        self.test_dir = tempfile.mkdtemp()
        self.original_memory_dir = os.environ.get("MEMORY_DIR")
        # Override the memory path to use test directory
        self.test_username = "test_user"
        
    def teardown_method(self):
        """Clean up after tests"""
        # Remove test directory
        if os.path.exists(self.test_dir):
            shutil.rmtree(self.test_dir)
        if self.original_memory_dir:
            os.environ["MEMORY_DIR"] = self.original_memory_dir
    
    def test_load_empty_memory(self):
        """Test loading memory when no file exists"""
        # Use a non-existent username
        memory = load_memory("nonexistent_user_12345")
        
        assert memory["last_check"] is None
        assert memory["sent_posts"] == []
        assert memory["stats"]["total_sent"] == 0
        assert memory["stats"]["last_post_shortcode"] is None
        assert memory["stats"]["type_counts"] == {}
    
    def test_load_old_json_format(self):
        """Test loading old JSON format and migrating to new format"""
        # Create old format memory file
        old_data = {"shortcode": "ABC123", "timestamp": "2026-01-30T01:42:13"}
        memory_path = get_memory_path(self.test_username)
        os.makedirs(os.path.dirname(memory_path), exist_ok=True)
        
        with open(memory_path, "w") as f:
            json.dump(old_data, f)
        
        # Load memory (should migrate)
        memory = load_memory(self.test_username)
        
        assert len(memory["sent_posts"]) == 1
        assert memory["sent_posts"][0]["shortcode"] == "ABC123"
        assert memory["stats"]["last_post_shortcode"] == "ABC123"
        assert memory["stats"]["total_sent"] == 1
        # Check timezone was added
        assert "+00:00" in memory["sent_posts"][0]["timestamp"]
    
    def test_load_plain_text_format(self):
        """Test loading plain text format (oldest format)"""
        # Create plain text memory file
        memory_path = get_memory_path(self.test_username)
        os.makedirs(os.path.dirname(memory_path), exist_ok=True)
        
        with open(memory_path, "w") as f:
            f.write("XYZ789")
        
        # Load memory (should migrate)
        memory = load_memory(self.test_username)
        
        assert len(memory["sent_posts"]) == 1
        assert memory["sent_posts"][0]["shortcode"] == "XYZ789"
        assert memory["stats"]["last_post_shortcode"] == "XYZ789"
        assert memory["stats"]["total_sent"] == 1
    
    def test_save_and_load_new_format(self):
        """Test saving and loading new memory format"""
        # Create new format memory with fixed timestamp
        last_check_time = "2026-02-01T10:00:00+00:00"
        sent_at_time = "2026-02-01T09:00:00+00:00"
        memory_data = {
            "last_check": last_check_time,
            "sent_posts": [
                {
                    "shortcode": "POST123",
                    "timestamp": "2026-01-31T12:00:00+00:00",
                    "sent_at": sent_at_time,
                    "type": "GraphImage",
                    "type_display": "Photo",
                    "is_video": False,
                    "is_pinned": False,
                    "caption_preview": "Test caption",
                    "url": "https://www.instagram.com/p/POST123/"
                }
            ],
            "stats": {
                "total_sent": 1,
                "last_post_shortcode": "POST123",
                "last_post_timestamp": "2026-01-31T12:00:00+00:00",
                "last_post_type": "Photo",
                "type_counts": {"Photo": 1}
            }
        }
        
        # Save memory
        save_memory(self.test_username, memory_data)
        
        # Load memory
        loaded_memory = load_memory(self.test_username)
        
        assert loaded_memory["stats"]["total_sent"] == 1
        assert loaded_memory["stats"]["last_post_shortcode"] == "POST123"
        assert len(loaded_memory["sent_posts"]) == 1
        assert loaded_memory["last_check"] == last_check_time
        assert loaded_memory["sent_posts"][0]["sent_at"] == sent_at_time
    
    def test_add_sent_post(self):
        """Test adding a post to memory"""
        # Ensure clean state - remove memory file if exists
        memory_path = get_memory_path(self.test_username)
        if os.path.exists(memory_path):
            os.remove(memory_path)
        
        # Create mock post
        mock_post = Mock()
        mock_post.shortcode = "NEWPOST123"
        mock_post.date = datetime.now(timezone.utc)
        mock_post.typename = "GraphClip"
        mock_post.is_video = True
        mock_post.is_pinned = False
        mock_post.caption = "This is a test reel caption"
        
        # Add post to memory
        add_sent_post(self.test_username, mock_post)
        
        # Load memory and verify
        memory = load_memory(self.test_username)
        
        assert len(memory["sent_posts"]) == 1, f"Expected 1 post, got {len(memory['sent_posts'])}"
        assert memory["sent_posts"][0]["shortcode"] == "NEWPOST123", f"Expected shortcode NEWPOST123, got {memory['sent_posts'][0]['shortcode']}"
        assert memory["sent_posts"][0]["type_display"] == "Reel", f"Expected Reel, got {memory['sent_posts'][0]['type_display']}"
        assert memory["sent_posts"][0]["is_video"] is True, f"Expected is_video=True, got {memory['sent_posts'][0]['is_video']}"
        assert memory["stats"]["total_sent"] == 1, f"Expected total_sent=1, got {memory['stats']['total_sent']}"
        assert memory["stats"]["type_counts"]["Reel"] == 1, f"Expected Reel count=1, got {memory['stats']['type_counts'].get('Reel', 0)}"
        # Verify last_check is set and is a valid ISO timestamp
        assert memory["last_check"] is not None, "Expected last_check to be set"
        assert "+00:00" in memory["last_check"], "Expected last_check to include timezone"
    
    def test_get_sent_shortcodes(self):
        """Test getting set of sent shortcodes"""
        # Create memory with multiple posts
        memory_data = {
            "last_check": datetime.now(timezone.utc).isoformat(),
            "sent_posts": [
                {"shortcode": "POST1", "timestamp": "2026-01-31T12:00:00+00:00"},
                {"shortcode": "POST2", "timestamp": "2026-01-30T12:00:00+00:00"},
                {"shortcode": "POST3", "timestamp": "2026-01-29T12:00:00+00:00"},
            ],
            "stats": {"total_sent": 3}
        }
        
        save_memory(self.test_username, memory_data)
        
        # Get shortcodes
        shortcodes = get_sent_shortcodes(self.test_username)
        
        assert len(shortcodes) == 3
        assert "POST1" in shortcodes
        assert "POST2" in shortcodes
        assert "POST3" in shortcodes
    
    def test_get_post_type_display(self):
        """Test post type display mapping"""
        # Test GraphImage
        mock_post = Mock()
        mock_post.typename = "GraphImage"
        typename, display = get_post_type_display(mock_post)
        assert typename == "GraphImage"
        assert display == "Photo"
        
        # Test GraphVideo
        mock_post.typename = "GraphVideo"
        typename, display = get_post_type_display(mock_post)
        assert display == "Video"
        
        # Test GraphClip (Reel)
        mock_post.typename = "GraphClip"
        typename, display = get_post_type_display(mock_post)
        assert display == "Reel"
        
        # Test GraphSidecar (Carousel)
        mock_post.typename = "GraphSidecar"
        typename, display = get_post_type_display(mock_post)
        assert display == "Carousel"
    
    def test_memory_limit_100_posts(self):
        """Test that memory only keeps last 100 posts"""
        # Add 105 posts
        for i in range(105):
            mock_post = Mock()
            mock_post.shortcode = f"POST{i:03d}"
            mock_post.date = datetime.now(timezone.utc)
            mock_post.typename = "GraphImage"
            mock_post.is_video = False
            mock_post.is_pinned = False
            mock_post.caption = f"Post {i}"
            
            add_sent_post(self.test_username, mock_post)
        
        # Load memory and verify only 100 posts kept
        memory = load_memory(self.test_username)
        assert len(memory["sent_posts"]) == 100
        
        # Verify newest posts are kept (POST104 down to POST005)
        assert memory["sent_posts"][0]["shortcode"] == "POST104"
        assert memory["sent_posts"][-1]["shortcode"] == "POST005"


if __name__ == "__main__":
    print("Running memory system tests...")
    test = TestMemorySystem()
    
    # Run tests
    test.setup_method()
    try:
        test.test_load_empty_memory()
        print("✓ test_load_empty_memory passed")
    except AssertionError as e:
        print(f"✗ test_load_empty_memory failed: {e}")
    finally:
        test.teardown_method()
    
    test.setup_method()
    try:
        test.test_load_old_json_format()
        print("✓ test_load_old_json_format passed")
    except AssertionError as e:
        print(f"✗ test_load_old_json_format failed: {e}")
    finally:
        test.teardown_method()
    
    test.setup_method()
    try:
        test.test_load_plain_text_format()
        print("✓ test_load_plain_text_format passed")
    except AssertionError as e:
        print(f"✗ test_load_plain_text_format failed: {e}")
    finally:
        test.teardown_method()
    
    test.setup_method()
    try:
        test.test_save_and_load_new_format()
        print("✓ test_save_and_load_new_format passed")
    except AssertionError as e:
        print(f"✗ test_save_and_load_new_format failed: {e}")
    finally:
        test.teardown_method()
    
    test.setup_method()
    try:
        test.test_add_sent_post()
        print("✓ test_add_sent_post passed")
    except AssertionError as e:
        print(f"✗ test_add_sent_post failed: {e}")
    finally:
        test.teardown_method()
    
    test.setup_method()
    try:
        test.test_get_sent_shortcodes()
        print("✓ test_get_sent_shortcodes passed")
    except AssertionError as e:
        print(f"✗ test_get_sent_shortcodes failed: {e}")
    finally:
        test.teardown_method()
    
    test.setup_method()
    try:
        test.test_get_post_type_display()
        print("✓ test_get_post_type_display passed")
    except AssertionError as e:
        print(f"✗ test_get_post_type_display failed: {e}")
    finally:
        test.teardown_method()
    
    test.setup_method()
    try:
        test.test_memory_limit_100_posts()
        print("✓ test_memory_limit_100_posts passed")
    except AssertionError as e:
        print(f"✗ test_memory_limit_100_posts failed: {e}")
    finally:
        test.teardown_method()
    
    print("\nAll tests completed!")
