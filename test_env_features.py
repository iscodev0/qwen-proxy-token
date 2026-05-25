#!/usr/bin/env python3
"""
Test script to verify Qwen provider features with environment variables.

Usage:
    # Test with thinking enabled (default)
    python test_env_features.py
    
    # Test with search enabled
    QWEN_ENABLE_SEARCH=true python test_env_features.py
    
    # Test with thinking disabled
    QWEN_ENABLE_THINKING=false python test_env_features.py
"""

import asyncio
import os
from hubia.providers.qwen_chat import QwenChatProvider
from hubia.core.provider import ChatRequest, ChatMessage, ProviderCredentials


async def test_features():
    """Test that environment variables are correctly applied to the payload."""
    
    print("=" * 60)
    print("Testing Qwen Provider Environment Variables")
    print("=" * 60)
    
    # Show current environment variables
    print("\n📋 Current Environment Variables:")
    print(f"  QWEN_CHAT_MODE: {os.environ.get('QWEN_CHAT_MODE', 'normal (default)')}")
    print(f"  QWEN_ENABLE_THINKING: {os.environ.get('QWEN_ENABLE_THINKING', 'true (default)')}")
    print(f"  QWEN_ENABLE_SEARCH: {os.environ.get('QWEN_ENABLE_SEARCH', 'false (default)')}")
    print(f"  QWEN_ENABLE_CODE_INTERPRETER: {os.environ.get('QWEN_ENABLE_CODE_INTERPRETER', 'false (default)')}")
    
    # Create provider
    provider = QwenChatProvider()
    
    # Build a test payload
    model = "qwen3.6-plus"
    messages = [{"role": "user", "content": "Test message"}]
    chat_id = "test-chat-id"
    
    # Get environment variables
    chat_mode = os.environ.get("QWEN_CHAT_MODE", "normal")
    enable_thinking = os.environ.get("QWEN_ENABLE_THINKING", "true").lower() == "true"
    enable_search = os.environ.get("QWEN_ENABLE_SEARCH", "false").lower() == "true"
    enable_code_interpreter = os.environ.get("QWEN_ENABLE_CODE_INTERPRETER", "false").lower() == "true"
    
    # Build payload
    payload = provider._build_chat_payload(
        model=model,
        messages=messages,
        chat_id=chat_id,
        stream=True,
        system_prompt=None,
        enable_thinking=enable_thinking,
        enable_search=enable_search,
        enable_code_interpreter=enable_code_interpreter,
        chat_mode=chat_mode,
    )
    
    print("\n🔧 Generated Payload Configuration:")
    print(f"  chat_mode: {payload['chat_mode']}")
    print(f"  model: {payload['model']}")
    print(f"  stream: {payload['stream']}")
    
    # Check feature_config from first message
    if payload['messages']:
        feature_config = payload['messages'][0].get('feature_config', {})
        print("\n📊 Feature Config:")
        print(f"  thinking_enabled: {feature_config.get('thinking_enabled')}")
        print(f"  auto_thinking: {feature_config.get('auto_thinking')}")
        print(f"  thinking_mode: {feature_config.get('thinking_mode')}")
        print(f"  thinking_format: {feature_config.get('thinking_format')}")
        print(f"  auto_search: {feature_config.get('auto_search')}")
        print(f"  research_mode: {feature_config.get('research_mode')}")
        
        if 'code_interpreter_enabled' in feature_config:
            print(f"  code_interpreter_enabled: {feature_config.get('code_interpreter_enabled')}")
    
    # Check tools
    if 'tools' in payload:
        print(f"\n🛠️  Tools Enabled: {len(payload['tools'])}")
        for tool in payload['tools']:
            print(f"  - {tool['function']['name']}")
    else:
        print("\n🛠️  Tools: None")
    
    print("\n" + "=" * 60)
    print("✅ Test Complete")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(test_features())
