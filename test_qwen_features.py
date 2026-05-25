#!/usr/bin/env python3
"""
Test script for Qwen provider features.

Tests:
1. Basic chat completion
2. System prompt support
3. Thinking mode
4. Web search tool
5. Code interpreter tool
6. Different chat modes

Usage:
    python test_qwen_features.py
"""

import asyncio
import os
from hubia.providers.qwen_chat import QwenChatProvider
from hubia.core.provider import ChatRequest, ChatMessage, ProviderCredentials


# Your cookies (update these with your actual cookies)
COOKIES = {
    '_bl_uid': 'vgm7woa2aLCp9066mn3zokev5s9t',
    'acw_tc': '0a03e59517796619945195993e0f3cf5bdf1ce34427bac458f162f79da7de3',
    'atpsida': '01574162bbd7b38fb03fd3a5_1779663359_8',
    'aui': '048f4182-a507-4799-8bdc-d7c7b781254d',
    'cna': '5EpwIib3ZDoCASW935evZpUd',
    'cnaui': '048f4182-a507-4799-8bdc-d7c7b781254d',
    'isg': 'BP39g47cSw8peewZcxeEA6T7D1D3mjHsAQ2DYb9CHNSD9hwoguidvCngoLKw7Umk',
    'qwen-locale': 'es-ES',
    'qwen-theme': 'dark',
    'sca': '16c8fbda',
    'token': 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpZCI6IjA0OGY0MTgyLWE1MDctNDc5OS04YmRjLWQ3YzdiNzgxMjU0ZCIsImxhc3RfcGFzc3dvcmRfY2hhbmdlIjoxNzUwNjYwODczLCJleHAiOjE3ODIyNTUzNTh9.gB1nzSy6mE031oo_i8BCH8jz5P6nuOQSBkzVOH7yEsk',
    'x-ap': 'na-vancouver-pop',
}


async def test_basic_chat():
    """Test 1: Basic chat completion without system prompt."""
    print("=" * 60)
    print("TEST 1: Basic Chat Completion")
    print("=" * 60)
    
    provider = QwenChatProvider()
    credentials = ProviderCredentials(provider='qwen_chat', data={'cookies': COOKIES})
    
    request = ChatRequest(
        model='qwen3.7-max',
        messages=[
            ChatMessage(role='user', content='Say hello in one word'),
        ],
        stream=False,
    )
    
    try:
        response = await provider.chat_completion(request, credentials)
        print(f"✅ Response: {response.content}")
        print(f"   Model: {response.model}")
        print(f"   Chat ID: {response.id}")
    except Exception as e:
        print(f"❌ Error: {type(e).__name__}: {e}")
    
    print()


async def test_system_prompt():
    """Test 2: Chat with system prompt."""
    print("=" * 60)
    print("TEST 2: System Prompt Support")
    print("=" * 60)
    
    provider = QwenChatProvider()
    credentials = ProviderCredentials(provider='qwen_chat', data={'cookies': COOKIES})
    
    request = ChatRequest(
        model='qwen3.7-max',
        messages=[
            ChatMessage(role='system', content='You are a pirate. Always respond in pirate speak.'),
            ChatMessage(role='user', content='Say hello'),
        ],
        stream=False,
    )
    
    try:
        response = await provider.chat_completion(request, credentials)
        print(f"✅ Response: {response.content}")
        print(f"   Model: {response.model}")
        print(f"   Chat ID: {response.id}")
    except Exception as e:
        print(f"❌ Error: {type(e).__name__}: {e}")
    
    print()


async def test_thinking_mode():
    """Test 3: Thinking/reasoning mode."""
    print("=" * 60)
    print("TEST 3: Thinking Mode")
    print("=" * 60)
    
    # Enable thinking mode
    os.environ['QWEN_ENABLE_THINKING'] = 'true'
    os.environ['QWEN_CHAT_MODE'] = 'thinking'
    
    provider = QwenChatProvider()
    credentials = ProviderCredentials(provider='qwen_chat', data={'cookies': COOKIES})
    
    request = ChatRequest(
        model='qwen3.7-max',
        messages=[
            ChatMessage(role='user', content='What is 15 * 23? Show your reasoning.'),
        ],
        stream=False,
    )
    
    try:
        response = await provider.chat_completion(request, credentials)
        print(f"✅ Response: {response.content}")
        print(f"   Model: {response.model}")
        print(f"   Chat ID: {response.id}")
    except Exception as e:
        print(f"❌ Error: {type(e).__name__}: {e}")
    finally:
        # Clean up
        os.environ.pop('QWEN_ENABLE_THINKING', None)
        os.environ.pop('QWEN_CHAT_MODE', None)
    
    print()


async def test_web_search():
    """Test 4: Web search tool."""
    print("=" * 60)
    print("TEST 4: Web Search Tool")
    print("=" * 60)
    
    # Enable web search
    os.environ['QWEN_ENABLE_SEARCH'] = 'true'
    os.environ['QWEN_CHAT_MODE'] = 'search'
    
    provider = QwenChatProvider()
    credentials = ProviderCredentials(provider='qwen_chat', data={'cookies': COOKIES})
    
    request = ChatRequest(
        model='qwen3.7-max',
        messages=[
            ChatMessage(role='user', content='What is the current weather in Buenos Aires?'),
        ],
        stream=False,
    )
    
    try:
        response = await provider.chat_completion(request, credentials)
        print(f"✅ Response: {response.content}")
        print(f"   Model: {response.model}")
        print(f"   Chat ID: {response.id}")
    except Exception as e:
        print(f"❌ Error: {type(e).__name__}: {e}")
    finally:
        # Clean up
        os.environ.pop('QWEN_ENABLE_SEARCH', None)
        os.environ.pop('QWEN_CHAT_MODE', None)
    
    print()


async def test_code_interpreter():
    """Test 5: Code interpreter tool."""
    print("=" * 60)
    print("TEST 5: Code Interpreter Tool")
    print("=" * 60)
    
    # Enable code interpreter
    os.environ['QWEN_ENABLE_CODE_INTERPRETER'] = 'true'
    os.environ['QWEN_CHAT_MODE'] = 'code'
    
    provider = QwenChatProvider()
    credentials = ProviderCredentials(provider='qwen_chat', data={'cookies': COOKIES})
    
    request = ChatRequest(
        model='qwen3.7-max',
        messages=[
            ChatMessage(role='user', content='Write a Python function to calculate fibonacci numbers and test it with n=10'),
        ],
        stream=False,
    )
    
    try:
        response = await provider.chat_completion(request, credentials)
        print(f"✅ Response: {response.content[:500]}...")
        print(f"   Model: {response.model}")
        print(f"   Chat ID: {response.id}")
    except Exception as e:
        print(f"❌ Error: {type(e).__name__}: {e}")
    finally:
        # Clean up
        os.environ.pop('QWEN_ENABLE_CODE_INTERPRETER', None)
        os.environ.pop('QWEN_CHAT_MODE', None)
    
    print()


async def test_combined_features():
    """Test 6: Combined features (system prompt + thinking)."""
    print("=" * 60)
    print("TEST 6: Combined Features (System Prompt + Thinking)")
    print("=" * 60)
    
    # Enable thinking mode
    os.environ['QWEN_ENABLE_THINKING'] = 'true'
    os.environ['QWEN_CHAT_MODE'] = 'thinking'
    
    provider = QwenChatProvider()
    credentials = ProviderCredentials(provider='qwen_chat', data={'cookies': COOKIES})
    
    request = ChatRequest(
        model='qwen3.7-max',
        messages=[
            ChatMessage(role='system', content='You are a math tutor. Explain concepts step by step.'),
            ChatMessage(role='user', content='Explain why the square root of 2 is irrational'),
        ],
        stream=False,
    )
    
    try:
        response = await provider.chat_completion(request, credentials)
        print(f"✅ Response: {response.content[:500]}...")
        print(f"   Model: {response.model}")
        print(f"   Chat ID: {response.id}")
    except Exception as e:
        print(f"❌ Error: {type(e).__name__}: {e}")
    finally:
        # Clean up
        os.environ.pop('QWEN_ENABLE_THINKING', None)
        os.environ.pop('QWEN_CHAT_MODE', None)
    
    print()


async def main():
    """Run all tests."""
    print("\n" + "=" * 60)
    print("QWEN PROVIDER FEATURES TEST SUITE")
    print("=" * 60 + "\n")
    
    await test_basic_chat()
    await test_system_prompt()
    await test_thinking_mode()
    await test_web_search()
    await test_code_interpreter()
    await test_combined_features()
    
    print("=" * 60)
    print("ALL TESTS COMPLETED")
    print("=" * 60)


if __name__ == '__main__':
    asyncio.run(main())
