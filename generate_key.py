import secrets

def generate_secret_key():
    """Gera uma chave secreta segura para o Flask."""
    return secrets.token_hex(32)

if __name__ == "__main__":
    print(f"\nNova SECRET_KEY gerada:\n{generate_secret_key()}\n")
    print("Copie e cole este valor no seu arquivo .env")
