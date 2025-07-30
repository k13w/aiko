# Sistema de Reconciliação Automática IUGU

Este projeto implementa um sistema automatizado para reconciliação de saldos entre um banco de dados PostgreSQL local e a plataforma IUGU.

## Funcionalidades

- Sincronização automática de saldos
- Detecção de divergências
- Ajuste automático de discrepâncias
- Logs detalhados de todas as operações
- Notificações de reconciliação

## Tecnologias Utilizadas

- Python 3.9+
- PostgreSQL
- API IUGU
- SQLAlchemy (ORM)
- FastAPI (API REST)
- APScheduler (Agendamento de tarefas)
- Docker

## Estrutura do Projeto

```
.
├── src/
│   ├── api/              # Endpoints da API
│   ├── core/             # Lógica principal
│   ├── database/         # Modelos e conexões do banco
│   ├── iugu/             # Integração com IUGU
│   ├── reconciliation/   # Lógica de reconciliação
│   └── utils/            # Utilitários
├── tests/                # Testes automatizados
├── docker/               # Arquivos Docker
├── requirements.txt      # Dependências Python
└── README.md            # Documentação
```

## Como Executar

1. Clone o repositório
2. Configure as variáveis de ambiente
3. Execute `docker-compose up`

## Configuração

Crie um arquivo `.env` com as seguintes variáveis:

```env
POSTGRES_URL=postgresql://user:password@localhost:5432/db
IUGU_API_KEY=sua_chave_api
RECONCILIATION_INTERVAL=3600  # intervalo em segundos
```

## Fluxo de Reconciliação

1. Sistema busca saldos no PostgreSQL
2. Consulta saldos na IUGU
3. Compara valores e identifica divergências
4. Aplica ajustes automáticos quando necessário
5. Registra todas as operações em log
6. Notifica sobre as reconciliações realizadas

## Contribuição

Contribuições são bem-vindas! Por favor, abra uma issue antes de enviar um pull request.