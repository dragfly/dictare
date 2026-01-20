#!/usr/bin/env python3
"""Test script to demonstrate escape sequence sanitization."""

from src.voxtype.injection.base import sanitize_text_for_injection

def test_sanitization():
    """Test various escape sequences and control characters."""

    test_cases = [
        # (input, expected_output, description)
        ("Hello World", "Hello World", "Normal text"),
        ("Hello[27;2;13~World", "HelloWorld", "Ghostty escape sequence"),
        ("Hello\x1b[31mWorld\x1b[0m", "HelloWorld", "ANSI color codes"),
        ("Hello\x1b]0;Title\x07World", "HelloWorld", "OSC sequence with BEL"),
        ("Test[1;5~[27;2;13~Text", "TestText", "Multiple escape sequences"),
        ("Line1\nLine2", "Line1\nLine2", "Newline preserved"),
        ("Tab\there", "Tab\there", "Tab preserved"),
        ("Test\x00Control", "TestControl", "Null byte removed"),
        ("Hello\x7fWorld", "HelloWorld", "DEL character removed"),
        ("Ciao Paola!", "Ciao Paola!", "Unicode preserved"),
        ("测试中文", "测试中文", "Chinese characters preserved"),
        ("Test\r\nWindows", "Test\r\nWindows", "Windows line endings preserved"),
        ("[27;2;13~Hello[27;2;13~World[27;2;13~", "HelloWorld", "Multiple Ghostty sequences"),
    ]

    print("Testing escape sequence sanitization:\n")
    print("=" * 80)

    all_passed = True
    for input_text, expected, description in test_cases:
        result = sanitize_text_for_injection(input_text)
        passed = result == expected
        all_passed = all_passed and passed

        status = "✓" if passed else "✗"
        print(f"\n{status} {description}")
        print(f"  Input:    {repr(input_text)}")
        print(f"  Expected: {repr(expected)}")
        print(f"  Result:   {repr(result)}")

        if not passed:
            print(f"  FAILED: Got {repr(result)} instead of {repr(expected)}")

    print("\n" + "=" * 80)
    if all_passed:
        print("✓ All tests passed!")
    else:
        print("✗ Some tests failed!")

    return all_passed

if __name__ == "__main__":
    import sys
    success = test_sanitization()
    sys.exit(0 if success else 1)
