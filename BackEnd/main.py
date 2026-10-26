import asyncio
import base64
import json
import os
import random
import re
import secrets
import uuid
from datetime import date, datetime
from pathlib import Path
from typing import List, Literal, Optional

from dotenv import load_dotenv
from fastapi import APIRouter, Depends, FastAPI, File, HTTPException, Query, Request, UploadFile
from fastapi.staticfiles import StaticFiles
try:
    from google import genai
except ImportError:
    genai = None
from pydantic import BaseModel, Field
from sqlalchemy import (
    Column,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Table,
    Text,
    UniqueConstraint,
    create_engine,
    func,
    or_,
)
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, declarative_base, relationship, sessionmaker
from starlette.middleware.sessions import SessionMiddleware


# ============================================================
# CONFIGURACAO
# ============================================================

BASE_DIR = Path(__file__).resolve().parent
PROJECT_DIR = BASE_DIR.parent
FRONTEND_DIR = PROJECT_DIR / "FrontEnd"

load_dotenv(BASE_DIR / ".env")

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "").strip()
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.5-flash-lite").strip()
ENVIRONMENT = os.getenv("ENVIRONMENT", "development").lower()
APP_LOGIN = os.getenv("APP_LOGIN", "admin" if ENVIRONMENT != "production" else "").strip()
APP_PASSWORD = os.getenv("APP_PASSWORD", "admin123" if ENVIRONMENT != "production" else "")
APP_SECRET_KEY = os.getenv("APP_SECRET_KEY", "desenvolvimento-local-altere-esta-chave-antes-de-publicar")

DATABASE_URL = os.getenv("DATABASE_URL", "").strip()
if not DATABASE_URL:
    local_database = (BASE_DIR / "administrativo.db").as_posix()
    DATABASE_URL = f"sqlite:///{local_database}"

# Render e outros provedores podem fornecer URLs sem o nome explicito do driver.
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql+psycopg://", 1)
elif DATABASE_URL.startswith("postgresql://"):
    DATABASE_URL = DATABASE_URL.replace("postgresql://", "postgresql+psycopg://", 1)

engine_options = {"pool_pre_ping": True}
if DATABASE_URL.startswith("sqlite"):
    engine_options["connect_args"] = {"check_same_thread": False}

engine = create_engine(DATABASE_URL, **engine_options)
SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)
Base = declarative_base()

client = genai.Client(api_key=GEMINI_API_KEY) if (GEMINI_API_KEY and genai is not None) else None


# ============================================================
# MODELOS DO BANCO DE DADOS
# ============================================================

movimento_classificacao = Table(
    "movimento_classificacao",
    Base.metadata,
    Column("movimento_id", ForeignKey("movimentocontas.id"), primary_key=True),
    Column("classificacao_id", ForeignKey("classificacao.id"), primary_key=True),
)


class Pessoa(Base):
    __tablename__ = "pessoas"
    __table_args__ = (
        Index("ix_pessoas_tipo_cnpj", "tipo", "cnpj"),
        Index("ix_pessoas_tipo_cpf", "tipo", "cpf"),
        Index("ix_pessoas_tipo_razao", "tipo", "razao_social"),
    )

    id = Column(Integer, primary_key=True, index=True)
    tipo = Column(String(30), nullable=False)  # CLIENTE-FORNECEDOR ou FATURADO
    razao_social = Column(String(255), nullable=False)
    nome_fantasia = Column(String(255), nullable=True)
    cnpj = Column(String(14), nullable=True)
    cpf = Column(String(11), nullable=True)
    status = Column(String(10), nullable=False, default="ATIVO")
    criado_em = Column(DateTime, nullable=False, default=datetime.utcnow)

    movimentos_fornecedor = relationship(
        "MovimentoConta", foreign_keys="MovimentoConta.fornecedor_id", back_populates="fornecedor"
    )
    movimentos_faturado = relationship(
        "MovimentoConta", foreign_keys="MovimentoConta.faturado_id", back_populates="faturado"
    )


class Classificacao(Base):
    __tablename__ = "classificacao"
    __table_args__ = (
        UniqueConstraint("tipo", "descricao", name="uq_classificacao_tipo_descricao"),
        Index("ix_classificacoes_tipo_status", "tipo", "status"),
    )

    id = Column(Integer, primary_key=True, index=True)
    tipo = Column(String(20), nullable=False)  # DESPESA ou RECEITA
    descricao = Column(String(180), nullable=False)
    status = Column(String(10), nullable=False, default="ATIVO")
    criado_em = Column(DateTime, nullable=False, default=datetime.utcnow)

    movimentos = relationship(
        "MovimentoConta", secondary=movimento_classificacao, back_populates="classificacoes"
    )


class MovimentoConta(Base):
    __tablename__ = "movimentocontas"
    __table_args__ = (
        Index("ix_movimento_tipo_status", "tipo", "status"),
        Index("ix_movimento_numero_nota", "numero_nota"),
    )

    id = Column(Integer, primary_key=True, index=True)
    tipo = Column(String(20), nullable=False, default="APAGAR")
    fornecedor_id = Column(Integer, ForeignKey("pessoas.id"), nullable=False)
    faturado_id = Column(Integer, ForeignKey("pessoas.id"), nullable=False)
    numero_nota = Column(String(80), nullable=True)
    data_emissao = Column(Date, nullable=True)
    produtos_json = Column(Text, nullable=False, default="[]")
    valor_total = Column(Float, nullable=False, default=0)
    status = Column(String(10), nullable=False, default="ATIVO")
    criado_em = Column(DateTime, nullable=False, default=datetime.utcnow)

    fornecedor = relationship("Pessoa", foreign_keys=[fornecedor_id], back_populates="movimentos_fornecedor")
    faturado = relationship("Pessoa", foreign_keys=[faturado_id], back_populates="movimentos_faturado")
    classificacoes = relationship(
        "Classificacao", secondary=movimento_classificacao, back_populates="movimentos"
    )
    parcelas = relationship(
        "ParcelaConta", back_populates="movimento", cascade="all, delete-orphan", order_by="ParcelaConta.numero"
    )


class ParcelaConta(Base):
    __tablename__ = "parcelacontas"

    id = Column(Integer, primary_key=True, index=True)
    identificacao = Column(String(180), nullable=False, unique=True, index=True)
    movimento_id = Column(Integer, ForeignKey("movimentocontas.id"), nullable=False)
    numero = Column(Integer, nullable=False, default=1)
    data_vencimento = Column(Date, nullable=True)
    valor = Column(Float, nullable=True)
    status = Column(String(10), nullable=False, default="ATIVO")
    criado_em = Column(DateTime, nullable=False, default=datetime.utcnow)

    movimento = relationship("MovimentoConta", back_populates="parcelas")


# ============================================================
# MODELOS DE ENTRADA E SAIDA DA API
# ============================================================

class Fornecedor(BaseModel):
    razaoSocial: str = Field(description="Razao social do fornecedor")
    fantasia: str = Field(description="Nome fantasia do fornecedor")
    cnpj: str = Field(description="CNPJ do fornecedor")


class Faturado(BaseModel):
    nomeCompleto: str = Field(description="Nome completo do faturado")
    cpf: str = Field(description="CPF do faturado")


class Parcela(BaseModel):
    numero: int = Field(default=1, description="Numero sequencial da parcela")
    dataVencimento: str = Field(default="", description="Data de vencimento em YYYY-MM-DD")
    valor: Optional[float] = Field(
        default=None,
        description="Valor da parcela se estiver informado no documento; caso contrario, null",
    )


CategoriaDespesa = Literal[
    "INSUMOS AGRÍCOLAS",
    "MANUTENÇÃO E OPERAÇÃO",
    "RECURSOS HUMANOS",
    "SERVIÇOS OPERACIONAIS",
    "INFRAESTRUTURA E UTILIDADES",
    "ADMINISTRATIVAS",
    "SEGUROS E PROTEÇÃO",
    "IMPOSTOS E TAXAS",
    "INVESTIMENTOS",
]


class ClassificacaoDespesa(BaseModel):
    categoria: CategoriaDespesa


class NotaFiscalExtraida(BaseModel):
    fornecedor: Fornecedor
    faturado: Faturado
    numeroNotaFiscal: str = ""
    dataEmissao: str = ""
    produtos: List[str] = Field(default_factory=list)
    quantidadeParcelas: int = 1
    parcelas: List[Parcela] = Field(default_factory=list)
    valorTotal: float = 0
    classificacoesDespesa: List[ClassificacaoDespesa] = Field(default_factory=list)


class LoginRequest(BaseModel):
    login: str
    senha: str


class PessoaInput(BaseModel):
    tipo: Literal["CLIENTE-FORNECEDOR", "FATURADO"]
    razao_social: str = Field(min_length=1, max_length=255)
    nome_fantasia: str = ""
    cnpj: str = ""
    cpf: str = ""


class ClassificacaoInput(BaseModel):
    tipo: Literal["DESPESA", "RECEITA"]
    descricao: str = Field(min_length=1, max_length=180)


# ============================================================
# APLICACAO FASTAPI / AUTENTICACAO
# ============================================================

app = FastAPI(
    title="Projeto Administrativo-Financeiro",
    description="Extracao de notas fiscais e lancamento de contas a pagar",
    version="2.0.0",
)
app.add_middleware(
    SessionMiddleware,
    secret_key=APP_SECRET_KEY,
    session_cookie="n2_paraiba_session",
    max_age=8 * 60 * 60,
    same_site="lax",
    https_only=(ENVIRONMENT == "production"),
)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def require_authenticated(request: Request):
    if not request.session.get("usuario"):
        raise HTTPException(status_code=401, detail="Entre no sistema para continuar.")


public_router = APIRouter(prefix="/api")
protected_router = APIRouter(prefix="/api", dependencies=[Depends(require_authenticated)])


@app.on_event("startup")
def create_database_tables():
    Base.metadata.create_all(bind=engine)


@app.get("/api/health")
def health_check():
    return {"status": "ok", "aplicacao": "Projeto Administrativo-Financeiro"}


@public_router.get("/versao")
def versao():
    commit = (
        os.getenv("RENDER_GIT_COMMIT")
        or os.getenv("GIT_COMMIT_SHA")
        or os.getenv("COMMIT_SHA")
        or "NAO PUBLICADO"
    )
    return {
        "commit": commit,
        "commitCurto": commit[:7] if commit != "NAO PUBLICADO" else commit,
        "ambiente": ENVIRONMENT,
    }


@public_router.get("/auth/status")
def auth_status(request: Request):
    return {
        "autenticado": bool(request.session.get("usuario")),
        "usuario": request.session.get("usuario"),
    }


@public_router.post("/auth/login")
def login(dados: LoginRequest, request: Request):
    if not APP_LOGIN or not APP_PASSWORD:
        raise HTTPException(
            status_code=503,
            detail="Configure APP_LOGIN e APP_PASSWORD nas variaveis de ambiente.",
        )

    login_ok = secrets.compare_digest(dados.login, APP_LOGIN)
    senha_ok = secrets.compare_digest(dados.senha, APP_PASSWORD)
    if not (login_ok and senha_ok):
        raise HTTPException(status_code=401, detail="Login ou senha incorretos.")

    request.session.clear()
    request.session["usuario"] = APP_LOGIN
    return {"mensagem": "Login realizado com sucesso.", "usuario": APP_LOGIN}


@public_router.post("/auth/logout")
def logout(request: Request):
    request.session.clear()
    return {"mensagem": "Sessao encerrada."}


# ============================================================
# FUNCOES AUXILIARES
# ============================================================


def somente_digitos(valor: Optional[str]) -> str:
    return re.sub(r"\D", "", valor or "")


def texto_normalizado(valor: Optional[str]) -> str:
    return " ".join((valor or "").strip().upper().split())


def converter_data(valor: Optional[str]) -> Optional[date]:
    if not valor or not valor.strip():
        return None
    try:
        return date.fromisoformat(valor.strip()[:10])
    except (ValueError, TypeError):
        return None


def localizar_pessoa(
    db: Session,
    tipo: str,
    documento: Optional[str] = None,
    nome: Optional[str] = None,
) -> Optional[Pessoa]:
    digitos = somente_digitos(documento)
    if tipo == "CLIENTE-FORNECEDOR" and len(digitos) == 14:
        pessoa = (
            db.query(Pessoa)
            .filter(Pessoa.tipo == tipo, Pessoa.cnpj == digitos)
            .first()
        )
        if pessoa:
            return pessoa
    elif tipo == "FATURADO" and len(digitos) == 11:
        pessoa = (
            db.query(Pessoa)
            .filter(Pessoa.tipo == tipo, Pessoa.cpf == digitos)
            .first()
        )
        if pessoa:
            return pessoa

    nome_norm = texto_normalizado(nome)
    if not nome_norm:
        return None

    return (
        db.query(Pessoa)
        .filter(
            Pessoa.tipo == tipo,
            func.upper(func.trim(Pessoa.razao_social)) == nome_norm,
        )
        .first()
    )


def localizar_classificacao(db: Session, descricao: str) -> Optional[Classificacao]:
    descricao_norm = texto_normalizado(descricao)
    if not descricao_norm:
        return None
    return (
        db.query(Classificacao)
        .filter(
            Classificacao.tipo == "DESPESA",
            func.upper(func.trim(Classificacao.descricao)) == descricao_norm,
        )
        .first()
    )


def status_consulta_pessoa(pessoa: Optional[Pessoa], nome: str, documento: str):
    if pessoa is None:
        return {
            "nome": nome,
            "documento": documento,
            "existe": False,
            "id": None,
            "status": None,
            "mensagem": "NAO EXISTE — sera cadastrado no lancamento.",
        }
    if pessoa.status == "INATIVO":
        mensagem = f"INATIVO — ID: {pessoa.id} (sera reativado no lancamento)."
    else:
        mensagem = f"EXISTE — ID: {pessoa.id}"
    return {
        "nome": pessoa.razao_social,
        "documento": documento,
        "existe": True,
        "id": pessoa.id,
        "status": pessoa.status,
        "mensagem": mensagem,
    }


def analisar_no_banco(db: Session, nota: NotaFiscalExtraida) -> dict:
    fornecedor = localizar_pessoa(
        db,
        "CLIENTE-FORNECEDOR",
        nota.fornecedor.cnpj,
        nota.fornecedor.razaoSocial,
    )
    faturado = localizar_pessoa(
        db,
        "FATURADO",
        nota.faturado.cpf,
        nota.faturado.nomeCompleto,
    )

    categorias = []
    nomes_vistos = set()
    for item in nota.classificacoesDespesa:
        descricao = texto_normalizado(item.categoria)
        if not descricao or descricao in nomes_vistos:
            continue
        nomes_vistos.add(descricao)
        classificacao = localizar_classificacao(db, descricao)
        if classificacao is None:
            categorias.append({
                "descricao": descricao,
                "existe": False,
                "id": None,
                "status": None,
                "mensagem": "NAO EXISTE — sera cadastrada no lancamento.",
            })
        elif classificacao.status == "INATIVO":
            categorias.append({
                "descricao": classificacao.descricao,
                "existe": True,
                "id": classificacao.id,
                "status": classificacao.status,
                "mensagem": f"INATIVA — ID: {classificacao.id} (sera reativada no lancamento).",
            })
        else:
            categorias.append({
                "descricao": classificacao.descricao,
                "existe": True,
                "id": classificacao.id,
                "status": classificacao.status,
                "mensagem": f"EXISTE — ID: {classificacao.id}",
            })

    return {
        "fornecedor": status_consulta_pessoa(
            fornecedor, nota.fornecedor.razaoSocial, nota.fornecedor.cnpj
        ),
        "faturado": status_consulta_pessoa(
            faturado, nota.faturado.nomeCompleto, nota.faturado.cpf
        ),
        "despesas": categorias,
    }


def serializar_pessoa(pessoa: Pessoa) -> dict:
    return {
        "id": pessoa.id,
        "tipo": pessoa.tipo,
        "razao_social": pessoa.razao_social,
        "nome_fantasia": pessoa.nome_fantasia or "",
        "cnpj": pessoa.cnpj or "",
        "cpf": pessoa.cpf or "",
        "status": pessoa.status,
        "criado_em": pessoa.criado_em.isoformat() if pessoa.criado_em else None,
    }


def serializar_classificacao(classificacao: Classificacao) -> dict:
    return {
        "id": classificacao.id,
        "tipo": classificacao.tipo,
        "descricao": classificacao.descricao,
        "status": classificacao.status,
        "criado_em": classificacao.criado_em.isoformat() if classificacao.criado_em else None,
    }


def serializar_conta(movimento: MovimentoConta) -> dict:
    try:
        produtos = json.loads(movimento.produtos_json or "[]")
    except json.JSONDecodeError:
        produtos = []
    return {
        "id": movimento.id,
        "tipo": movimento.tipo,
        "numeroNotaFiscal": movimento.numero_nota or "",
        "dataEmissao": movimento.data_emissao.isoformat() if movimento.data_emissao else "",
        "fornecedor": movimento.fornecedor.razao_social if movimento.fornecedor else "",
        "fornecedorId": movimento.fornecedor_id,
        "faturado": movimento.faturado.razao_social if movimento.faturado else "",
        "faturadoId": movimento.faturado_id,
        "produtos": produtos,
        "valorTotal": movimento.valor_total,
        "classificacoes": [
            {"id": c.id, "descricao": c.descricao, "status": c.status}
            for c in movimento.classificacoes
        ],
        "parcelas": [
            {
                "id": p.id,
                "identificacao": p.identificacao,
                "numero": p.numero,
                "dataVencimento": p.data_vencimento.isoformat() if p.data_vencimento else "",
                "valor": p.valor,
                "status": p.status,
            }
            for p in movimento.parcelas
        ],
        "status": movimento.status,
    }


# ============================================================
# EXTRAIR NOTA COM GEMINI
# ============================================================

PROMPT_EXTRACAO = """
Analise a nota fiscal brasileira em PDF para um sistema administrativo-financeiro.
Extraia os campos abaixo. Nao invente dados; se um campo textual nao estiver no
PDF, retorne uma string vazia. Datas no formato YYYY-MM-DD.

Fornecedor: razao social, nome fantasia e CNPJ.
Faturado/destinatario: nome completo e CPF.
Nota: numero, data de emissao, descricoes de produtos, quantidade de parcelas,
data(s) de vencimento e valor total.
Para cada parcela, retorne numero, dataVencimento e valor se o valor individual
estiver impresso. Se o valor individual nao estiver claro, retorne valor como null.
Se houver somente uma parcela, seu valor pode ser o valor total da nota.

Classifique os produtos/servicos da nota usando SOMENTE uma destas categorias:
- INSUMOS AGRÍCOLAS: sementes, fertilizantes, defensivos agrícolas, corretivos.
- MANUTENÇÃO E OPERAÇÃO: combustíveis e lubrificantes; peças, parafusos,
  componentes mecânicos; manutenção de máquinas e equipamentos; pneus, filtros,
  correias, ferramentas e utensílios.
- RECURSOS HUMANOS: mão de obra temporária, salários e encargos.
- SERVIÇOS OPERACIONAIS: frete e transporte, colheita terceirizada, secagem,
  armazenagem, pulverização e aplicação.
- INFRAESTRUTURA E UTILIDADES: energia elétrica, arrendamento de terras,
  construções e reformas, materiais de construção.
- ADMINISTRATIVAS: honorários contábeis, advocatícios ou agronômicos,
  despesas bancárias e financeiras.
- SEGUROS E PROTEÇÃO: seguro agrícola, seguro de ativos (máquinas/veículos),
  seguro prestamista.
- IMPOSTOS E TAXAS: ITR, IPTU, IPVA, INCRA-CCIR.
- INVESTIMENTOS: aquisição de máquinas e implementos, veículos, imóveis,
  infraestrutura rural.

Exemplos definidos pelo enunciado: Óleo Diesel -> MANUTENÇÃO E OPERAÇÃO;
Material Hidráulico -> INFRAESTRUTURA E UTILIDADES.
A estrutura aceita mais de uma parcela e mais de uma classificação.
"""


def erro_temporario_gemini(erro: Exception) -> bool:
    mensagem = str(erro).lower()
    return any(
        termo in mensagem
        for termo in ["503", "service_unavailable", "service unavailable", "high demand", "temporarily unavailable"]
    )


async def executar_gemini(modelo: str, pdf_base64: str):
    if not GEMINI_API_KEY:
        raise HTTPException(
            status_code=503,
            detail="GEMINI_API_KEY nao esta configurada no ambiente do servidor.",
        )
    if genai is None:
        raise HTTPException(
            status_code=503,
            detail="A biblioteca google-genai nao esta instalada. Execute pip install -r requirements.txt.",
        )

    return await asyncio.to_thread(
        client.interactions.create,
        model=modelo,
        input=[
            {"type": "document", "data": pdf_base64, "mime_type": "application/pdf"},
            {"type": "text", "text": PROMPT_EXTRACAO},
        ],
        response_format=[
            {
                "type": "text",
                "mime_type": "application/json",
                "schema": NotaFiscalExtraida.model_json_schema(),
            }
        ],
    )


async def processar_com_gemini(pdf_base64: str):
    ultimo_erro = None
    for tentativa in range(3):
        try:
            print(f"Tentando modelo: {GEMINI_MODEL} (tentativa {tentativa + 1}/3)")
            resultado = await executar_gemini(GEMINI_MODEL, pdf_base64)
            print(f"Sucesso usando: {GEMINI_MODEL}")
            return resultado
        except HTTPException:
            raise
        except Exception as erro:
            ultimo_erro = erro
            mensagem = str(erro).lower()
            print(f"Erro em {GEMINI_MODEL}: {erro}")

            if "429" in mensagem or "rate limit" in mensagem or "too_many_requests" in mensagem:
                raise HTTPException(
                    status_code=429,
                    detail="A cota do modelo Gemini configurado foi atingida. Confira a cota ou configure outro modelo em GEMINI_MODEL.",
                )

            if "401" in mensagem or "authentication" in mensagem:
                raise HTTPException(
                    status_code=502,
                    detail="O Gemini recusou a autenticacao. Confira a GEMINI_API_KEY configurada no ambiente.",
                )

            if "403" in mensagem or "permission_denied" in mensagem:
                raise HTTPException(
                    status_code=502,
                    detail="O Gemini negou acesso ao modelo configurado. Confira modelo, projeto e permissoes da API key.",
                )

            if not erro_temporario_gemini(erro):
                raise HTTPException(
                    status_code=502,
                    detail="Ocorreu um erro ao chamar o Gemini. Confira o terminal do backend para detalhes.",
                )
            if tentativa == 2:
                break

            espera = (2 ** tentativa) + random.uniform(0, 1)
            print(f"Servico temporariamente indisponivel; nova tentativa em {espera:.1f}s")
            await asyncio.sleep(espera)

    print(f"Falha ao processar PDF: {ultimo_erro}")
    raise HTTPException(
        status_code=503,
        detail="O Gemini esta temporariamente indisponivel. Tente novamente em alguns instantes.",
    )


@protected_router.post("/extrair-nota", response_model=NotaFiscalExtraida)
async def extrair_nota(arquivo: UploadFile = File(...)):
    nome_arquivo = (arquivo.filename or "").lower()
    if arquivo.content_type != "application/pdf" and not nome_arquivo.endswith(".pdf"):
        raise HTTPException(status_code=400, detail="O arquivo enviado precisa ser um PDF.")

    conteudo_pdf = await arquivo.read()
    if not conteudo_pdf:
        raise HTTPException(status_code=400, detail="O arquivo PDF esta vazio.")
    if len(conteudo_pdf) > 20 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="O PDF deve possuir no maximo 20 MB.")
    if not conteudo_pdf.startswith(b"%PDF"):
        raise HTTPException(status_code=400, detail="O arquivo selecionado nao parece ser um PDF valido.")

    pdf_base64 = base64.b64encode(conteudo_pdf).decode("utf-8")
    try:
        interaction = await processar_com_gemini(pdf_base64)
        texto_json = interaction.output_text
        nota = NotaFiscalExtraida.model_validate_json(texto_json)
        print(f"Nota extraida: {arquivo.filename}")
        return nota
    except HTTPException:
        raise
    except Exception as erro:
        print(f"Erro ao interpretar resposta do Gemini: {erro}")
        raise HTTPException(
            status_code=502,
            detail="O Gemini nao retornou dados em formato valido. Tente novamente com o PDF mais legivel.",
        )


# ============================================================
# CONSULTAR A NOTA EXTRAIDA NO BANCO
# ============================================================

@protected_router.post("/analisar-nota")
def analisar_nota(nota: NotaFiscalExtraida, db: Session = Depends(get_db)):
    return analisar_no_banco(db, nota)


# ============================================================
# CRIAR PESSOAS / CLASSIFICACOES E LANCAR MOVIMENTO + PARCELAS
# ============================================================

@protected_router.post("/registrar-conta")
def registrar_conta(nota: NotaFiscalExtraida, db: Session = Depends(get_db)):
    fornecedor = None
    faturado = None
    try:
        fornecedor = localizar_pessoa(
            db,
            "CLIENTE-FORNECEDOR",
            nota.fornecedor.cnpj,
            nota.fornecedor.razaoSocial,
        )
        if fornecedor and fornecedor.status == "INATIVO":
            fornecedor.status = "ATIVO"
        if fornecedor is None:
            nome_fornecedor = texto_normalizado(nota.fornecedor.razaoSocial)
            if not nome_fornecedor:
                raise HTTPException(
                    status_code=422,
                    detail="O fornecedor nao foi identificado; confira a nota antes de lancar.",
                )
            fornecedor = Pessoa(
                tipo="CLIENTE-FORNECEDOR",
                razao_social=nome_fornecedor,
                nome_fantasia=(nota.fornecedor.fantasia or "").strip() or None,
                cnpj=somente_digitos(nota.fornecedor.cnpj) or None,
                status="ATIVO",
            )
            db.add(fornecedor)
            db.flush()

        faturado = localizar_pessoa(
            db,
            "FATURADO",
            nota.faturado.cpf,
            nota.faturado.nomeCompleto,
        )
        if faturado and faturado.status == "INATIVO":
            faturado.status = "ATIVO"
        if faturado is None:
            nome_faturado = texto_normalizado(nota.faturado.nomeCompleto)
            if not nome_faturado:
                raise HTTPException(
                    status_code=422,
                    detail="O faturado nao foi identificado; confira a nota antes de lancar.",
                )
            faturado = Pessoa(
                tipo="FATURADO",
                razao_social=nome_faturado,
                cpf=somente_digitos(nota.faturado.cpf) or None,
                status="ATIVO",
            )
            db.add(faturado)
            db.flush()

        numero_nota = (nota.numeroNotaFiscal or "").strip() or None
        if numero_nota:
            existente = (
                db.query(MovimentoConta)
                .filter(
                    MovimentoConta.tipo == "APAGAR",
                    MovimentoConta.fornecedor_id == fornecedor.id,
                    MovimentoConta.numero_nota == numero_nota,
                )
                .first()
            )
            if existente:
                raise HTTPException(
                    status_code=409,
                    detail=f"A nota {numero_nota} desse fornecedor ja foi lancada (movimento ID: {existente.id}).",
                )

        categorias_lancamento = []
        nomes_vistos = set()
        for item in nota.classificacoesDespesa:
            descricao = texto_normalizado(item.categoria)
            if not descricao or descricao in nomes_vistos:
                continue
            nomes_vistos.add(descricao)
            classificacao = localizar_classificacao(db, descricao)
            if classificacao is None:
                classificacao = Classificacao(
                    tipo="DESPESA", descricao=descricao, status="ATIVO"
                )
                db.add(classificacao)
                db.flush()
            elif classificacao.status == "INATIVO":
                classificacao.status = "ATIVO"
            if classificacao not in categorias_lancamento:
                categorias_lancamento.append(classificacao)

        if not categorias_lancamento:
            raise HTTPException(
                status_code=422,
                detail="A nota nao possui classificacao de despesa. Confira o JSON antes de lancar.",
            )

        movimento = MovimentoConta(
            tipo="APAGAR",
            fornecedor_id=fornecedor.id,
            faturado_id=faturado.id,
            numero_nota=numero_nota,
            data_emissao=converter_data(nota.dataEmissao),
            produtos_json=json.dumps(nota.produtos, ensure_ascii=False),
            valor_total=float(nota.valorTotal or 0),
            status="ATIVO",
        )
        movimento.classificacoes = categorias_lancamento
        db.add(movimento)
        db.flush()

        parcelas_entrada = list(nota.parcelas or [])
        quantidade_esperada = max(1, int(nota.quantidadeParcelas or 1))
        if not parcelas_entrada:
            parcelas_entrada = [Parcela(numero=1, dataVencimento="", valor=nota.valorTotal)]
        while len(parcelas_entrada) < quantidade_esperada:
            proximo_numero = len(parcelas_entrada) + 1
            parcelas_entrada.append(
                Parcela(numero=proximo_numero, dataVencimento="", valor=None)
            )

        identificador_nota = numero_nota or f"SEMNUMERO-{uuid.uuid4().hex[:10]}"
        for indice, item_parcela in enumerate(parcelas_entrada, start=1):
            numero_parcela = item_parcela.numero or indice
            valor_parcela = item_parcela.valor
            if valor_parcela is None and len(parcelas_entrada) == 1:
                valor_parcela = float(nota.valorTotal or 0)
            identificacao = (
                f"NF-{fornecedor.id}-{identificador_nota}-P{numero_parcela}"
            )
            db.add(
                ParcelaConta(
                    identificacao=identificacao,
                    movimento_id=movimento.id,
                    numero=numero_parcela,
                    data_vencimento=converter_data(item_parcela.dataVencimento),
                    valor=valor_parcela,
                    status="ATIVO",
                )
            )

        db.commit()
        db.refresh(movimento)

        return {
            "sucesso": True,
            "mensagem": "Conta a pagar lancada com sucesso.",
            "movimentoId": movimento.id,
            "tipoMovimento": movimento.tipo,
            "fornecedor": {"id": fornecedor.id, "nome": fornecedor.razao_social},
            "faturado": {"id": faturado.id, "nome": faturado.razao_social},
            "classificacoes": [
                {"id": c.id, "descricao": c.descricao} for c in movimento.classificacoes
            ],
            "parcelas": [
                {
                    "id": p.id,
                    "identificacao": p.identificacao,
                    "numero": p.numero,
                    "dataVencimento": p.data_vencimento.isoformat() if p.data_vencimento else "",
                    "valor": p.valor,
                }
                for p in movimento.parcelas
            ],
        }
    except HTTPException:
        db.rollback()
        raise
    except IntegrityError as erro:
        db.rollback()
        print(f"Erro de integridade ao registrar conta: {erro}")
        raise HTTPException(
            status_code=409,
            detail="Nao foi possivel registrar a conta porque ja existe um registro conflitante. Confira se a nota ja foi lancada.",
        )
    except Exception as erro:
        db.rollback()
        print(f"Erro ao registrar conta: {erro}")
        raise HTTPException(status_code=500, detail="Erro interno ao registrar a conta a pagar.")


# ============================================================
# CADASTRO / CONSULTA DE PESSOAS
# ============================================================

@protected_router.get("/pessoas")
def listar_pessoas(
    busca: str = Query(default=""),
    tipo: str = Query(default=""),
    todos: bool = False,
    inativos: bool = False,
    db: Session = Depends(get_db),
):
    if not todos and not inativos and not busca.strip():
        return []

    consulta = db.query(Pessoa)
    consulta = consulta.filter(Pessoa.status == ("INATIVO" if inativos else "ATIVO"))
    if tipo.strip():
        consulta = consulta.filter(Pessoa.tipo == tipo.strip().upper())
    if busca.strip():
        termo = f"%{busca.strip()}%"
        digitos = somente_digitos(busca)
        filtros = [
            Pessoa.razao_social.ilike(termo),
            Pessoa.nome_fantasia.ilike(termo),
            Pessoa.tipo.ilike(termo),
        ]
        if digitos:
            filtros.extend([Pessoa.cnpj.ilike(f"%{digitos}%"), Pessoa.cpf.ilike(f"%{digitos}%")])
        consulta = consulta.filter(or_(*filtros))
    return [serializar_pessoa(p) for p in consulta.order_by(Pessoa.id.desc()).limit(500).all()]


@protected_router.post("/pessoas")
def criar_pessoa(dados: PessoaInput, db: Session = Depends(get_db)):
    nome = texto_normalizado(dados.razao_social)
    if not nome:
        raise HTTPException(status_code=422, detail="Informe o nome/razao social.")
    documento = somente_digitos(dados.cnpj if dados.tipo == "CLIENTE-FORNECEDOR" else dados.cpf)
    if dados.tipo == "CLIENTE-FORNECEDOR" and len(documento) == 14:
        repetido = db.query(Pessoa).filter(Pessoa.tipo == dados.tipo, Pessoa.cnpj == documento).first()
        if repetido:
            raise HTTPException(status_code=409, detail=f"Esse CNPJ ja esta cadastrado (ID: {repetido.id}).")
    if dados.tipo == "FATURADO" and len(documento) == 11:
        repetido = db.query(Pessoa).filter(Pessoa.tipo == dados.tipo, Pessoa.cpf == documento).first()
        if repetido:
            raise HTTPException(status_code=409, detail=f"Esse CPF ja esta cadastrado (ID: {repetido.id}).")
    pessoa = Pessoa(
        tipo=dados.tipo,
        razao_social=nome,
        nome_fantasia=texto_normalizado(dados.nome_fantasia) or None,
        cnpj=somente_digitos(dados.cnpj) or None,
        cpf=somente_digitos(dados.cpf) or None,
        status="ATIVO",
    )
    db.add(pessoa)
    db.commit()
    db.refresh(pessoa)
    return serializar_pessoa(pessoa)


@protected_router.put("/pessoas/{pessoa_id}")
def atualizar_pessoa(pessoa_id: int, dados: PessoaInput, db: Session = Depends(get_db)):
    pessoa = db.query(Pessoa).filter(Pessoa.id == pessoa_id).first()
    if not pessoa:
        raise HTTPException(status_code=404, detail="Pessoa nao encontrada.")
    pessoa.tipo = dados.tipo
    pessoa.razao_social = texto_normalizado(dados.razao_social)
    pessoa.nome_fantasia = texto_normalizado(dados.nome_fantasia) or None
    pessoa.cnpj = somente_digitos(dados.cnpj) or None
    pessoa.cpf = somente_digitos(dados.cpf) or None
    db.commit()
    db.refresh(pessoa)
    return serializar_pessoa(pessoa)


@protected_router.delete("/pessoas/{pessoa_id}")
def inativar_pessoa(pessoa_id: int, db: Session = Depends(get_db)):
    pessoa = db.query(Pessoa).filter(Pessoa.id == pessoa_id).first()
    if not pessoa:
        raise HTTPException(status_code=404, detail="Pessoa nao encontrada.")
    pessoa.status = "INATIVO"
    db.commit()
    return {"mensagem": f"Pessoa ID {pessoa.id} inativada.", "id": pessoa.id, "status": pessoa.status}


@protected_router.post("/pessoas/{pessoa_id}/reativar")
def reativar_pessoa(pessoa_id: int, db: Session = Depends(get_db)):
    pessoa = db.query(Pessoa).filter(Pessoa.id == pessoa_id).first()
    if not pessoa:
        raise HTTPException(status_code=404, detail="Pessoa nao encontrada.")
    pessoa.status = "ATIVO"
    db.commit()
    return {"mensagem": f"Pessoa ID {pessoa.id} reativada.", "id": pessoa.id, "status": pessoa.status}


# ============================================================
# CADASTRO / CONSULTA DE CLASSIFICACOES
# ============================================================

@protected_router.get("/classificacoes")
def listar_classificacoes(
    busca: str = Query(default=""),
    tipo: str = Query(default=""),
    todos: bool = False,
    inativos: bool = False,
    db: Session = Depends(get_db),
):
    if not todos and not inativos and not busca.strip():
        return []

    consulta = db.query(Classificacao)
    consulta = consulta.filter(Classificacao.status == ("INATIVO" if inativos else "ATIVO"))
    if tipo.strip():
        consulta = consulta.filter(Classificacao.tipo == tipo.strip().upper())
    if busca.strip():
        termo = f"%{busca.strip()}%"
        consulta = consulta.filter(Classificacao.descricao.ilike(termo))
    return [serializar_classificacao(c) for c in consulta.order_by(Classificacao.id.desc()).limit(500).all()]


@protected_router.post("/classificacoes")
def criar_classificacao(dados: ClassificacaoInput, db: Session = Depends(get_db)):
    descricao = texto_normalizado(dados.descricao)
    existente = (
        db.query(Classificacao)
        .filter(
            Classificacao.tipo == dados.tipo,
            func.upper(func.trim(Classificacao.descricao)) == descricao,
        )
        .first()
    )
    if existente:
        if existente.status == "INATIVO":
            existente.status = "ATIVO"
            db.commit()
            db.refresh(existente)
            return serializar_classificacao(existente)
        raise HTTPException(status_code=409, detail=f"Classificacao ja cadastrada (ID: {existente.id}).")
    classificacao = Classificacao(tipo=dados.tipo, descricao=descricao, status="ATIVO")
    db.add(classificacao)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="Classificacao duplicada.")
    db.refresh(classificacao)
    return serializar_classificacao(classificacao)


@protected_router.put("/classificacoes/{classificacao_id}")
def atualizar_classificacao(classificacao_id: int, dados: ClassificacaoInput, db: Session = Depends(get_db)):
    classificacao = db.query(Classificacao).filter(Classificacao.id == classificacao_id).first()
    if not classificacao:
        raise HTTPException(status_code=404, detail="Classificacao nao encontrada.")
    descricao = texto_normalizado(dados.descricao)
    repetida = (
        db.query(Classificacao)
        .filter(
            Classificacao.tipo == dados.tipo,
            func.upper(func.trim(Classificacao.descricao)) == descricao,
            Classificacao.id != classificacao_id,
        )
        .first()
    )
    if repetida:
        raise HTTPException(status_code=409, detail=f"Ja existe classificacao semelhante (ID: {repetida.id}).")
    classificacao.tipo = dados.tipo
    classificacao.descricao = descricao
    db.commit()
    db.refresh(classificacao)
    return serializar_classificacao(classificacao)


@protected_router.delete("/classificacoes/{classificacao_id}")
def inativar_classificacao(classificacao_id: int, db: Session = Depends(get_db)):
    classificacao = db.query(Classificacao).filter(Classificacao.id == classificacao_id).first()
    if not classificacao:
        raise HTTPException(status_code=404, detail="Classificacao nao encontrada.")
    classificacao.status = "INATIVO"
    db.commit()
    return {"mensagem": f"Classificacao ID {classificacao.id} inativada.", "id": classificacao.id, "status": classificacao.status}


@protected_router.post("/classificacoes/{classificacao_id}/reativar")
def reativar_classificacao(classificacao_id: int, db: Session = Depends(get_db)):
    classificacao = db.query(Classificacao).filter(Classificacao.id == classificacao_id).first()
    if not classificacao:
        raise HTTPException(status_code=404, detail="Classificacao nao encontrada.")
    classificacao.status = "ATIVO"
    db.commit()
    return {"mensagem": f"Classificacao ID {classificacao.id} reativada.", "id": classificacao.id, "status": classificacao.status}


# ============================================================
# CONSULTA DE CONTAS A PAGAR
# ============================================================

@protected_router.get("/contas")
def listar_contas(
    busca: str = Query(default=""),
    todos: bool = False,
    db: Session = Depends(get_db),
):
    if not todos and not busca.strip():
        return []

    movimentos = (
        db.query(MovimentoConta)
        .filter(MovimentoConta.tipo == "APAGAR", MovimentoConta.status == "ATIVO")
        .order_by(MovimentoConta.id.desc())
        .limit(1000)
        .all()
    )
    if busca.strip():
        termo = texto_normalizado(busca)
        digitos = somente_digitos(busca)
        encontrados = []
        for movimento in movimentos:
            dados = serializar_conta(movimento)
            texto = " ".join([
                str(dados["id"]),
                dados["numeroNotaFiscal"],
                dados["fornecedor"],
                dados["faturado"],
                " ".join(dados["produtos"]),
                " ".join(item["descricao"] for item in dados["classificacoes"]),
            ])
            if termo in texto_normalizado(texto) or (digitos and digitos in somente_digitos(texto)):
                encontrados.append(dados)
        return encontrados
    return [serializar_conta(m) for m in movimentos]


# Registrar rotas antes da montagem dos arquivos estaticos.
app.include_router(public_router)
app.include_router(protected_router)

# Servir o frontend pela propria API permite hospedar tudo como um unico servico.
# O diretorio de arquivos estaticos e calculado a partir da localizacao deste arquivo.
app.mount("/", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="frontend")
