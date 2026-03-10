"""
Example: How to call PythonAI API from your Python application
This shows proper authentication and usage
"""

import requests
from datetime import datetime, timedelta
import json

class PythonAIClient:
    """Client for PythonAI API with automatic authentication"""
    
    def __init__(self, api_url='http://localhost:8000'):
        self.api_url = api_url
        self.api_key = None
        self.jwt_token = None
        self.token_expiry = None
    
    def initialize(self):
        """Initialize API - Call this once when your app starts"""
        try:
            # Step 1: Generate API Key (do this once and save permanently)
            response = requests.post(f'{self.api_url}/api/auth/generate-key')
            response.raise_for_status()
            self.api_key = response.json()['api_key']
            print(f'✅ API Key generated: {self.api_key}')
            
            # Step 2: Get JWT Token
            self._refresh_token()
            
            print('✅ API initialized successfully')
        except Exception as e:
            print(f'❌ Failed to initialize API: {e}')
            raise
    
    def _refresh_token(self):
        """Get or refresh JWT token"""
        try:
            response = requests.post(
                f'{self.api_url}/api/auth/token',
                params={'api_key': self.api_key}
            )
            response.raise_for_status()
            data = response.json()
            self.jwt_token = data['access_token']
            self.token_expiry = datetime.now() + timedelta(seconds=data['expires_in'])
            print('✅ JWT Token refreshed')
        except Exception as e:
            print(f'❌ Failed to refresh token: {e}')
            raise
    
    def _ensure_valid_token(self):
        """Check if token is expired and refresh if needed"""
        # Refresh token 1 hour before expiry
        if not self.jwt_token or datetime.now() > (self.token_expiry - timedelta(hours=1)):
            self._refresh_token()
    
    def _get_headers(self):
        """Get headers with authorization"""
        self._ensure_valid_token()
        return {
            'Authorization': f'Bearer {self.jwt_token}',
            'Content-Type': 'application/json'
        }
    
    def chat(self, message):
        """
        Chat with AI
        
        Args:
            message (str): User's message
        
        Returns:
            str: AI's response
        """
        try:
            response = requests.post(
                f'{self.api_url}/api/chat',
                headers=self._get_headers(),
                json={'message': message}
            )
            
            if response.status_code == 401:
                print('❌ Unauthorized - Refreshing token...')
                self._refresh_token()
                # Retry once
                response = requests.post(
                    f'{self.api_url}/api/chat',
                    headers=self._get_headers(),
                    json={'message': message}
                )
            
            response.raise_for_status()
            return response.json()['response']
        except Exception as e:
            print(f'❌ Chat error: {e}')
            raise
    
    def get_balance(self):
        """
        Get balance from GL
        
        Returns:
            dict: Balance data
        """
        response = requests.get(
            f'{self.api_url}/api/balance',
            headers=self._get_headers()
        )
        response.raise_for_status()
        return response.json()
    
    def get_chart(self, chart_type, message):
        """
        Get chart data
        
        Args:
            chart_type (str): 'line', 'bar', or 'pie'
            message (str): Description or query
        
        Returns:
            dict: Chart data
        """
        response = requests.post(
            f'{self.api_url}/api/chart',
            headers=self._get_headers(),
            json={'chart_type': chart_type, 'message': message}
        )
        response.raise_for_status()
        return response.json()
    
    def get_inventory(self):
        """
        Get inventory data
        
        Returns:
            dict: Inventory data
        """
        response = requests.get(
            f'{self.api_url}/api/inventory',
            headers=self._get_headers()
        )
        response.raise_for_status()
        return response.json()


def example():
    """Example usage"""
    try:
        # Initialize client
        client = PythonAIClient(api_url='http://localhost:8000')
        client.initialize()
        
        # Use the API
        print('\n📝 Testing Chat...')
        chat_response = client.chat('What is the current balance?')
        print(f'AI: {chat_response}')
        
        print('\n💰 Testing Balance...')
        balance = client.get_balance()
        print(f'Balance: {json.dumps(balance, indent=2)}')
        
        print('\n📊 Testing Chart...')
        chart = client.get_chart('line', 'Show balance over time')
        print(f'Chart: {chart.get("type", "unknown")}')
        
        print('\n✅ All tests passed!')
        
    except Exception as e:
        print(f'❌ Error: {e}')


if __name__ == '__main__':
    example()
