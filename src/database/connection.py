from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.pool import QueuePool
from loguru import logger
import os

from .models import Base

class DatabaseConnection:
    def __init__(self):
        self.database_url = os.getenv('POSTGRES_URL')
        self.engine = None
        self.SessionLocal = None
        self.init_database()

    def init_database(self) -> None:
        """Inicializa a conexão com o banco de dados e cria as tabelas."""
        try:
            self.engine = create_engine(
                self.database_url,
                poolclass=QueuePool,
                pool_size=5,
                max_overflow=10,
                pool_timeout=30,
                pool_recycle=1800
            )

            self.SessionLocal = sessionmaker(
                autocommit=False,
                autoflush=False,
                bind=self.engine
            )

            # Cria todas as tabelas definidas nos modelos
            Base.metadata.create_all(bind=self.engine)
            logger.info("Conexão com o banco de dados estabelecida com sucesso")

        except Exception as e:
            logger.error(f"Erro ao inicializar banco de dados: {str(e)}")
            raise

    def get_session(self) -> Session:
        """Retorna uma nova sessão do banco de dados."""
        return self.SessionLocal()

    def close_connection(self) -> None:
        """Fecha a conexão com o banco de dados."""
        if self.engine:
            self.engine.dispose()
            logger.info("Conexão com o banco de dados fechada")

def get_db() -> Session:
    """Dependency para injeção da sessão do banco de dados."""
    db = DatabaseConnection().get_session()
    try:
        yield db
    finally:
        db.close()