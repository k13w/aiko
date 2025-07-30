from apscheduler.schedulers.asyncio import AsyncIOScheduler
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from loguru import logger
import os

from ..database.connection import DatabaseConnection
from ..iugu.client import IuguClient
from .intelligent_reconciliation import IntelligentReconciliationService

class AITrainingScheduler:
    def __init__(self):
        self.scheduler = AsyncIOScheduler()
        self.training_interval_hours = int(os.getenv('AI_TRAINING_INTERVAL_HOURS', 24))  # Treinar a cada 24 horas
        self.min_new_reconciliations = int(os.getenv('MIN_NEW_RECONCILIATIONS', 10))  # Mínimo de novas reconciliações para retreinar
        
    def start_training_scheduler(self):
        """Inicia o agendador de treinamento da IA."""
        self.scheduler.add_job(
            self.periodic_training_job,
            'interval',
            hours=self.training_interval_hours,
            id='ai_training_job',
            next_run_time=datetime.now() + timedelta(minutes=5)  # Primeira execução em 5 minutos
        )
        
        # Job para treinamento inicial se não houver modelo
        self.scheduler.add_job(
            self.initial_training_check,
            'date',
            run_date=datetime.now() + timedelta(minutes=1),
            id='initial_training_check'
        )
        
        self.scheduler.start()
        logger.info(f"Agendador de treinamento da IA iniciado. Intervalo: {self.training_interval_hours} horas")
    
    def stop_training_scheduler(self):
        """Para o agendador de treinamento."""
        if self.scheduler.running:
            self.scheduler.shutdown()
            logger.info("Agendador de treinamento da IA finalizado")
    
    async def initial_training_check(self):
        """Verifica se é necessário fazer treinamento inicial."""
        try:
            db_connection = DatabaseConnection()
            db = db_connection.get_session()
            iugu_client = IuguClient()
            intelligent_service = IntelligentReconciliationService(db, iugu_client)
            
            # Verificar se já existe modelo treinado
            if not intelligent_service.ml_engine.is_trained:
                logger.info("Modelo não encontrado. Iniciando treinamento inicial...")
                result = await intelligent_service.train_ai_model()
                
                if result.get('success'):
                    logger.info(f"Treinamento inicial concluído com sucesso: {result}")
                else:
                    logger.warning(f"Treinamento inicial falhou: {result}")
            else:
                logger.info("Modelo já treinado encontrado")
                
        except Exception as e:
            logger.error(f"Erro durante verificação de treinamento inicial: {str(e)}")
        finally:
            db.close()
    
    async def periodic_training_job(self):
        """Job periódico para retreinamento da IA."""
        try:
            db_connection = DatabaseConnection()
            db = db_connection.get_session()
            iugu_client = IuguClient()
            intelligent_service = IntelligentReconciliationService(db, iugu_client)
            
            # Verificar se há dados suficientes para retreinamento
            from ..database.models import ReconciliationRecord, ReconciliationStatus
            
            # Contar reconciliações recentes
            recent_reconciliations = db.query(ReconciliationRecord)\
                .filter(ReconciliationRecord.status == ReconciliationStatus.COMPLETED)\
                .filter(ReconciliationRecord.created_at > datetime.utcnow() - timedelta(hours=self.training_interval_hours))\
                .count()
            
            if recent_reconciliations >= self.min_new_reconciliations:
                logger.info(f"Iniciando retreinamento da IA. Novas reconciliações: {recent_reconciliations}")
                
                result = await intelligent_service.train_ai_model()
                
                if result.get('success'):
                    metrics = result.get('metrics', {})
                    logger.info(
                        f"Retreinamento da IA concluído com sucesso. "
                        f"MAE: {metrics.get('mean_absolute_error', 'N/A'):.4f}, "
                        f"R²: {metrics.get('r2_score', 'N/A'):.4f}, "
                        f"Amostras: {result.get('training_samples', 'N/A')}"
                    )
                else:
                    logger.error(f"Falha no retreinamento da IA: {result}")
            else:
                logger.info(
                    f"Retreinamento pulado. Reconciliações recentes: {recent_reconciliations} "
                    f"(mínimo: {self.min_new_reconciliations})"
                )
                
        except Exception as e:
            logger.error(f"Erro durante job de retreinamento da IA: {str(e)}")
        finally:
            db.close()
    
    async def force_training(self) -> dict:
        """Força um treinamento imediato da IA."""
        try:
            db_connection = DatabaseConnection()
            db = db_connection.get_session()
            iugu_client = IuguClient()
            intelligent_service = IntelligentReconciliationService(db, iugu_client)
            
            logger.info("Iniciando treinamento forçado da IA...")
            result = await intelligent_service.train_ai_model()
            
            if result.get('success'):
                logger.info(f"Treinamento forçado concluído: {result}")
            else:
                logger.error(f"Treinamento forçado falhou: {result}")
                
            return result
            
        except Exception as e:
            error_msg = f"Erro durante treinamento forçado: {str(e)}"
            logger.error(error_msg)
            return {"error": error_msg}
        finally:
            db.close()

# Instância global do agendador
ai_training_scheduler = AITrainingScheduler()