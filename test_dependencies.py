#!/usr/bin/env python3
"""
Test d'installation des dépendances Python pour KiVendTout
Usage: python3 test_dependencies.py
"""

import sys

def test_import(module_name, package_name=None):
    """Test l'import d'un module"""
    try:
        __import__(module_name)
        print(f"✅ {package_name or module_name}")
        return True
    except ImportError as e:
        print(f"❌ {package_name or module_name} - {e}")
        return False

def main():
    print("=" * 60)
    print("🧪 TEST DES DÉPENDANCES PYTHON - KiVendTout")
    print("=" * 60)
    print()
    
    dependencies = [
        ("psycopg2", "psycopg2-binary (PostgreSQL)"),
        ("pymongo", "pymongo (MongoDB)"),
        ("kafka", "kafka-python (Apache Kafka)"),
        ("lz4", "lz4 (Kafka Compression)"),
        ("snappy", "python-snappy (Kafka Compression)"),
        ("fastapi", "fastapi (API Framework)"),
        ("uvicorn", "uvicorn (ASGI Server)"),
        ("pydantic", "pydantic (Data Validation)"),
        ("pandas", "pandas (Data Processing)"),
        ("numpy", "numpy (Numerical Computing)"),
        ("dotenv", "python-dotenv (Environment Variables)"),
        ("requests", "requests (HTTP Client)"),
    ]
    
    results = []
    for module, name in dependencies:
        results.append(test_import(module, name))
    
    print()
    print("=" * 60)
    
    total = len(results)
    success = sum(results)
    failed = total - success
    
    print(f"📊 RÉSULTAT: {success}/{total} dépendances installées")
    
    if failed == 0:
        print("🎉 Toutes les dépendances sont installées !")
        print()
        print("Vous pouvez maintenant lancer:")
        print("  ./run.sh")
        return 0
    else:
        print(f"⚠️  {failed} dépendance(s) manquante(s)")
        print()
        print("Pour installer les dépendances manquantes:")
        print("  pip install -r requirements.txt")
        print()
        print("Note: Si vous êtes dans un venv, utilisez 'pip' au lieu de 'pip3'")
        return 1

if __name__ == "__main__":
    sys.exit(main())
