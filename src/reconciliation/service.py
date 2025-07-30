from datetime import datetime
from typing import Optional, Tuple, List
from sqlalchemy.orm import Session
from loguru import logger

from ..database.models import Account, ReconciliationRecord, AdjustmentRecord, ReconciliationStatus, ReconciliationType
from ..iugu.client import IuguClient

class ReconciliationService:
    def __init__(self, db_session: Session, iugu_client: IuguClient):
        self.db = db_session
        self.iugu_client = iugu_client
        self.tolerance = 0.01  # Diferença mínima para considerar uma divergência (em reais)

    def check_balance_difference(self, local_balance: float, iugu_balance: float) -> float:
        """Calcula a diferença entre os saldos local e IUGU."""
        return round(local_balance - iugu_balance, 2)

    def needs_reconciliation(self, difference: float) -> bool:
        """Determina se é necessário realizar a reconciliação baseado na diferença de saldos."""
        return abs(difference) > self.tolerance

    async def reconcile_account(self, account_id: int) -> Tuple[bool, Optional[str]]:
        """Realiza a reconciliação de uma conta específica."""
        try:
            account = self.db.query(Account).get(account_id)
            if not account:
                return False, "Conta não encontrada"

            # Verifica status da conta na IUGU
            if not self.iugu_client.verify_account_status(account.iugu_id):
                return False, "Conta IUGU não está acessível"

            # Obtém saldo da IUGU
            iugu_balance = self.iugu_client.get_account_balance(account.iugu_id)

            # Calcula diferença
            difference = self.check_balance_difference(account.current_balance, iugu_balance)

            # Cria registro de reconciliação
            reconciliation = ReconciliationRecord(
                account_id=account.id,
                local_balance=account.current_balance,
                iugu_balance=iugu_balance,
                difference=difference,
                status=ReconciliationStatus.IN_PROGRESS,
                type=ReconciliationType.AUTOMATIC
            )
            self.db.add(reconciliation)

            if self.needs_reconciliation(difference):
                # Tenta realizar o ajuste
                try:
                    adjustment = self.create_adjustment(reconciliation.id, difference)
                    if adjustment:
                        # Atualiza saldo local
                        account.current_balance = iugu_balance
                        account.last_sync = datetime.utcnow()
                        reconciliation.status = ReconciliationStatus.COMPLETED
                    else:
                        reconciliation.status = ReconciliationStatus.FAILED
                        reconciliation.error_message = "Falha ao criar ajuste"
                except Exception as e:
                    reconciliation.status = ReconciliationStatus.FAILED
                    reconciliation.error_message = str(e)
            else:
                reconciliation.status = ReconciliationStatus.COMPLETED

            self.db.commit()
            return True, None

        except Exception as e:
            logger.error(f"Erro durante reconciliação da conta {account_id}: {str(e)}")
            self.db.rollback()
            return False, str(e)

    def create_adjustment(self, reconciliation_id: int, difference: float) -> Optional[AdjustmentRecord]:
        """Cria um registro de ajuste para corrigir a divergência."""
        try:
            reconciliation = self.db.query(ReconciliationRecord).get(reconciliation_id)
            if not reconciliation:
                return None

            description = f"Ajuste automático de reconciliação - {datetime.utcnow()}"

            # Cria ajuste na IUGU
            iugu_adjustment = self.iugu_client.create_adjustment(
                reconciliation.account.iugu_id,
                difference,
                description
            )

            # Registra o ajuste localmente
            adjustment = AdjustmentRecord(
                reconciliation_id=reconciliation_id,
                amount=difference,
                description=description
            )
            self.db.add(adjustment)
            self.db.commit()

            return adjustment

        except Exception as e:
            logger.error(f"Erro ao criar ajuste para reconciliação {reconciliation_id}: {str(e)}")
            self.db.rollback()
            return None

    async def reconcile_all_accounts(self) -> List[Tuple[int, bool, Optional[str]]]:
        """Realiza a reconciliação de todas as contas cadastradas."""
        results = []
        accounts = self.db.query(Account).all()

        for account in accounts:
            success, error = await self.reconcile_account(account.id)
            results.append((account.id, success, error))

        return results