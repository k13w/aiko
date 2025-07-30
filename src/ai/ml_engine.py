import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestRegressor, IsolationForest
from sklearn.preprocessing import StandardScaler
from sklearn.model_selection import train_test_split
from sklearn.metrics import mean_absolute_error, r2_score
import joblib
from datetime import datetime, timedelta
from typing import Dict, List, Tuple, Optional
from loguru import logger
import os

class MLReconciliationEngine:
    def __init__(self):
        self.prediction_model = RandomForestRegressor(n_estimators=100, random_state=42)
        self.anomaly_detector = IsolationForest(contamination=0.1, random_state=42)
        self.scaler = StandardScaler()
        self.is_trained = False
        self.model_path = "models/"
        self.feature_columns = [
            'hour_of_day', 'day_of_week', 'day_of_month',
            'transaction_count_last_hour', 'transaction_count_last_day',
            'avg_transaction_amount', 'balance_volatility',
            'time_since_last_reconciliation', 'historical_difference_pattern'
        ]
        
    def extract_features(self, account_data: Dict, transaction_history: List[Dict]) -> np.ndarray:
        """Extrai características relevantes dos dados da conta e transações."""
        now = datetime.utcnow()
        
        # Características temporais
        hour_of_day = now.hour
        day_of_week = now.weekday()
        day_of_month = now.day
        
        # Análise de transações
        recent_transactions = [t for t in transaction_history 
                             if datetime.fromisoformat(t['created_at'].replace('Z', '+00:00')) > now - timedelta(hours=24)]
        
        transaction_count_last_hour = len([t for t in recent_transactions 
                                         if datetime.fromisoformat(t['created_at'].replace('Z', '+00:00')) > now - timedelta(hours=1)])
        transaction_count_last_day = len(recent_transactions)
        
        # Padrões de valor
        amounts = [float(t.get('amount', 0)) for t in recent_transactions]
        avg_transaction_amount = np.mean(amounts) if amounts else 0
        balance_volatility = np.std(amounts) if len(amounts) > 1 else 0
        
        # Tempo desde última reconciliação
        last_sync = account_data.get('last_sync')
        if last_sync:
            time_since_last = (now - datetime.fromisoformat(last_sync.replace('Z', '+00:00'))).total_seconds() / 3600
        else:
            time_since_last = 24  # Default para 24 horas
            
        # Padrão histórico de diferenças
        historical_differences = account_data.get('historical_differences', [])
        historical_difference_pattern = np.mean(historical_differences) if historical_differences else 0
        
        features = np.array([
            hour_of_day, day_of_week, day_of_month,
            transaction_count_last_hour, transaction_count_last_day,
            avg_transaction_amount, balance_volatility,
            time_since_last, historical_difference_pattern
        ])
        
        return features.reshape(1, -1)
    
    def predict_balance_difference(self, account_data: Dict, transaction_history: List[Dict]) -> float:
        """Prediz a diferença de saldo esperada baseada nos padrões aprendidos."""
        if not self.is_trained:
            logger.warning("Modelo não treinado. Retornando predição padrão.")
            return 0.0
            
        features = self.extract_features(account_data, transaction_history)
        scaled_features = self.scaler.transform(features)
        
        predicted_difference = self.prediction_model.predict(scaled_features)[0]
        return round(predicted_difference, 2)
    
    def detect_anomaly(self, account_data: Dict, transaction_history: List[Dict]) -> bool:
        """Detecta se o padrão atual é anômalo comparado ao histórico."""
        if not self.is_trained:
            return False
            
        features = self.extract_features(account_data, transaction_history)
        scaled_features = self.scaler.transform(features)
        
        anomaly_score = self.anomaly_detector.decision_function(scaled_features)[0]
        is_anomaly = self.anomaly_detector.predict(scaled_features)[0] == -1
        
        logger.info(f"Anomaly score: {anomaly_score}, Is anomaly: {is_anomaly}")
        return is_anomaly
    
    def calculate_confidence_score(self, predicted_diff: float, actual_diff: float) -> float:
        """Calcula a confiança da predição baseada na precisão histórica."""
        if abs(predicted_diff) < 0.01:  # Predição muito pequena
            return 0.5
            
        error = abs(predicted_diff - actual_diff)
        relative_error = error / max(abs(actual_diff), 0.01)
        
        # Confiança inversamente proporcional ao erro relativo
        confidence = max(0.1, 1.0 - relative_error)
        return min(confidence, 1.0)
    
    def should_auto_adjust(self, predicted_diff: float, confidence: float, 
                          is_anomaly: bool, account_risk_level: str = "medium") -> bool:
        """Decide se deve fazer ajuste automático baseado na IA."""
        # Thresholds baseados no nível de risco da conta
        risk_thresholds = {
            "low": {"confidence": 0.7, "max_amount": 100.0},
            "medium": {"confidence": 0.8, "max_amount": 50.0},
            "high": {"confidence": 0.9, "max_amount": 20.0}
        }
        
        threshold = risk_thresholds.get(account_risk_level, risk_thresholds["medium"])
        
        # Não ajustar se for anomalia
        if is_anomaly:
            logger.info("Anomalia detectada. Ajuste automático bloqueado.")
            return False
            
        # Verificar confiança e valor
        if confidence >= threshold["confidence"] and abs(predicted_diff) <= threshold["max_amount"]:
            return True
            
        return False
    
    def train_model(self, training_data: pd.DataFrame) -> Dict[str, float]:
        """Treina o modelo com dados históricos de reconciliação."""
        try:
            # Preparar dados
            X = training_data[self.feature_columns]
            y = training_data['actual_difference']
            
            # Dividir dados
            X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)
            
            # Escalar características
            X_train_scaled = self.scaler.fit_transform(X_train)
            X_test_scaled = self.scaler.transform(X_test)
            
            # Treinar modelo de predição
            self.prediction_model.fit(X_train_scaled, y_train)
            
            # Treinar detector de anomalias
            self.anomaly_detector.fit(X_train_scaled)
            
            # Avaliar modelo
            y_pred = self.prediction_model.predict(X_test_scaled)
            mae = mean_absolute_error(y_test, y_pred)
            r2 = r2_score(y_test, y_pred)
            
            self.is_trained = True
            
            # Salvar modelos
            self._save_models()
            
            metrics = {
                "mean_absolute_error": mae,
                "r2_score": r2,
                "training_samples": len(training_data)
            }
            
            logger.info(f"Modelo treinado com sucesso. MAE: {mae:.4f}, R²: {r2:.4f}")
            return metrics
            
        except Exception as e:
            logger.error(f"Erro durante treinamento do modelo: {str(e)}")
            raise
    
    def _save_models(self):
        """Salva os modelos treinados."""
        os.makedirs(self.model_path, exist_ok=True)
        
        joblib.dump(self.prediction_model, f"{self.model_path}prediction_model.pkl")
        joblib.dump(self.anomaly_detector, f"{self.model_path}anomaly_detector.pkl")
        joblib.dump(self.scaler, f"{self.model_path}scaler.pkl")
        
        logger.info("Modelos salvos com sucesso")
    
    def load_models(self) -> bool:
        """Carrega modelos previamente treinados."""
        try:
            if all(os.path.exists(f"{self.model_path}{file}") for file in 
                   ["prediction_model.pkl", "anomaly_detector.pkl", "scaler.pkl"]):
                
                self.prediction_model = joblib.load(f"{self.model_path}prediction_model.pkl")
                self.anomaly_detector = joblib.load(f"{self.model_path}anomaly_detector.pkl")
                self.scaler = joblib.load(f"{self.model_path}scaler.pkl")
                
                self.is_trained = True
                logger.info("Modelos carregados com sucesso")
                return True
            else:
                logger.warning("Arquivos de modelo não encontrados")
                return False
                
        except Exception as e:
            logger.error(f"Erro ao carregar modelos: {str(e)}")
            return False
    
    def update_model_with_feedback(self, account_data: Dict, transaction_history: List[Dict], 
                                 actual_difference: float, adjustment_success: bool):
        """Atualiza o modelo com feedback das reconciliações realizadas."""
        # Implementar aprendizado incremental
        # Por simplicidade, armazenar dados para retreinamento periódico
        feedback_data = {
            'timestamp': datetime.utcnow().isoformat(),
            'account_id': account_data.get('id'),
            'features': self.extract_features(account_data, transaction_history).flatten().tolist(),
            'actual_difference': actual_difference,
            'adjustment_success': adjustment_success
        }
        
        # Salvar feedback para retreinamento futuro
        self._save_feedback(feedback_data)
    
    def _save_feedback(self, feedback_data: Dict):
        """Salva dados de feedback para retreinamento."""
        feedback_file = f"{self.model_path}feedback_data.jsonl"
        os.makedirs(self.model_path, exist_ok=True)
        
        with open(feedback_file, 'a') as f:
            import json
            f.write(json.dumps(feedback_data) + '\n')