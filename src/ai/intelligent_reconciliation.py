from datetime import datetime, timedelta
from typing import Dict, List, Tuple, Optional
from sqlalchemy.orm import Session
from loguru import logger
import pandas as pd
import json

from ..database.models import Account, ReconciliationRecord, AdjustmentRecord, ReconciliationStatus, ReconciliationType
from ..iugu.client import IuguClient
from .ml_engine import MLReconciliationEngine

class IntelligentReconciliationService:
    def __init__(self, db_session: Session, iugu_client: IuguClient):
        self.db = db_session
        self.iugu_client = iugu_client
        self.ml_engine = MLReconciliationEngine()
        self.tolerance = 0.01
        
        # Carregar modelos treinados se existirem
        self.ml_engine.load_models()
    
    def analyze_account_patterns(self, account_id: int) -> Dict:
        """Analisa padrões históricos da conta para alimentar a IA."""
        account = self.db.query(Account).get(account_id)
        if not account:
            return {}
        
        # Buscar histórico de reconciliações
        reconciliations = self.db.query(ReconciliationRecord)\
            .filter(ReconciliationRecord.account_id == account_id)\
            .order_by(ReconciliationRecord.created_at.desc())\
            .limit(100)\
            .all()
        
        # Buscar transações recentes da IUGU
        try:
            transactions = self.iugu_client.get_account_transactions(
                account.iugu_id,
                start_date=datetime.utcnow() - timedelta(days=30)
            )
        except Exception as e:
            logger.error(f"Erro ao buscar transações: {str(e)}")
            transactions = []
        
        # Compilar dados da conta
        account_data = {
            'id': account.id,
            'iugu_id': account.iugu_id,
            'current_balance': account.current_balance,
            'last_sync': account.last_sync.isoformat() if account.last_sync else None,
            'historical_differences': [r.difference for r in reconciliations],
            'reconciliation_count': len(reconciliations),
            'avg_difference': sum(r.difference for r in reconciliations) / len(reconciliations) if reconciliations else 0
        }
        
        return {
            'account_data': account_data,
            'transaction_history': transactions,
            'reconciliation_history': reconciliations
        }
    
    async def intelligent_reconcile_account(self, account_id: int) -> Tuple[bool, Optional[str], Dict]:
        """Realiza reconciliação inteligente usando IA para tomada de decisão."""
        try:
            account = self.db.query(Account).get(account_id)
            if not account:
                return False, "Conta não encontrada", {}
            
            # Verificar status da conta na IUGU
            if not self.iugu_client.verify_account_status(account.iugu_id):
                return False, "Conta IUGU não está acessível", {}
            
            # Analisar padrões da conta
            patterns = self.analyze_account_patterns(account_id)
            account_data = patterns['account_data']
            transaction_history = patterns['transaction_history']
            
            # Obter saldo atual da IUGU
            iugu_balance = self.iugu_client.get_account_balance(account.iugu_id)
            actual_difference = round(account.current_balance - iugu_balance, 2)
            
            # Usar IA para predizer diferença esperada
            predicted_difference = self.ml_engine.predict_balance_difference(
                account_data, transaction_history
            )
            
            # Detectar anomalias
            is_anomaly = self.ml_engine.detect_anomaly(account_data, transaction_history)
            
            # Calcular confiança da predição
            confidence = self.ml_engine.calculate_confidence_score(
                predicted_difference, actual_difference
            )
            
            # Determinar nível de risco da conta
            risk_level = self._assess_account_risk(account_data, transaction_history)
            
            # Decidir se deve fazer ajuste automático
            should_auto_adjust = self.ml_engine.should_auto_adjust(
                predicted_difference, confidence, is_anomaly, risk_level
            )
            
            # Criar registro de reconciliação com dados da IA
            reconciliation = ReconciliationRecord(
                account_id=account.id,
                local_balance=account.current_balance,
                iugu_balance=iugu_balance,
                difference=actual_difference,
                status=ReconciliationStatus.IN_PROGRESS,
                type=ReconciliationType.AUTOMATIC
            )
            self.db.add(reconciliation)
            
            ai_insights = {
                'predicted_difference': predicted_difference,
                'confidence_score': confidence,
                'is_anomaly': is_anomaly,
                'risk_level': risk_level,
                'auto_adjust_recommended': should_auto_adjust,
                'prediction_accuracy': abs(predicted_difference - actual_difference)
            }
            
            # Lógica de ajuste baseada na IA
            adjustment_made = False
            if abs(actual_difference) > self.tolerance:
                if should_auto_adjust:
                    # IA recomenda ajuste automático
                    try:
                        adjustment = self._create_intelligent_adjustment(
                            reconciliation.id, actual_difference, ai_insights
                        )
                        if adjustment:
                            account.current_balance = iugu_balance
                            account.last_sync = datetime.utcnow()
                            reconciliation.status = ReconciliationStatus.COMPLETED
                            adjustment_made = True
                            logger.info(f"Ajuste automático realizado pela IA para conta {account_id}")
                        else:
                            reconciliation.status = ReconciliationStatus.FAILED
                            reconciliation.error_message = "Falha ao criar ajuste inteligente"
                    except Exception as e:
                        reconciliation.status = ReconciliationStatus.FAILED
                        reconciliation.error_message = f"Erro no ajuste inteligente: {str(e)}"
                else:
                    # IA não recomenda ajuste automático - marcar para revisão manual
                    reconciliation.status = ReconciliationStatus.PENDING
                    reconciliation.error_message = "IA recomenda revisão manual"
                    logger.warning(f"IA bloqueou ajuste automático para conta {account_id}. Motivo: baixa confiança ou anomalia")
            else:
                reconciliation.status = ReconciliationStatus.COMPLETED
            
            # Fornecer feedback para a IA
            self.ml_engine.update_model_with_feedback(
                account_data, transaction_history, actual_difference, adjustment_made
            )
            
            self.db.commit()
            return True, None, ai_insights
            
        except Exception as e:
            logger.error(f"Erro durante reconciliação inteligente da conta {account_id}: {str(e)}")
            self.db.rollback()
            return False, str(e), {}
    
    def _assess_account_risk(self, account_data: Dict, transaction_history: List[Dict]) -> str:
        """Avalia o nível de risco da conta baseado em padrões históricos."""
        # Fatores de risco
        balance = account_data.get('current_balance', 0)
        avg_difference = abs(account_data.get('avg_difference', 0))
        transaction_count = len(transaction_history)
        
        # Calcular volatilidade das transações
        amounts = [float(t.get('amount', 0)) for t in transaction_history]
        volatility = pd.Series(amounts).std() if len(amounts) > 1 else 0
        
        # Lógica de classificação de risco
        risk_score = 0
        
        # Saldo alto = maior risco
        if balance > 10000:
            risk_score += 2
        elif balance > 1000:
            risk_score += 1
        
        # Diferenças históricas altas = maior risco
        if avg_difference > 100:
            risk_score += 2
        elif avg_difference > 10:
            risk_score += 1
        
        # Alta volatilidade = maior risco
        if volatility > 500:
            risk_score += 2
        elif volatility > 100:
            risk_score += 1
        
        # Muitas transações = maior risco
        if transaction_count > 100:
            risk_score += 1
        
        # Classificar risco
        if risk_score >= 5:
            return "high"
        elif risk_score >= 3:
            return "medium"
        else:
            return "low"
    
    def _create_intelligent_adjustment(self, reconciliation_id: int, difference: float, 
                                     ai_insights: Dict) -> Optional[AdjustmentRecord]:
        """Cria ajuste inteligente com metadados da IA."""
        try:
            reconciliation = self.db.query(ReconciliationRecord).get(reconciliation_id)
            if not reconciliation:
                return None
            
            # Descrição enriquecida com dados da IA
            description = (
                f"Ajuste inteligente automático - {datetime.utcnow()} | "
                f"Confiança: {ai_insights['confidence_score']:.2f} | "
                f"Predição: {ai_insights['predicted_difference']:.2f} | "
                f"Risco: {ai_insights['risk_level']}"
            )
            
            # Criar ajuste na IUGU
            iugu_adjustment = self.iugu_client.create_adjustment(
                reconciliation.account.iugu_id,
                difference,
                description
            )
            
            # Registrar ajuste localmente
            adjustment = AdjustmentRecord(
                reconciliation_id=reconciliation_id,
                amount=difference,
                description=description
            )
            self.db.add(adjustment)
            self.db.commit()
            
            return adjustment
            
        except Exception as e:
            logger.error(f"Erro ao criar ajuste inteligente: {str(e)}")
            self.db.rollback()
            return None
    
    async def train_ai_model(self) -> Dict:
        """Treina o modelo de IA com dados históricos."""
        try:
            # Buscar dados históricos de reconciliação
            reconciliations = self.db.query(ReconciliationRecord)\
                .filter(ReconciliationRecord.status == ReconciliationStatus.COMPLETED)\
                .all()
            
            if len(reconciliations) < 50:
                return {"error": "Dados insuficientes para treinamento (mínimo 50 reconciliações)"}
            
            # Preparar dados de treinamento
            training_data = []
            for rec in reconciliations:
                account_patterns = self.analyze_account_patterns(rec.account_id)
                if account_patterns:
                    features = self.ml_engine.extract_features(
                        account_patterns['account_data'],
                        account_patterns['transaction_history']
                    ).flatten()
                    
                    row = dict(zip(self.ml_engine.feature_columns, features))
                    row['actual_difference'] = rec.difference
                    training_data.append(row)
            
            if len(training_data) < 50:
                return {"error": "Dados de características insuficientes para treinamento"}
            
            # Treinar modelo
            df = pd.DataFrame(training_data)
            metrics = self.ml_engine.train_model(df)
            
            logger.info(f"Modelo de IA treinado com {len(training_data)} amostras")
            return {"success": True, "metrics": metrics, "training_samples": len(training_data)}
            
        except Exception as e:
            logger.error(f"Erro durante treinamento da IA: {str(e)}")
            return {"error": str(e)}
    
    async def get_ai_insights(self, account_id: int) -> Dict:
        """Obtém insights da IA sobre uma conta específica."""
        try:
            patterns = self.analyze_account_patterns(account_id)
            if not patterns:
                return {"error": "Dados da conta não encontrados"}
            
            account_data = patterns['account_data']
            transaction_history = patterns['transaction_history']
            
            # Predições da IA
            predicted_diff = self.ml_engine.predict_balance_difference(account_data, transaction_history)
            is_anomaly = self.ml_engine.detect_anomaly(account_data, transaction_history)
            risk_level = self._assess_account_risk(account_data, transaction_history)
            
            return {
                "predicted_difference": predicted_diff,
                "is_anomaly": is_anomaly,
                "risk_level": risk_level,
                "model_trained": self.ml_engine.is_trained,
                "historical_avg_difference": account_data.get('avg_difference', 0),
                "reconciliation_count": account_data.get('reconciliation_count', 0)
            }
            
        except Exception as e:
            logger.error(f"Erro ao obter insights da IA: {str(e)}")
            return {"error": str(e)}