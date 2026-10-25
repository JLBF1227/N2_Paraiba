import os
import base64
import asyncio
import random

from typing import List, Literal

from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from google import genai
from dotenv import load_dotenv

from pydantic import BaseModel, Field


# =====================================================
# CARREGAR VARIÁVEIS DO ARQUIVO .env
# =====================================================

load_dotenv()

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")


if not GEMINI_API_KEY:
    raise RuntimeError(
        "GEMINI_API_KEY não encontrada no arquivo .env"
    )


# =====================================================
# CLIENTE GEMINI
# =====================================================

client = genai.Client(
    api_key=GEMINI_API_KEY
)


# =====================================================
# MODELOS PYDANTIC
# Estes modelos definem a estrutura do JSON
# =====================================================


class Fornecedor(BaseModel):

    razaoSocial: str = Field(
        description="Razão Social do fornecedor."
    )

    fantasia: str = Field(
        description="Nome fantasia do fornecedor."
    )

    cnpj: str = Field(
        description="CNPJ do fornecedor."
    )


class Faturado(BaseModel):

    nomeCompleto: str = Field(
        description="Nome completo do faturado."
    )

    cpf: str = Field(
        description="CPF do faturado."
    )


class Parcela(BaseModel):

    numero: int = Field(
        description="Número sequencial da parcela."
    )

    dataVencimento: str = Field(
        description=(
            "Data de vencimento da parcela "
            "no formato YYYY-MM-DD."
        )
    )


# =====================================================
# CATEGORIAS PERMITIDAS
# =====================================================

CategoriaDespesa = Literal[
    "INSUMOS AGRÍCOLAS",
    "MANUTENÇÃO E OPERAÇÃO",
    "RECURSOS HUMANOS",
    "SERVIÇOS OPERACIONAIS",
    "INFRAESTRUTURA E UTILIDADES",
    "ADMINISTRATIVAS",
    "SEGUROS E PROTEÇÃO",
    "IMPOSTOS E TAXAS",
    "INVESTIMENTOS"
]


class ClassificacaoDespesa(BaseModel):

    categoria: CategoriaDespesa = Field(
        description=(
            "Categoria de despesa interpretada "
            "a partir dos produtos da nota fiscal."
        )
    )


class NotaFiscalExtraida(BaseModel):

    fornecedor: Fornecedor

    faturado: Faturado

    numeroNotaFiscal: str = Field(
        description="Número da nota fiscal."
    )

    dataEmissao: str = Field(
        description=(
            "Data de emissão no formato YYYY-MM-DD."
        )
    )

    produtos: List[str] = Field(
        description=(
            "Lista contendo as descrições dos "
            "produtos encontrados na nota fiscal."
        )
    )

    quantidadeParcelas: int = Field(
        description=(
            "Quantidade total de parcelas "
            "identificadas."
        )
    )

    parcelas: List[Parcela] = Field(
        description=(
            "Lista de parcelas e suas "
            "respectivas datas de vencimento."
        )
    )

    valorTotal: float = Field(
        description="Valor total da nota fiscal."
    )

    classificacoesDespesa: List[
        ClassificacaoDespesa
    ] = Field(
        description=(
            "Classificações das despesas "
            "interpretadas pela IA."
        )
    )


# =====================================================
# CRIAR APLICAÇÃO FASTAPI
# =====================================================

app = FastAPI(
    title="Projeto Administrativo Financeiro",
    description=(
        "API para extração de dados "
        "de notas fiscais utilizando Gemini"
    ),
    version="1.0.0"
)


# =====================================================
# CORS
# Permite comunicação do FrontEnd com o BackEnd
# =====================================================

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"]
)


# =====================================================
# ROTA INICIAL
# =====================================================

@app.get("/")
def home():

    return {
        "mensagem": "API funcionando corretamente!"
    }


# =====================================================
# PROMPT PARA O GEMINI
# =====================================================

PROMPT_EXTRACAO = """
Você é responsável por analisar uma nota fiscal brasileira
para um sistema administrativo-financeiro.

Analise cuidadosamente o documento PDF fornecido.

Extraia somente informações presentes no documento ou que
possam ser determinadas diretamente a partir dele.

NÃO invente informações.

=========================================================
FORNECEDOR
=========================================================

Extraia:

- Razão Social
- Nome Fantasia
- CNPJ


=========================================================
FATURADO / DESTINATÁRIO
=========================================================

Extraia:

- Nome Completo
- CPF

O faturado é a pessoa ou entidade para quem a nota fiscal
foi emitida.

Caso o documento não possua CPF, não invente um.
Retorne uma string vazia.


=========================================================
DADOS DA NOTA
=========================================================

Extraia:

- Número da Nota Fiscal
- Data de Emissão
- Descrição dos produtos
- Quantidade de parcelas
- Data de vencimento das parcelas
- Valor Total


As datas deverão ser retornadas no formato:

YYYY-MM-DD


=========================================================
PRODUTOS
=========================================================

Retorne somente a descrição dos produtos.

Exemplo:

[
    "Óleo Diesel S10",
    "Filtro de combustível"
]


=========================================================
PARCELAS
=========================================================

Neste momento normalmente haverá apenas uma parcela.

Porém, a estrutura precisa permitir várias parcelas.

Cada parcela deverá possuir:

- número da parcela
- data de vencimento

Caso haja somente uma parcela:

numero = 1


=========================================================
CLASSIFICAÇÃO DA DESPESA
=========================================================

IMPORTANTE:

A classificação da despesa NÃO é um campo que deve ser
simplesmente copiado da nota fiscal.

Você deve analisar os produtos ou serviços presentes
na nota e interpretar qual categoria de despesa melhor
representa a compra.

Utilize SOMENTE uma das categorias abaixo:


=========================================================
INSUMOS AGRÍCOLAS
=========================================================

Exemplos:

- Sementes
- Fertilizantes
- Defensivos agrícolas
- Corretivos


=========================================================
MANUTENÇÃO E OPERAÇÃO
=========================================================

Exemplos:

- Combustíveis
- Lubrificantes
- Peças
- Parafusos
- Componentes mecânicos
- Manutenção de máquinas
- Manutenção de equipamentos
- Pneus
- Filtros
- Correias
- Ferramentas
- Utensílios


=========================================================
RECURSOS HUMANOS
=========================================================

Exemplos:

- Mão de obra temporária
- Salários
- Encargos


=========================================================
SERVIÇOS OPERACIONAIS
=========================================================

Exemplos:

- Frete
- Transporte
- Colheita terceirizada
- Secagem
- Armazenagem
- Pulverização
- Aplicação


=========================================================
INFRAESTRUTURA E UTILIDADES
=========================================================

Exemplos:

- Energia elétrica
- Arrendamento de terras
- Construções
- Reformas
- Materiais de construção
- Material hidráulico


=========================================================
ADMINISTRATIVAS
=========================================================

Exemplos:

- Honorários contábeis
- Honorários advocatícios
- Honorários agronômicos
- Despesas bancárias
- Despesas financeiras


=========================================================
SEGUROS E PROTEÇÃO
=========================================================

Exemplos:

- Seguro agrícola
- Seguro de ativos
- Seguro de máquinas
- Seguro de veículos
- Seguro prestamista


=========================================================
IMPOSTOS E TAXAS
=========================================================

Exemplos:

- ITR
- IPTU
- IPVA
- INCRA-CCIR


=========================================================
INVESTIMENTOS
=========================================================

Exemplos:

- Aquisição de máquinas
- Aquisição de implementos
- Aquisição de veículos
- Aquisição de imóveis
- Infraestrutura rural


=========================================================
EXEMPLOS DE CLASSIFICAÇÃO
=========================================================

Produto:

Óleo Diesel

Classificação:

MANUTENÇÃO E OPERAÇÃO


Produto:

Material Hidráulico

Classificação:

INFRAESTRUTURA E UTILIDADES


=========================================================
REGRAS IMPORTANTES
=========================================================

1. Não invente CPF.

2. Não invente CNPJ.

3. Não invente datas.

4. Não invente número da nota fiscal.

5. Caso um campo textual não esteja disponível,
   retorne uma string vazia.

6. O valorTotal deverá ser um número.

7. A quantidade de parcelas deverá ser um número inteiro.

8. Neste momento normalmente haverá apenas uma
   classificação de despesa.

9. A estrutura, entretanto, deve permitir várias
   classificações no futuro.

10. Utilize exclusivamente as categorias de despesas
    fornecidas acima.
"""


# =====================================================
# VERIFICAR SE O ERRO É TEMPORÁRIO
# =====================================================

def erro_temporario_gemini(erro):

    mensagem = str(erro).lower()

    indicadores = [
        "503",
        "service_unavailable",
        "service unavailable",
        "high demand",
        "temporarily unavailable",
        "unavailable"
    ]

    return any(
        indicador in mensagem
        for indicador in indicadores
    )


# =====================================================
# EXECUTAR UMA CHAMADA AO GEMINI
# =====================================================

async def executar_gemini(
    modelo,
    pdf_base64
):

    # client.interactions.create é síncrono.
    # asyncio.to_thread evita bloquear toda a API
    # enquanto esperamos a resposta do Gemini.

    interaction = await asyncio.to_thread(

        client.interactions.create,

        model=modelo,

        input=[
            {
                "type": "document",
                "data": pdf_base64,
                "mime_type": "application/pdf"
            },

            {
                "type": "text",
                "text": PROMPT_EXTRACAO
            }
        ],

        response_format=[
            {
                "type": "text",
                "mime_type": "application/json",
                "schema":
                    NotaFiscalExtraida.model_json_schema()
            }
        ]

    )

    return interaction


# =====================================================
# PROCESSAR COM RETENTATIVAS E FALLBACK
# =====================================================

async def processar_com_gemini(pdf_base64):

    modelos = [
        "gemini-3.5-flash-lite"
    ]

    ultimo_erro = None

    for modelo in modelos:

        print()
        print(f"Tentando modelo: {modelo}")

        for tentativa in range(3):

            try:

                interaction = await executar_gemini(
                    modelo,
                    pdf_base64
                )

                print(
                    f"Sucesso usando: {modelo}"
                )

                return interaction

            except Exception as erro:

                ultimo_erro = erro

                mensagem = str(erro).lower()

                print(
                    f"Erro em {modelo}: {erro}"
                )

                # =====================================
                # ERRO 429
                # Cota do modelo acabou.
                # Não adianta esperar alguns segundos.
                # Vamos direto para o próximo modelo.
                # =====================================

                if (
                    "429" in mensagem
                    or "rate limit" in mensagem
                    or "too_many_requests" in mensagem
                ):

                    print(
                        f"Limite de uso do {modelo} "
                        "foi atingido."
                    )

                    print(
                        "Tentando próximo modelo..."
                    )

                    break


                # =====================================
                # ERRO 503
                # É temporário, então tentamos novamente.
                # =====================================

                if (
                    "503" in mensagem
                    or "service_unavailable" in mensagem
                    or "service unavailable" in mensagem
                    or "high demand" in mensagem
                ):

                    if tentativa < 2:

                        espera = (
                            2 ** tentativa
                            + random.uniform(0, 1)
                        )

                        print(
                            f"Serviço temporariamente "
                            f"indisponível."
                        )

                        print(
                            f"Nova tentativa em "
                            f"{espera:.1f} segundos..."
                        )

                        await asyncio.sleep(
                            espera
                        )

                        continue

                    else:

                        print(
                            f"{modelo} continuou "
                            "indisponível."
                        )

                        break


                # Se for outro erro,
                # não escondemos o problema.

                raise erro


    if ultimo_erro:

        raise ultimo_erro


    raise RuntimeError(
        "Nenhum modelo Gemini disponível."
    )


# =====================================================
# ROTA PARA EXTRAIR NOTA FISCAL
# =====================================================

@app.post(
    "/extrair-nota",
    response_model=NotaFiscalExtraida
)
async def extrair_nota(
    arquivo: UploadFile = File(...)
):


    # =================================================
    # VALIDAR O TIPO DO ARQUIVO
    # =================================================

    if arquivo.content_type != "application/pdf":

        raise HTTPException(
            status_code=400,
            detail=(
                "O arquivo enviado precisa ser um PDF."
            )
        )


    # =================================================
    # LER O PDF
    # =================================================

    conteudo_pdf = await arquivo.read()


    # =================================================
    # VERIFICAR ARQUIVO VAZIO
    # =================================================

    if len(conteudo_pdf) == 0:

        raise HTTPException(
            status_code=400,
            detail="O arquivo PDF está vazio."
        )


    # =================================================
    # LIMITE DE TAMANHO DO NOSSO SISTEMA
    # 20 MB
    # =================================================

    limite = 20 * 1024 * 1024


    if len(conteudo_pdf) > limite:

        raise HTTPException(
            status_code=400,
            detail=(
                "O PDF deve possuir "
                "no máximo 20 MB."
            )
        )


    print()
    print("=" * 60)

    print(
        f"Arquivo recebido: {arquivo.filename}"
    )

    print(
        f"Tamanho: {len(conteudo_pdf)} bytes"
    )

    print("=" * 60)


    try:

        # =============================================
        # CONVERTER PDF PARA BASE64
        # =============================================

        pdf_base64 = base64.b64encode(
            conteudo_pdf
        ).decode("utf-8")


        # =============================================
        # ENVIAR PARA O GEMINI
        # =============================================

        interaction = (
            await processar_com_gemini(
                pdf_base64
            )
        )


        # =============================================
        # PEGAR O JSON PRODUZIDO
        # =============================================

        json_recebido = (
            interaction.output_text
        )


        print()
        print(
            "Resposta recebida do Gemini."
        )


        # =============================================
        # VALIDAR JSON COM PYDANTIC
        # =============================================

        nota = (
            NotaFiscalExtraida
            .model_validate_json(
                json_recebido
            )
        )


        print(
            f"Nota processada com sucesso: "
            f"{arquivo.filename}"
        )

        print("=" * 60)
        print()


        # FastAPI transforma o objeto Pydantic
        # automaticamente em JSON.

        return nota


    except HTTPException:

        raise


    except Exception as erro:

        print()
        print(
            "Erro ao processar nota:"
        )

        print(
            erro
        )

        print("=" * 60)
        print()


        # =============================================
        # CASO SEJA ERRO 503 DO GEMINI
        # =============================================

        if erro_temporario_gemini(
            erro
        ):

            raise HTTPException(
                status_code=503,
                detail=(
                    "O serviço do Gemini está "
                    "temporariamente sobrecarregado. "
                    "Tente novamente em alguns instantes."
                )
            )


        # =============================================
        # OUTROS ERROS
        # =============================================

        raise HTTPException(
            status_code=500,
            detail=(
                "Não foi possível processar "
                "a nota fiscal com o Gemini."
            )
        )