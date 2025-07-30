import os
import requests
from typing import Dict, Any, Optional
from loguru import logger
from datetime import datetime

class IuguClient:
    def __init__(self):
        self.api_key = os.getenv('IUGU_API_KEY')
        self.base_url = os.getenv('IUGU_API_URL', 'https://api.iugu.com/v1')
        self.session = requests.Session()
        self.session.headers.update({
            'Authorization': f'Basic {self.api_key}',
            'Content-Type': 'application/json'
        })

    def _make_request(self, method: str, endpoint: str, **kwargs) -> Dict[str, Any]:
        """Realiza uma requisição para a API da IUGU."""
        url = f"{self.base_url}/{endpoint.lstrip('/')}"
        
        try:
            response = self.session.request(method, url, **kwargs)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            logger.error(f"Erro na requisição para IUGU: {str(e)}")
            raise

    def get_account_balance(self, account_id: str) -> float:
        """Obtém o saldo atual da conta na IUGU."""
        try:
            response = self._make_request('GET', f'/accounts/{account_id}')
            return float(response.get('balance', 0.0))
        except Exception as e:
            logger.error(f"Erro ao obter saldo da conta {account_id}: {str(e)}")
            raise

    def get_account_transactions(self, account_id: str, start_date: Optional[datetime] = None, 
                               end_date: Optional[datetime] = None) -> list:
        """Obtém as transações da conta em um período específico."""
        params = {}
        if start_date:
            params['start_date'] = start_date.strftime('%Y-%m-%d')
        if end_date:
            params['end_date'] = end_date.strftime('%Y-%m-%d')

        try:
            response = self._make_request('GET', f'/accounts/{account_id}/transactions', params=params)
            return response.get('items', [])
        except Exception as e:
            logger.error(f"Erro ao obter transações da conta {account_id}: {str(e)}")
            raise

    def create_adjustment(self, account_id: str, amount: float, description: str) -> Dict[str, Any]:
        """Cria um ajuste de saldo na conta IUGU."""
        data = {
            'amount': amount,
            'description': description
        }

        try:
            response = self._make_request('POST', f'/accounts/{account_id}/adjustments', json=data)
            return response
        except Exception as e:
            logger.error(f"Erro ao criar ajuste para conta {account_id}: {str(e)}")
            raise

    def verify_account_status(self, account_id: str) -> bool:
        """Verifica se a conta está ativa e acessível."""
        try:
            response = self._make_request('GET', f'/accounts/{account_id}/status')
            return response.get('active', False)
        except Exception as e:
            logger.error(f"Erro ao verificar status da conta {account_id}: {str(e)}")
            return False