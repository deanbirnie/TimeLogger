import unittest

from app.time_logger import *


class TestCleanDescription(unittest.TestCase):
    def test_expected_string(self):
        description = "This is a description. #test-123"
        result = clean_description(description)
        self.assertEqual(result, "This is a description.")
        
    def test_no_tag(self):
        description = "This is a description without a tag."
        result = clean_description(description)
        self.assertEqual(result, "This is a description without a tag.")
        
    def test_trailing_white_space(self):
        description = "This is a description with trailing whitespace. "
        result = clean_description(description)
        self.assertEqual(result, "This is a description with trailing whitespace.")
    
    def test_tag_only(self):
        description = "#tag-123"
        result = clean_description(description)
        self.assertEqual(result, "")

    def test_space_and_tag(self):
        description = " #tag-123"
        result = clean_description(description)
        self.assertEqual(result, "")

    def test_multiple_tags(self):
        description = "This is a description. #tag-123 #second_tag"
        result = clean_description(description)
        self.assertEqual(result, "This is a description.")

    def test_none_input(self):
        with self.assertRaises(ValueError) as cd:
            clean_description(None)
        self.assertEqual(str(cd.exception), "Work log description should be a string.")

    def test_int_input(self):
        with self.assertRaises(ValueError) as cd:
            clean_description(12345)
        self.assertEqual(str(cd.exception), "Work log description should be a string.")

    def test_list_input(self):
        with self.assertRaises(ValueError) as cd:
            clean_description(["This is a description.", "#tag-123"])
        self.assertEqual(str(cd.exception), "Work log description should be a string.")
