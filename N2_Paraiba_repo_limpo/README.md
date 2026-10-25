# Projeto Administrativo-Financeiro

Aplicação web para extração de dados de notas fiscais em PDF com FastAPI e Gemini.

## Estrutura

- `BackEnd/main.py`: API FastAPI e integração com o Gemini.
- `BackEnd/requirements.txt`: dependências Python.
- `BackEnd/.env.example`: modelo das variáveis de ambiente necessárias.
- `FrontEnd/`: interface HTML, CSS e JavaScript.

## Executar localmente

1. Instale Python 3.11 ou superior.
2. Abra o terminal na pasta `BackEnd`.
3. Crie e ative um ambiente virtual:
   - Windows: `py -m venv .venv`
   - PowerShell: `\.venv\Scripts\Activate.ps1`
4. Instale as dependências:
   `python -m pip install -r requirements.txt`
5. Copie `.env.example` para `.env` e defina `GEMINI_API_KEY` no arquivo `.env`.
6. Inicie a API:
   `python -m uvicorn main:app --reload`
7. Abra a API em `http://127.0.0.1:8000` e a documentação em `http://127.0.0.1:8000/docs`.
8. Abra `FrontEnd/index.html` com uma extensão de servidor local, como Live Server.

## Segurança

- Nunca publique o arquivo `.env` nem uma chave real da Gemini API.
- Configure `GEMINI_API_KEY` como variável de ambiente no provedor de hospedagem.
- O `FrontEnd/script.js` ainda aponta para `http://127.0.0.1:8000`; antes de publicar, será necessário configurar a URL pública do backend.

## Estado atual

Esta cópia contém a versão atual de extração de PDF. Os requisitos de banco de dados, consultas e registro de contas da segunda etapa ainda precisam ser implementados.
