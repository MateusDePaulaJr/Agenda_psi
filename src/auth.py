import hashlib
import os

# OBS: Simples para didática. Em produção, use bibliotecas consagradas (bcrypt, passlib etc.).

def gerar_salt(tamanho: int = 16) -> str:
    return os.urandom(tamanho).hex()

def hash_senha(senha: str, salt: str) -> str:
    # Gera um hash SHA-256 a partir de senha+salt
    texto = (senha + salt).encode('utf-8')
    return hashlib.sha256(texto).hexdigest()

def verificar_senha(senha_digitada: str, salt: str, hash_armazenado: str) -> bool:
    return hash_senha(senha_digitada, salt) == hash_armazenado
