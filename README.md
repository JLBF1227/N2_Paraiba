# Projeto Administrativo-Financeiro — N2 Paraiba

Sistema web para extração e gerenciamento de notas fiscais, desenvolvido como projeto acadêmico.

## Tecnologias utilizadas

- **Frontend:** HTML, CSS e JavaScript.
- **Backend:** Python e FastAPI.
- **Inteligência Artificial:** Google Gemini API.
- **Banco de dados:** SQLite para desenvolvimento local e PostgreSQL para hospedagem.

## Funcionalidades

- Extração de dados de notas fiscais em PDF.
- Identificação de fornecedores e faturados.
- Classificação automática de despesas com IA.
- Consulta e cadastro de registros no banco de dados.
- Registro de contas a pagar e parcelas.
- Gerenciamento de pessoas e classificações.
- Inativação e reativação de cadastros.
- Exibição do identificador da versão publicada.

## Como executar localmente

1. Entre na pasta `BackEnd`.
2. Crie um ambiente virtual Python.
3. Instale as dependências com `python -m pip install -r requirements.txt`.
4. Copie `.env.example` para `.env` e configure as variáveis de ambiente.
5. Inicie o servidor com `python -m uvicorn main:app --reload`.
6. Acesse `http://127.0.0.1:8000`.

## Configuração

Configure a chave do Gemini, as credenciais de acesso, a chave secreta de sessão e a URL do banco de dados em variáveis de ambiente.

Não publique chaves de API, senhas ou arquivos `.env` no repositório.

## Repositório

https://github.com/JLBF1227/N2_Paraiba
