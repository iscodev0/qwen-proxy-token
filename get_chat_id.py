#!/usr/bin/env python3
"""
Script to get your Qwen chat_id after creating a chat manually.

Usage:
1. Go to https://chat.qwen.ai/ and send any message
2. Run this script: python get_chat_id.py
3. Copy the chat_id and use it in your provider configuration
"""

import httpx
import json
import sys

# Your cookies (update these with your actual cookies)
cookies = {
    '_bl_uid': 'vgm7woa2aLCp9066mn3zokev5s9t',
    'acw_tc': '0a06abd817796593862215329e418357a55cb05e64640924f4098505c564cd',
    'atpsida': 'afeeea5ddda6da2d48264a9f_1779375254_10',
    'aui': '048f4182-a507-4799-8bdc-d7c7b781254d',
    'cna': '5EpwIib3ZDoCASW935evZpUd',
    'cnaui': '048f4182-a507-4799-8bdc-d7c7b781254d',
    'isg': 'BJeXskr_sf1HKjaLhRGOEeoVJQLh3Gs-f3P5E-nEhWbNGLVa8a-Ij4MzeiAG60O2',
    'qwen-locale': 'es-ES',
    'qwen-theme': 'dark',
    'sca': '16c8fbda',
    'token': 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpZCI6IjA0OGY0MTgyLWE1MDctNDc5OS04YmRjLWQ3YzdiNzgxMjU0ZCIsImxhc3RfcGFzc3dvcmRfY2hhbmdlIjoxNzUwNjYwODczLCJleHAiOjE3ODIyNTE0NjB9.i-hEb2jZWBrKP6_G3FxeM-Rys-_0yPD2RLn_dZ8lnC0',
    'x-ap': 'na-vancouver-pop',
}

headers = {
    'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
    'Accept': 'application/json',
    'Content-Type': 'application/json',
    'Origin': 'https://chat.qwen.ai',
    'Referer': 'https://chat.qwen.ai/',
}

def main():
    print('🔍 Fetching your Qwen chats...')
    print()
    
    try:
        with httpx.Client(timeout=30, follow_redirects=True) as client:
            response = client.get(
                'https://chat.qwen.ai/api/v2/chats/',
                headers=headers,
                cookies=cookies,
            )
        
        if response.status_code != 200:
            print(f'❌ Error: HTTP {response.status_code}')
            print(response.text)
            sys.exit(1)
        
        data = response.json()
        
        if not data.get('success'):
            print(f'❌ API Error: {data}')
            sys.exit(1)
        
        chats = data.get('data', [])
        
        if not chats:
            print('❌ No chats found in your account.')
            print()
            print('📝 To create a chat:')
            print('1. Go to https://chat.qwen.ai/')
            print('2. Send any message (e.g., "Hello")')
            print('3. Run this script again')
            sys.exit(1)
        
        print(f'✅ Found {len(chats)} chat(s) in your account:')
        print()
        
        for i, chat in enumerate(chats[:10], 1):
            chat_id = chat.get('id')
            title = chat.get('title', 'No title')
            chat_type = chat.get('chat_type', 'unknown')
            updated = chat.get('updated_at', 'unknown')
            
            print(f'{i}. {title}')
            print(f'   🆔 chat_id: {chat_id}')
            print(f'   📝 Type: {chat_type}')
            print(f'   🕐 Updated: {updated}')
            print()
        
        # Show the most recent chat_id for easy copying
        most_recent = chats[0]
        chat_id = most_recent.get('id')
        
        print('=' * 60)
        print('📋 Most recent chat_id (copy this):')
        print()
        print(f'   {chat_id}')
        print()
        print('=' * 60)
        print()
        print('💡 Add this to your environment or config:')
        print(f'   export QWEN_CHAT_ID="{chat_id}"')
        print()
        
    except Exception as e:
        print(f'❌ Error: {e}')
        sys.exit(1)

if __name__ == '__main__':
    main()
