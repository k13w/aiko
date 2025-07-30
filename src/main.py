from fastapi import FastAPI, Depends, HTTPException
from sqlalchemy.orm import Session
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from datetime import datetime
from typing import List, Dict
from loguru import logger
import os

from .database.connection import get_db
from .database.models import Account, ReconciliationRecord
from .iugu.client import IuguClient
from .reconciliation.service import ReconciliationService
from .ai.intelligent_reconciliation import IntelligentReconciliationService
from .ai.training_scheduler import ai_training_scheduler

app = FastAPI(
    title="Sistema de Reconciliação IUGU",
    description="API para reconciliação automática de saldos entre banco local e IUGU",
    version="1.0.0"
)

# Configuração do scheduler
scheduler = AsyncIOScheduler()

@app.on_event("startup")
async def startup_event():
    """Inicializa os schedulers na inicialização da aplicação."""
    reconciliation_interval = int(os.getenv('RECONCILIATION_INTERVAL', 3600))
    
    # Agenda a tarefa de reconciliação
    scheduler.add_job(
        reconcile_all_accounts_job,
        'interval',
        seconds=reconciliation_interval,
        id='reconciliation_job'
    )
    scheduler.start()
    logger.info(f"Scheduler de reconciliação iniciado com intervalo de {reconciliation_interval} segundos")
    
    # Inicia o agendador de treinamento da IA
    ai_training_scheduler.start_training_scheduler()
    logger.info("Sistema de IA inicializado com agendamento automático de treinamento")

@app.on_event("shutdown")
def shutdown_event():
    """Para os schedulers quando a aplicação é encerrada."""
    scheduler.shutdown()
    ai_training_scheduler.stop_training_scheduler()
    logger.info("Schedulers finalizados")

# Rotas da API
@app.post("/accounts/")
async def create_account(iugu_id: str, name: str, db: Session = Depends(get_db)):
    """Cria uma nova conta para monitoramento."""
    try:
        account = Account(iugu_id=iugu_id, name=name)
        db.add(account)
        db.commit()
        db.refresh(account)
        return {"message": "Conta criada com sucesso", "account": account}
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(e))

@app.get("/accounts/")
async def list_accounts(db: Session = Depends(get_db)):
    """Lista todas as contas cadastradas."""
    accounts = db.query(Account).all()
    return accounts

@app.get("/accounts/{account_id}/reconciliations")
async def get_account_reconciliations(
    account_id: int,
    db: Session = Depends(get_db)
):
    """Obtém o histórico de reconciliações de uma conta."""
    reconciliations = db.query(ReconciliationRecord)\
        .filter(ReconciliationRecord.account_id == account_id)\
        .order_by(ReconciliationRecord.created_at.desc())\
        .all()
    return reconciliations

@app.post("/reconciliation/manual/{account_id}")
async def trigger_manual_reconciliation(
    account_id: int,
    db: Session = Depends(get_db)
):
    """Dispara uma reconciliação manual para uma conta específica."""
    iugu_client = IuguClient()
    reconciliation_service = ReconciliationService(db, iugu_client)
    
    success, error = await reconciliation_service.reconcile_account(account_id)
    
    if success:
        return {"message": "Reconciliação realizada com sucesso"}
    else:
        raise HTTPException(status_code=400, detail=error)

@app.post("/reconciliation/intelligent/{account_id}")
async def trigger_intelligent_reconciliation(
    account_id: int,
    db: Session = Depends(get_db)
):
    """Dispara uma reconciliação inteligente usando IA para uma conta específica."""
    iugu_client = IuguClient()
    intelligent_service = IntelligentReconciliationService(db, iugu_client)
    
    success, error, ai_insights = await intelligent_service.intelligent_reconcile_account(account_id)
    
    if success:
        return {
            "message": "Reconciliação inteligente realizada com sucesso",
            "ai_insights": ai_insights
        }
    else:
        raise HTTPException(status_code=400, detail=error)

@app.get("/ai/insights/{account_id}")
async def get_ai_insights(
    account_id: int,
    db: Session = Depends(get_db)
):
    """Obtém insights da IA sobre uma conta específica."""
    iugu_client = IuguClient()
    intelligent_service = IntelligentReconciliationService(db, iugu_client)
    
    insights = await intelligent_service.get_ai_insights(account_id)
    return insights

@app.post("/ai/train")
async def train_ai_model(
    db: Session = Depends(get_db)
):
    """Treina o modelo de IA com dados históricos."""
    result = await ai_training_scheduler.force_training()
    return result

@app.post("/ai/retrain")
async def retrain_ai_model(
    db: Session = Depends(get_db)
):
    """Força um retreinamento imediato do modelo de IA."""
    result = await ai_training_scheduler.force_training()
    return result

@app.get("/ai/status")
async def get_ai_status(
    db: Session = Depends(get_db)
):
    """Obtém o status atual do sistema de IA."""
    iugu_client = IuguClient()
    intelligent_service = IntelligentReconciliationService(db, iugu_client)
    
    return {
        "model_trained": intelligent_service.ml_engine.is_trained,
        "model_path": intelligent_service.ml_engine.model_path,
        "feature_columns": intelligent_service.ml_engine.feature_columns
    }

@app.get("/reconciliation/status")
async def get_reconciliation_status(db: Session = Depends(get_db)):
    """Obtém o status atual das reconciliações."""
    last_reconciliations = db.query(ReconciliationRecord)\
        .order_by(ReconciliationRecord.created_at.desc())\
        .limit(10)\
        .all()
    return last_reconciliations

async def reconcile_all_accounts_job():
    """Job para reconciliação automática inteligente de todas as contas."""
    try:
        db = next(get_db())
        iugu_client = IuguClient()
        intelligent_service = IntelligentReconciliationService(db, iugu_client)
        
        # Buscar todas as contas
        accounts = db.query(Account).all()
        
        for account in accounts:
            try:
                success, error, ai_insights = await intelligent_service.intelligent_reconcile_account(account.id)
                
                if success:
                    logger.info(
                        f"Reconciliação inteligente bem-sucedida para conta {account.id}. "
                        f"Confiança: {ai_insights.get('confidence_score', 'N/A')}, "
                        f"Risco: {ai_insights.get('risk_level', 'N/A')}"
                    )
                else:
                    logger.error(f"Falha na reconciliação inteligente da conta {account.id}: {error}")
                    
            except Exception as e:
                logger.error(f"Erro na reconciliação da conta {account.id}: {str(e)}")
                
    except Exception as e:
        logger.error(f"Erro durante job de reconciliação inteligente: {str(e)}")
    finally:
        db.close()

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)